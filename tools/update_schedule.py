import json,re,sys,time
from datetime import date,timedelta
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from html import unescape
from pathlib import Path

COURSES=r"札幌|函館|福島|新潟|東京|中山|中京|京都|阪神|小倉"
HEADING=re.compile(rf"^#+\s*(\d+)回\s*({COURSES})\s*(\d+)日\s*$")
RACE_MARK=re.compile(r"^\s*(?:\|\s*)?(\d{1,2})\s*レース\b")
TIME_RE=re.compile(r"(\d{1,2})\s*時\s*(\d{1,2})\s*分")
DIST_RE=re.compile(r"([0-9,]+)\s*[（(]\s*(芝(?:・外)?|ダ|芝→ダート|ダート)\s*[）)]")

def fetch(url, timeout=30, jina=False):
    headers={
        "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/153 Safari/537.36 (KEIBA-NOTE/5.4.7)",
        "Accept":"text/plain,text/markdown,text/html;q=0.9,*/*;q=0.8",
        "Accept-Language":"ja,en-US;q=0.8,en;q=0.6",
        "Cache-Control":"no-cache",
    }
    if jina:
        headers.update({"x-no-cache":"true","x-engine":"browser"})
    req=Request(url,headers=headers)
    with urlopen(req,timeout=timeout) as r:
        return r.read().decode("utf-8","replace")

def norm(s):
    s=unescape(str(s)).replace("\xa0"," ").replace("\u3000"," ")
    s=re.sub(r"\*\*(.*?)\*\*",r"\1",s)
    s=re.sub(r"`","",s)
    s=re.sub(r"\[(.*?)\]\([^)]*\)",r"\1",s)
    s=re.sub(r"\s+"," ",s).strip()
    return s

def clean_line(line):
    line=norm(line).strip()
    line=re.sub(r"^\s*[-*]\s*","",line)
    return line.strip()

def parse_text(text, ds):
    # Jina Reader can represent a table as:
    #   1レース
    #   レース名・条件
    #   10時00分
    # instead of a single Markdown table row.
    # Therefore parse by race markers + nearby time rather than one exact row regex.
    lines=[clean_line(x) for x in str(text).splitlines() if clean_line(x)]
    out=[]
    course=""
    meeting=""

    i=0
    while i < len(lines):
        line=lines[i]
        h=HEADING.match(line)
        if h:
            course=h.group(2)
            meeting=f"{h.group(1)}回{h.group(3)}日"
            i += 1
            continue

        rm=RACE_MARK.match(line)
        if not rm or not course:
            i += 1
            continue

        race=int(rm.group(1))
        if not 1 <= race <= 12:
            i += 1
            continue

        # Collect a small window after the race marker. This handles both
        # one-line Markdown rows and multi-line Jina table extraction.
        window=[]
        j=i
        for _ in range(12):
            if j >= len(lines):
                break
            x=lines[j]
            if j != i and HEADING.match(x):
                break
            if j != i and RACE_MARK.match(x):
                break
            window.append(x)
            if TIME_RE.search(x):
                break
            j += 1

        joined=" ".join(window)
        tm=TIME_RE.search(joined)
        if not tm:
            i += 1
            continue

        # Remove race number and time from the condition/name text.
        cond=joined
        cond=re.sub(r"^\s*\|?\s*\d{1,2}\s*レース\s*\|?\s*","",cond)
        cond=re.sub(r"\|"," ",cond)
        cond=re.sub(r"\s*"+re.escape(tm.group(0))+r".*$","",cond)
        cond=re.sub(r"\s+"," ",cond).strip(" -|")

        # Skip table headers accidentally matching around a race marker.
        if not cond:
            i=j+1
            continue

        dm=DIST_RE.search(cond)
        distance=(dm.group(1).replace(",","")+"m") if dm else ""
        surface=dm.group(2) if dm else ""
        if surface=="ダート":
            surface="ダ"

        name=re.sub(r"\s*[0-9,]+\s*[（(].*$","",cond).strip()
        if not name:
            name=cond

        out.append({
            "date":ds,
            "course":course,
            "race":race,
            "raceName":name,
            "raceCondition":cond,
            "distance":distance,
            "surface":surface,
            "startTime":f"{int(tm.group(1)):02d}:{int(tm.group(2)):02d}",
            "raceKey":f"{ds}-{course}-{race}",
            "meeting":meeting,
        })
        i=max(i+1,j+1)

    seen=set()
    result=[]
    for r in out:
        key=(r["date"],r["course"],r["race"])
        if key not in seen:
            seen.add(key)
            result.append(r)
    return result

