#!/usr/bin/env python3
"""Frozen requirements. Agents attach evidence. Evidence is something that ran."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import tomllib
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9._-]{0,63}$")
STATUSES = ("draft", "frozen", "proven", "accepted")
HOME = Path(os.environ.get("MUST_HOME", Path.home() / ".must"))


class Error(SystemExit):
    def __init__(self, message: str, code: int = 2, payload: dict[str, Any] | None = None) -> None:
        self.payload = payload or {
            "error": {"code": "must_error", "message": message, "retryable": False}
        }
        print(f"must: {message}", file=sys.stderr)
        if "--json" in sys.argv:
            json.dump(self.payload, sys.stdout)
            sys.stdout.write("\n")
        super().__init__(code)


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_generation() -> str:
    return uuid.uuid4().hex


def emit(obj: Any, as_json: bool, lines: list[str] | None = None) -> None:
    if as_json:
        json.dump(obj, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return
    if lines is None:
        print(obj)
        return
    print("\n".join(lines))


def find_root(start: Path | None = None) -> Path:
    cur = (start or Path.cwd()).resolve()
    for path in [cur, *cur.parents]:
        if (path / ".must.toml").exists() or (path / ".git").exists():
            return path
    return cur


def load_project(root: Path) -> dict[str, str]:
    cfg = root / ".must.toml"
    if cfg.exists():
        data = tomllib.loads(cfg.read_text())
        name = str(data.get("project") or root.name)
        return {"name": name, "root": str(root)}
    return {"name": root.name, "root": str(root)}


def db_path(project: str) -> Path:
    HOME.mkdir(parents=True, exist_ok=True)
    return HOME / f"{project}.sqlite"


def connect(project: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path(project))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS requirements (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            status TEXT NOT NULL,
            generation TEXT NOT NULL,
            created_at TEXT NOT NULL,
            frozen_at TEXT,
            proven_at TEXT,
            accepted_at TEXT
        );
        CREATE TABLE IF NOT EXISTS evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            req_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            command TEXT,
            exit_code INTEGER,
            ok INTEGER NOT NULL,
            excerpt TEXT,
            output_sha TEXT,
            observed_at TEXT NOT NULL,
            FOREIGN KEY(req_id) REFERENCES requirements(id)
        );
        """
    )
    return conn


