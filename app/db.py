import hashlib
import hmac
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from decouple import config

DB_PATH = Path(config("db_path", cast=str, default="data/secret_friend.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    admin_token TEXT UNIQUE NOT NULL,
    share_token TEXT UNIQUE,
    title TEXT NOT NULL,
    budget TEXT NOT NULL DEFAULT '',
    event_date TEXT NOT NULL DEFAULT '',
    event_time TEXT NOT NULL DEFAULT '',
    message TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    closed_at TEXT
);
CREATE TABLE IF NOT EXISTS participants (
    id INTEGER PRIMARY KEY,
    event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    token TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    email TEXT NOT NULL DEFAULT '',
    group_name TEXT NOT NULL DEFAULT '',
    is_manager INTEGER NOT NULL DEFAULT 0,
    target_id INTEGER REFERENCES participants(id),
    viewed_at TEXT,
    emailed_at TEXT,
    pin_hash TEXT,
    claimed_at TEXT,
    failed_pins INTEGER NOT NULL DEFAULT 0
);
"""

MIGRATIONS = {
    "events": {"share_token": "TEXT", "event_time": "TEXT NOT NULL DEFAULT ''", "closed_at": "TEXT"},
    "participants": {
        "pin_hash": "TEXT",
        "claimed_at": "TEXT",
        "failed_pins": "INTEGER NOT NULL DEFAULT 0",
        "is_manager": "INTEGER NOT NULL DEFAULT 0",
    },
}
MAX_PIN_ATTEMPTS = 5


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_token(nbytes: int = 12) -> str:
    return secrets.token_urlsafe(nbytes)


def init() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.executescript(SCHEMA)
        for table, columns in MIGRATIONS.items():
            existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
            for column, decl in columns.items():
                if column not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
        for event in conn.execute("SELECT id FROM events WHERE share_token IS NULL").fetchall():
            conn.execute("UPDATE events SET share_token = ? WHERE id = ?", (new_token(6), event["id"]))


def hash_pin(pin: str) -> str:
    salt = secrets.token_hex(8)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt.encode(), 100_000).hex()
    return f"{salt}${digest}"


def check_pin(pin: str, stored: str) -> bool:
    salt, digest = stored.split("$", 1)
    candidate = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt.encode(), 100_000).hex()
    return hmac.compare_digest(candidate, digest)


@contextmanager
def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def create_event(title, budget, event_date, event_time, message, people, pairs) -> str:
    """people: list of dicts (name, email, group, manager). pairs: {giver_index: receiver_index}."""
    admin_token = new_token(18)
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO events (admin_token, share_token, title, budget, event_date, event_time, message, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (admin_token, new_token(6), title, budget, event_date, event_time, message, now()),
        )
        event_id = cur.lastrowid
        row_ids = []
        for p in people:
            cur = conn.execute(
                "INSERT INTO participants (event_id, token, name, email, group_name, is_manager)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (event_id, new_token(), p["name"], p["email"], p["group"], int(p["manager"])),
            )
            row_ids.append(cur.lastrowid)
        for giver, receiver in pairs.items():
            conn.execute(
                "UPDATE participants SET target_id = ? WHERE id = ?",
                (row_ids[receiver], row_ids[giver]),
            )
    return admin_token


def get_event_by_admin(admin_token: str):
    with connect() as conn:
        event = conn.execute(
            "SELECT * FROM events WHERE admin_token = ?", (admin_token,)
        ).fetchone()
        if not event:
            return None, []
        people = conn.execute(
            "SELECT * FROM participants WHERE event_id = ? ORDER BY name COLLATE NOCASE",
            (event["id"],),
        ).fetchall()
    return event, people


def list_events():
    with connect() as conn:
        return conn.execute(
            """SELECT e.*,
                      COUNT(p.id) AS people,
                      COUNT(p.viewed_at) AS viewed,
                      GROUP_CONCAT(CASE WHEN p.is_manager THEN p.name END, ', ') AS managers
               FROM events e LEFT JOIN participants p ON p.event_id = e.id
               GROUP BY e.id ORDER BY e.created_at DESC"""
        ).fetchall()


def get_event_by_share(share_token: str):
    with connect() as conn:
        event = conn.execute(
            "SELECT * FROM events WHERE share_token = ?", (share_token,)
        ).fetchone()
        if not event:
            return None, []
        people = conn.execute(
            "SELECT * FROM participants WHERE event_id = ? ORDER BY name COLLATE NOCASE",
            (event["id"],),
        ).fetchall()
    return event, people


def claim(participant_id: int, pin: str) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE participants SET pin_hash = ?, claimed_at = ?, failed_pins = 0"
            " WHERE id = ? AND claimed_at IS NULL",
            (hash_pin(pin), now(), participant_id),
        )


def record_pin_attempt(participant_id: int, ok: bool) -> None:
    with connect() as conn:
        if ok:
            conn.execute("UPDATE participants SET failed_pins = 0 WHERE id = ?", (participant_id,))
        else:
            conn.execute(
                "UPDATE participants SET failed_pins = failed_pins + 1 WHERE id = ?",
                (participant_id,),
            )


def release(event_id: int, participant_id: int) -> None:
    """Free a name. The token is rotated so whoever had the old link (claimed or emailed) loses access."""
    with connect() as conn:
        conn.execute(
            "UPDATE participants SET pin_hash = NULL, claimed_at = NULL, emailed_at = NULL,"
            " failed_pins = 0, token = ?"
            " WHERE id = ? AND event_id = ?",
            (new_token(), participant_id, event_id),
        )


def get_participant(token: str):
    """Returns (participant, event, target) or (None, None, None)."""
    with connect() as conn:
        me = conn.execute("SELECT * FROM participants WHERE token = ?", (token,)).fetchone()
        if not me:
            return None, None, None
        event = conn.execute("SELECT * FROM events WHERE id = ?", (me["event_id"],)).fetchone()
        target = conn.execute(
            "SELECT * FROM participants WHERE id = ?", (me["target_id"],)
        ).fetchone()
    return me, event, target


def mark_viewed(participant_id: int) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE participants SET viewed_at = ? WHERE id = ? AND viewed_at IS NULL",
            (now(), participant_id),
        )


def mark_emailed(participant_id: int) -> None:
    with connect() as conn:
        conn.execute("UPDATE participants SET emailed_at = ? WHERE id = ?", (now(), participant_id))


def redraw(event_id: int, pairs: dict[int, int]) -> None:
    with connect() as conn:
        for giver, receiver in pairs.items():
            conn.execute(
                "UPDATE participants SET target_id = ? WHERE id = ? AND event_id = ?",
                (receiver, giver, event_id),
            )


def set_closed(event_id: int, closed: bool) -> None:
    with connect() as conn:
        conn.execute("UPDATE events SET closed_at = ? WHERE id = ?", (now() if closed else None, event_id))


def delete_event(event_id: int) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
