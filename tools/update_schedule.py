"""Update KEIBA NOTE's bundled JRA schedule safely.

V5.4.12 policy:
- JRA official daily program is the only online source.
- The updater prioritizes today and recent past data; future data is optional.
- Failed/partial downloads never overwrite the existing JSON.
- The application itself never depends on this script or on live JRA access.
"""
import json
import re
import sys
import time
from datetime import date, datetime, timedelta
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

COURSES = {"札幌", "函館", "福島", "新潟", "東京", "中山", "中京", "京都", "阪神", "小倉"}
HEADING_RE = re.compile(r"(\d{1,2})\s*回\s*(札幌|函館|福島|新潟|東京|中山|中京|京都|阪神|小倉)\s*(\d{1,2})\s*日")
RACE_RE = re.compile(r"(?:第\s*)?(\d{1,2})\s*(?:レース|R|Ｒ)(?![A-Za-z])", re.I)
TIME_RE = re.compile(r"(\d{1,2})\s*時\s*(\d{1,2})\s*分")
DIST_RE = re.compile(r"([0-9,]+)\s*[（(]\s*(芝(?:・外)?|ダ|ダート)\s*[）)]")


class JraTableParser(HTMLParser):
    """Extract JRA table rows while retaining the current course heading."""

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
            text = normalize(" ".join(self.heading_text))
            self._update_meeting(text)
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
        m = HEADING_RE.search(text)
        if m:
            self.current_course = m.group(2)
            self.current_meeting = f"{m.group(1)}回{m.group(3)}日"


def normalize(value):
    value = unescape(str(value)).replace("\xa0", " ").replace("\u3000", " ")
    value = re.sub(r"\s+", " ", value).strip()
    return value


