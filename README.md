# must

[![battle](https://github.com/flipperspectives-crypto/must/actions/workflows/battle.yml/badge.svg)](https://github.com/flipperspectives-crypto/must/actions/workflows/battle.yml)

A requirement is a contract. Once frozen, nobody — including the coding agent — may rewrite it. They may only attach **evidence**, and evidence is a command that ran just now.

## Five minutes

Needs Python 3.11+ and git.

```bash
git clone https://github.com/flipperspectives-crypto/must.git
cd must
python3 tests/battle.py
```

Expect `62 passed, 0 failed` and exit 0. That is the product. If it is not green, the contract is a story.

Install the CLI only if you want to freeze your own:

```bash
install -m 0755 scripts/must.py ~/.local/bin/must
```

kata tracks work. roborev checks the diff. **must** answers the question agents fail at: *did we actually satisfy what was asked?*

```
$ must add --id R1 --title "login rejects a bad password" \
    --body "POST /login with a wrong password returns 401."
$ must freeze R1
$ must prove R1 --cmd 'make test-login-401' --contains '401'
PROVEN R1  exit 0
$ must accept R1
```

`--agent` (or `MUST_AGENT=1`) refuses freeze, edit, accept, and reopen. Drafts can come from an agent. The contract cannot.

## Why this exists

Wes McKinney, [The Mythical Agent-Month](https://kenn.io/blog/mythical-agent-month/):

> When generating code is free, knowing when to say ‘no’ is your last defense.

And the [Clanker Constitution](https://github.com/kenn-io/constitution): never claim success without fresh evidence; honor the request as a contract; distinguish verified facts from inference.

Markdown plans die with the session. Chat says “done.” `must prove` either ran the check or it did not. There is no third state.

## Install

```bash
install -m 0755 scripts/must.py ~/.local/bin/must
cd /path/to/repo
must init --name myproject
```

The ledger is local SQLite under `$MUST_HOME` (default `~/.must`). The repo keeps a secret-free `.must.toml`.

## Agent loop

```bash
must --agent --json list --unmet
must --agent prove R1 --cmd 'make test' --contains 'passed'
must --json status          # exit 1 if anything unmet
must render                 # writes MUST.md
```

`prove` records exit code, a SHA-256 of combined output, and a short excerpt. A failing command **does not** move the requirement. Generation is checked if you pass `--expected-generation` from `must show`.

## Not kata

| | kata | must |
| --- | --- | --- |
| Unit | an issue someone will work | a contract that must remain true |
| Who writes it | agents and humans | humans freeze; agents may draft |
| Close | claim with optional evidence | command that ran, or it stays unmet |
| Rewrite | comments, reopen | frozen body is immutable |

Keep roadmaps in the company tracker. Keep in-flight work in kata. Put the few statements you are unwilling to let drift in `must`.

## Status

stdlib Python 3.11. One file. This is the form, not a Go daemon. If the form holds up, the rewrite is obvious.
