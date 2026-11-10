"""The event calendar: data/ticker/events.json, kept by the market brief. It renders to
calendar.md for the desk and to an iCalendar feed Daniel subscribes to."""

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

NAME = "Market Events"
COLOR = "#E8A317"
FEED = "events.ics"


def path(root: Path) -> Path:
    return root / "ticker" / "events.json"


def load(root: Path) -> list[dict]:
    p = path(root)
    if not p.exists():
        return []
    rows = json.loads(p.read_text())
    return sorted(rows, key=lambda e: (e["date"], e.get("time") or ""))


def upcoming(rows: list[dict], today: date | None = None) -> list[dict]:
    today = today or datetime.now(UTC).date()
    return [e for e in rows if date.fromisoformat(e.get("end") or e["date"]) >= today]


def markdown(rows: list[dict]) -> str:
    """One line per event for the agents, with the summary that says why it matters."""
    out = []
    for e in rows:
        when = e["date"] + (f" {e['time']} UTC" if e.get("time") else "")
        if e.get("end"):
            when += f" to {e['end']}"
        out.append(f"- {when} {e['title']}: {e.get('summary', '')}".rstrip(": "))
    return "\n".join(out) + "\n" if out else ""


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> list[str]:
    """iCalendar lines are at most 75 octets; longer ones continue after a space."""
    out, chunk = [], ""
    for ch in line:
        if len((chunk + ch).encode()) > (75 if not out else 74):
            out.append(chunk)
            chunk = ""
        chunk += ch
    out.append(chunk)
    return [out[0], *(" " + c for c in out[1:])]


def _uid(e: dict) -> str:
    key = e.get("id") or f"{e['date']}-{e['title']}"
    return hashlib.sha1(key.encode()).hexdigest()[:16] + "@market-calendar"


def _description(e: dict) -> str:
    parts = [e.get("summary", ""), e.get("notes", "")]
    links = e.get("links") or []
    if links:
        parts.append("\n".join(f"{x.get('title', x['url'])}: {x['url']}" for x in links))
    return "\n\n".join(p for p in parts if p)


def ics(rows: list[dict], stamp: datetime | None = None) -> str:
    stamp = (stamp or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//tradedesk//market calendar//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{NAME}",
        f"X-APPLE-CALENDAR-COLOR:{COLOR}",
        "X-WR-TIMEZONE:UTC",
        "REFRESH-INTERVAL;VALUE=DURATION:PT6H",
        "X-PUBLISHED-TTL:PT6H",
    ]
    for e in rows:
        start = date.fromisoformat(e["date"])
        lines += ["BEGIN:VEVENT", f"UID:{_uid(e)}", f"DTSTAMP:{stamp}"]
        if e.get("time"):
            t = datetime.combine(start, datetime.strptime(e["time"], "%H:%M").time(), UTC)
            end = t + timedelta(minutes=int(e.get("minutes") or 60))
            lines += [f"DTSTART:{t:%Y%m%dT%H%M%SZ}", f"DTEND:{end:%Y%m%dT%H%M%SZ}"]
        else:
            last = date.fromisoformat(e.get("end") or e["date"])
            lines += [
                f"DTSTART;VALUE=DATE:{start:%Y%m%d}",
                f"DTEND;VALUE=DATE:{last + timedelta(days=1):%Y%m%d}",
                "TRANSP:TRANSPARENT",
            ]
        lines.append(f"SUMMARY:{_escape(e['title'])}")
        desc = _description(e)
        if desc:
            lines.append(f"DESCRIPTION:{_escape(desc)}")
        if e.get("category"):
            lines.append(f"CATEGORIES:{_escape(e['category'])}")
        if e.get("links"):
            lines.append(f"URL:{e['links'][0]['url']}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(f for line in lines for f in _fold(line)) + "\r\n"


def write(root: Path, feed_dir: Path | None = None) -> list[Path]:
    """calendar.md with what's coming, the feed with every event ever added."""
    rows = load(root)
    md = root / "ticker" / "calendar.md"
    md.write_text(markdown(upcoming(rows)))
    out = [md]
    if feed_dir is not None:
        feed_dir.mkdir(parents=True, exist_ok=True)
        feed = feed_dir / FEED
        feed.write_text(ics(rows), newline="")
        out.append(feed)
    return out