def get_req(conn: sqlite3.Connection, req_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM requirements WHERE id = ?", (req_id,)).fetchone()
    if row is None:
        raise Error(f"unknown requirement {req_id}", payload={
            "error": {"code": "not_found", "message": f"unknown requirement {req_id}", "retryable": False}
        })
    return row


def evidence_rows(conn: sqlite3.Connection, req_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT kind, command, exit_code, ok, excerpt, output_sha, observed_at "
        "FROM evidence WHERE req_id = ? ORDER BY id",
        (req_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def req_dict(row: sqlite3.Row, evidence: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    data = {
        "id": row["id"],
        "title": row["title"],
        "body": row["body"],
        "status": row["status"],
        "generation": row["generation"],
        "created_at": row["created_at"],
        "frozen_at": row["frozen_at"],
        "proven_at": row["proven_at"],
        "accepted_at": row["accepted_at"],
    }
    if evidence is not None:
        data["evidence"] = evidence
    return data


def refuse_agent(args: argparse.Namespace, action: str) -> None:
    if args.agent:
        raise Error(
            f"agents cannot {action}; a human must run this",
            payload={"error": {"code": "human_required", "message": f"agents cannot {action}", "retryable": False}},
        )


def cmd_init(args: argparse.Namespace) -> None:
    root = find_root()
    cfg = root / ".must.toml"
    name = args.name or root.name
    if not cfg.exists():
        cfg.write_text(f'project = "{name}"\n')
    project = load_project(root)
    connect(project["name"]).close()
    emit(
        {"project": project["name"], "root": project["root"], "ledger": str(db_path(project["name"]))},
        args.json,
        [f"project {project['name']}", f"ledger {db_path(project['name'])}"],
    )


def cmd_add(args: argparse.Namespace) -> None:
    if not ID_RE.match(args.id):
        raise Error("id must match [A-Za-z][A-Za-z0-9._-]{0,63}")
    project = load_project(find_root())
    conn = connect(project["name"])
    if conn.execute("SELECT 1 FROM requirements WHERE id = ?", (args.id,)).fetchone():
        raise Error(f"{args.id} already exists")
    body = args.body or args.title
    conn.execute(
        "INSERT INTO requirements(id, title, body, status, generation, created_at) "
        "VALUES (?, ?, ?, 'draft', ?, ?)",
        (args.id, args.title, body, new_generation(), now()),
    )
    conn.commit()
    row = get_req(conn, args.id)
    emit(req_dict(row, []), args.json, [f"draft {args.id}: {args.title}"])


def cmd_edit(args: argparse.Namespace) -> None:
    refuse_agent(args, "edit a requirement")
    project = load_project(find_root())
    conn = connect(project["name"])
    row = get_req(conn, args.id)
    if row["status"] != "draft":
        raise Error(f"{args.id} is {row['status']}; unfreeze before editing the contract")
    title = args.title or row["title"]
    body = args.body or row["body"]
    conn.execute("UPDATE requirements SET title = ?, body = ? WHERE id = ?", (title, body, args.id))
    conn.commit()
    emit(req_dict(get_req(conn, args.id)), args.json, [f"edited {args.id}"])


def cmd_freeze(args: argparse.Namespace) -> None:
    refuse_agent(args, "freeze a requirement")
    project = load_project(find_root())
    conn = connect(project["name"])
    row = get_req(conn, args.id)
    if row["status"] not in ("draft", "frozen"):
        raise Error(f"{args.id} is {row['status']}")
    conn.execute(
        "UPDATE requirements SET status = 'frozen', frozen_at = COALESCE(frozen_at, ?) WHERE id = ?",
        (now(), args.id),
    )
    conn.commit()
    emit(req_dict(get_req(conn, args.id)), args.json, [f"frozen {args.id}"])


def cmd_reopen(args: argparse.Namespace) -> None:
    refuse_agent(args, "reopen a requirement")
    project = load_project(find_root())
    conn = connect(project["name"])
    row = get_req(conn, args.id)
    conn.execute(
        "UPDATE requirements SET status = 'frozen', proven_at = NULL, accepted_at = NULL, generation = ? WHERE id = ?",
        (new_generation(), args.id),
    )
    conn.commit()
    emit(req_dict(get_req(conn, args.id)), args.json, [f"reopened {args.id} (new generation)"])


def run_cmd(command: str, cwd: Path, timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        shell=True,
        cwd=cwd,
        text=True,
        capture_output=True,
        timeout=timeout,
    )


def cmd_prove(args: argparse.Namespace) -> None:
    project = load_project(find_root())
    root = Path(project["root"])
    conn = connect(project["name"])
    row = get_req(conn, args.id)
    if row["status"] == "draft":
        raise Error(f"{args.id} is still a draft; freeze it before proving")
    if row["status"] == "accepted" and not args.force:
        raise Error(f"{args.id} is accepted; reopen it to attach new evidence")
    if args.contains is not None and args.contains == "":
        raise Error("--contains must be a non-empty substring")
    if args.expected_generation and args.expected_generation != row["generation"]:
        raise Error(
            "generation mismatch; refresh must show",
            payload={"error": {"code": "generation_changed", "message": "generation mismatch", "retryable": True}},
        )
    try:
        result = run_cmd(args.cmd, root, args.timeout)
    except subprocess.TimeoutExpired as exc:
        raise Error(f"command timed out after {args.timeout}s") from exc
    combined = (result.stdout or "") + (result.stderr or "")
    excerpt = combined[-2000:]
    digest = hashlib.sha256(combined.encode("utf-8", errors="replace")).hexdigest()
    expect_exit = args.exit
    contains_ok = True if args.contains is None else args.contains in combined
    ok = result.returncode == expect_exit and contains_ok
    conn.execute(
        "INSERT INTO evidence(req_id, kind, command, exit_code, ok, excerpt, output_sha, observed_at) "
        "VALUES (?, 'cmd', ?, ?, ?, ?, ?, ?)",
        (args.id, args.cmd, result.returncode, int(ok), excerpt, digest, now()),
    )
    if ok and row["status"] in ("frozen", "proven"):
        conn.execute(
            "UPDATE requirements SET status = 'proven', proven_at = ? WHERE id = ?",
            (now(), args.id),
        )
    conn.commit()
    payload = {
        "id": args.id,
        "ok": ok,
        "exit_code": result.returncode,
        "expected_exit": expect_exit,
        "contains": args.contains,
        "contains_ok": contains_ok,
        "output_sha": digest,
        "excerpt": excerpt[-400:],
        "status": get_req(conn, args.id)["status"],
    }
    if not ok:
        reason = []
        if result.returncode != expect_exit:
            reason.append(f"exit {result.returncode}, expected {expect_exit}")
        if not contains_ok:
            reason.append(f"output missing {args.contains!r}")
        emit(payload, args.json, [f"FAIL {args.id}: " + "; ".join(reason)])
        raise SystemExit(1)
    emit(payload, args.json, [f"PROVEN {args.id}  exit {result.returncode}  sha {digest[:12]}"])


def cmd_accept(args: argparse.Namespace) -> None:
    refuse_agent(args, "accept a requirement")
    project = load_project(find_root())
    conn = connect(project["name"])
    row = get_req(conn, args.id)
    if row["status"] != "proven":
        raise Error(f"{args.id} is {row['status']}; prove it before accepting")
    conn.execute(
        "UPDATE requirements SET status = 'accepted', accepted_at = ? WHERE id = ?",
        (now(), args.id),
    )
    conn.commit()
    emit(req_dict(get_req(conn, args.id)), args.json, [f"accepted {args.id}"])


def cmd_show(args: argparse.Namespace) -> None:
    project = load_project(find_root())
    conn = connect(project["name"])
    row = get_req(conn, args.id)
    evidence = evidence_rows(conn, args.id)
    payload = req_dict(row, evidence)
    lines = [
        f"{row['id']}  {row['status']}",
        row["title"],
        "",
        row["body"],
        "",
        f"generation {row['generation']}",
    ]
    if evidence:
        lines.append("")
        for item in evidence:
            mark = "ok" if item["ok"] else "FAIL"
            lines.append(f"- {mark} {item['observed_at']} `{item['command']}` exit {item['exit_code']}")
    emit(payload, args.json, lines)


def cmd_list(args: argparse.Namespace) -> None:
    project = load_project(find_root())
    conn = connect(project["name"])
    sql = "SELECT * FROM requirements"
    params: list[str] = []
    if args.status:
        sql += " WHERE status = ?"
        params.append(args.status)
    sql += " ORDER BY id"
    rows = [req_dict(r) for r in conn.execute(sql, params).fetchall()]
    if args.unmet:
        rows = [r for r in rows if r["status"] not in ("proven", "accepted")]
    lines = [f"{r['status']:<9} {r['id']:<16} {r['title']}" for r in rows]
    emit(rows, args.json, lines or ["(no requirements)"])


def cmd_status(args: argparse.Namespace) -> None:
    project = load_project(find_root())
    conn = connect(project["name"])
    rows = [req_dict(r) for r in conn.execute("SELECT * FROM requirements ORDER BY id").fetchall()]
    counts = {s: 0 for s in STATUSES}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    unmet = [r["id"] for r in rows if r["status"] not in ("proven", "accepted")]
    payload = {
        "project": project["name"],
        "counts": counts,
        "unmet": unmet,
        "ready": not unmet and bool(rows),
    }
    summary = " ".join(f"{k}={v}" for k, v in counts.items())
    if not rows:
        lines = ["no requirements"]
    elif unmet:
        lines = [summary, "unmet: " + ", ".join(unmet)]
    else:
        lines = [summary, "all requirements proven or accepted"]
    emit(payload, args.json, lines)
    if unmet:
        raise SystemExit(1)


def cmd_render(args: argparse.Namespace) -> None:
    project = load_project(find_root())
    root = Path(project["root"])
    conn = connect(project["name"])
    rows = conn.execute("SELECT * FROM requirements ORDER BY id").fetchall()
    lines = [
        f"# Requirements — {project['name']}",
        "",
        "Frozen statements are the contract. Proven means a command ran and matched.",
        "Accepted means a human signed the proof. Agents may not rewrite frozen text.",
        "",
    ]
    if not rows:
        lines.append("_No requirements yet._")
    for row in rows:
        lines += [f"## {row['id']} · {row['status']}", "", f"**{row['title']}**", "", row["body"], ""]
        ev = evidence_rows(conn, row["id"])
        if ev:
            last = ev[-1]
            mark = "passed" if last["ok"] else "failed"
            lines += [f"Last evidence ({mark}): `{last['command']}` exit {last['exit_code']} at {last['observed_at']}", ""]
    text = "\n".join(lines).rstrip() + "\n"
    dest = Path(args.output) if args.output else root / "MUST.md"
    dest.write_text(text)
    emit({"path": str(dest), "count": len(rows)}, args.json, [str(dest)])


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="must",
        description="Frozen requirements with fail-closed evidence. A close is not a feeling.",
    )
    p.add_argument("--json", action="store_true")
    p.add_argument("--agent", action="store_true", help="agent mode: refuse freeze/edit/accept")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="Bind this repo to a local ledger")
    s.add_argument("--name")
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("add", help="Add a draft requirement")
    s.add_argument("--id", required=True)
    s.add_argument("--title", required=True)
    s.add_argument("--body")
    s.set_defaults(func=cmd_add)

    s = sub.add_parser("edit", help="Edit a draft (human)")
    s.add_argument("id")
    s.add_argument("--title")
    s.add_argument("--body")
    s.set_defaults(func=cmd_edit)

    s = sub.add_parser("freeze", help="Freeze the contract (human)")
    s.add_argument("id")
    s.set_defaults(func=cmd_freeze)

    s = sub.add_parser("prove", help="Run a command and record whether it satisfied the contract")
    s.add_argument("id")
    s.add_argument("--cmd", required=True)
    s.add_argument("--contains", help="require this substring in combined output")
    s.add_argument("--exit", type=int, default=0, dest="exit")
    s.add_argument("--timeout", type=int, default=60)
    s.add_argument("--expected-generation")
    s.add_argument("--force", action="store_true")
    s.set_defaults(func=cmd_prove)

    s = sub.add_parser("accept", help="Human accepts a proven requirement")
    s.add_argument("id")
    s.set_defaults(func=cmd_accept)

    s = sub.add_parser("reopen", help="Return to frozen and mint a new generation (human)")
    s.add_argument("id")
    s.set_defaults(func=cmd_reopen)

    s = sub.add_parser("show", help="Show one requirement and its evidence")
    s.add_argument("id")
    s.set_defaults(func=cmd_show)

    s = sub.add_parser("list", help="List requirements")
    s.add_argument("--status", choices=STATUSES)
    s.add_argument("--unmet", action="store_true")
    s.set_defaults(func=cmd_list)

    s = sub.add_parser("status", help="Exit 1 if anything is unmet")
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("render", help="Write MUST.md")
    s.add_argument("-o", "--output")
    s.set_defaults(func=cmd_render)
    return p


def main() -> None:
    args = build_parser().parse_args()
    if os.environ.get("MUST_AGENT") == "1":
        args.agent = True
    args.func(args)


if __name__ == "__main__":
    main()
