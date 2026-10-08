"""Public interface: import_issues() and read_issues().

Both return JSON-compatible dicts and never raise for expected failures:
    success: {"ok": True, ...}
    failure: {"ok": False, "error": {"type": "...", "message": "..."}}
"""

from __future__ import annotations

import os
import sqlite3
from typing import Dict, Optional

from . import db
from .api import SnapshotError, fetch_open_issues, normalize_repo

DEFAULT_DB_PATH = "issues.db"
DB_ENV_VAR = "SNAPSHOT_DB"


def resolve_db_path(db_path: Optional[str] = None) -> str:
    """Priority: explicit argument > SNAPSHOT_DB env var > ./issues.db"""
    return db_path or os.environ.get(DB_ENV_VAR) or DEFAULT_DB_PATH


def _failure(error_type: str, message: str) -> Dict:
    return {"ok": False, "error": {"type": error_type, "message": message}}


def import_issues(repo: str, db_path: Optional[str] = None) -> Dict:
    """Fetch one page of open issues (no PRs) from GitHub and upsert them into SQLite."""
    try:
        repo = normalize_repo(repo)
        issues = fetch_open_issues(repo)
        conn = db.connect(resolve_db_path(db_path))
        try:
            db.upsert_issues(conn, repo, issues)
            total = len(db.get_issues(conn, repo))
        finally:
            conn.close()
        return {"ok": True, "repo": repo, "imported": len(issues), "total_stored": total}
    except SnapshotError as err:
        return _failure(err.type, err.message)
    except sqlite3.Error as err:
        return _failure("database_error", f"Database error: {err}")


def read_issues(repo: str, db_path: Optional[str] = None) -> Dict:
    """Return saved issues for a repo from SQLite. Never calls GitHub."""
    try:
        repo = normalize_repo(repo)
        conn = db.connect(resolve_db_path(db_path))
        try:
            issues = db.get_issues(conn, repo)
        finally:
            conn.close()
        return {"ok": True, "repo": repo, "count": len(issues), "issues": issues}
    except SnapshotError as err:
        return _failure(err.type, err.message)
    except sqlite3.Error as err:
        return _failure("database_error", f"Database error: {err}")
