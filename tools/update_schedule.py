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

def fetch(url,timeout=30):
 req=Request(url,headers={
     "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36",
     "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,text/markdown;q=0.8,*/*;q=0.7",
     "Accept-Language":"ja,en-US;q=0.9,en;q=0.8",
     "Referer":"https://www.jra.go.jp/",
     "Cache-Control":"no-cache",
 })
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

def is_forbidden(text):
 s=norm(text)[:12000].lower()
 return ("403" in s and "forbidden" in s) or "title: forbidden" in s

def parse_jra_markdown(text, ds):
    """Parse JRA's rendered Markdown table, including multi-line race names."""
    s = str(text).replace("\r", "\n")
    s = unescape(s)
    # Preserve table structure while normalizing HTML remnants.
    s = re.sub(r'<br\s*/?>', '\n', s, flags=re.I)
    s = re.sub(r'<[^>]+>', ' ', s)

    lines = [norm(x).strip() for x in s.splitlines() if norm(x).strip()]
    races = []
    course = ""
    meeting = ""
    pending_race = None
    pending_condition = []

    def flush_pending():
        nonlocal pending_race, pending_condition
        if pending_race is None or not course:
            pending_race = None
            pending_condition = []
            return
        race = pending_race
        cond = norm(" ".join(pending_condition))
        # Extract time first.
        tm = re.search(r'(\d{1,2})時\s*(\d{1,2})分', cond)
        if not tm:
            pending_race = None
            pending_condition = []
            return
        start = f"{int(tm.group(1)):02d}:{int(tm.group(2)):02d}"
        cond = re.sub(r'\|?\s*\d{1,2}時\s*\d{1,2}分.*$', '', cond).strip(" |")
        # Extract distance/surface.
        dm = re.search(r'([0-9,]+)\s*（\s*(芝(?:・外)?|ダ)\s*）', cond)
        if not dm:
            dm = re.search(r'([0-9,]+)\s*[（(]\s*(芝(?:・外)?|ダ)\s*[）)]', cond)
        distance = (dm.group(1).replace(",", "") + "m") if dm else ""
        surface = dm.group(2) if dm else ""
        name = cond
        if dm:
            name = cond[:dm.start()].strip()
        # JRA sometimes puts a line break before the race title.
        name = re.sub(r'\s+', ' ', name).strip()
        races.append({
            "date": ds, "course": course, "race": race,
            "raceName": name, "raceCondition": cond,
            "distance": distance, "surface": surface,
            "startTime": start,
            "raceKey": f"{ds}-{course}-{race}", "meeting": meeting
        })
        pending_race = None
        pending_condition = []

    for line in lines:
        # Heading: 4回中山2日
        hm = re.search(r'(\d{1,2})回\s*([^\s|]+?)(\d{1,2})日', line)
        if hm:
            flush_pending()
            meeting = f"{hm.group(1)}回{hm.group(3)}日"
            course = hm.group(2)
            continue

        # Ignore header/separator rows.
        if "レース番号" in line and "発走時刻" in line:
            continue
        if re.fullmatch(r'[-| :]+', line):
            continue

        # Exact common JRA table row.
        rm = re.match(r'^\|?\s*(\d{1,2})レース\s*\|\s*(.*?)\s*\|\s*(\d{1,2})時\s*(\d{1,2})分\s*\|?\s*$', line)
        if rm:
            flush_pending()
            pending_race = int(rm.group(1))
            pending_condition = [rm.group(2), f"{rm.group(3)}時{rm.group(4)}分"]
            flush_pending()
            continue

        # Alternate flattened table: "1レース ... 10時05分"
        rm = re.search(r'(?<!\d)(\d{1,2})レース\b(.*?)(\d{1,2})時\s*(\d{1,2})分', line)
        if rm:
            flush_pending()
            pending_race = int(rm.group(1))
            pending_condition = [rm.group(2), f"{rm.group(3)}時{rm.group(4)}分"]
            flush_pending()
            continue

        # Markdown may split the race title over multiple lines.
        if pending_race is not None:
            pending_condition.append(line)

    flush_pending()

    # Deduplicate.
    seen = set()
    result = []
    for r in races:
        key = (r["date"], r["course"], r["race"])
        if key not in seen and 1 <= r["race"] <= 12:
            seen.add(key)
            result.append(r)
    return result


