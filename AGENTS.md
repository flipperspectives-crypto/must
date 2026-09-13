# must — agent contract

Requirements in this repo are the spec. Frozen text is not a suggestion.

1. Run `must --agent --json list --unmet` before claiming a task is done.
2. Satisfy unmet ids with `must --agent prove ID --cmd '...'`. The command must actually run. Do not paste old logs.
3. Do not use `--agent` with `freeze`, `edit`, `accept`, or `reopen`. Those are human.
4. Do not edit `.must.toml` or the SQLite ledger by hand.
5. After a successful prove, `must render` so `MUST.md` matches the ledger.
6. `must --json status` exiting 1 means you are not done.

Direct user instructions override this file.
