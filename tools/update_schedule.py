import json, re, sys, time
from datetime import date, timedelta
from urllib.request import Request, urlopen
from html import unescape

COURSES = r"札幌|函館|福島|新潟|東京|中山|中京|京都|阪神|小倉"

def fetch(url):
    req=Request(url, headers={"User-Agent":"Mozilla/5.0 KEIBA-NOTE schedule updater"})
    with urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", errors="replace")

def strip_html(html):
    # Good enough for JRA's table text and avoids external dependencies.
    html=re.sub(r'<script[\s\S]*?</script>', ' ', html, flags=re.I)
    html=re.sub(r'<style[\s\S]*?</style>', ' ', html, flags=re.I)
    html=re.sub(r'<br\s*/?>', '\n', html, flags=re.I)
    html=re.sub(r'</(?:p|div|tr|li|h[1-6]|table)>', '\n', html, flags=re.I)
    html=re.sub(r'<(?:td|th)\b[^>]*>', '\n', html, flags=re.I)
    text=re.sub(r'<[^>]+>', ' ', html)
    text=unescape(text).replace('\xa0',' ')
    return [re.sub(r'\s+',' ',x).strip() for x in text.splitlines() if re.sub(r'\s+',' ',x).strip()]

def parse(html, ds):
    lines=strip_html(html)
    out=[]
    heading=re.compile(rf'^(\d+)回\s*({COURSES})\s*(\d+)日$')
    race=re.compile(r'^(\d+)レース$')
    current=None
    for i,line in enumerate(lines):
        m=heading.match(line)
        if m:
            current=(m.group(2), f"{m.group(1)}回{m.group(3)}日")
            continue
        if not current:
            continue
        rm=race.match(line)
        if not rm or i+2>=len(lines):
            continue
        try:rno=int(rm.group(1))
        except:continue
        if not 1<=rno<=12:continue
        name=lines[i+1]
        tm=lines[i+2]
        if not re.match(r'^\d+時\d+分$',tm):
            # Search a few cells ahead in case the parser inserted an extra note.
            for j in range(i+2,min(i+6,len(lines))):
                if re.match(r'^\d+時\d+分$',lines[j]):
                    tm=lines[j];break
            else:continue
        dm=re.search(r'([0-9,]+)\s*（?(芝(?:・外)?|ダ|芝→ダート|ダート)）?',name)
        distance=(dm.group(1).replace(',','')+'m') if dm else ''
        surface=dm.group(2) if dm else ''
        if surface=='ダート':surface='ダ'
        out.append({
            'date':ds,'course':current[0],'race':rno,'raceName':name,
            'raceCondition':name,'distance':distance,'surface':surface,
            'startTime':tm.replace('時',':').replace('分',''),
            'raceKey':f'{ds}-{current[0]}-{rno}','meeting':current[1]
        })
    # de-duplicate while preserving order
    seen=set(); clean=[]
    for r in out:
        k=(r['date'],r['course'],r['race'])
        if k not in seen:seen.add(k);clean.append(r)
    return clean

def main():
    today=date.today()
    # Keep a rolling window. Future program pages are already published by JRA,
    # while recent days remain useful for analysis.
    dates=[today+timedelta(days=i) for i in range(-7,31)]
    allr=[]; ok=[]
    for d in dates:
        ds=d.isoformat(); url=f'https://www.jra.go.jp/keiba/calendar{d.year}/{d.year}/{d.month}/{d.month:02d}{d.day:02d}.html'
        try:
            races=parse(fetch(url),ds)
            if races:
                allr.extend(races);ok.append(ds)
        except Exception as e:
            print(f'WARN {ds}: {e}',file=sys.stderr)
    path='data/jra-schedule.json'
    payload={'updatedAt':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'source':'JRA official daily program via GitHub Actions','dates':ok,'races':allr}
    with open(path,'w',encoding='utf-8') as f:json.dump(payload,f,ensure_ascii=False,indent=2)
    print(f'updated {len(allr)} races for {len(ok)} dates')

if __name__=='__main__':main()
