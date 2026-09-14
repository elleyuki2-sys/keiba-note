"""Update KEIBA NOTE's bundled race-name schedule safely.

V5.4.14 policy:
- The app needs only date/course/race number/race name as the minimum.
- Try the JRA official daily program directly first.
- If JRA blocks GitHub Actions, try the same official page through Jina Reader.
- Parse both HTML tables and Markdown/text representations.
- Partial valid race data is accepted; bad data never overwrites existing JSON.
- Future race acquisition is enabled. Target is previous 7 days + today + next 14 days (JST).
"""
import json
import re
import sys
import time
from datetime import datetime, timedelta
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

COURSES = ("札幌", "函館", "福島", "新潟", "東京", "中山", "中京", "京都", "阪神", "小倉")
COURSE_RE = "|".join(COURSES)
MEETING_RE = re.compile(r"(\d{1,2})\s*回\s*(札幌|函館|福島|新潟|東京|中山|中京|京都|阪神|小倉)\s*(\d{1,2})\s*日")
RACE_RE = re.compile(r"(?:第\s*)?(\d{1,2})\s*(?:レース|R|Ｒ)(?![A-Za-z])", re.I)
TIME_RE = re.compile(r"(?:発走(?:時刻)?\s*)?(\d{1,2})\s*時\s*(\d{1,2})\s*分")
DIST_RE = re.compile(r"([0-9,]+)\s*[（(]\s*(芝(?:・外)?|ダ|ダート)\s*[）)]")
DATE_TEXT_RE = re.compile(r"\d{4}年\d{1,2}月\d{1,2}日(?:（[^）]+）)?")


