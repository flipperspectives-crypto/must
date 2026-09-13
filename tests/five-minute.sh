#!/bin/sh
# Stranger path: run the battle test with nothing but this tree and Python 3.11+.
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
python3 --version
python3 "$ROOT/tests/battle.py"
