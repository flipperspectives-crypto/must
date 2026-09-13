#!/usr/bin/env python3
"""Adversarial battle test for must. Run the CLI. Do not mock prove."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

MUST = Path(__file__).resolve().parents[1] / "scripts" / "must.py"
PASS = 0
FAIL = 0
RESULTS: list[str] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        RESULTS.append(f"PASS  {name}")
        return
    FAIL += 1
    extra = f" — {detail}" if detail else ""
    RESULTS.append(f"FAIL  {name}{extra}")


class Harness:
    def __init__(self) -> None:
        self.home = Path(tempfile.mkdtemp(prefix="must-battle-home-"))
        self.work = Path(tempfile.mkdtemp(prefix="must-battle-work-"))
        self._git()

    def close(self) -> None:
        shutil.rmtree(self.home, ignore_errors=True)
        shutil.rmtree(self.work, ignore_errors=True)

    def _git(self) -> None:
        self.run_raw(["git", "init", "-q"], cwd=self.work)
        self.run_raw(["git", "config", "user.email", "battle@t"], cwd=self.work)
        self.run_raw(["git", "config", "user.name", "battle"], cwd=self.work)
        (self.work / "anchor").write_text("present\n")
        self.run_raw(["git", "add", "anchor"], cwd=self.work)
        self.run_raw(["git", "commit", "-qm", "i"], cwd=self.work)

    def run_raw(self, argv: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        merged = os.environ.copy()
        merged["MUST_HOME"] = str(self.home)
        merged.pop("MUST_AGENT", None)
        if env:
            merged.update(env)
        return subprocess.run(argv, cwd=cwd or self.work, text=True, capture_output=True, env=merged)

    def must(self, *args: str, env: dict[str, str] | None = None, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        return self.run_raw([sys.executable, str(MUST), *args], cwd=cwd, env=env)

    def j(self, *args: str, **kwargs: object) -> tuple[subprocess.CompletedProcess[str], object]:
        proc = self.must("--json", *args, **kwargs)  # type: ignore[arg-type]
        payload: object = None
        if proc.stdout.strip():
            try:
                payload = json.loads(proc.stdout)
            except json.JSONDecodeError:
                payload = {"_unparsed": proc.stdout}
        return proc, payload


def show_status(h: Harness, req_id: str) -> str:
    _, payload = h.j("show", req_id)
    assert isinstance(payload, dict)
    return str(payload["status"])


def evidence(h: Harness, req_id: str) -> list[dict]:
    _, payload = h.j("show", req_id)
    assert isinstance(payload, dict)
    return list(payload.get("evidence") or [])


def battle() -> int:
    h = Harness()
    try:
        _run(h)
    finally:
        h.close()
    print("\n".join(RESULTS))
    print(f"\n{PASS} passed, {FAIL} failed, {PASS + FAIL} cases")
    return 1 if FAIL else 0


def _run(h: Harness) -> None:
    proc, payload = h.j("init", "--name", "battle")
    record("init writes toml and sqlite", proc.returncode == 0 and (h.work / ".must.toml").exists() and (h.home / "battle.sqlite").exists(), proc.stderr)
    record("init json names project", isinstance(payload, dict) and payload.get("project") == "battle", str(payload))

    proc, _ = h.j("init", "--name", "other")
    toml = (h.work / ".must.toml").read_text()
    record("second init does not clobber project name", "battle" in toml and "other" not in toml, toml)

    proc = h.must("--json", "status")
    payload = json.loads(proc.stdout) if proc.stdout.strip() else {}
    record(
        "empty ledger is not ready",
        proc.returncode != 0 or payload.get("ready") is False,
        f"exit={proc.returncode} payload={payload}",
    )
    record("empty ledger ready is false", payload.get("ready") is False, str(payload))

    bad_ids = ["", "1bad", "../etc", "has space", "bad/id", "-x"]
    rejected = True
    for bad in bad_ids:
        args = ["add", "--id", bad, "--title", "x"] if bad else ["add", "--id", "", "--title", "x"]
        p = h.must(*args)
        if p.returncode == 0:
            rejected = False
            break
    record("junk ids rejected", rejected)

    p = h.must("add", "--id", "R1", "--title", "anchor present", "--body", "anchor file exists")
    record("add draft", p.returncode == 0, p.stderr)
    p = h.must("add", "--id", "R1", "--title", "dup")
    record("duplicate id rejected", p.returncode != 0, p.stdout + p.stderr)

    p = h.must("--agent", "add", "--id", "R2", "--title", "second", "--body", "second contract")
    record("agent may add a draft", p.returncode == 0, p.stderr)

    p = h.must("--agent", "freeze", "R1")
    record("agent cannot freeze via --agent", p.returncode != 0 and "cannot freeze" in (p.stderr + p.stdout), p.stderr)
    record("R1 still draft after agent freeze", show_status(h, "R1") == "draft")

    p = h.must("freeze", "R1", env={"MUST_AGENT": "1"})
    record("MUST_AGENT=1 cannot freeze", p.returncode != 0, p.stderr)

    p = h.must("prove", "R1", "--cmd", "true")
    record("cannot prove a draft", p.returncode != 0, p.stderr)
    record("draft prove did not mint evidence", evidence(h, "R1") == [])

    p = h.must("edit", "R1", "--body", "edited-before-freeze")
    record("human can edit a draft", p.returncode == 0, p.stderr)
    _, shown = h.j("show", "R1")
    record("draft edit changed body", isinstance(shown, dict) and shown.get("body") == "edited-before-freeze", str(shown))

    p = h.must("--agent", "edit", "R1", "--body", "agent-rewrite")
    record("agent cannot edit", p.returncode != 0, p.stderr)

    p = h.must("freeze", "R1")
    record("human freeze", p.returncode == 0, p.stderr)
    frozen_body = json.loads(h.must("--json", "show", "R1").stdout)["body"]
    gen1 = json.loads(h.must("--json", "show", "R1").stdout)["generation"]

    p = h.must("edit", "R1", "--body", "sneak-rewrite")
    record("cannot edit frozen body", p.returncode != 0, p.stderr)
    _, shown = h.j("show", "R1")
    record("frozen body unchanged after edit attempt", isinstance(shown, dict) and shown.get("body") == frozen_body, str(shown))

    p = h.must("accept", "R1")
    record("cannot accept frozen (unproven)", p.returncode != 0, p.stderr)

    p = h.must("prove", "R1", "--cmd", "false")
    record("false does not prove", p.returncode != 0, p.stderr)
    record("false leaves status frozen", show_status(h, "R1") == "frozen")
    ev = evidence(h, "R1")
    record("false still records FAIL evidence", len(ev) == 1 and ev[0]["ok"] == 0, str(ev))

    marker = h.work / "ran.flag"
    p = h.must("prove", "R1", "--cmd", "echo missing-token", "--contains", "TOKEN-NEVER")
    record("missing contains does not prove", p.returncode != 0, p.stderr)
    record("missing contains leaves frozen", show_status(h, "R1") == "frozen")

    p = h.must("prove", "R1", "--cmd", "true", "--contains", "")
    empty_contains_proved = p.returncode == 0 and show_status(h, "R1") == "proven"
    record("empty --contains is not a free pass", not empty_contains_proved, f"exit={p.returncode} status={show_status(h, 'R1')}")
    if empty_contains_proved:
        h.must("reopen", "R1")
        gen1 = json.loads(h.must("--json", "show", "R1").stdout)["generation"]

    before = len(evidence(h, "R1"))
    p = h.must("prove", "R1", "--cmd", f"touch {marker} && test -f anchor", "--expected-generation", "deadbeef")
    record("stale generation rejected", p.returncode != 0, p.stderr)
    record("stale generation did not run the command", not marker.exists(), "marker exists")
    record("stale generation evidence count unchanged", len(evidence(h, "R1")) == before, str(len(evidence(h, "R1"))))

    p = h.must("prove", "R1", "--cmd", f"touch {marker} && test -f anchor", "--expected-generation", gen1)
    record("matching generation prove runs", p.returncode == 0 and marker.exists(), p.stderr + p.stdout)
    record("successful prove sets proven", show_status(h, "R1") == "proven")
    record("success evidence marked ok", evidence(h, "R1")[-1]["ok"] == 1)

    p = h.must("prove", "R1", "--cmd", "sleep 5", "--timeout", "1")
    record("timeout does not prove", p.returncode != 0, p.stderr)
    record("timeout leaves proven (does not reopen)", show_status(h, "R1") == "proven")

    p = h.must("--agent", "accept", "R1")
    record("agent cannot accept", p.returncode != 0, p.stderr)
    record("still proven after agent accept", show_status(h, "R1") == "proven")

    p = h.must("accept", "R1")
    record("human accept proven", p.returncode == 0, p.stderr)
    record("accepted status", show_status(h, "R1") == "accepted")

    p = h.must("prove", "R1", "--cmd", "true")
    record("cannot prove accepted without --force", p.returncode != 0, p.stderr)

    p = h.must("--agent", "reopen", "R1")
    record("agent cannot reopen", p.returncode != 0, p.stderr)

    old_gen = json.loads(h.must("--json", "show", "R1").stdout)["generation"]
    p = h.must("reopen", "R1")
    record("human reopen", p.returncode == 0, p.stderr)
    record("reopen returns frozen", show_status(h, "R1") == "frozen")
    new_gen = json.loads(h.must("--json", "show", "R1").stdout)["generation"]
    record("reopen mints new generation", new_gen != old_gen, f"{old_gen} -> {new_gen}")
    shown = json.loads(h.must("--json", "show", "R1").stdout)
    record("reopen clears proven_at", shown.get("proven_at") is None, str(shown.get("proven_at")))

    p = h.must("prove", "R1", "--cmd", "true", "--expected-generation", old_gen)
    record("old generation cannot prove after reopen", p.returncode != 0, p.stderr)

    sub = h.work / "nested" / "deep"
    sub.mkdir(parents=True)
    p = h.must("prove", "R1", "--cmd", "test -f anchor", cwd=sub)
    record("prove from subdirectory uses repo root", p.returncode == 0, p.stderr)
    record("subdir prove sets proven", show_status(h, "R1") == "proven")

    p = h.must("freeze", "R2")
    record("freeze R2", p.returncode == 0, p.stderr)
    proc, payload = h.j("status")
    record("status exits 1 while unmet remain", proc.returncode == 1, str(payload))
    record("status lists unmet R2", isinstance(payload, dict) and "R2" in payload.get("unmet", []), str(payload))

    p = h.must("prove", "R2", "--cmd", "true")
    record("prove R2", p.returncode == 0, p.stderr)
    proc, payload = h.j("status")
    record("status exits 0 when all proven", proc.returncode == 0 and payload.get("ready") is True, str(payload))

    proc, payload = h.j("list", "--unmet")
    record("list --unmet is empty when all proven", proc.returncode == 0 and payload == [], str(payload))

    p = h.must("render")
    md = h.work / "MUST.md"
    record("render writes MUST.md", p.returncode == 0 and md.exists(), p.stderr)
    text = md.read_text()
    record("render includes frozen contract text", "edited-before-freeze" in text, text[:400])
    record("render does not include sneak-rewrite", "sneak-rewrite" not in text)

    # JSON on error path
    p = h.must("--json", "show", "NO-SUCH")
    json_ok = False
    try:
        err_payload = json.loads(p.stdout) if p.stdout.strip() else json.loads(p.stderr)
        json_ok = isinstance(err_payload, dict)
    except json.JSONDecodeError:
        json_ok = False
    record("json errors are JSON", p.returncode != 0 and json_ok, f"stdout={p.stdout!r} stderr={p.stderr!r}")

    # isolation
    h2 = Harness()
    try:
        h2.must("init", "--name", "otherbox")
        h2.must("add", "--id", "R1", "--title", "other")
        _, here = h.j("show", "R1")
        _, there = h2.j("show", "R1")
        record(
            "ledgers do not leak across MUST_HOME",
            isinstance(here, dict) and isinstance(there, dict) and here.get("title") != there.get("title"),
            f"{here.get('title') if isinstance(here, dict) else here} vs {there.get('title') if isinstance(there, dict) else there}",
        )
    finally:
        h2.close()

    # --exit 1 with false is allowed (explicit expected failure) but records the real exit
    h.must("add", "--id", "R3", "--title", "expect fail")
    h.must("freeze", "R3")
    p = h.must("--json", "prove", "R3", "--cmd", "false", "--exit", "1")
    payload = json.loads(p.stdout) if p.stdout.strip() else {}
    record("explicit --exit 1 on false is proven", p.returncode == 0 and payload.get("ok") is True, str(payload))
    record("explicit --exit still records exit_code 1", evidence(h, "R3")[-1]["exit_code"] == 1)

    # stderr contains counts
    h.must("add", "--id", "R4", "--title", "stderr token")
    h.must("freeze", "R4")
    p = h.must("prove", "R4", "--cmd", "echo token-err >&2", "--contains", "token-err")
    record("contains matches stderr", p.returncode == 0, p.stderr)


if __name__ == "__main__":
    raise SystemExit(battle())
