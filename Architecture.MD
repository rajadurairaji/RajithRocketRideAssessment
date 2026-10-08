# Architecture

## Interface

Two functions in `snapshot/service.py`, re-exported from `snapshot`:

- `import_issues(repo, db_path=None)`: fetch one page of open issues from GitHub and upsert them.
- `read_issues(repo, db_path=None)`: return saved issues from SQLite. Never calls GitHub.

Both return JSON-compatible dicts with a consistent shape and never raise for expected failures:

```
success: {"ok": true, "repo": "owner/name", "imported": 12, "total_stored": 12}   # import
         {"ok": true, "repo": "owner/name", "count": 12, "issues": [{number, title, url}]}   # read
failure: {"ok": false, "error": {"type": "not_found", "message": "..."}}
```

`snapshot/cli.py` is a thin wrapper that prints the result as JSON (`python -m snapshot import|read`).

## Components

| File | Responsibility |
|------|----------------|
| `api.py` | Validate `owner/name`, call the GitHub API, filter out PRs, map HTTP/network failures to `SnapshotError` |
| `db.py` | Schema, upsert, and read queries (SQLite) |
| `service.py` | Public functions; wires API and DB together; converts exceptions to result dicts; resolves the DB path |
| `cli.py`, `__main__.py` | Command-line interface |

## Data flow

```
import_issues("owner/name")
  -> normalize_repo (validate, lowercase)
  -> GET /repos/owner/name/issues?state=open&per_page=100
  -> drop items that have a "pull_request" key; keep number, title, html_url
  -> upsert into SQLite in one transaction
  -> {"ok": true, "imported": N, "total_stored": M}

read_issues("owner/name")
  -> SELECT from SQLite (no network) -> {"ok": true, "issues": [...]}
```

## Database schema

```sql
CREATE TABLE IF NOT EXISTS issues (
    repo   TEXT    NOT NULL,   -- lowercase "owner/name"
    number INTEGER NOT NULL,
    title  TEXT    NOT NULL,
    url    TEXT    NOT NULL,
    PRIMARY KEY (repo, number)
)
```

The composite primary key plus `INSERT ... ON CONFLICT DO UPDATE` makes repeated imports
update existing rows. The database enforces uniqueness, not application code.

## Configuration

DB path: function argument / `--db`, then `SNAPSHOT_DB` env var, then `./issues.db`.
Optional `GITHUB_TOKEN` env var raises GitHub's rate limit; it is not required.

## Error handling

Every expected failure becomes `{"ok": false, "error": {"type", "message"}}`:
`invalid_repo` (bad format), `not_found` (404), `rate_limited` (429, or 403 with no quota left),
`network_error` (DNS, connection, timeout; 10 s timeout), `api_error` (other HTTP status or
malformed response), `database_error`. Upserts run in a single transaction, so a failed import
saves nothing, and a failed re-import leaves earlier data intact.

## Key tradeoffs

- **No deletion of stale issues.** Only one page (100) is fetched, so an issue missing from the
  response may still be open. Deleting it would be wrong, so closed issues stay until a
  future version fetches all pages and reconciles.
- **One table, repo as a column.** Simpler than a separate `repos` table; fine for this scope.
- **Lowercased repo names.** GitHub names are case-insensitive, so this avoids duplicate rows
  for `Psf/Requests` vs `psf/requests`.
- **Standard library only (`urllib`, `sqlite3`).** No runtime dependencies; pytest is only for tests.
- **Result dicts instead of exceptions.** Callers get one consistent, JSON-compatible shape.
