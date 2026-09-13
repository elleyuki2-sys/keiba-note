"""Update KEIBA NOTE's bundled JRA schedule safely.

V5.4.11 policy:
- JRA official daily program is the only online source.
- Failed/partial downloads never overwrite the existing JSON.
- The application itself never depends on this script or on live JRA access.
"""
import json
import re
import sys
import time
from datetime import date, timedelta
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

COURSES = {"札幌", "函館", "福島", "新潟", "東京", "中山", "中京", "京都", "阪神", "小倉"}
HEADING_RE = re.compile(r"(\d{1,2})回\s*(札幌|函館|福島|新潟|東京|中山|中京|京都|阪神|小倉)\s*(\d{1,2})日")
RACE_RE = re.compile(r"(?:第\s*)?(\d{1,2})\s*(?:レース|R|Ｒ)\b", re.I)
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
            m = HEADING_RE.search(text)
            if m:
                self.current_course = m.group(2)
                self.current_meeting = f"{m.group(1)}回{m.group(3)}日"
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
        if self.heading_depth:
            self.heading_text.append(data)
        if self.current_cell is not None:
            self.current_cell.append(data)


def normalize(value):
    value = unescape(str(value)).replace("\xa0", " ").replace("\u3000", " ")
    value = re.sub(r"\s+", " ", value).strip()
    return value


def fetch(url, timeout=8):
    request = Request(
        url,
        headers={
            "User-Agent": "KEIBA-NOTE/5.4.11 (+GitHub Actions)",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
            "Referer": "https://www.jra.go.jp/",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", "replace")


def parse_html(html, ds):
    parser = JraTableParser()
    parser.feed(str(html))
    parser.close()
    result = []
    seen = set()

    for course, meeting, cells in parser.rows:
        if not course or not meeting or len(cells) < 2:
            continue
        joined = " | ".join(c for c in cells if c)
        race_match = RACE_RE.search(cells[0]) or RACE_RE.search(joined)
        time_match = TIME_RE.search(joined)
        if not race_match or not time_match:
            continue
        race = int(race_match.group(1))
        if not 1 <= race <= 12:
            continue

        # The middle cell is the race name/conditions on the official page.
        condition_cells = [c for c in cells if c and not RACE_RE.fullmatch(c)]
        condition = normalize(" ".join(condition_cells))
        condition = re.sub(r"\|", " ", condition)
        condition = re.sub(r"\d{1,2}\s*時\s*\d{1,2}\s*分.*$", "", condition).strip()
        if not condition:
            continue

        dm = DIST_RE.search(condition)
        distance = dm.group(1).replace(",", "") + "m" if dm else ""
        surface = dm.group(2) if dm else ""
        if surface == "ダート":
            surface = "ダ"

        name = condition[: dm.start()].strip() if dm else condition
        # Keep the complete condition when no distance marker is available.
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
    """Accept only complete-looking daily program data."""
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
        required = ["raceName", "raceCondition", "distance", "surface", "startTime", "raceKey", "meeting"]
        if any(not str(race.get(k, "")).strip() for k in required):
            return False
        by_course.setdefault(race["course"], set()).add(number)

    # A normal JRA meeting has a continuous 1R..12R program. Requiring at
    # least 10 races avoids replacing good data with a truncated response,
    # while still tolerating unusual cancellations/changes.
    return all(len(nums) >= 10 and min(nums) == 1 and max(nums) <= 12 for nums in by_course.values())


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
    old_payload, old_races = load_existing(path)
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

    today = date.today()
    successful_dates = []
    fetched = 0

    # Update only the near future. Running once a week is enough for the
    # planned-program data and greatly reduces unnecessary JRA requests.
    for offset in range(0, 15):
        ds = (today + timedelta(days=offset)).isoformat()
        d = date.fromisoformat(ds)
        url = f"https://www.jra.go.jp/keiba/calendar{d.year}/{d.year}/{d.month}/{d.month:02d}{d.day:02d}.html"
        try:
            raw = fetch(url)
            races = parse_html(raw, ds)
            if not validate_races(races, ds):
                print(f"WARN {ds}: JRA content received but daily program validation failed")
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
        "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%S+09:00", time.localtime()),
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