def fetch(url, timeout=10):
    request = Request(
        url,
        headers={
            "User-Agent": "KEIBA-NOTE/5.4.12 (+GitHub Actions)",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
            "Referer": "https://www.jra.go.jp/",
            "Connection": "close",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", "replace")


def parse_meetings_from_text(text):
    """Find all course/meeting headings anywhere in the document text."""
    return [(m.start(), m.group(2), f"{m.group(1)}回{m.group(3)}日") for m in HEADING_RE.finditer(normalize(text))]


def infer_course_for_rows(parser):
    """Fallback for pages where the meeting heading is not an h1-h6 element."""
    if any(course for course, _, _ in parser.rows):
        return parser.rows

    full_text = " ".join(parser.all_text)
    meetings = parse_meetings_from_text(full_text)
    if not meetings:
        return parser.rows

    # When headings are outside h1-h6, use their order. JRA's daily program
    # presents one table per course, each containing a continuous 1R..12R list.
    output = []
    current = 0
    counts = {}
    for _, _, cells in parser.rows:
        if len(meetings) > 1:
            # Switch course after a row containing a new course heading if it
            # is represented inside the row text; otherwise use the expected
            # 12-race blocks.
            joined = " ".join(cells)
            found = HEADING_RE.search(joined)
            if found:
                current = min(current + 1, len(meetings) - 1)
        course = meetings[current][1]
        meeting = meetings[current][2]
        output.append((course, meeting, cells))
        race_match = RACE_RE.search(" ".join(cells))
        if race_match:
            counts[current] = counts.get(current, 0) + 1
            if counts[current] >= 12 and current < len(meetings) - 1:
                current += 1
    return output


def parse_html(html, ds):
    parser = JraTableParser()
    parser.feed(str(html))
    parser.close()
    rows = infer_course_for_rows(parser)
    result = []
    seen = set()

    for course, meeting, cells in rows:
        if not course or not meeting or len(cells) < 2:
            continue
        joined = " | ".join(c for c in cells if c)
        race_match = RACE_RE.search(joined)
        time_match = TIME_RE.search(joined)
        if not race_match or not time_match:
            continue
        race = int(race_match.group(1))
        if not 1 <= race <= 12:
            continue

        # Remove the race-number cell/header and the start-time text. The
        # remaining text is the official race name/conditions.
        condition_parts = []
        for cell in cells:
            if not cell:
                continue
            if RACE_RE.fullmatch(cell):
                continue
            if TIME_RE.fullmatch(cell):
                continue
            if cell in {"レース番号", "レース名・条件", "発走時刻"}:
                continue
            condition_parts.append(cell)
        condition = normalize(" ".join(condition_parts))
        if not condition:
            continue

        dm = DIST_RE.search(condition)
        distance = dm.group(1).replace(",", "") + "m" if dm else ""
        surface = dm.group(2) if dm else ""
        if surface == "ダート":
            surface = "ダ"

        name = condition[: dm.start()].strip() if dm else condition
        key = (ds, course, race)
        if key in seen:
            continue
        seen.add(key)
        result.append(
            {
                "date": ds,
                "course": course,
                "race": race,
                "raceName": name,
                "raceCondition": condition,
                "distance": distance,
                "surface": surface,
                "startTime": f"{int(time_match.group(1)):02d}:{int(time_match.group(2)):02d}",
                "raceKey": f"{ds}-{course}-{race}",
                "meeting": meeting,
            }
        )

    return sorted(result, key=lambda r: (r["course"], r["race"]))


def validate_races(races, ds):
    """Accept only complete-looking race lists; distance/surface are optional."""
    if not races:
        return False
    by_course = {}
    for race in races:
        if race.get("date") != ds:
            return False
        if race.get("course") not in COURSES:
            return False
        try:
            number = int(race.get("race", 0))
        except Exception:
            return False
        if not 1 <= number <= 12:
            return False
        required = ["raceName", "raceCondition", "startTime", "raceKey", "meeting"]
        if any(not str(race.get(k, "")).strip() for k in required):
            return False
        by_course.setdefault(race["course"], set()).add(number)

    # A valid course block should normally contain 1R..12R. We require all
    # 12 here because this data is the race selector, not a partial result feed.
    return all(len(nums) == 12 and min(nums) == 1 and max(nums) == 12 for nums in by_course.values())


def load_existing(path):
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        races = payload.get("races", []) if isinstance(payload, dict) else []
        return payload, races if isinstance(races, list) else []
    except Exception as exc:
        print(f"WARN: existing JSON could not be read: {exc}")
        return {}, []


def target_dates():
    """Return today plus the previous 7 calendar days in Japan time.

    Future dates are intentionally not required. This keeps the updater useful
    for same-day accounting even when JRA blocks future-page requests.
    """
    today = datetime.now(ZoneInfo("Asia/Tokyo")).date()
    return [today - timedelta(days=offset) for offset in range(0, 8)]


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

    successful_dates = []
    fetched = 0

    for d in target_dates():
        ds = d.isoformat()
        url = f"https://www.jra.go.jp/keiba/calendar{d.year}/{d.year}/{d.month}/{d.month:02d}{d.day:02d}.html"
        try:
            raw = fetch(url)
            races = parse_html(raw, ds)
            if not validate_races(races, ds):
                print(f"WARN {ds}: JRA content received but daily program validation failed ({len(races)} races parsed)")
                continue
            print(f"OK {ds}: JRA official parsed {len(races)} races")
            successful_dates.append(ds)
            fetched += len(races)
            for race in races:
                existing[(race["date"], race["course"], race["race"])] = race
        except HTTPError as exc:
            print(f"WARN {ds}: JRA HTTP Error {exc.code}: {exc.reason}")
        except (URLError, TimeoutError) as exc:
            print(f"WARN {ds}: JRA network error: {exc}")
        except Exception as exc:
            print(f"WARN {ds}: JRA processing error: {exc}")
        time.sleep(0.2)

    if not fetched:
        print("INFO: no new valid JRA schedule data; existing JSON was preserved.")
        return 0

    races = sorted(existing.values(), key=lambda r: (r.get("date", ""), r.get("course", ""), int(r.get("race", 0))))
    payload = {
        "updatedAt": datetime.now(ZoneInfo("Asia/Tokyo")).isoformat(timespec="seconds"),
        "source": "JRA official daily program",
        "races": races,
    }
    temp = path.with_suffix(".json.tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)
    print(f"OK: added/updated {fetched} races across {len(successful_dates)} date(s); stored {len(races)} races")
    return 0


if __name__ == "__main__":
    sys.exit(main())