def normalize(value):
    value = unescape(str(value)).replace("\xa0", " ").replace("\u3000", " ")
    value = re.sub(r"\\\\", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


class JraHtmlParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self.current_row = None
        self.current_cell = None
        self.heading_depth = 0
        self.heading_text = []
        self.current_course = ""
        self.current_meeting = ""
        self.all_text = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.heading_depth += 1
            self.heading_text = []
        elif tag == "tr":
            self.current_row = []
        elif tag in {"td", "th"} and self.current_row is not None:
            self.current_cell = []
        elif tag == "br" and self.current_cell is not None:
            self.current_cell.append(" ")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"} and self.heading_depth:
            self._update_meeting(normalize(" ".join(self.heading_text)))
            self.heading_depth -= 1
        elif tag in {"td", "th"} and self.current_row is not None and self.current_cell is not None:
            self.current_row.append(normalize("".join(self.current_cell)))
            self.current_cell = None
        elif tag == "tr":
            if self.current_row:
                self.rows.append((self.current_course, self.current_meeting, self.current_row[:]))
            self.current_row = None
            self.current_cell = None

    def handle_data(self, data):
        if data.strip():
            self.all_text.append(data)
        if self.heading_depth:
            self.heading_text.append(data)
        if self.current_cell is not None:
            self.current_cell.append(data)

    def _update_meeting(self, text):
        m = MEETING_RE.search(text)
        if m:
            self.current_course = m.group(2)
            self.current_meeting = f"{m.group(1)}回{m.group(3)}日"


def parse_meetings(text):
    return [(m.start(), m.group(2), f"{m.group(1)}回{m.group(3)}日") for m in MEETING_RE.finditer(normalize(text))]


def assign_meetings(rows, all_text):
    """Assign a course/meeting when the source representation lost headings."""
    if any(c for c, _, _ in rows):
        return rows
    meetings = parse_meetings(all_text)
    if not meetings:
        return rows
    out = []
    idx = 0
    count = 0
    for row in rows:
        course, meeting, cells = row
        if course:
            out.append(row)
            continue
        out.append((meetings[idx][1], meetings[idx][2], cells))
        if RACE_RE.search(" | ".join(cells)):
            count += 1
            if count >= 12 and idx + 1 < len(meetings):
                idx += 1
                count = 0
    return out


def race_name_from_cells(cells):
    texts = []
    for cell in cells:
        c = normalize(cell)
        if not c:
            continue
        if c in {"レース番号", "レース名・条件", "発走時刻", "Race", "レース"}:
            continue
        if RACE_RE.fullmatch(c) or TIME_RE.fullmatch(c):
            continue
        # Remove common Markdown table decoration and link syntax.
        c = re.sub(r"^\[([^\]]+)\]\([^)]*\)$", r"\1", c)
        c = c.replace("|", " ")
        texts.append(c)
    if not texts:
        return "", ""
    condition = normalize(" ".join(texts))
    condition = DATE_TEXT_RE.sub("", condition).strip()
    condition = re.sub(r"^(?:第\s*)?\d{1,2}\s*(?:レース|R|Ｒ)\s*", "", condition, flags=re.I)
    dm = DIST_RE.search(condition)
    name = condition[:dm.start()].strip() if dm else condition
    # Avoid treating generic labels as a race name.
    if name in {"開催日程", "競馬番組", "JRA", "本文へ移動する"}:
        return "", ""
    return name, condition


def build_race(ds, course, meeting, race, name, condition="", start_time=""):
    if not course or course not in COURSES or not (1 <= race <= 12) or not name:
        return None
    dm = DIST_RE.search(condition)
    distance = dm.group(1).replace(",", "") + "m" if dm else ""
    surface = dm.group(2) if dm else ""
    if surface == "ダート":
        surface = "ダ"
    return {
        "date": ds,
        "course": course,
        "race": race,
        "raceName": name,
        "raceCondition": condition or name,
        "distance": distance,
        "surface": surface,
        "startTime": start_time,
        "raceKey": f"{ds}-{course}-{race}",
        "meeting": meeting or "",
    }


def parse_html(html, ds):
    parser = JraHtmlParser()
    parser.feed(str(html))
    parser.close()
    rows = assign_meetings(parser.rows, " ".join(parser.all_text))
    result = []
    seen = set()
    for course, meeting, cells in rows:
        joined = " | ".join(cells)
        rm = RACE_RE.search(joined)
        if not rm:
            continue
        race = int(rm.group(1))
        tm = TIME_RE.search(joined)
        name, condition = race_name_from_cells(cells)
        item = build_race(ds, course, meeting, race, name, condition,
                          f"{int(tm.group(1)):02d}:{int(tm.group(2)):02d}" if tm else "")
        if item and item["raceKey"] not in seen:
            seen.add(item["raceKey"])
            result.append(item)
    return sorted(result, key=lambda r: (r["course"], r["race"]))


def markdown_lines(text):
    lines = []
    for raw in str(text).splitlines():
        line = raw.strip()
        if not line or line.startswith("[![") or line.startswith("---"):
            continue
        line = re.sub(r"^\s*#+\s*", "", line)
        line = line.replace("\\|", "|")
        lines.append(normalize(line))
    return lines


def parse_markdown(text, ds):
    """Parse Jina Reader's Markdown/text output without depending on HTML tags."""
    lines = markdown_lines(text)
    meetings = []
    for i, line in enumerate(lines):
        m = MEETING_RE.search(line)
        if m:
            meetings.append((i, m.group(2), f"{m.group(1)}回{m.group(3)}日"))
    result = []
    seen = set()
    course_idx = 0
    race_count = 0
    current_course = meetings[0][1] if meetings else ""
    current_meeting = meetings[0][2] if meetings else ""

    for i, line in enumerate(lines):
        # Prefer an explicit meeting/course line whenever present.
        mm = MEETING_RE.search(line)
        if mm:
            current_course = mm.group(2)
            current_meeting = f"{mm.group(1)}回{mm.group(3)}日"
            for j, (pos, _, _) in enumerate(meetings):
                if pos == i:
                    course_idx = j
                    race_count = 0
                    break
            continue

        rm = RACE_RE.search(line)
        if not rm:
            continue
        race = int(rm.group(1))
        if not 1 <= race <= 12:
            continue

        # A race line in Jina Markdown is commonly a table row. Collect its cells.
        candidate = line
        if "|" in candidate:
            cells = [normalize(x) for x in candidate.strip("|").split("|")]
        else:
            # If the race marker is on its own line, use the next few lines.
            cells = [candidate]
            for nxt in lines[i + 1:i + 4]:
                if RACE_RE.search(nxt) or MEETING_RE.search(nxt):
                    break
                if nxt:
                    cells.append(nxt)
                    if len(cells) >= 3:
                        break
        name, condition = race_name_from_cells(cells)
        if not name:
            continue
        tm = TIME_RE.search(" | ".join(cells))
        if not current_course and meetings:
            current_course = meetings[min(course_idx, len(meetings)-1)][1]
            current_meeting = meetings[min(course_idx, len(meetings)-1)][2]
        item = build_race(ds, current_course, current_meeting, race, name, condition,
                          f"{int(tm.group(1)):02d}:{int(tm.group(2)):02d}" if tm else "")
        if item and item["raceKey"] not in seen:
            seen.add(item["raceKey"])
            result.append(item)
            race_count += 1
            if race == 12 and course_idx + 1 < len(meetings):
                course_idx += 1
                current_course = meetings[course_idx][1]
                current_meeting = meetings[course_idx][2]
                race_count = 0
    return sorted(result, key=lambda r: (r["course"], r["race"]))


def fetch(url, timeout=15, user_agent="KEIBA-NOTE/5.4.14 (+GitHub Actions)"):
    request = Request(url, headers={
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.8",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        "Referer": "https://www.jra.go.jp/",
        "Connection": "close",
    })
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", "replace")


def fetch_jra_page(ds):
    d = datetime.strptime(ds, "%Y-%m-%d").date()
    url = f"https://www.jra.go.jp/keiba/calendar{d.year}/{d.year}/{d.month}/{d.month:02d}{d.day:02d}.html"
    try:
        raw = fetch(url)
        races = parse_html(raw, ds)
        if races:
            print(f"OK {ds}: JRA direct parsed {len(races)} minimum race records")
            return races
        print(f"WARN {ds}: JRA direct content received but 0 minimum race records parsed")
    except HTTPError as exc:
        print(f"WARN {ds}: JRA direct HTTP {exc.code}: {exc.reason}")
    except (URLError, TimeoutError) as exc:
        print(f"WARN {ds}: JRA direct network error: {exc}")
    except Exception as exc:
        print(f"WARN {ds}: JRA direct processing error: {exc}")

    # Jina Reader is only a server-side fallback; the browser never calls it.
    jina_url = "https://r.jina.ai/http://www.jra.go.jp" + url.split("www.jra.go.jp", 1)[1]
    try:
        text = fetch(jina_url, timeout=25, user_agent="Mozilla/5.0 (compatible; KEIBA-NOTE/5.4.14)")
        races = parse_markdown(text, ds)
        if races:
            print(f"OK {ds}: Jina fallback parsed {len(races)} minimum race records")
            return races
        print(f"WARN {ds}: Jina content received but 0 minimum race records parsed")
    except HTTPError as exc:
        print(f"WARN {ds}: Jina HTTP {exc.code}: {exc.reason}")
    except (URLError, TimeoutError) as exc:
        print(f"WARN {ds}: Jina network error: {exc}")
    except Exception as exc:
        print(f"WARN {ds}: Jina processing error: {exc}")
    return []


def target_dates():
    """Return a small rolling window around today.

    Past 7 days are kept for result/accounting continuity. The next 14 days
    are newly included so planned JRA programs can appear before race day.
    Dates for which JRA has not published a program simply return no records
    and therefore never overwrite existing JSON.
    """
    today = datetime.now(ZoneInfo("Asia/Tokyo")).date()
    start = today - timedelta(days=7)
    end = today + timedelta(days=14)
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def load_existing(path):
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        races = payload.get("races", []) if isinstance(payload, dict) else []
        return payload, races if isinstance(races, list) else []
    except Exception as exc:
        print(f"WARN: existing JSON could not be read: {exc}")
        return {}, []


def main():
    path = Path("data/jra-schedule.json")
    _, old_races = load_existing(path)
    existing = {}
    for race in old_races:
        if not isinstance(race, dict):
            continue
        try:
            key = (race.get("date"), race.get("course"), int(race.get("race", 0)))
        except Exception:
            continue
        if key[0] and key[1] and key[2]:
            existing[key] = race

    added = 0
    successful_dates = 0
    for d in target_dates():
        ds = d.isoformat()
        races = fetch_jra_page(ds)
        if not races:
            continue
        successful_dates += 1
        for race in races:
            key = (race["date"], race["course"], race["race"])
            old = existing.get(key, {})
            # Keep richer fields from an older record if the fallback only supplied the minimum.
            merged = dict(old)
            merged.update({k: v for k, v in race.items() if v not in ("", None)})
            existing[key] = merged
            added += 1
        time.sleep(0.2)

    if not successful_dates:
        print("INFO: no new valid race-name data; existing JSON was preserved.")
        return 0

    races = sorted(existing.values(), key=lambda r: (r.get("date", ""), r.get("course", ""), int(r.get("race", 0))))
    payload = {
        "updatedAt": datetime.now(ZoneInfo("Asia/Tokyo")).isoformat(timespec="seconds"),
        "source": "JRA official daily program (direct + Jina server-side fallback)",
        "races": races,
    }
    temp = path.with_suffix(".json.tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)
    print(f"OK: merged {added} race records from {successful_dates} date(s); stored {len(races)} records")
    return 0


if __name__ == "__main__":
    sys.exit(main())
