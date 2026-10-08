"""Command-line wrapper around import_issues() / read_issues()."""

from __future__ import annotations

import argparse
import json
import sys

from .service import import_issues, read_issues


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="snapshot", description="GitHub issue snapshot connector")
    parser.add_argument("--db", help="SQLite file path (default: $SNAPSHOT_DB or ./issues.db)")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("import", help="fetch open issues from GitHub and save them").add_argument(
        "repo", help="repository as owner/name"
    )
    commands.add_parser("read", help="show saved issues (no network)").add_argument(
        "repo", help="repository as owner/name"
    )
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    action = import_issues if args.command == "import" else read_issues
    result = action(args.repo, db_path=args.db)
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
