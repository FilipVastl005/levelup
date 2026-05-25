# RFID Canteen Access Control — Complete Database Documentation

> **Who this is for:** Anyone who needs to understand, extend, query, or debug this system's data layer — including AI models with limited context. Every concept is explained from first principles. No assumptions are made about prior knowledge of this codebase.

---

## Table of Contents

1. [What the database is and where it lives](#1-what-the-database-is-and-where-it-lives)
2. [How to connect to the database](#2-how-to-connect-to-the-database)
3. [The four tables — complete reference](#3-the-four-tables--complete-reference)
   - [allowed_list](#31-allowed_list)
   - [logs](#32-logs)
   - [exits](#33-exits)
   - [admin_accounts](#34-admin_accounts)
4. [How the tables relate to each other](#4-how-the-tables-relate-to-each-other)
5. [Indexes — what they are and why they exist](#5-indexes--what-they-are-and-why-they-exist)
6. [Every database operation in the codebase](#6-every-database-operation-in-the-codebase)
7. [The canteen occupancy calculation](#7-the-canteen-occupancy-calculation)
8. [Input validation rules](#8-input-validation-rules)
9. [How to write queries correctly for both databases](#9-how-to-write-queries-correctly-for-both-databases)
10. [Common tasks with exact SQL](#10-common-tasks-with-exact-sql)
11. [What can go wrong and how to fix it](#11-what-can-go-wrong-and-how-to-fix-it)

---

## 1. What the database is and where it lives

The system stores all its data in a **SQLite** database file by default, or in a **PostgreSQL** database in production.

**SQLite** means the entire database is a single file on disk. There is no separate database server process. You can open it directly with the `sqlite3` command-line tool or any SQLite browser app.

**PostgreSQL** is a full database server. It is only used when the system is deployed with Docker in production. The code switches between them automatically based on a setting in the `.env` file.

### Finding the database file (SQLite)

The file path is set by the `SQLITE_PATH` variable in the `.env` file in the project root folder.

```
# .env file
SQLITE_PATH=rfid_system.db
```

This means the file is named `rfid_system.db` and lives in the same folder as `app.py`. If you ran `setup.py`, this file was created automatically.

To open it directly from the terminal:
```bash
sqlite3 rfid_system.db
```

To see all tables once inside:
```sql
.tables
```

To see the structure of a table:
```sql
.schema allowed_list
```

### Switching to PostgreSQL (production only)

In the `.env` file, change:
```
USE_POSTGRES=true
DATABASE_URL=postgresql://rfid_user:rfid_pass@db:5432/rfid_db
```

The application code detects this at startup and uses PostgreSQL for everything. You do not need to change any other code.

---

## 2. How to connect to the database

### From within the Python application (app.py)

The application uses a helper called `get_db()`. It opens a connection, runs your code, commits the changes if everything worked, or rolls back if something went wrong, and then closes the connection. You never call `connect()` directly.

```python
# This is how every database operation in the app works:
with get_db() as conn:
    cur = conn.cursor()
    cur.execute("SELECT * FROM allowed_list WHERE isic_id = ?", ("A1B2C3",))
    row = _fetchone(cur)   # returns a dict like {"isic_id": "A1B2C3", "name": "Jana", "is_allowed": 1}
```

The `with` block means:
- If the code inside runs without errors → the changes are saved (committed)
- If any error happens → the changes are undone (rolled back)
- The connection is always closed at the end, whether it worked or not

### From the terminal (SQLite)

```bash
# Open the database
sqlite3 rfid_system.db

# Run a query
SELECT * FROM allowed_list LIMIT 5;

# Exit
.quit
```

### From a GUI tool

Download **DB Browser for SQLite** (free, available at sqlitebrowser.org). Open the `.db` file with it to browse tables and run queries with a visual interface.

---

## 3. The four tables — complete reference

The database has exactly four tables. Here is everything about each one.

---

### 3.1 `allowed_list`

**Purpose:** This is the master list of all RFID card holders. It stores who is allowed into the canteen and who is blocked. Every registered student or staff member has exactly one row here.

**How it is created:**
```sql
CREATE TABLE IF NOT EXISTS allowed_list (
    isic_id    TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    is_allowed INTEGER NOT NULL DEFAULT 1
)
```

**Columns:**

| Column | Type | Rules | Example | What it means |
|--------|------|--------|---------|----------------|
| `isic_id` | TEXT | Primary key. Must be unique. Cannot be NULL. Only letters, numbers, hyphens, underscores. Max 64 characters. | `A1B2C3` | The unique ID stored on the physical RFID card. This is what the card reader sends to the server. |
| `name` | TEXT | Cannot be NULL. Max 120 characters. Letters, spaces, hyphens, dots, apostrophes allowed. | `Jana Nováková` | The full name of the card holder, for display in the admin dashboard. |
| `is_allowed` | INTEGER | Must be exactly `1` or `0`. Default is `1`. | `1` | `1` means the person is allowed in. `0` means they are blocked. This is the access control switch. |

**What "PRIMARY KEY" means:**
`isic_id` is the primary key. This means two things:
1. Every row must have a different `isic_id`. You cannot have two rows with the same card ID.
2. The database builds an automatic index on this column, so looking up a card by ID is instant even with millions of rows.

**Example rows:**
```
isic_id   | name              | is_allowed
----------+-------------------+-----------
A1B2C3    | Jana Nováková     | 1
B2C3D4    | Jan Novák         | 0
C3D4E5    | Marie Svobodová   | 1
```

In this example, Jana and Marie can enter. Jan is blocked.

---

### 3.2 `logs`

**Purpose:** A record of every card scan at the entrance. Every time someone holds their card to the reader at the door, one row is added here. Rows are never deleted (unless an admin explicitly clears all logs).

**How it is created:**
```sql
CREATE TABLE IF NOT EXISTS logs (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,   -- SQLite
    -- OR:
    id        SERIAL PRIMARY KEY,                   -- PostgreSQL
    isic_id   TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    status    TEXT NOT NULL
)
```

**Columns:**

| Column | Type | Rules | Example | What it means |
|--------|------|--------|---------|----------------|
| `id` | INTEGER | Auto-assigned. Never set manually. Each row gets the next number. | `42` | Just a unique number so each scan event has an ID. The application uses this for ordering (newest scan = highest id). |
| `isic_id` | TEXT | Cannot be NULL. This is the card ID that was scanned. | `A1B2C3` | The ID read from the physical card. Note: this does NOT have a foreign key constraint to `allowed_list`. A scan can be recorded even if the card is not in `allowed_list` (that is how UNKNOWN status works). |
| `timestamp` | TEXT | Cannot be NULL. Format is always `YYYY-MM-DD HH:MM:SS`. | `2025-07-04 13:45:22` | The exact date and time of the scan, down to the second. Stored as text, not a date type, because SQLite does not have a native date type. |
| `status` | TEXT | Cannot be NULL. Must be one of three values: `ALLOWED`, `DENIED`, or `UNKNOWN`. | `ALLOWED` | The result of the access check at the time of the scan. See below for what each value means. |

**The three status values:**

- `ALLOWED` — The card was found in `allowed_list` and `is_allowed = 1`. The person was let in. The door opened (or a green LED lit).
- `DENIED` — The card was found in `allowed_list` but `is_allowed = 0`. The person is blocked. The door did not open.
- `UNKNOWN` — The card was NOT found in `allowed_list` at all. The card is not registered in the system.

**Example rows:**
```
id  | isic_id | timestamp           | status
----+---------+---------------------+---------
1   | A1B2C3  | 2025-07-04 08:01:05 | ALLOWED
2   | B2C3D4  | 2025-07-04 08:01:47 | DENIED
3   | ZZZZZZ  | 2025-07-04 08:02:11 | UNKNOWN
4   | A1B2C3  | 2025-07-04 12:00:33 | ALLOWED
```

**Important:** The same `isic_id` can appear many times — once for each scan. `logs` is append-only.

---

### 3.3 `exits`

**Purpose:** A record of every time someone exits the canteen. When a person holds their card to the exit reader, one row is added here. This table is how the system knows how many people are currently inside.

**How it is created:**
```sql
CREATE TABLE IF NOT EXISTS exits (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,   -- SQLite
    -- OR:
    id        SERIAL PRIMARY KEY,                   -- PostgreSQL
    isic_id   TEXT NOT NULL,
    timestamp TEXT NOT NULL
)
```

**Columns:**

| Column | Type | Rules | Example | What it means |
|--------|------|--------|---------|----------------|
| `id` | INTEGER | Auto-assigned. | `17` | Unique identifier for each exit event. |
| `isic_id` | TEXT | Cannot be NULL. | `A1B2C3` | The card that was scanned at the exit. |
| `timestamp` | TEXT | Cannot be NULL. Format: `YYYY-MM-DD HH:MM:SS`. | `2025-07-04 13:55:00` | When the person left. |

**Example rows:**
```
id  | isic_id | timestamp
----+---------+---------------------
1   | A1B2C3  | 2025-07-04 08:45:00
2   | C3D4E5  | 2025-07-04 09:10:22
3   | A1B2C3  | 2025-07-04 13:55:00
```

**Why exits is separate from logs:**
The entrance scanner and exit scanner are two different physical ESP devices. The entrance device calls `/rfid` (which writes to `logs`). The exit device calls `/unlog` (which writes to `exits`). Keeping them in separate tables makes the occupancy calculation simple: subtract exit count from entry count.

---

### 3.4 `admin_accounts`

**Purpose:** Stores the login credentials for people who can access the admin dashboard. This is completely separate from the RFID card holders in `allowed_list`. An admin account is a human staff member who manages the system through the web interface.

**How it is created:**
```sql
CREATE TABLE IF NOT EXISTS admin_accounts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,   -- SQLite
    -- OR:
    id            SERIAL PRIMARY KEY,                   -- PostgreSQL
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'operator',
    created_at    TEXT NOT NULL,
    last_login    TEXT
)
```

**Columns:**

| Column | Type | Rules | Example | What it means |
|--------|------|--------|---------|----------------|
| `id` | INTEGER | Auto-assigned. | `1` | Unique number for each account. Used in URLs like `/admin-accounts/delete/1`. |
| `username` | TEXT | Cannot be NULL. Must be unique. 3–32 characters: letters, numbers, underscores, hyphens only. | `jan.novak` | The login name. Used on the admin login page. |
| `password_hash` | TEXT | Cannot be NULL. Never stores the real password. | `pbkdf2:sha256:600000$...` | The password is hashed using Werkzeug's `generate_password_hash()` before storing. The real password is never written to the database. To check a login, `check_password_hash(stored_hash, entered_password)` is called. |
| `role` | TEXT | Cannot be NULL. Must be `operator` or `superadmin`. Default is `operator`. | `superadmin` | Controls what the admin can do. See the roles table below. |
| `created_at` | TEXT | Cannot be NULL. Format: `YYYY-MM-DD HH:MM:SS`. | `2025-07-01 09:00:00` | When this account was created. Set once and never changed. |
| `last_login` | TEXT | Can be NULL (if the account has never been used). Format: `YYYY-MM-DD HH:MM:SS`. | `2025-07-04 08:30:00` | Updated every time this account successfully logs in. NULL means the account was created but never logged into. |

**The two roles:**

| Role | What they can do |
|------|-----------------|
| `operator` | View the live scan log. Manage the card database (add, edit, delete, block/allow cards). Import cards from CSV/Excel. |
| `superadmin` | Everything an operator can do, PLUS: create and delete admin accounts, change other accounts' roles, reset other accounts' passwords, clear all logs. |

**Example rows:**
```
id | username   | password_hash       | role       | created_at          | last_login
---+------------+---------------------+------------+---------------------+--------------------
1  | admin      | pbkdf2:sha256:...   | superadmin | 2025-07-01 09:00:00 | 2025-07-04 08:30:00
2  | jan.novak  | pbkdf2:sha256:...   | operator   | 2025-07-02 10:15:00 | NULL
```

---

## 4. How the tables relate to each other

The tables are related through the `isic_id` field, but there are **no foreign key constraints** enforced by the database. This is a deliberate design choice: if a card scans and is not in `allowed_list`, we still want to record the scan (as UNKNOWN status). A foreign key would prevent that.

Here is the relationship:

```
allowed_list                  logs                    exits
─────────────                 ────────────────        ─────────────────
isic_id (PK) ◄─── (match) ── isic_id                 isic_id
name                          id                      id
is_allowed                    timestamp               timestamp
                              status
```

**The connection is logical, not enforced.** To get a scan record together with the person's name, you use a LEFT JOIN:

```sql
SELECT
    l.id,
    l.isic_id,
    l.timestamp,
    l.status,
    COALESCE(a.name, 'UNKNOWN') AS name
FROM logs l
LEFT JOIN allowed_list a ON l.isic_id = a.isic_id
ORDER BY l.id DESC
LIMIT 40;
```

`LEFT JOIN` means: include every row from `logs`, and if there is a matching row in `allowed_list`, attach the name. If there is no match (the card was UNKNOWN), `a.name` will be NULL, and `COALESCE(a.name, 'UNKNOWN')` replaces NULL with the text `'UNKNOWN'`.

**What each relationship means:**

- One `allowed_list` row → zero or many `logs` rows (a person can scan many times, or never)
- One `allowed_list` row → zero or many `exits` rows (a person can exit many times, or never)
- `logs` rows with `status = 'UNKNOWN'` → no matching `allowed_list` row (card not registered)

---

## 5. Indexes — what they are and why they exist

An index is a separate data structure that the database builds alongside a table to make certain queries faster. Without an index, a query must read every single row to find what it needs. With an index, it can jump directly to the right rows.

### Automatic index: primary keys

Every primary key column (`allowed_list.isic_id`, `logs.id`, `exits.id`, `admin_accounts.id`) gets an automatic index. This means:

```sql
-- These are instant, no matter how many rows there are:
SELECT * FROM allowed_list WHERE isic_id = 'A1B2C3';
SELECT * FROM logs WHERE id = 500;
SELECT * FROM admin_accounts WHERE id = 1;
```

### Automatic index: UNIQUE constraint

`admin_accounts.username` has a UNIQUE constraint. SQLite automatically creates an index for this. Looking up an admin by username is instant:

```sql
-- Also instant:
SELECT * FROM admin_accounts WHERE username = 'jan.novak';
```

### Manual indexes: card search

The admin dashboard has a search box. When you type in it, the app searches both `name` and `isic_id` for your text. To make this fast, two extra indexes are created:

**SQLite:**
```sql
CREATE INDEX IF NOT EXISTS idx_allowed_name_lower
ON allowed_list (lower(name));

CREATE INDEX IF NOT EXISTS idx_allowed_isic_lower
ON allowed_list (lower(isic_id));
```

`lower()` converts the text to lowercase before indexing. This makes case-insensitive searches fast. The query `WHERE lower(name) LIKE lower('%jan%')` can use this index.

**PostgreSQL:**
```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX IF NOT EXISTS idx_allowed_name_trgm
ON allowed_list USING GIN (lower(name) gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_allowed_isic_trgm
ON allowed_list USING GIN (lower(isic_id) gin_trgm_ops);
```

PostgreSQL uses a different type of index called GIN with trigrams (breaking text into 3-character chunks) which supports very fast partial text matching (ILIKE `%jan%`) on large tables.

---

## 6. Every database operation in the codebase

This section lists every place in `app.py` where the database is read or written. For each operation, you can see what SQL is run and when it happens.

---

### 6.1 Database initialization (`init_db`)

**When:** Called once when the server starts (`python app.py`). Creates tables and indexes if they do not already exist. Safe to run on a database that already has data — `IF NOT EXISTS` means nothing is deleted or changed.

**SQL run:**
```sql
CREATE TABLE IF NOT EXISTS allowed_list (...);
CREATE TABLE IF NOT EXISTS logs (...);
CREATE TABLE IF NOT EXISTS exits (...);
CREATE TABLE IF NOT EXISTS admin_accounts (...);
CREATE INDEX IF NOT EXISTS idx_allowed_name_lower ON allowed_list (lower(name));
CREATE INDEX IF NOT EXISTS idx_allowed_isic_lower ON allowed_list (lower(isic_id));
```

---

### 6.2 ESP card scan — entrance (`POST /rfid`)

**When:** The entrance ESP device scans a card. Called automatically by hardware.

**Two modes:**

**Mode A: `is_test = true` in the request (registering a new card)**
```sql
-- Upsert: insert the card, or update it if the isic_id already exists
INSERT INTO allowed_list (isic_id, name, is_allowed) VALUES (?, ?, ?)
ON CONFLICT(isic_id) DO UPDATE SET name=excluded.name, is_allowed=excluded.is_allowed;
```
This is an "upsert" — insert OR update. If the card already exists, its name and is_allowed are updated. If it does not exist, a new row is created.

**Mode B: `is_test = false` (normal scan)**
```sql
-- Step 1: Check if the card is registered and whether it is allowed
SELECT is_allowed FROM allowed_list WHERE isic_id = ?;
-- Returns one row, or no rows if the card is not registered.

-- Step 2: Write the scan event to logs
INSERT INTO logs (isic_id, timestamp, status) VALUES (?, ?, ?);
-- status is set to 'ALLOWED', 'DENIED', or 'UNKNOWN' based on step 1
```

---

### 6.3 ESP card scan — exit (`POST /unlog`)

**When:** The exit ESP device scans a card when someone leaves.

```sql
-- Step 1: Get the person's name for the response
SELECT name FROM allowed_list WHERE isic_id = ?;

-- Step 2: Count how many times this card entered today
SELECT COUNT(*) AS cnt FROM logs
WHERE isic_id = ? AND status = 'ALLOWED' AND timestamp LIKE '2025-07-04%';

-- Step 3: Count how many times this card has already exited today
SELECT COUNT(*) AS cnt FROM exits
WHERE isic_id = ? AND timestamp LIKE '2025-07-04%';

-- If entries - exits <= 0, the person is not currently inside. Return NOT_INSIDE. Stop here.

-- Step 4: Record the exit
INSERT INTO exits (isic_id, timestamp) VALUES (?, ?);
```

The `LIKE '2025-07-04%'` pattern matches any timestamp that starts with today's date. This is how the app filters to "today only" without a proper date column.

---

### 6.4 Admin dashboard — live log (`GET /dashboard` and `GET /api/logs`)

**When:** An admin opens the dashboard, or the dashboard refreshes its data via the API.

```sql
SELECT
    l.id,
    l.isic_id,
    l.timestamp,
    l.status,
    COALESCE(a.name, 'UNKNOWN') AS name
FROM logs l
LEFT JOIN allowed_list a ON l.isic_id = a.isic_id
ORDER BY l.id DESC
LIMIT 40;
```

Returns the 40 most recent scan events, newest first, with the person's name attached if available.

---

### 6.5 Admin login (`POST /admin-login`)

**When:** An admin submits the login form.

```sql
-- Step 1: Find the account
SELECT id, username, password_hash, role
FROM admin_accounts
WHERE username = ?;
-- The app then calls check_password_hash() in Python to verify the password.
-- This is not a SQL check. It happens in Python code.

-- Step 2: If login was successful, update last_login
UPDATE admin_accounts SET last_login = ? WHERE username = ?;
```

---

### 6.6 Card management — view (`GET /manage` and `GET /api/users`)

**When:** An admin opens the Manage Cards page.

**Simple load (GET /manage — no search):**
```sql
SELECT isic_id, name, is_allowed
FROM allowed_list
ORDER BY name;
```
Returns all cards sorted alphabetically by name.

**Paginated search (GET /api/users — used by the search box):**
```sql
-- Count total results (for pagination)
SELECT COUNT(*) AS cnt
FROM allowed_list
WHERE lower(name) LIKE lower('%search_term%')
   OR lower(isic_id) LIKE lower('%search_term%');

-- Get one page of results
SELECT isic_id, name, is_allowed
FROM allowed_list
WHERE lower(name) LIKE lower('%search_term%')
   OR lower(isic_id) LIKE lower('%search_term%')
ORDER BY name
LIMIT 50 OFFSET 0;
```

The `OFFSET` changes based on the page number. Page 1 = OFFSET 0. Page 2 = OFFSET 50. And so on.

Optional `status` filter adds an extra condition:
```sql
-- status=authorized:
WHERE is_allowed = 1 AND (lower(name) LIKE ...)

-- status=blocked:
WHERE is_allowed = 0 AND (lower(name) LIKE ...)
```

---

### 6.7 Card management — add or update a card (`POST /manage`)

**When:** An admin submits the "Add / Update Card" form on the Manage Cards page.

```sql
INSERT INTO allowed_list (isic_id, name, is_allowed) VALUES (?, ?, ?)
ON CONFLICT(isic_id) DO UPDATE SET name=excluded.name, is_allowed=excluded.is_allowed;
```

Same upsert as the ESP registration mode. If you submit a card ID that already exists, the name and is_allowed are updated. If it is new, a new row is created.

---

### 6.8 Toggle allow/block for one card (`GET /toggle/<isic_id>`)

**When:** An admin clicks "Block" or "Allow" next to a card in the manage page.

```sql
UPDATE allowed_list
SET is_allowed = CASE WHEN is_allowed = 1 THEN 0 ELSE 1 END
WHERE isic_id = ?;
```

This flips the value. If it was `1`, it becomes `0`. If it was `0`, it becomes `1`. One query, no need to read the current value first.

---

### 6.9 Delete one card (`GET /delete/<isic_id>`)

**When:** An admin clicks "Delete" next to a card.

```sql
DELETE FROM allowed_list WHERE isic_id = ?;
```

Only removes the row from `allowed_list`. The card's past scan history in `logs` and `exits` is kept.

---

### 6.10 Bulk action on multiple cards (`POST /api/bulk-action`)

**When:** An admin selects multiple cards and clicks "Allow Selected", "Block Selected", or "Delete Selected".

```sql
-- For each card ID in the list (up to 500):

-- action = "allow":
UPDATE allowed_list SET is_allowed = 1 WHERE isic_id = ?;

-- action = "block":
UPDATE allowed_list SET is_allowed = 0 WHERE isic_id = ?;

-- action = "delete":
DELETE FROM allowed_list WHERE isic_id = ?;
```

Each card ID is processed in the same database transaction. If something fails mid-way, all changes in that batch are rolled back.

---

### 6.11 Bulk import from CSV/Excel (`POST /import`)

**When:** An admin uploads a `.csv` or `.xlsx` file.

For each row in the file:
```sql
INSERT INTO allowed_list (isic_id, name, is_allowed) VALUES (?, ?, ?)
ON CONFLICT(isic_id) DO UPDATE SET name=excluded.name, is_allowed=excluded.is_allowed;
```

Same upsert. Rows that fail validation (bad card ID format, name too long, etc.) are skipped and counted as errors. Valid rows are saved.

---

### 6.12 Clear all logs (`GET /clear`)

**When:** A superadmin clicks "Clear Logs".

```sql
DELETE FROM logs;
DELETE FROM exits;
```

This deletes every row from both tables. `allowed_list` and `admin_accounts` are untouched. The card database and admin accounts survive a log clear.

---

### 6.13 Admin account management — view (`GET /admin-accounts`)

**When:** A superadmin opens the Admin Accounts page.

```sql
SELECT id, username, role, created_at, last_login
FROM admin_accounts
ORDER BY username;
```

Note: `password_hash` is NOT selected. It is never sent to the browser.

---

### 6.14 Admin account management — create (`POST /admin-accounts/add`)

**When:** A superadmin submits the "Create Account" form.

```sql
INSERT INTO admin_accounts (username, password_hash, role, created_at)
VALUES (?, ?, ?, ?);
```

The password is hashed in Python before this query runs. The plain-text password is never stored.

---

### 6.15 Admin account management — delete (`GET /admin-accounts/delete/<id>`)

**When:** A superadmin clicks "Delete" on an account.

```sql
-- Step 1: Check the account exists and is not the current user
SELECT username FROM admin_accounts WHERE id = ?;

-- Step 2: Delete it
DELETE FROM admin_accounts WHERE id = ?;
```

The app prevents deleting your own account. This check is done in Python, not SQL.

---

### 6.16 Admin account management — reset password (`POST /admin-accounts/reset-password/<id>`)

**When:** A superadmin submits a new password for another account.

```sql
UPDATE admin_accounts SET password_hash = ? WHERE id = ?;
```

The new password is hashed in Python first. The old hash is overwritten.

---

### 6.17 Admin account management — toggle role (`GET /admin-accounts/toggle-role/<id>`)

**When:** A superadmin clicks "Make Operator" or "Make Superadmin".

```sql
-- Step 1: Get the current role
SELECT username, role FROM admin_accounts WHERE id = ?;

-- Step 2: Set the opposite role
UPDATE admin_accounts SET role = ? WHERE id = ?;
-- New role is determined in Python: if current = 'superadmin' then new = 'operator', and vice versa
```

---

### 6.18 Canteen state (`GET /api/canteen`)

**When:** The student occupancy page loads or refreshes.

```sql
-- Count entries today (status=ALLOWED scans)
SELECT COUNT(*) AS cnt
FROM logs
WHERE status = 'ALLOWED' AND timestamp LIKE '2025-07-04%';

-- Count exits today
SELECT COUNT(*) AS cnt
FROM exits
WHERE timestamp LIKE '2025-07-04%';

-- Count denied/unknown scans today (for informational display)
SELECT COUNT(*) AS cnt
FROM logs
WHERE status IN ('DENIED', 'UNKNOWN') AND timestamp LIKE '2025-07-04%';
```

The number of people inside = `entries - exits`, clamped to `[0, CANTEEN_CAPACITY]`.

---

## 7. The canteen occupancy calculation

This is the most important business logic in the system. Understanding it requires understanding all four tables together.

**The formula:**
```
people_inside = CLAMP(total_entries_today - total_exits_today, minimum=0, maximum=CANTEEN_CAPACITY)
```

In Python (`_get_canteen_state()` in app.py):
```python
inside = max(0, min(entries - exits, CANTEEN_CAPACITY))
```

- `max(0, ...)` — prevents negative numbers (more exits than entries, which can happen if the system was reset mid-day or someone exited without being recorded as entering)
- `min(..., CANTEEN_CAPACITY)` — prevents going above the maximum capacity (e.g., if someone enters without scanning)

**"Today" means anything where the timestamp starts with today's date string.** The query uses `LIKE '2025-07-04%'` which matches `2025-07-04 08:01:05`, `2025-07-04 13:45:00`, etc.

**Important: this resets automatically at midnight.** Because the filter is "today's date", yesterday's entries and exits stop being counted when the date changes. You do not need to run any cleanup job.

**Hourly chart calculation** (for the student occupancy page):
For each hour (0 to 23), the app counts how many people were inside at the end of that hour. It does this by counting all `ALLOWED` entries up to `HH:59:59` and all exits up to `HH:59:59`, then subtracting.

**Weekly peak calculation:**
For each of the last 7 days, the app finds the peak occupancy (the highest value seen in any single hour of that day).

---

## 8. Input validation rules

Before any data is written to the database, the app validates it in Python. Invalid data is rejected with an error message. These rules are enforced by functions in `app.py`:

| What is being validated | Function | Rules |
|------------------------|----------|-------|
| Card ID (`isic_id`) | `_validate_card_id()` | 1 to 64 characters. Only A-Z, a-z, 0-9, hyphen `-`, underscore `_`. No spaces. |
| Person's name | `_validate_name()` | 1 to 120 characters. Letters (any Unicode), spaces, hyphens, dots, apostrophes. |
| is_allowed value | `_validate_is_allowed()` | Must be exactly `0` or `1` when converted to integer. |
| Admin username | `_validate_username()` | 3 to 32 characters. Only A-Z, a-z, 0-9, underscore, hyphen. |
| Admin password | `_validate_password()` | At least 8 characters. No other restrictions. |

**These validations prevent:**
- SQL injection (bad characters in card IDs)
- Database errors from oversized values
- Confusing data (e.g., `is_allowed = 5`)

---

## 9. How to write queries correctly for both databases

The codebase supports both SQLite and PostgreSQL. They are almost identical but have two differences you must handle.

### Difference 1: Parameter placeholder

SQLite uses `?` as a placeholder for values. PostgreSQL uses `%s`.

```python
# SQLite:
cur.execute("SELECT * FROM allowed_list WHERE isic_id = ?", ("A1B2C3",))

# PostgreSQL:
cur.execute("SELECT * FROM allowed_list WHERE isic_id = %s", ("A1B2C3",))
```

The app has a helper function `_ph(sql)` that converts `?` to `%s` when PostgreSQL is active:

```python
def _ph(sql):
    return sql.replace("?", "%s") if USE_POSTGRES else sql

# Usage:
cur.execute(_ph("SELECT * FROM allowed_list WHERE isic_id = ?"), ("A1B2C3",))
# On SQLite: SELECT * FROM allowed_list WHERE isic_id = ?
# On PostgreSQL: SELECT * FROM allowed_list WHERE isic_id = %s
```

**Always use `_ph()` when your query has `?` placeholders. Never write raw values into SQL strings.**

### Difference 2: Auto-increment column definition

SQLite uses `INTEGER PRIMARY KEY AUTOINCREMENT`. PostgreSQL uses `SERIAL PRIMARY KEY`.

```python
serial = "SERIAL PRIMARY KEY" if USE_POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"

cur.execute(f"CREATE TABLE IF NOT EXISTS logs (id {serial}, ...)")
```

This only matters in `CREATE TABLE` statements. For all other operations, the `id` column works the same.

### Difference 3: Upsert syntax

Both use the same syntax for upserts (`INSERT ... ON CONFLICT ... DO UPDATE`), but PostgreSQL uses `%s` placeholders:

```python
def _upsert_allowed(cur, isic_id, name, is_allowed):
    if USE_POSTGRES:
        cur.execute("""
            INSERT INTO allowed_list (isic_id, name, is_allowed) VALUES (%s, %s, %s)
            ON CONFLICT(isic_id) DO UPDATE SET name=EXCLUDED.name, is_allowed=EXCLUDED.is_allowed
        """, (isic_id, name, is_allowed))
    else:
        cur.execute("""
            INSERT INTO allowed_list (isic_id, name, is_allowed) VALUES (?, ?, ?)
            ON CONFLICT(isic_id) DO UPDATE SET name=excluded.name, is_allowed=excluded.is_allowed
        """, (isic_id, name, is_allowed))
```

### Pattern for new database operations

When adding a new database operation to the codebase, follow this exact pattern:

```python
# Reading data (returns a list of dicts):
with get_db() as conn:
    cur = conn.cursor()
    cur.execute(_ph("SELECT isic_id, name FROM allowed_list WHERE is_allowed = ?"), (1,))
    results = _fetchall(cur)  # returns [{"isic_id": "A1B2C3", "name": "Jana"}, ...]

# Reading one row (returns a dict or None):
with get_db() as conn:
    cur = conn.cursor()
    cur.execute(_ph("SELECT * FROM allowed_list WHERE isic_id = ?"), ("A1B2C3",))
    row = _fetchone(cur)  # returns {"isic_id": "A1B2C3", "name": "Jana", "is_allowed": 1} or None

# Writing data:
with get_db() as conn:
    cur = conn.cursor()
    cur.execute(_ph("UPDATE allowed_list SET is_allowed = ? WHERE isic_id = ?"), (0, "A1B2C3"))
    # No need to call conn.commit() — the `with` block does it automatically
```

---

## 10. Common tasks with exact SQL

These are ready-to-use queries for common tasks. Run these directly in `sqlite3` or in a Python script using the pattern above.

### Get everyone who is currently allowed in

```sql
SELECT isic_id, name
FROM allowed_list
WHERE is_allowed = 1
ORDER BY name;
```

### Get everyone who is blocked

```sql
SELECT isic_id, name
FROM allowed_list
WHERE is_allowed = 0
ORDER BY name;
```

### Find a card by partial name (case-insensitive)

```sql
SELECT isic_id, name, is_allowed
FROM allowed_list
WHERE lower(name) LIKE lower('%novak%');
```

### Find a card by partial ID

```sql
SELECT isic_id, name, is_allowed
FROM allowed_list
WHERE lower(isic_id) LIKE lower('%A1B2%');
```

### See the most recent 20 scans with names

```sql
SELECT
    l.id,
    l.isic_id,
    COALESCE(a.name, 'UNKNOWN') AS name,
    l.timestamp,
    l.status
FROM logs l
LEFT JOIN allowed_list a ON l.isic_id = a.isic_id
ORDER BY l.id DESC
LIMIT 20;
```

### Count total scans today by status

```sql
SELECT status, COUNT(*) AS count
FROM logs
WHERE timestamp LIKE '2025-07-04%'
GROUP BY status;
```
Replace `2025-07-04` with today's actual date.

### How many people are inside right now

```sql
SELECT
    (SELECT COUNT(*) FROM logs  WHERE status='ALLOWED' AND timestamp LIKE '2025-07-04%') -
    (SELECT COUNT(*) FROM exits WHERE timestamp LIKE '2025-07-04%')
AS people_inside;
```
If this returns a negative number, clamp it to 0 manually.

### How many times a specific card has entered this week

```sql
SELECT COUNT(*) AS entries
FROM logs
WHERE isic_id = 'A1B2C3'
  AND status = 'ALLOWED'
  AND timestamp >= '2025-06-28 00:00:00';
```

### All scans from a specific card (full history)

```sql
SELECT timestamp, status
FROM logs
WHERE isic_id = 'A1B2C3'
ORDER BY id DESC;
```

### See all admin accounts (without passwords)

```sql
SELECT id, username, role, created_at, last_login
FROM admin_accounts
ORDER BY username;
```

### Check if a specific card ID exists

```sql
SELECT COUNT(*) AS found
FROM allowed_list
WHERE isic_id = 'A1B2C3';
-- Returns 1 if found, 0 if not
```

### Add a new card

```sql
INSERT INTO allowed_list (isic_id, name, is_allowed)
VALUES ('D4E5F6', 'New Person', 1);
```

### Block a card

```sql
UPDATE allowed_list SET is_allowed = 0 WHERE isic_id = 'A1B2C3';
```

### Allow a blocked card

```sql
UPDATE allowed_list SET is_allowed = 1 WHERE isic_id = 'A1B2C3';
```

### Delete a card (keeps scan history)

```sql
DELETE FROM allowed_list WHERE isic_id = 'A1B2C3';
```

### Delete ALL logs (same as the Clear Logs button)

```sql
DELETE FROM logs;
DELETE FROM exits;
```

### Count how many cards are in the system

```sql
SELECT
    COUNT(*) AS total,
    SUM(is_allowed) AS allowed,
    COUNT(*) - SUM(is_allowed) AS blocked
FROM allowed_list;
```

---

## 11. What can go wrong and how to fix it

### Problem: The database file does not exist

**Symptom:** The server crashes on startup with `sqlite3.OperationalError: unable to open database file`.

**Cause:** The path in `SQLITE_PATH` points to a folder that does not exist, or the app has no permission to create the file there.

**Fix:** Run `python3 setup.py` to create the database. Or check that the directory in `SQLITE_PATH` exists and is writable.

### Problem: "table already exists" error

**Symptom:** Error on startup.

**Cause:** This should not happen because all `CREATE TABLE` statements use `IF NOT EXISTS`. If you see this, something else modified the database schema manually.

**Fix:** Check if there is a schema conflict in the database using `sqlite3 rfid_system.db ".schema"`.

### Problem: Occupancy count is wrong (shows too many or too few people)

**Symptom:** The student occupancy page shows a number that does not match reality.

**Cause 1:** The system was reset mid-day. Old entries from before the reset are counted but the exits may not match.

**Fix:** Clear the logs using the admin dashboard Clear Logs button, or run:
```sql
DELETE FROM logs WHERE timestamp LIKE '2025-07-04%';
DELETE FROM exits WHERE timestamp LIKE '2025-07-04%';
```

**Cause 2:** The exit scanner is not working. Entries are being counted but no exits.

**Fix:** Check the exit ESP device connection and that it is calling `/unlog` correctly.

**Cause 3:** Someone entered without scanning (walked in behind someone else).

**Fix:** This is a physical security issue, not a database issue. The formula clamps to 0 so it will self-correct as people exit.

### Problem: A card shows as UNKNOWN even though it was registered

**Symptom:** Admin sees UNKNOWN scans for a card that appears in `allowed_list`.

**Cause:** The card ID sent by the ESP device does not exactly match the `isic_id` stored in `allowed_list`. Card IDs are case-sensitive. `A1B2C3` and `a1b2c3` are treated as different IDs.

**Fix:** Check the actual value being sent by the ESP device (visible in the serial monitor) and compare it exactly to what is in the database:
```sql
SELECT isic_id FROM allowed_list WHERE lower(isic_id) = lower('the_id_from_esp');
```
If it matches on the lowercase version but not the exact version, update the stored ID:
```sql
UPDATE allowed_list SET isic_id = 'exact_id_from_esp' WHERE lower(isic_id) = lower('exact_id_from_esp');
```
Note: you cannot update a primary key directly if there are referencing rows. In this case, you would need to insert a new row with the correct ID and delete the old one.

### Problem: Admin cannot log in

**Symptom:** Login page returns "Invalid credentials" for a known username and password.

**Cause 1:** Wrong password. Passwords are hashed — you cannot read them from the database. To reset:
1. Generate a new hash in Python: `python3 -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('newpassword123'))"`
2. Copy the output hash.
3. Run: `UPDATE admin_accounts SET password_hash = 'paste_hash_here' WHERE username = 'jan.novak';`

**Cause 2:** No admin accounts exist. Run `python3 setup.py` again to create the superadmin account (it will update if the username already exists, not duplicate it).

### Problem: Search is very slow

**Symptom:** Typing in the search box on the Manage Cards page is slow.

**Cause:** The search indexes were not created. This can happen if you created the database manually instead of through `init_db()`.

**Fix:** Run these in `sqlite3`:
```sql
CREATE INDEX IF NOT EXISTS idx_allowed_name_lower ON allowed_list (lower(name));
CREATE INDEX IF NOT EXISTS idx_allowed_isic_lower ON allowed_list (lower(isic_id));
```

### Problem: Import fails with "isic_id and name columns required"

**Symptom:** Uploading a CSV or Excel file shows an error.

**Cause:** The column headers in the file do not match exactly. The importer normalizes them to lowercase and strips spaces, then looks for `isic_id` and `name`.

**Fix:** Make sure the first row of your file has at least these columns:
```
isic_id,name
```
Optional third column: `is_allowed` (values `1` or `0`). If missing, all imported cards default to allowed.

---

*End of documentation. This document covers the complete database layer as it exists in the current codebase.*
