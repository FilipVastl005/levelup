"""
services/db.py — SQLite database layer for LevelUp
Replaces PocketBase entirely. All data lives in /mnt/storage/levelup.db
"""

import sqlite3
import os
import hashlib
import secrets
from contextlib import contextmanager
from datetime import datetime, timedelta

DB_PATH = os.getenv("DB_PATH", "/mnt/storage/levelup.db")


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def row_to_dict(row):
    if row is None:
        return None
    return dict(row)


def rows_to_list(rows):
    return [dict(r) for r in rows]


# ─────────────────────────────────────────────
# INIT
# ─────────────────────────────────────────────

def init_db():
    """Create all tables if they don't exist. Safe to call on every startup."""
    with get_db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id              TEXT PRIMARY KEY,
            username        TEXT NOT NULL UNIQUE,
            email           TEXT NOT NULL UNIQUE,
            password_hash   TEXT NOT NULL,
            total_xp        INTEGER DEFAULT 0,
            physical_xp     INTEGER DEFAULT 0,
            sharpness_xp    INTEGER DEFAULT 0,
            wellbeing_xp    INTEGER DEFAULT 0,
            physical_level  INTEGER DEFAULT 1,
            sharpness_level INTEGER DEFAULT 1,
            wellbeing_level INTEGER DEFAULT 1,
            total_level     INTEGER DEFAULT 1,
            current_streak  INTEGER DEFAULT 0,
            last_log_date   TEXT DEFAULT '',
            physical_baseline   INTEGER DEFAULT 5,
            sharpness_baseline  INTEGER DEFAULT 5,
            wellbeing_baseline  INTEGER DEFAULT 5,
            onboarding_done INTEGER DEFAULT 0,
            theme           TEXT DEFAULT 'light',
            created         TEXT NOT NULL,
            updated         TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sessions (
            token       TEXT PRIMARY KEY,
            user_id     TEXT NOT NULL,
            expires_at  TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS logs (
            id          TEXT PRIMARY KEY,
            user_id     TEXT NOT NULL,
            category    TEXT NOT NULL,
            description TEXT NOT NULL,
            screenshot  TEXT DEFAULT '',
            xp_awarded  INTEGER DEFAULT 0,
            ai_response TEXT DEFAULT '',
            verified    INTEGER DEFAULT 0,
            created     TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS queue (
            id          TEXT PRIMARY KEY,
            job_id      TEXT NOT NULL,
            user_id     TEXT NOT NULL,
            category    TEXT NOT NULL,
            description TEXT NOT NULL,
            status      TEXT DEFAULT 'pending',
            xp_awarded  INTEGER DEFAULT 0,
            ai_response TEXT DEFAULT '',
            verified    INTEGER DEFAULT 0,
            created     TEXT NOT NULL,
            updated     TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS friends (
            id          TEXT PRIMARY KEY,
            user_id     TEXT NOT NULL,
            friend_id   TEXT NOT NULL,
            status      TEXT DEFAULT 'pending',
            created     TEXT NOT NULL,
            FOREIGN KEY (user_id)   REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (friend_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS groups_tbl (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            created_by  TEXT NOT NULL,
            member_ids  TEXT DEFAULT '[]',
            created     TEXT NOT NULL,
            FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS feedback (
            id          TEXT PRIMARY KEY,
            user_id     TEXT NOT NULL,
            queue_id    TEXT NOT NULL,
            message     TEXT NOT NULL,
            reviewed    INTEGER DEFAULT 0,
            created     TEXT NOT NULL,
            FOREIGN KEY (user_id)  REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (queue_id) REFERENCES queue(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_sessions_user    ON sessions(user_id);
        CREATE INDEX IF NOT EXISTS idx_logs_user        ON logs(user_id);
        CREATE INDEX IF NOT EXISTS idx_logs_created     ON logs(created);
        CREATE INDEX IF NOT EXISTS idx_queue_user       ON queue(user_id);
        CREATE INDEX IF NOT EXISTS idx_queue_status     ON queue(status);
        CREATE INDEX IF NOT EXISTS idx_friends_user     ON friends(user_id);
        CREATE INDEX IF NOT EXISTS idx_friends_friend   ON friends(friend_id);
        """)


def _new_id():
    return secrets.token_hex(7)  # 14-char hex, similar to PocketBase IDs


def _now():
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


# ─────────────────────────────────────────────
# AUTH
# ─────────────────────────────────────────────

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    h = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}:{h}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, h = stored.split(":", 1)
        return hashlib.sha256((salt + password).encode()).hexdigest() == h
    except Exception:
        return False


def create_user(username: str, email: str, password: str) -> dict | None:
    uid = _new_id()
    now = _now()
    try:
        with get_db() as conn:
            conn.execute(
                """INSERT INTO users (id, username, email, password_hash, created, updated)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (uid, username, email.lower(), hash_password(password), now, now)
            )
        return get_user_by_id(uid)
    except sqlite3.IntegrityError:
        return None


def get_user_by_email(email: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email.lower(),)
        ).fetchone()
    return row_to_dict(row)


def get_user_by_id(user_id: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return row_to_dict(row)


def get_user_by_username(username: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE lower(username) = lower(?)", (username,)
        ).fetchone()
    return row_to_dict(row)


def authenticate_user(email: str, password: str) -> dict | None:
    user = get_user_by_email(email)
    if user and verify_password(password, user["password_hash"]):
        return user
    return None


def create_session(user_id: str) -> str:
    token = secrets.token_hex(32)
    expires = (datetime.utcnow() + timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    with get_db() as conn:
        conn.execute(
            "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
            (token, user_id, expires)
        )
    return token


def get_session_user(token: str) -> dict | None:
    now = _now()
    with get_db() as conn:
        row = conn.execute(
            """SELECT u.* FROM users u
               JOIN sessions s ON s.user_id = u.id
               WHERE s.token = ? AND s.expires_at > ?""",
            (token, now)
        ).fetchone()
    return row_to_dict(row)


def delete_session(token: str):
    with get_db() as conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))


# ─────────────────────────────────────────────
# USER UPDATES
# ─────────────────────────────────────────────

def update_user_xp(user_id: str, physical_xp: int, sharpness_xp: int,
                   wellbeing_xp: int, total_xp: int,
                   physical_level: int, sharpness_level: int,
                   wellbeing_level: int, total_level: int,
                   current_streak: int, last_log_date: str):
    with get_db() as conn:
        conn.execute(
            """UPDATE users SET
               physical_xp=?, sharpness_xp=?, wellbeing_xp=?, total_xp=?,
               physical_level=?, sharpness_level=?, wellbeing_level=?, total_level=?,
               current_streak=?, last_log_date=?, updated=?
               WHERE id=?""",
            (physical_xp, sharpness_xp, wellbeing_xp, total_xp,
             physical_level, sharpness_level, wellbeing_level, total_level,
             current_streak, last_log_date, _now(), user_id)
        )


def update_user_theme(user_id: str, theme: str):
    with get_db() as conn:
        conn.execute(
            "UPDATE users SET theme=?, updated=? WHERE id=?",
            (theme, _now(), user_id)
        )


# ─────────────────────────────────────────────
# LOGS
# ─────────────────────────────────────────────

def create_log(user_id: str, category: str, description: str,
               screenshot: str = "", xp_awarded: int = 0,
               ai_response: str = "", verified: bool = False) -> dict:
    lid = _new_id()
    now = _now()
    with get_db() as conn:
        conn.execute(
            """INSERT INTO logs (id, user_id, category, description, screenshot,
               xp_awarded, ai_response, verified, created)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (lid, user_id, category, description, screenshot,
             xp_awarded, ai_response, 1 if verified else 0, now)
        )
    return {"id": lid, "user_id": user_id, "category": category,
            "description": description, "xp_awarded": xp_awarded,
            "ai_response": ai_response, "verified": verified, "created": now}


def update_log_after_ai(log_id: str, xp_awarded: int, ai_response: str, verified: bool):
    with get_db() as conn:
        conn.execute(
            "UPDATE logs SET xp_awarded=?, ai_response=?, verified=? WHERE id=?",
            (xp_awarded, ai_response, 1 if verified else 0, log_id)
        )


def get_logs_for_user(user_id: str, category: str, limit: int = 20) -> list:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM logs WHERE user_id=? AND category=?
               ORDER BY created DESC LIMIT ?""",
            (user_id, category, limit)
        ).fetchall()
    return rows_to_list(rows)


def count_logs_today(user_id: str, category: str) -> int:
    today = datetime.utcnow().strftime("%Y-%m-%d")
    with get_db() as conn:
        row = conn.execute(
            """SELECT COUNT(*) as cnt FROM logs
               WHERE user_id=? AND category=? AND created LIKE ?""",
            (user_id, category, f"{today}%")
        ).fetchone()
    return row["cnt"] if row else 0


# ─────────────────────────────────────────────
# QUEUE
# ─────────────────────────────────────────────

def create_queue_entry(job_id: str, user_id: str, category: str, description: str) -> dict:
    qid = _new_id()
    now = _now()
    with get_db() as conn:
        conn.execute(
            """INSERT INTO queue (id, job_id, user_id, category, description, status, created, updated)
               VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)""",
            (qid, job_id, user_id, category, description, now, now)
        )
    return {"id": qid, "job_id": job_id, "user_id": user_id, "category": category,
            "description": description, "status": "pending", "created": now}


def update_queue_status(queue_id: str, status: str, xp_awarded: int = 0,
                        ai_response: str = "", verified: bool = False):
    with get_db() as conn:
        conn.execute(
            """UPDATE queue SET status=?, xp_awarded=?, ai_response=?, verified=?, updated=?
               WHERE id=?""",
            (status, xp_awarded, ai_response, 1 if verified else 0, _now(), queue_id)
        )


def update_queue_status_by_job(job_id: str, status: str, xp_awarded: int = 0,
                               ai_response: str = "", verified: bool = False):
    with get_db() as conn:
        conn.execute(
            """UPDATE queue SET status=?, xp_awarded=?, ai_response=?, verified=?, updated=?
               WHERE job_id=?""",
            (status, xp_awarded, ai_response, 1 if verified else 0, _now(), job_id)
        )


def get_queue_for_user(user_id: str) -> list:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM queue WHERE user_id=? ORDER BY created DESC LIMIT 50",
            (user_id,)
        ).fetchall()
    return rows_to_list(rows)


def get_active_jobs() -> list:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT q.*, u.username FROM queue q JOIN users u ON q.user_id=u.id WHERE q.status IN ('pending','processing') ORDER BY q.created ASC"
        ).fetchall()
    return rows_to_list(rows)


def get_failed_jobs() -> list:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM queue WHERE status='failed' ORDER BY updated DESC LIMIT 50"
        ).fetchall()
    return rows_to_list(rows)


def retry_job(queue_id: str):
    with get_db() as conn:
        conn.execute(
            "UPDATE queue SET status='pending', updated=? WHERE id=?",
            (_now(), queue_id)
        )


# ─────────────────────────────────────────────
# LEADERBOARD
# ─────────────────────────────────────────────

def get_leaderboard(limit: int = 100) -> list:
    # Wellbeing excluded from leaderboard per spec
    with get_db() as conn:
        rows = conn.execute(
            """SELECT id, username, total_level,
               (physical_xp + sharpness_xp) AS total_xp
               FROM users
               ORDER BY (physical_xp + sharpness_xp) DESC
               LIMIT ?""",
            (limit,)
        ).fetchall()
    return rows_to_list(rows)


# ─────────────────────────────────────────────
# FRIENDS
# ─────────────────────────────────────────────

def add_friend(user_id: str, friend_id: str) -> dict | None:
    # Prevent duplicates
    with get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM friends WHERE user_id=? AND friend_id=?",
            (user_id, friend_id)
        ).fetchone()
        if existing:
            return None
        fid = _new_id()
        now = _now()
        conn.execute(
            "INSERT INTO friends (id, user_id, friend_id, status, created) VALUES (?,?,?,'accepted',?)",
            (fid, user_id, friend_id, now)
        )
    return {"id": fid, "user_id": user_id, "friend_id": friend_id}


def get_friends(user_id: str) -> list:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT u.id, u.username, u.total_level as level
               FROM friends f
               JOIN users u ON u.id = f.friend_id
               WHERE f.user_id=? AND f.status='accepted'""",
            (user_id,)
        ).fetchall()
    return rows_to_list(rows)


# ─────────────────────────────────────────────
# GROUPS
# ─────────────────────────────────────────────

def create_group(name: str, created_by: str, member_ids: list) -> dict:
    import json
    gid = _new_id()
    now = _now()
    with get_db() as conn:
        conn.execute(
            "INSERT INTO groups_tbl (id, name, created_by, member_ids, created) VALUES (?,?,?,?,?)",
            (gid, name, created_by, json.dumps(member_ids), now)
        )
    return {"id": gid, "name": name}


def get_groups_for_user(user_id: str) -> list:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM groups_tbl WHERE created_by=? OR member_ids LIKE ?",
            (user_id, f'%"{user_id}"%')
        ).fetchall()
    return rows_to_list(rows)


# ─────────────────────────────────────────────
# FEEDBACK
# ─────────────────────────────────────────────

def create_feedback(user_id: str, queue_id: str, message: str) -> dict:
    fid = _new_id()
    now = _now()
    with get_db() as conn:
        conn.execute(
            "INSERT INTO feedback (id, user_id, queue_id, message, reviewed, created) VALUES (?,?,?,?,0,?)",
            (fid, user_id, queue_id, message, now)
        )
    return {"id": fid}


def get_feedback_inbox() -> list:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT f.id, f.message, f.reviewed, f.created,
               u.username, q.description as log_description
               FROM feedback f
               JOIN users u ON u.id = f.user_id
               JOIN queue q ON q.id = f.queue_id
               WHERE f.reviewed=0
               ORDER BY f.created DESC""",
        ).fetchall()
    return rows_to_list(rows)


def mark_feedback_reviewed(feedback_id: str):
    with get_db() as conn:
        conn.execute("UPDATE feedback SET reviewed=1 WHERE id=?", (feedback_id,))


# ─────────────────────────────────────────────
# ADMIN STATS
# ─────────────────────────────────────────────

def get_admin_stats() -> dict:
    today = datetime.utcnow().strftime("%Y-%m-%d")
    with get_db() as conn:
        total_users = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
        total_logs = conn.execute("SELECT COUNT(*) as c FROM logs").fetchone()["c"]
        total_xp = conn.execute("SELECT COALESCE(SUM(total_xp),0) as s FROM users").fetchone()["s"]
        pending = conn.execute("SELECT COUNT(*) as c FROM queue WHERE status='pending'").fetchone()["c"]
        processing = conn.execute("SELECT COUNT(*) as c FROM queue WHERE status='processing'").fetchone()["c"]
        completed_today = conn.execute(
            "SELECT COUNT(*) as c FROM queue WHERE status='completed' AND created LIKE ?",
            (f"{today}%",)
        ).fetchone()["c"]
        failed_today = conn.execute(
            "SELECT COUNT(*) as c FROM queue WHERE status='failed' AND created LIKE ?",
            (f"{today}%",)
        ).fetchone()["c"]
        cutoff = (datetime.utcnow() - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
        active_users = rows_to_list(conn.execute(
            "SELECT username, updated, total_xp FROM users WHERE updated > ? ORDER BY updated DESC LIMIT 20",
            (cutoff,)
        ).fetchall())
    return {
        "total_users": total_users,
        "total_logs": total_logs,
        "total_xp": total_xp,
        "pending": pending,
        "processing": processing,
        "completed_today": completed_today,
        "failed_today": failed_today,
        "active_users": active_users,
    }
