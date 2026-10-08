"""GitHub API client: fetch one page of open issues and normalize them."""

from __future__ import annotations

import json
import os
import re
import socket
import urllib.error
import urllib.request
from typing import Dict, List

API_URL = "https://api.github.com/repos/{repo}/issues?state=open&per_page=100"
TIMEOUT_SECONDS = 10

# GitHub owner/repo names: letters, digits, '-', '_', '.'
_REPO_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class SnapshotError(Exception):
    """An expected failure with a machine-readable type and a human message."""

    def __init__(self, error_type: str, message: str):
        super().__init__(message)
        self.type = error_type
        self.message = message


def normalize_repo(repo: str) -> str:
    """Validate 'owner/name' and lowercase it (GitHub names are case-insensitive)."""
    if not isinstance(repo, str) or not _REPO_PATTERN.match(repo.strip()):
        raise SnapshotError(
            "invalid_repo",
            f"Invalid repository {repo!r}. Expected the form 'owner/name', e.g. 'psf/requests'.",
        )
    return repo.strip().lower()


def _get_json(url: str):
    """GET a URL and return parsed JSON, mapping every failure to SnapshotError."""
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "github-issue-snapshot",  # GitHub rejects requests without one
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN")  # optional: only raises the rate limit
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        if err.code == 404:
            raise SnapshotError("not_found", "Repository not found (or it is private).")
        if err.code == 429 or (err.code == 403 and err.headers.get("X-RateLimit-Remaining") == "0"):
            raise SnapshotError(
                "rate_limited",
                "GitHub rate limit reached. Wait a while, or set GITHUB_TOKEN for a higher limit.",
            )
        raise SnapshotError("api_error", f"GitHub API returned HTTP {err.code}.")
    except (urllib.error.URLError, socket.timeout, TimeoutError) as err:
        raise SnapshotError("network_error", f"Could not reach GitHub: {err}")
    except ValueError:  # includes json.JSONDecodeError and UnicodeDecodeError
        raise SnapshotError("api_error", "GitHub returned a response that was not valid JSON.")


def fetch_open_issues(repo: str) -> List[Dict]:
    """Return one page (up to 100) of open issues as [{number, title, url}], excluding PRs."""
    payload = _get_json(API_URL.format(repo=normalize_repo(repo)))
    if not isinstance(payload, list):
        raise SnapshotError("api_error", "Unexpected response shape from GitHub.")

    issues = []
    for item in payload:
        # GitHub's issues endpoint also returns pull requests; they carry a 'pull_request' key.
        if "pull_request" in item:
            continue
        issues.append(
            {"number": item["number"], "title": item["title"], "url": item["html_url"]}
        )
    return issues
