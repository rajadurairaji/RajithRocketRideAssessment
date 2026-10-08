"""GitHub issue snapshot connector: import open issues into SQLite, read them back."""

from .service import import_issues, read_issues

__all__ = ["import_issues", "read_issues"]
