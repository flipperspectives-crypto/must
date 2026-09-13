# Requirements — must

Frozen statements are the contract. Proven means a command ran and matched.
Accepted means a human signed the proof. Agents may not rewrite frozen text.

This file is the public contract for **must** itself. The live ledger lives under `$MUST_HOME`. Re-prove with `python3 tests/battle.py`.

## R-fail-closed · accepted

**Failing checks do not prove**

If the command exits non-zero, `must prove` must fail and the requirement must stay frozen.

## R-agent-boundary · accepted

**Agents cannot freeze**

`must --agent freeze` must refuse. Only a human freezes the contract.

## R-battle · accepted

**Battle test stays green**

`python3 tests/battle.py` exits 0 and prints `0 failed`.
