#!/usr/bin/env bash
# Reminder helper: verify pyproject version, then print tag + gh release commands.
# Trusted Publishing uploads to PyPI when the GitHub Release is published.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
V="${1:?Usage: $0 X.Y.Z   (must match version in pyproject.toml)}"
if ! grep -q "^version = \"$V\"" pyproject.toml; then
  echo "error: pyproject.toml version is not $V — edit it first." >&2
  exit 1
fi
echo "OK: pyproject.toml version is $V"
echo "Next (after git push of main):"
echo "  git tag -a v$V -m \"Release $V\" && git push origin v$V"
echo "  gh release create v$V --repo IronAdamant/Trammel --title \"v$V\" --generate-notes"
echo "Then wait for the 'Publish to PyPI' workflow and check https://pypi.org/project/trammel/"
