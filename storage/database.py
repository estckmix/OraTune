"""SQLite connection and schema initialisation.

Database file: ~/.oratune/sessions.db
Created automatically on first use.
"""

import sqlite3
from pathlib import Path

_DB_PATH = Path.home() / ".oratune" / "sessions.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id              TEXT PRIMARY KEY,
    timestamp       TEXT NOT NULL,
    summary         TEXT,
    baseline_files  TEXT,
    current_files   TEXT,
    results_json    TEXT NOT NULL
);
"""


def get_connection() -> sqlite3.Connection:
    """Return an open SQLite connection, creating the DB file if needed."""
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn
