import json,re,sys,time
from datetime import date,timedelta
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from html import unescape
from pathlib import Path

COURSES=r"札幌|函館|福島|新潟|東京|中山|中京|京都|阪神|小倉"
HEADING=re.compile(rf"^#+\s*(\d+)回\s*({COURSES})\s*(\d+)日\s*$")
RACE_LINE=re.compile(r"^\s*\|?\s*(\d{1,2})\s*レース\s*\|\s*(.*?)\s*\|\s*(\d{1,2})時\s*(\d{1,2})分\s*\|?\s*$")
RACE_LINE_ALT=re.compile(r"^\s*(\d{1,2})\s*レース\s*[|｜]\s*(.*?)\s*[|｜]\s*(\d{1,2})時\s*(\d{1,2})分\s*$")


def fetch(url, timeout=30, jina=False):
    headers={
        "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/153 Safari/537.36 (KEIBA-NOTE/5.4.5)",
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
    s=re.sub(r"\*\*(.*?)\*\*",r"\1",s).replace("`","")
    s=re.sub(r"\s+"," ",s).strip()
    return s


def clean_line(line):
    line=norm(line).strip()
    line=re.sub(r"^\s*[-*]\s*", "", line)
    line=line.strip("|").strip()
    return line


def parse_text(text, ds):
    lines=[norm(x) for x in str(text).splitlines() if norm(x)]
    out=[]; course=""; meeting=""
    for raw in lines:
        line=clean_line(raw)
        # Jina Reader commonly returns markdown headings such as "### 4回中山4日".
        h=HEADING.match(line)
        if h:
            course=h.group(2)
            meeting=f"{h.group(1)}回{h.group(3)}日"
            continue

        # Ignore markdown table separator rows and unrelated text.
        if re.fullmatch(r"[:\-\s|]+", line):
            continue

        m=RACE_LINE.match(line) or RACE_LINE_ALT.match(line)
        if not m or not course:
            continue

        race=int(m.group(1))
        if not 1<=race<=12:
            continue

        cond=re.sub(r"\s+"," ",m.group(2)).strip()
        dm=re.search(r"([0-9,]+)\s*（\s*(芝(?:・外)?|ダ|芝→ダート|ダート)\s*）",cond)
        if not dm:
            # Be tolerant of normal parentheses or slightly different spacing.
            dm=re.search(r"([0-9,]+)\s*[（(]\s*(芝(?:・外)?|ダ|芝→ダート|ダート)\s*[）)]",cond)
        distance=(dm.group(1).replace(",","")+"m") if dm else ""
        surface=dm.group(2) if dm else ""
        surface="ダ" if surface=="ダート" else surface
        name=re.sub(r"\s+[0-9,]+\s*[（(].*", "", cond).strip() or cond
        out.append({
            "date":ds,
            "course":course,
            "race":race,
            "raceName":name,
            "raceCondition":cond,
            "distance":distance,
            "surface":surface,
            "startTime":f"{int(m.group(3)):02d}:{int(m.group(4)):02d}",
            "raceKey":f"{ds}-{course}-{race}",
            "meeting":meeting,
        })

    seen=set(); result=[]
    for r in out:
        key=(r["date"],r["course"],r["race"])
        if key not in seen:
            seen.add(key); result.append(r)
    return result


def strip_html(html):
    html=re.sub(r'<script[\s\S]*?</script>',' ',html,flags=re.I)
    html=re.sub(r'<style[\s\S]*?</style>',' ',html,flags=re.I)
    html=re.sub(r'<br\s*/?>','\n',html,flags=re.I)
    html=re.sub(r'</(?:p|div|tr|li|h[1-6]|table)>','\n',html,flags=re.I)
    html=re.sub(r'<(?:td|th)\b[^>]*>',' | ',html,flags=re.I)
    text=re.sub(r'<[^>]+>',' ',html)
    return '\n'.join(norm(x) for x in text.splitlines() if norm(x))


def fetch_date(ds):
    d=date.fromisoformat(ds)
    target=f"https://www.jra.go.jp/keiba/calendar{d.year}/{d.year}/{d.month}/{d.month:02d}{d.day:02d}.html"

    # Primary: Jina Reader. The V5.4.5 parser missed markdown headings,
    # so V5.4.5 explicitly supports Jina's normal markdown output.
    jina_url=f"https://r.jina.ai/{target}"
    try:
        raw=fetch(jina_url,jina=True)
        races=parse_text(raw,ds)
        if races:
            return races
        print(f"WARN {ds}: Jina returned content but parser found 0 races",file=sys.stderr)
    except Exception as e:
        print(f"WARN {ds}: Jina fetch failed: {e}",file=sys.stderr)

    # Secondary: direct JRA access. A 403 here is expected on some GitHub-hosted
    # runner requests; it is logged and does not erase existing JSON.
    try:
        raw=fetch(target)
        races=parse_text(strip_html(raw),ds)
        if races:
            return races
        print(f"WARN {ds}: JRA returned content but parser found 0 races",file=sys.stderr)
    except HTTPError as e:
        print(f"WARN {ds}: JRA HTTP {e.code} {e.reason}",file=sys.stderr)
    except Exception as e:
        print(f"WARN {ds}: JRA fetch failed: {e}",file=sys.stderr)
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
            try:key=(r.get("date"),r.get("course"),int(r.get("race",0)))
            except Exception:continue
            if key[0] and key[1] and key[2]: existing[key]=r

    fetched=0; successful_dates=[]
    for i in range(-3,15):
        ds=(today+timedelta(days=i)).isoformat()
        races=fetch_date(ds)
        if races:
            fetched+=len(races)
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
