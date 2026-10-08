"""SQLite storage: settings, topic queue, productions, publish schedule, channel profiles."""
import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

from . import config

DB_PATH = config.DATA / "ytauto.db"
_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS shorts_queue (
  id INTEGER PRIMARY KEY AUTOINCREMENT, topic TEXT NOT NULL, position REAL NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued', job_id INTEGER, note TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS productions (
  id INTEGER PRIMARY KEY AUTOINCREMENT, topic TEXT, format TEXT, status TEXT NOT NULL,
  title TEXT, description TEXT, tags TEXT, script TEXT, video_path TEXT, thumb_path TEXT,
  duration REAL, credit TEXT, made_for_kids INTEGER DEFAULT 0, error TEXT, source TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS publish_schedule (
  id INTEGER PRIMARY KEY AUTOINCREMENT, production_id INTEGER NOT NULL, publish_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'scheduled', youtube_id TEXT, error TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, payload TEXT, status TEXT NOT NULL DEFAULT 'pending',
  result TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS channel_profiles (
  channel_id TEXT PRIMARY KEY, title TEXT, profile TEXT, active INTEGER DEFAULT 0, created_at TEXT NOT NULL);
"""

DEFAULT_SETTINGS = {
    "approval_required": "true",
    "cartoon_target_seconds": "50",
    "made_for_kids": "false",
    "cartoon_style_notes": "",
    "cartoon_format": "story",
    "story_series": json.dumps({"niche": "scary", "style": "creepy_comic", "captions": "bold_stroke",
                                "narrator": "john", "language": "en"}),
    "automation_paused": "false",
}


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def utc_iso(value):
    """Parse a stored timestamp as UTC (SQLite strings have no zone; never treat them as local time)."""
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@contextmanager
def connect():
    with _lock:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


def init():
    with connect() as c:
        c.executescript(SCHEMA)
        for k, v in DEFAULT_SETTINGS.items():
            c.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (k, v))


# settings
def get_setting(key, default=None):
    with connect() as c:
        row = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key, value):
    if not isinstance(value, str):
        value = json.dumps(value)
    with connect() as c:
        c.execute("INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                  (key, value))


def get_json_setting(key, default=None):
    raw = get_setting(key)
    try:
        return json.loads(raw) if raw else default
    except json.JSONDecodeError:
        return default


# topic queue
def list_queue(include_done=False):
    q = "SELECT * FROM shorts_queue"
    if not include_done:
        q += " WHERE status IN ('queued','started')"
    with connect() as c:
        return [dict(r) for r in c.execute(q + " ORDER BY position, id")]


def add_queue_item(topic, note=None):
    now = utc_now()
    with connect() as c:
        pos = c.execute("SELECT COALESCE(MAX(position), 0) + 1 FROM shorts_queue").fetchone()[0]
        cur = c.execute("INSERT INTO shorts_queue(topic, position, note, created_at, updated_at) VALUES (?,?,?,?,?)",
                        (topic.strip(), pos, note, now, now))
        return cur.lastrowid


def update_queue_item(item_id, **fields):
    fields["updated_at"] = utc_now()
    cols = ", ".join(f"{k}=?" for k in fields)
    with connect() as c:
        c.execute(f"UPDATE shorts_queue SET {cols} WHERE id=?", (*fields.values(), item_id))


def move_queue_item_to_top(item_id):
    with connect() as c:
        low = c.execute("SELECT COALESCE(MIN(position), 1) FROM shorts_queue WHERE status='queued'").fetchone()[0]
        c.execute("UPDATE shorts_queue SET position=?, updated_at=? WHERE id=?", (low - 1, utc_now(), item_id))


def next_queue_item():
    with connect() as c:
        row = c.execute("SELECT * FROM shorts_queue WHERE status='queued' ORDER BY position, id LIMIT 1").fetchone()
    return dict(row) if row else None


# productions
def create_production(**fields):
    now = utc_now()
    fields.setdefault("status", "rendering")
    fields.update(created_at=now, updated_at=now)
    cols = ", ".join(fields)
    with connect() as c:
        cur = c.execute(f"INSERT INTO productions({cols}) VALUES ({', '.join('?' * len(fields))})",
                        tuple(fields.values()))
        return cur.lastrowid


def update_production(pid, **fields):
    for k in ("script", "tags"):
        if k in fields and not isinstance(fields[k], str):
            fields[k] = json.dumps(fields[k])
    fields["updated_at"] = utc_now()
    cols = ", ".join(f"{k}=?" for k in fields)
    with connect() as c:
        c.execute(f"UPDATE productions SET {cols} WHERE id=?", (*fields.values(), pid))


def _decode(row):
    d = dict(row)
    for k in ("script", "tags"):
        if d.get(k):
            try:
                d[k] = json.loads(d[k])
            except json.JSONDecodeError:
                pass
    return d


def get_production(pid):
    with connect() as c:
        row = c.execute("SELECT * FROM productions WHERE id=?", (pid,)).fetchone()
    return _decode(row) if row else None


def list_library(limit=200):
    """Productions joined with their latest publish_schedule row."""
    q = """SELECT p.*, s.publish_at, s.status AS publish_status, s.youtube_id, s.error AS publish_error
           FROM productions p
           LEFT JOIN publish_schedule s ON s.id = (SELECT MAX(id) FROM publish_schedule WHERE production_id=p.id)
           ORDER BY p.id DESC LIMIT ?"""
    with connect() as c:
        return [_decode(r) for r in c.execute(q, (limit,))]


def recent_titles(n=25):
    with connect() as c:
        return [r[0] for r in c.execute(
            "SELECT title FROM productions WHERE title IS NOT NULL ORDER BY id DESC LIMIT ?", (n,))]


def pending_review_count():
    with connect() as c:
        return c.execute("SELECT COUNT(*) FROM productions WHERE status IN ('needs_review','needs_attention')"
                         ).fetchone()[0]


# publish schedule
def schedule_publish(pid, publish_at):
    now = utc_now()
    with connect() as c:
        c.execute("INSERT INTO publish_schedule(production_id, publish_at, created_at, updated_at) VALUES (?,?,?,?)",
                  (pid, publish_at, now, now))
        c.execute("UPDATE productions SET status='scheduled', updated_at=? WHERE id=?", (now, pid))


def scheduled_slots():
    with connect() as c:
        return [r[0] for r in c.execute("SELECT publish_at FROM publish_schedule WHERE status='scheduled'")]


def due_publications(now_iso):
    with connect() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM publish_schedule WHERE status='scheduled' AND publish_at <= ? ORDER BY publish_at",
            (now_iso,))]


def update_publication(sid, **fields):
    fields["updated_at"] = utc_now()
    cols = ", ".join(f"{k}=?" for k in fields)
    with connect() as c:
        c.execute(f"UPDATE publish_schedule SET {cols} WHERE id=?", (*fields.values(), sid))


def cancel_schedule(pid):
    with connect() as c:
        c.execute("UPDATE publish_schedule SET status='cancelled', updated_at=? WHERE production_id=? "
                  "AND status='scheduled'", (utc_now(), pid))
        c.execute("UPDATE productions SET status='needs_review', updated_at=? WHERE id=?", (utc_now(), pid))


# channel profiles
def save_profile(channel_id, title, profile, activate=True):
    with connect() as c:
        if activate:
            c.execute("UPDATE channel_profiles SET active=0")
        c.execute("INSERT INTO channel_profiles(channel_id, title, profile, active, created_at) VALUES (?,?,?,?,?) "
                  "ON CONFLICT(channel_id) DO UPDATE SET title=excluded.title, profile=excluded.profile, "
                  "active=excluded.active", (channel_id, title, json.dumps(profile), int(activate), utc_now()))


def active_profile():
    with connect() as c:
        row = c.execute("SELECT * FROM channel_profiles WHERE active=1").fetchone()
    if not row:
        return None
    d = dict(row)
    d["profile"] = json.loads(d["profile"])
    return d


def list_profiles():
    with connect() as c:
        return [dict(r) for r in c.execute("SELECT channel_id, title, active, created_at FROM channel_profiles")]


def deactivate_profiles():
    with connect() as c:
        c.execute("UPDATE channel_profiles SET active=0")


def reset_content():
    """Clear content tables (keeps settings and channel profiles)."""
    with connect() as c:
        for t in ("productions", "publish_schedule", "shorts_queue"):
            c.execute(f"DELETE FROM {t}")


# dashboard -> worker jobs
def enqueue_job(kind, payload=None):
    now = utc_now()
    with connect() as c:
        return c.execute("INSERT INTO jobs(kind, payload, created_at, updated_at) VALUES (?,?,?,?)",
                         (kind, json.dumps(payload or {}), now, now)).lastrowid


def claim_job():
    with connect() as c:
        row = c.execute("SELECT * FROM jobs WHERE status='pending' ORDER BY id LIMIT 1").fetchone()
        if not row:
            return None
        c.execute("UPDATE jobs SET status='running', updated_at=? WHERE id=?", (utc_now(), row["id"]))
    d = dict(row)
    d["payload"] = json.loads(d["payload"] or "{}")
    return d


def finish_job(job_id, status, result=""):
    with connect() as c:
        c.execute("UPDATE jobs SET status=?, result=?, updated_at=? WHERE id=?",
                  (status, str(result)[:2000], utc_now(), job_id))


def list_jobs(limit=15):
    with connect() as c:
        return [dict(r) for r in c.execute("SELECT * FROM jobs ORDER BY id DESC LIMIT ?", (limit,))]
