"""Tests use mocked GitHub responses; no network access is needed."""

import json
import urllib.error

import pytest

from snapshot import api, import_issues, read_issues


def fake_payload(*items):
    """Build a GitHub-style issues response. Items with pr=True look like pull requests."""
    payload = []
    for number, title, *flags in items:
        entry = {
            "number": number,
            "title": title,
            "html_url": f"https://github.com/octo/demo/issues/{number}",
        }
        if flags and flags[0] == "pr":
            entry["pull_request"] = {"url": "https://api.github.com/..."}
        payload.append(entry)
    return payload


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.db")


@pytest.fixture
def mock_github(monkeypatch):
    """Replace the HTTP call; set mock_github.payload before importing."""

    class Mock:
        payload = []
        calls = 0

    mock = Mock()

    def fake_get_json(url):
        mock.calls += 1
        return mock.payload

    monkeypatch.setattr(api, "_get_json", fake_get_json)
    return mock


# ---- import + read --------------------------------------------------------

def test_import_then_read(mock_github, db_path):
    mock_github.payload = fake_payload((2, "Second bug"), (1, "First bug"))

    result = import_issues("octo/demo", db_path=db_path)
    assert result == {"ok": True, "repo": "octo/demo", "imported": 2, "total_stored": 2}

    saved = read_issues("octo/demo", db_path=db_path)
    assert saved["ok"] is True
    assert saved["count"] == 2
    assert saved["issues"][0] == {
        "number": 2,
        "title": "Second bug",
        "url": "https://github.com/octo/demo/issues/2",
    }


def test_results_are_json_serializable(mock_github, db_path):
    mock_github.payload = fake_payload((1, "Bug"))
    json.dumps(import_issues("octo/demo", db_path=db_path))
    json.dumps(read_issues("octo/demo", db_path=db_path))


def test_pull_requests_are_excluded(mock_github, db_path):
    mock_github.payload = fake_payload((1, "Real issue"), (2, "A pull request", "pr"))

    result = import_issues("octo/demo", db_path=db_path)

    assert result["imported"] == 1
    numbers = [i["number"] for i in read_issues("octo/demo", db_path=db_path)["issues"]]
    assert numbers == [1]


def test_read_does_not_call_github(mock_github, db_path):
    mock_github.payload = fake_payload((1, "Bug"))
    import_issues("octo/demo", db_path=db_path)
    calls_after_import = mock_github.calls

    read_issues("octo/demo", db_path=db_path)

    assert mock_github.calls == calls_after_import


def test_data_persists_in_the_database_file(mock_github, db_path):
    mock_github.payload = fake_payload((1, "Bug"))
    import_issues("octo/demo", db_path=db_path)

    mock_github.payload = None  # simulate a fresh process: nothing but the file remains
    assert read_issues("octo/demo", db_path=db_path)["count"] == 1


def test_read_unimported_repo_returns_empty_list(db_path):
    result = read_issues("octo/never-imported", db_path=db_path)
    assert result == {"ok": True, "repo": "octo/never-imported", "count": 0, "issues": []}


# ---- repeated imports -----------------------------------------------------

def test_repeated_import_creates_no_duplicates(mock_github, db_path):
    mock_github.payload = fake_payload((1, "Bug"), (2, "Other bug"))

    import_issues("octo/demo", db_path=db_path)
    second = import_issues("octo/demo", db_path=db_path)

    assert second["total_stored"] == 2
    assert read_issues("octo/demo", db_path=db_path)["count"] == 2


def test_repeated_import_updates_existing_records(mock_github, db_path):
    mock_github.payload = fake_payload((1, "Old title"))
    import_issues("octo/demo", db_path=db_path)

    mock_github.payload = fake_payload((1, "New title"))
    import_issues("octo/demo", db_path=db_path)

    issues = read_issues("octo/demo", db_path=db_path)["issues"]
    assert [i["title"] for i in issues] == ["New title"]