def parse_html_tables(text, ds):
    """Parse JRA HTML tables while preserving table-cell boundaries."""
    from html.parser import HTMLParser

    class P(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.rows=[]; self.row=[]; self.cell=[]; self.in_cell=False
        def handle_starttag(self, tag, attrs):
            tag=tag.lower()
            if tag=="tr":
                self.row=[]
            elif tag in ("td","th"):
                self.in_cell=True; self.cell=[]
            elif tag=="br" and self.in_cell:
                self.cell.append(" ")
        def handle_endtag(self, tag):
            tag=tag.lower()
            if tag in ("td","th") and self.in_cell:
                self.row.append(norm("".join(self.cell)))
                self.in_cell=False
            elif tag=="tr" and self.row:
                self.rows.append(self.row[:])
        def handle_data(self, data):
            if self.in_cell:
                self.cell.append(data)

    try:
        p=P(); p.feed(str(text)); p.close()
    except Exception:
        return []

    flat=strip_html(text)
    headings=re.findall(
        r'(\d{1,2})回\s*(札幌|函館|福島|新潟|東京|中山|中京|京都|阪神|小倉)\s*(\d{1,2})日',
        flat
    )
    default_course=headings[0][1] if len(headings)==1 else ""
    default_meeting=(f"{headings[0][0]}回{headings[0][2]}日" if len(headings)==1 else "")

    out=[]
    for row in p.rows:
        joined=" | ".join(row)
        rm=re.search(r'(?:第\s*)?(\d{1,2})\s*(?:R|Ｒ|レース)', joined, re.I)
        tm=TIME_RE.search(joined)
        if not rm or not tm:
            continue
        race=int(rm.group(1))
        if not 1 <= race <= 12:
            continue
        hm=re.search(r'(\d{1,2})回\s*(札幌|函館|福島|新潟|東京|中山|中京|京都|阪神|小倉)\s*(\d{1,2})日', joined)
        course=hm.group(2) if hm else default_course
        meeting=(f"{hm.group(1)}回{hm.group(3)}日" if hm else default_meeting)
        if not course:
            continue

        cells=[x for x in row if x and not re.search(r'(?:第\s*)?\d{1,2}\s*(?:R|Ｒ|レース)',x,re.I)]
        cond=norm(" ".join(cells))
        cond=re.sub(r'\d{1,2}\s*時\s*\d{1,2}\s*分.*$', '', cond).strip(" |")
        dm=DIST_RE.search(cond)
        distance=(dm.group(1).replace(",","")+"m") if dm else ""
        surface=dm.group(2) if dm else ""
        if surface=="ダート": surface="ダ"
        name=cond[:dm.start()].strip() if dm else cond

        out.append({
            "date":ds,"course":course,"race":race,
            "raceName":name,"raceCondition":cond,
            "distance":distance,"surface":surface,
            "startTime":f"{int(tm.group(1)):02d}:{int(tm.group(2)):02d}",
            "raceKey":f"{ds}-{course}-{race}","meeting":meeting
        })

    seen=set(); result=[]
    for r in out:
        k=(r["date"],r["course"],r["race"])
        if k not in seen:
            seen.add(k); result.append(r)
    return result

def parse_flexible_text(text, ds):
    """Parse flattened JRA text using 1R/１Ｒ/1レース markers."""
    s=unescape(str(text)).replace("\r","\n").replace("\u3000"," ")
    s=re.sub(r'<br\s*/?>','\n',s,flags=re.I)
    s=re.sub(r'<[^>]+>',' ',s)
    lines=[norm(x) for x in s.splitlines() if norm(x)]

    headings=re.findall(
        r'(\d{1,2})回\s*(札幌|函館|福島|新潟|東京|中山|中京|京都|阪神|小倉)\s*(\d{1,2})日',
        "\n".join(lines)
    )
    course=headings[0][1] if len(headings)==1 else ""
    meeting=(f"{headings[0][0]}回{headings[0][2]}日" if len(headings)==1 else "")
    out=[]

    for i,line in enumerate(lines):
        rm=re.search(r'(?:第\s*)?(\d{1,2})\s*(?:R|Ｒ|レース)\b',line,re.I)
        if not rm:
            continue
        race=int(rm.group(1))
        if not 1 <= race <= 12:
            continue
        window=" ".join(lines[i:i+8])
        tm=TIME_RE.search(window)
        if not tm:
            continue
        cond=re.sub(r'^.*?(?:第\s*)?\d{1,2}\s*(?:R|Ｒ|レース)\b','',window,count=1,flags=re.I)
        cond=re.sub(r'\d{1,2}\s*時\s*\d{1,2}\s*分.*$','',cond).strip(" |")
        dm=DIST_RE.search(cond)
        distance=(dm.group(1).replace(",","")+"m") if dm else ""
        surface=dm.group(2) if dm else ""
        if surface=="ダート": surface="ダ"
        name=cond[:dm.start()].strip() if dm else cond
        if course:
            out.append({
                "date":ds,"course":course,"race":race,
                "raceName":name,"raceCondition":cond,
                "distance":distance,"surface":surface,
                "startTime":f"{int(tm.group(1)):02d}:{int(tm.group(2)):02d}",
                "raceKey":f"{ds}-{course}-{race}","meeting":meeting
            })

    seen=set(); result=[]
    for r in out:
        k=(r["date"],r["course"],r["race"])
        if k not in seen:
            seen.add(k); result.append(r)
    return result

def parse_table_rows(text,ds):
    for parser in (
        lambda x: parse_html_tables(x, ds),
        lambda x: parse_jra_markdown(x, ds),
        lambda x: parse_generic_table_rows(x, ds),
        lambda x: parse_flexible_text(x, ds),
    ):
        races=parser(text)
        if races:
            return races
    return []

def parse_generic_table_rows(text,ds):
    """Parse JRA table rows in HTML, Markdown, or flattened text."""
    s=str(text)
    # Normalize HTML table cells into pipe-delimited rows.
    s=re.sub(r'</(?:td|th)\s*>', '|', s, flags=re.I)
    s=re.sub(r'<tr\b[^>]*>', '\n', s, flags=re.I)
    s=re.sub(r'</tr\s*>', '\n', s, flags=re.I)
    s=re.sub(r'<br\s*/?>', ' ', s, flags=re.I)
    s=re.sub(r'<[^>]+>', ' ', s)
    s=unescape(s).replace('\r','\n')
    lines=[norm(x) for x in s.splitlines() if norm(x)]
    out=[]
    course=""
    meeting=""
    for line in lines:
        clean=line.strip().strip("|").strip()
        h=HEADING.match(clean)
        if h:
            course=h.group(2)
            meeting=f"{h.group(1)}回{h.group(3)}日"
            continue
        # JRA table row: race | condition | time
        m=re.search(r'(?<!\d)(\d{1,2})\s*レース\s*\|\s*(.*?)\s*\|\s*(\d{1,2})時\s*(\d{1,2})分', clean)
        if not m:
            m=re.search(r'^\|?\s*(\d{1,2})\s*\|\s*(.*?)\s*\|\s*(\d{1,2})時\s*(\d{1,2})分\s*\|?$', clean)
        if not m or not course:
            continue
        race=int(m.group(1))
        if not 1<=race<=12:
            continue
        cond=norm(m.group(2))
        dm=re.search(r'([0-9,]+)\s*（\s*(芝(?:・外)?|ダ|芝→ダート|ダート)\s*）',cond)
        if not dm:
            dm=re.search(r'([0-9,]+)\s*(?:m)?\s*[（(]\s*(芝(?:・外)?|ダ|芝→ダート|ダート)\s*[）)]',cond)
        distance=(dm.group(1).replace(",","")+"m") if dm else ""
        surface=dm.group(2) if dm else ""
        if surface=="ダート":
            surface="ダ"
        name=re.sub(r'\s+[0-9,]+\s*（.*','',cond).strip()
        name=re.sub(r'\s+[0-9,]+\s*[（(].*','',name).strip() or cond
        out.append({
            "date":ds,"course":course,"race":race,
            "raceName":name,"raceCondition":cond,
            "distance":distance,"surface":surface,
            "startTime":f"{int(m.group(3)):02d}:{int(m.group(4)):02d}",
            "raceKey":f"{ds}-{course}-{race}","meeting":meeting
        })
    seen=set()
    return [r for r in out if not ((r["date"],r["course"],r["race"]) in seen or seen.add((r["date"],r["course"],r["race"])))]


def fetch_date(ds):
    d=date.fromisoformat(ds)
    path=f"/keiba/calendar2026/2026/{d.month}/{d.month:02d}{d.day:02d}.html"
    sources=[
        ("JRA",f"https://www.jra.go.jp{path}"),
        ("JRA-alt",f"https://jra.jp{path}"),
        ("Jina",f"https://r.jina.ai/https://www.jra.go.jp{path}"),
        ("Jina-alt",f"https://r.jina.ai/https://jra.jp{path}")
    ]
    for source,url in sources:
        try:
            raw=fetch(url)
            if is_forbidden(raw):
                print(f"WARN {ds}: {source} returned 403/Forbidden; skipping")
                continue
            races=parse_table_rows(raw,ds)
            if races:
                print(f"OK {ds}: {source} parsed {len(races)} races")
                return races
            print(f"WARN {ds}: {source} returned content but no race rows were detected")
            raw_s=str(raw)
            clues=[]
            for pat in (
                r'[^\\n]{0,100}(?:1レース|1R|１Ｒ|レース番号)[^\\n]{0,180}',
                r'[^\\n]{0,100}(?:10時|11時|12時|13時|14時|15時|16時)[^\\n]{0,180}',
                r'[^\\n]{0,100}(?:中山|阪神|中京|東京|京都|新潟|福島|札幌|函館|小倉)[^\\n]{0,140}'
            ):
                clues.extend(re.findall(pat, raw_s, flags=re.I))
            for clue in list(dict.fromkeys(clues))[:6]:
                print(f"DEBUG {ds}: {norm(clue)[:280]}")
        except Exception as e:
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
