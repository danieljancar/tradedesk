"""Notes and chart levels from the human. They show up in book.md, so the agents read them
before every decision. They are input to weigh, never orders."""

from tradedesk.db import Database, now

SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY,
    ts TEXT NOT NULL,
    kind TEXT NOT NULL,
    asset TEXT,
    price REAL,
    text TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);
"""
KINDS = {"note", "level", "idea"}


def ensure(db: Database) -> None:
    db.conn.executescript(SCHEMA)


def add(
    db: Database, kind: str, text: str, asset: str | None = None, price: float | None = None
) -> dict:
    ensure(db)
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {sorted(KINDS)}")
    text = text.strip()[:500]
    if not text:
        raise ValueError("text is empty")
    note_id = db.insert(
        "notes",
        ts=now(),
        kind=kind,
        asset=(asset or None) and asset.upper(),
        price=price,
        text=text,
    )
    return db.one("SELECT * FROM notes WHERE id = ?", note_id)


def active(db: Database) -> list[dict]:
    ensure(db)
    return db.all("SELECT * FROM notes WHERE active = 1 ORDER BY ts DESC LIMIT 50")


def archive(db: Database, note_id: int) -> None:
    ensure(db)
    db.update("notes", note_id, active=0)


def book_lines(db: Database) -> list[str]:
    rows = active(db)
    if not rows:
        return []
    lines = ["## Notes from the human (weigh them, they are not orders)"]
    for n in rows[:15]:
        where = f"{n['asset']} " if n["asset"] else ""
        at = f"@ {n['price']:g} " if n["price"] is not None else ""
        lines.append(f"- [{n['ts'][:16].replace('T', ' ')}] {n['kind']} {where}{at}: {n['text']}")
    return lines
