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
    args = parser.parse_args()

    if args.goal is None:
        if sys.stdin.isatty():
            parser.print_help()
            sys.exit(2)
        payload = json.load(sys.stdin)
        goal = str(payload.get("goal", ""))
    else:
        goal = args.goal

    result = plan_and_execute(goal, args.root, num_beams=args.beams, db_path=args.db)
    print(json.dumps(result, indent=2))
