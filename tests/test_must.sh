#!/bin/sh
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MUST="$ROOT/scripts/must.py"
export MUST_HOME="$(mktemp -d)"
export PATH="$(dirname "$MUST"):$PATH"
WORKDIR="$(mktemp -d)"
trap 'rm -rf "$MUST_HOME" "$WORKDIR"' EXIT
cd "$WORKDIR"
git init -q
git config user.email t@t
git config user.name t
echo x > f
git add f
git commit -qm i

python3 "$MUST" init --name testdemo
python3 "$MUST" add --id R1 --title "file exists" --body "f is present"
python3 "$MUST" --agent freeze R1 >/tmp/must-freeze.err 2>&1 && {
  echo "agent was allowed to freeze"; exit 1
}
python3 "$MUST" freeze R1
python3 "$MUST" prove R1 --cmd 'false' >/tmp/must-false.out 2>&1 && {
  echo "false proved"; exit 1
}
python3 "$MUST" prove R1 --cmd 'test -f f'
python3 "$MUST" prove R1 --cmd 'echo hello-evidence' --contains 'nope' >/tmp/must-contains.out 2>&1 && {
  echo "missing contains proved"; exit 1
}
python3 "$MUST" --json status >/tmp/must-status.json || true
python3 - <<'PY'
import json
print(open("/tmp/must-status.json").read())
PY
python3 "$MUST" accept R1
python3 "$MUST" --json status
python3 "$MUST" render
test -f MUST.md
echo TEST_OK
