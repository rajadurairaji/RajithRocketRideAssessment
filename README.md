# GitHub Issue Snapshot Connector

Imports open issues (not pull requests) from a public GitHub repository into a local SQLite
database, and reads them back without calling GitHub again.

## Prerequisites

- Python 3.9+
- Internet access for real imports (tests run offline)
- No GitHub token needed for public repos (optional `GITHUB_TOKEN` raises the rate limit)

## Setup

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt  # only needed for tests (pytest); the app uses the standard library
```

## Run

```bash
python -m snapshot import psf/requests     # fetch one page of open issues, save to SQLite
python -m snapshot read psf/requests       # read saved issues (no network)
python -m snapshot --db my.db read psf/requests   # custom database path
```

Database path priority: `--db` / `db_path=` argument, then the `SNAPSHOT_DB` environment
variable, then `./issues.db`. The CLI exits `0` on success and `1` on error.

As a library:

```python
from snapshot import import_issues, read_issues

import_issues("psf/requests", db_path="my.db")
read_issues("psf/requests", db_path="my.db")
```

## Test

```bash
python -m pytest -v
```

Tests use mocked GitHub responses (no network). They cover import and read, no duplicates on
repeat imports, updates to existing records, PR exclusion, persistence, API failures
(500, 404, rate limit, network), invalid repository names, and database path configuration.

## Example inputs and outputs

<!-- EDIT: replace this block with the real output from YOUR run of `python -m snapshot import psf/requests` -->
```
$ python -m snapshot import psf/requests
{
  "ok": true,
  "repo": "psf/requests",
  "imported": <n>,
  "total_stored": <n>
}
```

```
$ python -m snapshot read psf/requests
{
  "ok": true,
  "repo": "psf/requests",
  "count": <n>,
  "issues": [
    {"number": <n>, "title": "<title>", "url": "https://github.com/psf/requests/issues/<n>"}
  ]
}
```

Errors (real output):

```
$ python -m snapshot import notarepo
{
  "ok": false,
  "error": {
    "type": "invalid_repo",
    "message": "Invalid repository 'notarepo'. Expected the form 'owner/name', e.g. 'psf/requests'."
  }
}

$ python -m snapshot import fake-owner-xyz/doesnotexist
{
  "ok": false,
  "error": {
    "type": "not_found",
    "message": "Repository not found (or it is private)."
  }
}
```

Error types: `invalid_repo`, `not_found`, `rate_limited`, `network_error`, `api_error`,
`database_error`.

## Tools used

<!-- EDIT: keep only what is true for you, and describe in your own words what each helped with -->
- **Claude (claude.ai chat):** [e.g. researched the GitHub Issues API, drafted the modules and tests, helped debug a failing test]
- **VS Code:** editor and integrated terminal
- **pytest / unittest.mock:** automated tests with mocked API responses
- **sqlite3 CLI:** checked the database contents directly
- **GitHub REST API docs:** confirmed response fields and rate-limit headers

## An unfamiliar problem solved with AI

<!-- EDIT: rewrite in your own words, using what YOU actually did and saw. Delete this comment. -->
**Pull requests show up in the issues endpoint.** GitHub's "list repository issues" endpoint
returns pull requests too, because GitHub treats a PR as a kind of issue. PRs are
distinguished only by an extra `pull_request` field. [Describe how you learned this and how
you verified it, for example: counting items with that key in a raw API response for a real
repo, then adding a test where a PR is mixed into the mocked response and confirming that it
is excluded.]

To reproduce the check yourself:

```bash
curl -s -H "User-Agent: x" "https://api.github.com/repos/psf/requests/issues?state=open&per_page=100" \
  | python -c "import json,sys; d=json.load(sys.stdin); print(len(d), sum('pull_request' in i for i in d))"
```
