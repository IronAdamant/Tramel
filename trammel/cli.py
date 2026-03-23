"""CLI entrypoint: `python -m trammel` or `trammel` console script."""

from __future__ import annotations

import argparse
import json
import os
import sys

from . import __version__, plan_and_execute


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Trammel: dependency-aware planning with bounded beam exploration.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("goal", nargs="?", default=None, help="High-level goal string")
    parser.add_argument("--root", default=os.getcwd(), help="Project root (default: cwd)")
    parser.add_argument("--beams", type=int, default=3, help="Requested beam count (capped by CPU)")
    parser.add_argument("--db", default="trammel.db", help="SQLite path for recipes and plans")
    parser.add_argument(
        "--test-cmd", nargs="+", default=None,
        help="Custom test command (default: unittest discover)",
    )
    parser.add_argument("--language", default=None, help="Project language (auto-detected if omitted)")
    parser.add_argument("--scope", default=None, help="Subdirectory scope for analysis (monorepo support)")
    parser.add_argument("--dry-run", action="store_true", help="Preview decomposition without running tests")
    args = parser.parse_args()

    if args.goal is None:
        if sys.stdin.isatty():
            parser.print_help()
            sys.exit(2)
        try:
            payload = json.load(sys.stdin)
        except json.JSONDecodeError as exc:
            print(f"Error: invalid JSON on stdin: {exc}", file=sys.stderr)
            sys.exit(1)
        goal = str(payload.get("goal", ""))
    else:
        goal = args.goal

    if args.dry_run:
        from . import explore
        result = explore(
            goal, args.root, num_beams=args.beams, db_path=args.db,
            language=args.language, scope=args.scope,
        )
    else:
        result = plan_and_execute(
            goal, args.root, num_beams=args.beams, db_path=args.db,
            test_cmd=args.test_cmd, language=args.language, scope=args.scope,
        )
    print(json.dumps(result, indent=2))
