import sqlite3
from typing import List
from config import DB_PATH

def get_conn() -> sqlite3.Connection:
    # WAL + a generous busy timeout lets the scheduler, API requests and the
    # UI read/write at the same time without intermittent "database is locked"
    # failures (which used to surface as silent 500s in the dashboard).
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    try:
        conn.execute("PRAGMA journal_mode = WAL")
    except sqlite3.OperationalError:
        pass
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn

def _add_column_if_missing(conn, table: str, column: str, ddl: str) -> None:
    cols = [r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

def init_db() -> None:
    conn = get_conn()
    cur = conn.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT,
        media_url TEXT,
        link TEXT,
        category TEXT,
        status TEXT DEFAULT 'isNotPosted',
        posted_at TEXT,
        last_posted_at TEXT,
        updated_at TEXT
    );
    CREATE TABLE IF NOT EXISTS groups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        category TEXT,
        location TEXT,
        n INTEGER DEFAULT 1,
        isPostedProductToday INTEGER DEFAULT 0,
        link TEXT,
        is_my_group INTEGER DEFAULT 0,
        is_core INTEGER DEFAULT 0,
        failures INTEGER DEFAULT 0,
        is_active INTEGER DEFAULT 1,
        total_misses INTEGER DEFAULT 0,
        is_silenced INTEGER DEFAULT 0,
        silenced_at TEXT,
        silence_reason TEXT,
        last_missed_at TEXT,
        last_success_at TEXT
    );
    CREATE TABLE IF NOT EXISTS clients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        number TEXT NOT NULL,
        category TEXT,
        location TEXT,
        birthdays TEXT
    );
    CREATE TABLE IF NOT EXISTS campaigns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        campaign_type TEXT NOT NULL,
        product_id INTEGER,
        group_id INTEGER,
        client_id INTEGER,
        my_group_link TEXT,
        scheduled_time TEXT,
        status TEXT DEFAULT 'isScheduledFor',
        rePost INTEGER DEFAULT 0,
        repeatPost INTEGER DEFAULT 0,
        frequency TEXT,
        repeat_day INTEGER,
        repeat_time TEXT,
        target_scope TEXT DEFAULT 'single',
        auto_product INTEGER DEFAULT 0,
        batch_size INTEGER DEFAULT 0,
        duration_minutes INTEGER DEFAULT 60,
        last_run_at TEXT,
        next_run_at TEXT,
        posts_sent INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS campaign_clients (
        campaign_id INTEGER NOT NULL,
        client_id INTEGER NOT NULL,
        PRIMARY KEY (campaign_id, client_id),
        FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
    );
    CREATE TABLE IF NOT EXISTS group_batches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT
    );
    CREATE TABLE IF NOT EXISTS group_batch_members (
        batch_id INTEGER NOT NULL,
        group_id INTEGER NOT NULL,
        PRIMARY KEY (batch_id, group_id),
        FOREIGN KEY (batch_id) REFERENCES group_batches(id)
    );
    CREATE TABLE IF NOT EXISTS campaign_group_batches (
        campaign_id INTEGER NOT NULL,
        batch_id INTEGER NOT NULL,
        PRIMARY KEY (campaign_id, batch_id),
        FOREIGN KEY (campaign_id) REFERENCES campaigns(id),
        FOREIGN KEY (batch_id) REFERENCES group_batches(id)
    );
    CREATE TABLE IF NOT EXISTS schedules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        campaign_id INTEGER NOT NULL,
        start_time TEXT NOT NULL,
        end_time TEXT NOT NULL,
        status TEXT DEFAULT 'active',
        FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
    );
    CREATE TABLE IF NOT EXISTS campaign_posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        campaign_id INTEGER,
        target_type TEXT,
        target_id INTEGER,
        target_name TEXT,
        posted_at TEXT DEFAULT (datetime('now')),
        status TEXT,
        FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
    );
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        level TEXT DEFAULT 'info',
        message TEXT NOT NULL,
        source TEXT DEFAULT 'bot',
        created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS analytics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        posts_sent INTEGER DEFAULT 0,
        groups_reached INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS app_meta (
        key TEXT PRIMARY KEY,
        value TEXT
    );
    CREATE TABLE IF NOT EXISTS campaign_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        campaign_id INTEGER NOT NULL,
        campaign_name TEXT,
        campaign_type TEXT,
        status TEXT DEFAULT 'starting',
        phase TEXT DEFAULT 'starting',
        product_id INTEGER,
        product_name TEXT,
        target_type TEXT,
        current_target_id INTEGER,
        current_target_name TEXT,
        total_targets INTEGER DEFAULT 0,
        processed INTEGER DEFAULT 0,
        sent INTEGER DEFAULT 0,
        failed INTEGER DEFAULT 0,
        skipped INTEGER DEFAULT 0,
        remaining INTEGER DEFAULT 0,
        cycle_complete INTEGER DEFAULT 0,
        skip_requested INTEGER DEFAULT 0,
        error TEXT,
        started_at TEXT DEFAULT (datetime('now')),
        finished_at TEXT,
        last_update TEXT
    );
    CREATE TABLE IF NOT EXISTS campaign_run_targets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER NOT NULL,
        campaign_id INTEGER NOT NULL,
        batch_no INTEGER,
        queue_index INTEGER,
        target_type TEXT,
        target_id INTEGER,
        target_name TEXT,
        source_name TEXT,
        status TEXT DEFAULT 'pending',
        attempts INTEGER DEFAULT 0,
        message TEXT,
        started_at TEXT,
        finished_at TEXT,
        UNIQUE(run_id, target_type, target_id)
    );
    CREATE INDEX IF NOT EXISTS idx_run_targets_run_status
        ON campaign_run_targets(run_id, status);
    CREATE TABLE IF NOT EXISTS campaign_run_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER,
        campaign_id INTEGER,
        level TEXT DEFAULT 'info',
        event_type TEXT,
        target_type TEXT,
        target_id INTEGER,
        target_name TEXT,
        message TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_run_events_run_id
        ON campaign_run_events(run_id, id);
    CREATE TABLE IF NOT EXISTS bot_state (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        state TEXT DEFAULT 'unknown',
        message TEXT,
        attempt INTEGER DEFAULT 0,
        max_attempts INTEGER,
        qr_visible INTEGER DEFAULT 0,
        next_retry_at TEXT,
        updated_at TEXT
    );
    """)
    # ── Migrate existing databases: add any missing columns ──────────────
    _add_column_if_missing(conn, "products", "category", "TEXT")
    _add_column_if_missing(conn, "products", "status", "TEXT DEFAULT 'isNotPosted'")
    _add_column_if_missing(conn, "products", "posted_at", "TEXT")
    _add_column_if_missing(conn, "products", "last_posted_at", "TEXT")
    _add_column_if_missing(conn, "products", "description", "TEXT")
    _add_column_if_missing(conn, "products", "updated_at", "TEXT")
    _add_column_if_missing(conn, "groups", "category", "TEXT")
    _add_column_if_missing(conn, "groups", "location", "TEXT")
    _add_column_if_missing(conn, "groups", "n", "INTEGER DEFAULT 1")
    _add_column_if_missing(conn, "groups", "isPostedProductToday", "INTEGER DEFAULT 0")
    _add_column_if_missing(conn, "groups", "link", "TEXT")
    _add_column_if_missing(conn, "groups", "is_my_group", "INTEGER DEFAULT 0")
    _add_column_if_missing(conn, "groups", "is_core", "INTEGER DEFAULT 0")
    _add_column_if_missing(conn, "groups", "failures", "INTEGER DEFAULT 0")
    _add_column_if_missing(conn, "groups", "is_active", "INTEGER DEFAULT 1")
    _add_column_if_missing(conn, "groups", "total_misses", "INTEGER DEFAULT 0")
    _add_column_if_missing(conn, "groups", "is_silenced", "INTEGER DEFAULT 0")
    _add_column_if_missing(conn, "groups", "silenced_at", "TEXT")
    _add_column_if_missing(conn, "groups", "silence_reason", "TEXT")
    _add_column_if_missing(conn, "groups", "last_missed_at", "TEXT")
    _add_column_if_missing(conn, "groups", "last_success_at", "TEXT")
    _add_column_if_missing(conn, "clients", "category", "TEXT")
    _add_column_if_missing(conn, "clients", "location", "TEXT")
    _add_column_if_missing(conn, "clients", "birthdays", "TEXT")
    _add_column_if_missing(conn, "campaigns", "campaign_type", "TEXT NOT NULL DEFAULT 'product_group'")
    _add_column_if_missing(conn, "campaigns", "product_id", "INTEGER")
    _add_column_if_missing(conn, "campaigns", "group_id", "INTEGER")
    _add_column_if_missing(conn, "campaigns", "client_id", "INTEGER")
    _add_column_if_missing(conn, "campaigns", "my_group_link", "TEXT")
    _add_column_if_missing(conn, "campaigns", "scheduled_time", "TEXT")
    _add_column_if_missing(conn, "campaigns", "status", "TEXT DEFAULT 'isScheduledFor'")
    _add_column_if_missing(conn, "campaigns", "rePost", "INTEGER DEFAULT 0")
    _add_column_if_missing(conn, "campaigns", "repeatPost", "INTEGER DEFAULT 0")
    _add_column_if_missing(conn, "campaigns", "frequency", "TEXT")
    _add_column_if_missing(conn, "campaigns", "repeat_day", "INTEGER")
    _add_column_if_missing(conn, "campaigns", "repeat_time", "TEXT")
    _add_column_if_missing(conn, "campaigns", "target_scope", "TEXT DEFAULT 'single'")
    _add_column_if_missing(conn, "campaigns", "auto_product", "INTEGER DEFAULT 0")
    _add_column_if_missing(conn, "campaigns", "batch_size", "INTEGER DEFAULT 0")
    _add_column_if_missing(conn, "campaigns", "duration_minutes", "INTEGER DEFAULT 60")
    _add_column_if_missing(conn, "campaigns", "last_run_at", "TEXT")
    _add_column_if_missing(conn, "campaigns", "next_run_at", "TEXT")
    _add_column_if_missing(conn, "campaigns", "posts_sent", "INTEGER DEFAULT 0")
    # Normalise datetime-local values ("2026-12-01T09:00") so schedule
    # comparisons against "%Y-%m-%d %H:%M" work consistently.
    conn.execute("UPDATE schedules SET start_time = REPLACE(start_time, 'T', ' '), end_time = REPLACE(end_time, 'T', ' ')")
    conn.execute("UPDATE campaigns SET scheduled_time = REPLACE(scheduled_time, 'T', ' ') WHERE scheduled_time IS NOT NULL")
    # A crash/reload mid-run would otherwise leave a campaign stuck as
    # "isRunning" forever, blocking every future campaign as "busy".
    stale = conn.execute("SELECT COUNT(*) AS c FROM campaigns WHERE status = 'isRunning'").fetchone()["c"]
    if stale:
        conn.execute("UPDATE campaigns SET status = 'isPosted' WHERE status = 'isRunning'")
    # Same idea for live run state: a process that died mid-run must not leave
    # a forever-"running" run behind.
    conn.execute(
        "UPDATE campaign_runs SET status = 'interrupted', phase = 'finished', "
        "finished_at = COALESCE(finished_at, datetime('now')) "
        "WHERE status IN ('starting', 'running', 'paused', 'waiting_login', "
        "'waiting_qr', 'reconnecting')"
    )
    conn.execute("INSERT OR IGNORE INTO bot_state (id, state) VALUES (1, 'unknown')")
    conn.commit()
    conn.close()

def log(level: str, message: str, source: str = "bot") -> None:
    conn = get_conn()
    conn.execute(
        "INSERT INTO logs (level, message, source) VALUES (?, ?, ?)",
        (level, message, source),
    )
    conn.commit()
    conn.close()

def logs(limit: int = 50) -> List[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM logs ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def query(sql: str, params: tuple = ()) -> List[dict]:
    conn = get_conn()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def execute(sql: str, params: tuple = ()) -> int:
    conn = get_conn()
    cur = conn.execute(sql, params)
    conn.commit()
    lastrowid = cur.lastrowid
    conn.close()
    return lastrowid
