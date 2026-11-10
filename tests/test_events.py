import json
from datetime import UTC, date, datetime

from tradedesk import events

ROWS = [
    {
        "id": "fomc-2026-12",
        "date": "2026-12-09",
        "time": "19:00",
        "title": "FOMC rate decision",
        "category": "central bank",
        "summary": "Markets price a hike.",
        "notes": "Last meeting held rates; a long note that has to be folded across "
        "several lines, with commas; and semicolons.",
        "links": [
            {
                "title": "Fed calendar",
                "url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
            }
        ],
    },
    {
        "id": "iran-talks",
        "date": "2026-11-20",
        "end": "2026-11-22",
        "title": "Iran talks",
        "summary": "Second round.",
    },
    {"id": "old", "date": "2026-01-01", "title": "Old event"},
]


def test_feed_has_timed_and_all_day_events():
    text = events.ics(ROWS, datetime(2026, 11, 10, tzinfo=UTC))
    assert "DTSTART:20261209T190000Z" in text and "DTEND:20261209T200000Z" in text
    assert "DTSTART;VALUE=DATE:20261120" in text and "DTEND;VALUE=DATE:20261123" in text
    assert "X-APPLE-CALENDAR-COLOR" in text and "\\, with commas\;" in text.replace("\r\n ", "")
    assert all(len(line.encode()) <= 75 for line in text.split("\r\n"))


def test_markdown_lists_only_upcoming(tmp_path):
    (tmp_path / "ticker").mkdir()
    events.path(tmp_path).write_text(json.dumps(ROWS))
    md = events.markdown(events.upcoming(events.load(tmp_path), date(2026, 11, 10)))
    assert md.splitlines()[0].startswith("- 2026-11-20 to 2026-11-22 Iran talks")
    assert "Old event" not in md and "19:00 UTC FOMC" in md