def test_repo_name_is_case_insensitive(mock_github, db_path):
    mock_github.payload = fake_payload((1, "Bug"))
    import_issues("Octo/Demo", db_path=db_path)
    import_issues("octo/demo", db_path=db_path)
    assert read_issues("OCTO/DEMO", db_path=db_path)["count"] == 1


def test_repos_are_stored_separately(mock_github, db_path):
    mock_github.payload = fake_payload((1, "Bug"))
    import_issues("octo/one", db_path=db_path)
    import_issues("octo/two", db_path=db_path)
    assert read_issues("octo/one", db_path=db_path)["count"] == 1
    assert read_issues("octo/two", db_path=db_path)["count"] == 1


# ---- failures -------------------------------------------------------------

def http_error(code, headers=None):
    return urllib.error.HTTPError("https://api.github.com/x", code, "err", headers or {}, None)


def fail_with(monkeypatch, error):
    def fake_urlopen(*args, **kwargs):
        raise error

    monkeypatch.setattr(api.urllib.request, "urlopen", fake_urlopen)


def test_api_failure_returns_error_and_saves_nothing(monkeypatch, db_path):
    fail_with(monkeypatch, http_error(500))

    result = import_issues("octo/demo", db_path=db_path)

    assert result["ok"] is False
    assert result["error"]["type"] == "api_error"
    assert read_issues("octo/demo", db_path=db_path)["count"] == 0


def test_repo_not_found(monkeypatch, db_path):
    fail_with(monkeypatch, http_error(404))
    result = import_issues("octo/missing", db_path=db_path)
    assert result["error"]["type"] == "not_found"


def test_rate_limit(monkeypatch, db_path):
    fail_with(monkeypatch, http_error(403, {"X-RateLimit-Remaining": "0"}))
    result = import_issues("octo/demo", db_path=db_path)
    assert result["error"]["type"] == "rate_limited"


def test_network_failure(monkeypatch, db_path):
    fail_with(monkeypatch, urllib.error.URLError("no route to host"))
    result = import_issues("octo/demo", db_path=db_path)
    assert result["error"]["type"] == "network_error"


def test_failed_reimport_keeps_previously_saved_data(mock_github, monkeypatch, db_path):
    mock_github.payload = fake_payload((1, "Bug"))
    import_issues("octo/demo", db_path=db_path)

    def failing_get_json(url):
        raise api.SnapshotError("api_error", "GitHub API returned HTTP 500.")

    monkeypatch.setattr(api, "_get_json", failing_get_json)
    assert import_issues("octo/demo", db_path=db_path)["ok"] is False
    assert read_issues("octo/demo", db_path=db_path)["count"] == 1


@pytest.mark.parametrize("bad", ["", "justaname", "a/b/c", "owner/", "/name", "bad repo/x", "o/n;drop"])
def test_invalid_repo_format(bad, db_path):
    for action in (import_issues, read_issues):
        result = action(bad, db_path=db_path)
        assert result["ok"] is False
        assert result["error"]["type"] == "invalid_repo"


# ---- configuration --------------------------------------------------------

def test_db_path_from_environment(mock_github, tmp_path, monkeypatch):
    env_db = tmp_path / "from_env.db"
    monkeypatch.setenv("SNAPSHOT_DB", str(env_db))
    mock_github.payload = fake_payload((1, "Bug"))

    import_issues("octo/demo")

    assert env_db.exists()
    assert read_issues("octo/demo")["count"] == 1


def test_explicit_db_path_beats_environment(mock_github, tmp_path, monkeypatch):
    monkeypatch.setenv("SNAPSHOT_DB", str(tmp_path / "env.db"))
    explicit = tmp_path / "explicit.db"
    mock_github.payload = fake_payload((1, "Bug"))

    import_issues("octo/demo", db_path=str(explicit))

    assert explicit.exists()
    assert not (tmp_path / "env.db").exists()
