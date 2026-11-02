import sqlite3
from pathlib import Path
from datetime import datetime
from typing import List, Optional
from config import DB_PATH

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

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
        source TEXT DEFAULT 'catalog',
        status TEXT DEFAULT 'pending',
        posted_at TEXT
    );
    CREATE TABLE IF NOT EXISTS groups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        url TEXT,
        category TEXT
    );
    CREATE TABLE IF NOT EXISTS campaigns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        product_ids TEXT DEFAULT '[]',
        group_ids TEXT DEFAULT '[]',
        status TEXT DEFAULT 'idle',
        created_at TEXT DEFAULT (datetime('now')),
        posts_sent INTEGER DEFAULT 0
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
    """)
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
