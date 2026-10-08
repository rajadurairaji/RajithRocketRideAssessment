"""SQLite storage: schema, upsert, and read queries."""

from __future__ import annotations

import sqlite3
from typing import Dict, List

SCHEMA = """
CREATE TABLE IF NOT EXISTS issues (
    repo   TEXT    NOT NULL,
    number INTEGER NOT NULL,
    title  TEXT    NOT NULL,
    url    TEXT    NOT NULL,
    PRIMARY KEY (repo, number)
)
"""

UPSERT = """
INSERT INTO issues (repo, number, title, url)
VALUES (:repo, :number, :title, :url)
ON CONFLICT(repo, number) DO UPDATE SET title = excluded.title, url = excluded.url
"""


def connect(db_path: str) -> sqlite3.Connection:
    """Open the database and make sure the schema exists."""
    conn = sqlite3.connect(db_path)
    conn.execute(SCHEMA)
    return conn


def upsert_issues(conn: sqlite3.Connection, repo: str, issues: List[Dict]) -> None:
    """Insert new issues and update existing ones, atomically."""
    rows = [{"repo": repo, **issue} for issue in issues]
    with conn:  # one transaction: all rows are saved or none are
        conn.executemany(UPSERT, rows)


def get_issues(conn: sqlite3.Connection, repo: str) -> List[Dict]:
    """Return saved issues for a repo, newest issue number first."""
    cursor = conn.execute(
        "SELECT number, title, url FROM issues WHERE repo = ? ORDER BY number DESC", (repo,)
    )
    return [{"number": n, "title": t, "url": u} for n, t, u in cursor]
