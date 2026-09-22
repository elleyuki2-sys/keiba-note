"""Fetch official JRA meeting result reports and store structured race results.

The updater is server-side (GitHub Actions). The browser never calls JRA directly.
Primary source: JRA official "成績表" PDF. If direct JRA access is blocked,
Jina Reader is used server-side only to retrieve the same official PDF content.
"""
import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

COURSES = ("札幌", "函館", "福島", "新潟", "東京", "中山", "中京", "京都", "阪神", "小倉")
COURSE_RE = "|".join(COURSES)
MEETING_RE = re.compile(r"(\d+)回\s*(" + COURSE_RE + r")\s*(\d+)日")
RACE_RE = re.compile(r"第\s*(\d{1,2})\s*競走")
DATE_RE = re.compile(r"(\d{1,2})月(\d{1,2})日")


def clean(s):
    return re.sub(r"\s+", " ", str(s).replace("\u3000", " ").replace("−", "-")).strip()


def fetch(url, timeout=30):
    req = Request(url, headers={
        "User-Agent": "KEIBA-NOTE/5.6 (+GitHub Actions)",
        "Accept": "application/pdf,text/html,text/plain,*/*",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        "Referer": "https://www.jra.go.jp/",
    })
    with urlopen(req, timeout=timeout) as r:
        return r.read(), r.headers.get("content-type", "")


def meeting_rows(schedule, date):
    out = {}
    for r in schedule:
        if not isinstance(r, dict) or str(r.get("date", ""))[:10] != date:
            continue
        course = r.get("course", "")
        meeting = str(r.get("meeting", ""))
        m = re.search(r"(\d+)回(\d+)日", meeting)
        if course in COURSES and m:
            out[(course, int(m.group(1)), int(m.group(2)))] = meeting
    return sorted(out)


def pdf_text(pdf_bytes):
    with tempfile.TemporaryDirectory() as td:
        pdf = Path(td) / "report.pdf"
        txt = Path(td) / "report.txt"
        pdf.write_bytes(pdf_bytes)
        p = subprocess.run(["pdftotext", "-layout", str(pdf), str(txt)], capture_output=True, text=True)
        if p.returncode != 0:
            raise RuntimeError("pdftotext failed: " + p.stderr[:300])
        return txt.read_text(encoding="utf-8", errors="replace")


def jina_text(pdf_url):
    jina = "https://r.jina.ai/http://" + pdf_url.split("https://", 1)[1]
    data, _ = fetch(jina, timeout=60)
    return data.decode("utf-8", "replace")


def split_races(text):
    matches = list(RACE_RE.finditer(text))
    blocks = []
    for i, m in enumerate(matches):
        race = int(m.group(1))
        if not 1 <= race <= 12:
            continue
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        blocks.append((race, text[m.start():end]))
    return blocks


def parse_number(s):
    s = str(s).replace(",", "").replace("円", "").strip()
    try:
        return int(float(s))
    except ValueError:
        return None


