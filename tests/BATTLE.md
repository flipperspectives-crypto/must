# Battle test

Attacks the claims in `must/README.md` and `must/AGENTS.md` by running the **installed CLI as a subprocess**. No mocked prove. No imported internals for the verdict.

## Claims under fire

1. A failing command does not prove.
2. Missing `--contains` does not prove.
3. Draft cannot be proven; frozen text cannot be edited.
4. `--agent` / `MUST_AGENT=1` cannot freeze, edit, accept, or reopen.
5. `--expected-generation` rejects stale prove.
6. Reopen mints a new generation and drops proven/accepted.
7. Evidence is a command that actually ran (side effects, timeout).
8. `status` is honest: unmet exits 1; empty is not `ready`.
9. `--json` is JSON on both success and CLI errors.
10. Two `MUST_HOME` values do not share a ledger.
11. `--contains ''` is not a free pass.
12. Duplicate / junk ids are rejected.

If a case fails, the contract is not real yet. Do not add features until this file's runner is green.