def strip_html(html):
    html=re.sub(r'<script[\s\S]*?</script>',' ',html,flags=re.I)
    html=re.sub(r'<style[\s\S]*?</style>',' ',html,flags=re.I)
    html=re.sub(r'<br\s*/?>','\n',html,flags=re.I)
    html=re.sub(r'</(?:p|div|tr|li|h[1-6]|table)>','\n',html,flags=re.I)
    html=re.sub(r'<(?:td|th)\b[^>]*>',' | ',html,flags=re.I)
    text=re.sub(r'<[^>]+>',' ',html)
    return '\n'.join(norm(x) for x in text.splitlines() if norm(x))

def diagnose_jina_response(ds, raw, limit=8000):
    """Print a bounded Jina response excerpt for parser debugging."""
    print(f"===== JINA RESPONSE START {ds} =====")
    sample = str(raw)[:limit]
    print(sample)
    if len(str(raw)) > limit:
        print(f"... [truncated; total chars={len(str(raw))}]")
    print(f"===== JINA RESPONSE END {ds} =====")

def fetch_date(ds):
    d=date.fromisoformat(ds)
    target=f"https://www.jra.go.jp/keiba/calendar{d.year}/{d.year}/{d.month}/{d.month:02d}{d.day:02d}.html"
    jina_url=f"https://r.jina.ai/{target}"
    # Diagnostic build: inspect the first Jina response that returns HTTP content
    # but produces zero parsed races. Do not spam logs for every date.
    diagnostic_shown=False
    for url,jina in [(jina_url,True),(target,False)]:
        try:
            raw=fetch(url)
            if jina:
                r=parse_text(raw,ds)
                if r:
                    return r
                print(f"WARN {ds}: Jina returned content but parser found 0 races")
                if not diagnostic_shown:
                    diagnose_jina_response(ds, raw)
                    diagnostic_shown=True
            else:
                r=parse_text(strip_html(raw),ds)
                if r:
                    return r
                print(f"WARN {ds}: JRA returned content but parser found 0 races")
        except Exception as e:
            source="Jina" if jina else "JRA"
            print(f"WARN {ds}: {source} {e}",file=sys.stderr)
    return []


def main():
    today=date.today()
    path=Path("data/jra-schedule.json")
    try:
        old=json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        old={"races":[]}

    existing={}
    for r in old.get("races",[]):
        if isinstance(r,dict):
            try:
                key=(r.get("date"),r.get("course"),int(r.get("race",0)))
            except Exception:
                continue
            if key[0] and key[1] and key[2]:
                existing[key]=r

    fetched=0
    successful_dates=[]
    for i in range(-3,15):
        ds=(today+timedelta(days=i)).isoformat()
        races=fetch_date(ds)
        if races:
            fetched += len(races)
            successful_dates.append(ds)
            for r in races:
                existing[(r["date"],r["course"],r["race"])]=r

    if not fetched:
        raise SystemExit("ERROR: 0 JRA races fetched; existing JSON was not overwritten.")

    races=sorted(existing.values(),key=lambda r:(r.get("date",""),r.get("course",""),int(r.get("race",0))))
    payload={
        "updatedAt":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),
        "source":"JRA official daily program via Jina Reader/GitHub Actions",
        "dates":sorted({r["date"] for r in races}),
        "races":races,
    }
    path.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"OK: fetched {fetched} races on {len(successful_dates)} date(s); stored {len(races)} races")

if __name__=="__main__":
    main()
