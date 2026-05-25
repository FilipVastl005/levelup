# LevelUp — SQLite Backend

PocketBase has been replaced with a direct SQLite database. No more
admin credential mismatches, no more volume mount bugs, and the queue
worker can write XP directly without a separate HTTP auth step.

## What changed

| Before | After |
|---|---|
| PocketBase container | Gone |
| `services/pocketbase.py` | Replaced by `services/db.py` |
| `.env` needs PB credentials | Only `ADMIN_PASSWORD` needed |
| XP write via PB admin token | Direct SQLite write in queue worker |
| DB at `/mnt/storage/pocketbase/pb_data/data.db` | DB at `/mnt/storage/levelup.db` |

## First deploy

```bash
# 1. Copy env file
cp .env.example .env
# Edit .env — set SECRET_KEY and ADMIN_PASSWORD

# 2. Create queue directories (if they don't exist)
mkdir -p /mnt/storage/queue/{pending,processing,completed,failed,screenshots}

# 3. Build and start (no pocketbase container anymore)
docker compose up -d --build

# 4. Check logs
docker logs levelup_app -f
```

The database (`/mnt/storage/levelup.db`) is created automatically on first startup.

## Migrating existing PocketBase data

If you have users and logs in your old PocketBase instance, run the migration
script BEFORE starting the new stack:

```bash
# On the server, outside Docker
python3 migrate_from_pocketbase.py \
  --pb /mnt/storage/pocketbase/pb_data/data.db \
  --new /mnt/storage/levelup.db
```

> **Note:** PocketBase uses bcrypt for passwords. The migration script cannot
> transfer them. Migrated users will have a placeholder password hash and will
> need their passwords reset. For a fresh start, just skip the migration and
> have users re-register.

## Admin panel

Visit `/admin` (no link on the main site). Enter the `ADMIN_PASSWORD` from `.env`.
Shows: server stats, active queue, failed jobs (with retry), feedback inbox.

## Reading the database directly

```bash
sqlite3 /mnt/storage/levelup.db
.tables
SELECT username, total_xp, total_level FROM users ORDER BY total_xp DESC;
SELECT * FROM queue WHERE status='failed';
.quit
```

## Fixes in this version

- **Queue worker XP write**: Works now. No admin token needed — it writes
  directly to SQLite.
- **Ollama JSON parsing**: Three-strategy extractor (full parse → regex block →
  field-by-field). Much more robust.
- **Thermal note**: CPU cap still needs to be applied after each reboot:
  ```bash
  echo 2400000 | tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_max_freq
  ```
  Add to `/etc/rc.local` to make it permanent.
