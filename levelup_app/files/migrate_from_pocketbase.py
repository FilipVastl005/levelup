#!/usr/bin/env python3
"""
migrate_from_pocketbase.py
===========================
One-time migration script: reads your old PocketBase SQLite file
(pb_data/data.db) and imports users + logs into the new levelup.db.

Usage (on the server, outside Docker):
  python3 migrate_from_pocketbase.py \
    --pb /mnt/storage/pocketbase/pb_data/data.db \
    --new /mnt/storage/levelup.db

Run BEFORE starting the new stack. Safe to run multiple times
(uses INSERT OR IGNORE so it won't duplicate).
"""

import argparse
import sqlite3
import secrets
import hashlib
from datetime import datetime


def new_id():
    return secrets.token_hex(7)


def now():
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def connect(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def migrate(pb_path: str, new_path: str):
    pb = connect(pb_path)
    new = connect(new_path)
    new.execute("PRAGMA foreign_keys=OFF")

    # ── USERS ──────────────────────────────────────────────────
    print("Migrating users...")
    pb_users = pb.execute("SELECT * FROM users").fetchall()
    migrated_users = 0
    user_id_map = {}  # pb_id → new_id (they should be the same, but just in case)

    for u in pb_users:
        uid = u["id"]
        user_id_map[uid] = uid
        try:
            new.execute("""
                INSERT OR IGNORE INTO users (
                    id, username, email, password_hash,
                    total_xp, physical_xp, sharpness_xp, wellbeing_xp,
                    physical_level, sharpness_level, wellbeing_level, total_level,
                    current_streak, last_log_date,
                    physical_baseline, sharpness_baseline, wellbeing_baseline,
                    onboarding_done, theme, created, updated
                ) VALUES (?,?,?,?, ?,?,?,?, ?,?,?,?, ?,?, ?,?,?, ?,?,?,?)
            """, (
                uid,
                u["username"],
                u["email"],
                # PocketBase stores bcrypt — we can't verify it in our system.
                # Set a placeholder; user will need to reset password OR
                # you can set a temp password here.
                "MIGRATED:set_new_password",
                u.get("total_xp", 0),
                u.get("physical_xp", 0),
                u.get("sharpness_xp", 0),
                u.get("wellbeing_xp", 0),
                u.get("physical_level", 1),
                u.get("sharpness_level", 1),
                u.get("wellbeing_level", 1),
                u.get("total_level", 1),
                u.get("current_streak", 0),
                u.get("last_log_date", ""),
                u.get("physical_baseline", 5),
                u.get("sharpness_baseline", 5),
                u.get("wellbeing_baseline", 5),
                1 if u.get("onboarding_done") else 0,
                u.get("theme", "light"),
                u.get("created", now()),
                u.get("updated", now()),
            ))
            migrated_users += 1
        except Exception as e:
            print(f"  Skipped user {uid}: {e}")

    print(f"  Migrated {migrated_users}/{len(pb_users)} users")

    # ── LOGS ───────────────────────────────────────────────────
    print("Migrating logs...")
    try:
        pb_logs = pb.execute("SELECT * FROM logs").fetchall()
    except Exception:
        pb_logs = []

    migrated_logs = 0
    for log in pb_logs:
        try:
            new.execute("""
                INSERT OR IGNORE INTO logs (
                    id, user_id, category, description,
                    screenshot, xp_awarded, ai_response, verified, created
                ) VALUES (?,?,?,?, ?,?,?,?,?)
            """, (
                log["id"],
                log["user_id"],
                log["category"],
                log["description"],
                log.get("screenshot", ""),
                log.get("xp_awarded", 0),
                log.get("ai_response", ""),
                1 if log.get("verified") else 0,
                log.get("created", now()),
            ))
            migrated_logs += 1
        except Exception as e:
            print(f"  Skipped log {log['id']}: {e}")

    print(f"  Migrated {migrated_logs}/{len(pb_logs)} logs")

    # ── FRIENDS ────────────────────────────────────────────────
    print("Migrating friends...")
    try:
        pb_friends = pb.execute("SELECT * FROM friends").fetchall()
    except Exception:
        pb_friends = []

    for f in pb_friends:
        try:
            new.execute("""
                INSERT OR IGNORE INTO friends (id, user_id, friend_id, status, created)
                VALUES (?,?,?,?,?)
            """, (f["id"], f["user_id"], f["friend_id"],
                  f.get("status", "accepted"), f.get("created", now())))
        except Exception:
            pass

    print(f"  Migrated {len(pb_friends)} friend records")

    new.commit()
    pb.close()
    new.close()
    print("\nMigration complete!")
    print("NOTE: Migrated users have password_hash='MIGRATED:set_new_password'.")
    print("They will need to be manually reset, or use the admin panel to set passwords.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pb", required=True, help="Path to PocketBase data.db")
    parser.add_argument("--new", required=True, help="Path to new levelup.db")
    args = parser.parse_args()
    migrate(args.pb, args.new)