def parse_race(block, date, course, meeting, race, source_url):
    # Name/condition: text between race marker and first obvious header.
    header = clean(block[:1600])
    race_name = ""
    mname = re.search(r"第\s*\d{1,2}\s*競走\s+(.+?)(?:\s+発走|\s+本賞|\s+\d{3,4}\s*メートル)", header)
    if mname:
        race_name = clean(mname.group(1))

    # Parse runner rows from pdftotext -layout. Typical row ends with odds + popularity.
    runners = []
    row_re = re.compile(r"^\s*(\d{1,2})\s+(\d{1,2})\s+(.+?)\s+(\d+(?:\.\d+)?)\s+(\d+)\s*$")
    seen_horses = set()
    for line in block.splitlines():
        s = clean(line)
        if not s:
            continue
        m = row_re.match(line)
        if not m:
            continue
        frame = int(m.group(1)); horse = int(m.group(2)); odds = float(m.group(4)); pop = int(m.group(5))
        if horse in seen_horses or not 1 <= horse <= 18:
            continue
        # Exclude lines that are clearly not runner rows.
        if odds <= 0 or pop <= 0:
            continue
        seen_horses.add(horse)
        runners.append({"horseNo": horse, "finish": len(runners) + 1, "odds": odds, "popularity": pop})

    # Payouts are easier to parse from the report's explicit payout section.
    payouts = {"win": [], "place": [], "wide": [], "quinella": [], "quinellaPlace": [], "trio": [], "trifecta": []}
    pay_start = re.search(r"払戻金[・･]?[給付金]*", block)
    pay = block[pay_start.start():] if pay_start else block
    win = re.search(r"単勝\s+([0-9]{1,2})\s+([0-9,]+)円", pay)
    if win:
        payouts["win"].append({"horses": win.group(1), "payout": parse_number(win.group(2))})

    # These sections may contain several horse/combo + payout pairs on following lines.
    def section_pairs(label, next_labels):
        look = "|".join(map(re.escape, next_labels)) if next_labels else r"$"
        pat = re.escape(label) + r"(.*?)(?=" + look + r")"
        mm = re.search(pat, pay, flags=re.S)
        if not mm:
            return []
        chunk = mm.group(1)
        pairs = re.findall(r"(\d{1,2}(?:-\d{1,2}){0,2})\s+([0-9,]+)円", chunk)
        return [{"horses": a, "payout": parse_number(b)} for a, b in pairs]

    labels = ["単勝", "複勝", "枠連", "馬連", "ワイド", "馬単", "3連複", "3連単"]
    payouts["place"] = section_pairs("複勝", labels[2:])
    payouts["wide"] = section_pairs("ワイド", labels[5:])
    payouts["quinella"] = section_pairs("馬連", labels[5:])
    payouts["quinellaPlace"] = section_pairs("枠連", labels[3:])
    payouts["trio"] = section_pairs("3連複", ["3連単"])
    payouts["trifecta"] = section_pairs("3連単", [])

    # If the PDF extractor split the table, keep the race only when the core result exists.
    if not runners or not (payouts["win"] or payouts["place"]):
        return None

    return {
        "date": date,
        "course": course,
        "meeting": meeting,
        "race": race,
        "raceName": race_name,
        "sourceUrl": source_url,
        "runners": runners,
        "payouts": payouts,
        "updatedAt": datetime.now(ZoneInfo("Asia/Tokyo")).isoformat(timespec="seconds"),
    }


def fetch_meeting(date, course, meeting_no, day_no):
    year = int(date[:4])
    filename = f"{year}-{meeting_no}{course}{day_no}.pdf"
    url = f"https://www.jra.go.jp/datafile/seiseki/report/{year}/{filename}"
    text = None
    try:
        raw, ctype = fetch(url)
        if raw[:4] == b"%PDF":
            text = pdf_text(raw)
            print(f"OK {date} {course}: direct JRA PDF")
    except Exception as exc:
        print(f"WARN {date} {course}: direct PDF failed: {exc}")
    if not text:
        try:
            text = jina_text(url)
            print(f"OK {date} {course}: Jina fallback")
        except Exception as exc:
            print(f"WARN {date} {course}: Jina fallback failed: {exc}")
            return []
    meeting = f"{meeting_no}回{day_no}日"
    results = []
    for race, block in split_races(text):
        item = parse_race(block, date, course, meeting, race, url)
        if item:
            results.append(item)
    print(f"INFO {date} {course}: parsed {len(results)} races")
    return results


def target_dates():
    today = datetime.now(ZoneInfo("Asia/Tokyo")).date()
    start = today - timedelta(days=14)
    return [(start + timedelta(days=i)).isoformat() for i in range((today - start).days + 1)]


def main():
    schedule_path = Path("data/jra-schedule.json")
    result_path = Path("data/jra-results.json")
    if not schedule_path.exists():
        print("ERROR: schedule JSON not found")
        return 1
    schedule_payload = json.loads(schedule_path.read_text(encoding="utf-8"))
    schedule = schedule_payload.get("races", []) if isinstance(schedule_payload, dict) else schedule_payload
    old = {}
    if result_path.exists():
        try:
            payload = json.loads(result_path.read_text(encoding="utf-8"))
            for r in payload.get("results", []):
                if isinstance(r, dict):
                    old[(r.get("date"), r.get("course"), int(r.get("race", 0)))] = r
        except Exception:
            pass

    fetched = 0
    for date in target_dates():
        for course, meeting_no, day_no in meeting_rows(schedule, date):
            for r in fetch_meeting(date, course, meeting_no, day_no):
                old[(r["date"], r["course"], r["race"])] = r
                fetched += 1

    results = sorted(old.values(), key=lambda r: (r.get("date", ""), r.get("course", ""), int(r.get("race", 0))))
    payload = {
        "updatedAt": datetime.now(ZoneInfo("Asia/Tokyo")).isoformat(timespec="seconds"),
        "source": "JRA official 成績表 PDF (direct + Jina server-side fallback)",
        "results": results,
    }
    result_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = result_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(result_path)
    print(f"OK: stored {len(results)} race results; refreshed {fetched} records")
    return 0


if __name__ == "__main__":
    sys.exit(main())
