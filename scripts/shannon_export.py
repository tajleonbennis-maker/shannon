#!/usr/bin/env python3
"""
Shannon 扫描结果结构化落库工具（独立模块，不侵入 shannon 核心代码）

读取一个 shannon workspace 的产出（session.json + deliverables/report.json），
标准化后写入 SQLite 数据库（或输出标准化 JSON）。

用法:
  python3 shannon_export.py <workspace_dir> [--db out.db] [--json out.json] [--list]

表结构:
  scan_runs   — 扫描元数据（目标/状态/成本/模型/时间）
  findings    — 漏洞发现（类型/严重度/位置/摘要/利用步骤）
  agents      — 各阶段 agent 执行记录（耗时/成本/token）
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime


# ---------- 数据读取 ----------

def load_json(path):
    """安全读取 JSON 文件，失败返回 None。"""
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def find_file(base, *rel):
    """在 workspace 下定位文件（兼容新旧目录布局）。"""
    candidates = [
        os.path.join(base, *rel),
        os.path.join(base, ".shannon", *rel),
        os.path.join(base, ".shannon", "deliverables", *rel),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


def extract_finding_id(raw):
    """兼容 ExploitFinding / AnalysisFinding 两种形态。"""
    if isinstance(raw, dict):
        return raw.get("id") or raw.get("title") or "unknown"
    return str(raw)


def extract_finding(f, idx):
    """把 report.json 中的 finding 标准化为落库记录。"""
    if not isinstance(f, dict):
        return None
    summary = f.get("summary") or {}
    steps = f.get("exploitationSteps") or []
    step_text = []
    for s in steps:
        if isinstance(s, dict):
            items = s.get("items") or []
            for it in items:
                if isinstance(it, dict) and it.get("kind") == "code":
                    step_text.append(it.get("block", {}).get("content", ""))
                elif isinstance(it, dict) and it.get("kind") == "prose":
                    step_text.append(it.get("text", ""))
    return {
        "id": f.get("id") or f"finding-{idx}",
        "title": f.get("title", ""),
        "category": f.get("category", "Other"),
        "severity": f.get("severity", "Low"),
        "status": f.get("status") or f.get("confidence") or "Identified",
        "vulnerable_location": (summary.get("vulnerableLocation") or "")[:500],
        "overview": (summary.get("overview") or "")[:2000],
        "impact": (summary.get("impact") or "")[:2000],
        "prerequisites": (f.get("prerequisites") or "")[:1000],
        "exploitation_steps": "\n".join(step_text)[:8000],
        "raw_json": json.dumps(f, ensure_ascii=False)[:50000],
    }


def collect_agents(session):
    """从 session.json 的 agents 段收集执行记录。

    数据可能在顶层 `agents` 或 `metrics.agents`（两种布局都兼容）。
    """
    rows = []
    agents = None
    if isinstance(session, dict):
        agents = session.get("agents") or (session.get("metrics") or {}).get("agents")
    if not isinstance(agents, dict):
        return rows
    for name, a in agents.items():
        if not isinstance(a, dict):
            continue
        attempts = a.get("attempts") or []
        if isinstance(attempts, list):
            for at in attempts:
                if isinstance(at, dict):
                    rows.append({
                        "agent": name,
                        "attempt": at.get("attempt_number", 1),
                        "status": at.get("success") is not False and "success" or "failed",
                        "duration_ms": at.get("duration_ms", 0),
                        "cost_usd": at.get("cost_usd", 0),
                        "input_tokens": at.get("input_tokens", 0),
                        "output_tokens": at.get("output_tokens", 0),
                        "cache_read_tokens": at.get("cache_read_tokens", 0),
                        "turns": at.get("turns", 0),
                        "model": at.get("model", ""),
                    })
        else:
            rows.append({
                "agent": name,
                "attempt": 1,
                "status": a.get("status", "unknown"),
                "duration_ms": a.get("final_duration_ms", 0),
                "cost_usd": a.get("total_cost_usd", 0),
                "input_tokens": a.get("total_input_tokens", 0),
                "output_tokens": a.get("total_output_tokens", 0),
                "cache_read_tokens": a.get("total_cache_read_tokens", 0),
                "turns": 0,
                "model": a.get("model", ""),
            })
    return rows


# ---------- SQLite 落库 ----------

SCHEMA = """
CREATE TABLE IF NOT EXISTS scan_runs (
    id TEXT PRIMARY KEY,
    target_url TEXT,
    repo_path TEXT,
    status TEXT,
    created_at TEXT,
    completed_at TEXT,
    total_duration_ms INTEGER,
    total_cost_usd REAL,
    vuln_classes TEXT,
    exploit INTEGER,
    model TEXT,
    report_path TEXT
);

CREATE TABLE IF NOT EXISTS findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id TEXT,
    finding_ref TEXT,
    title TEXT,
    category TEXT,
    severity TEXT,
    status TEXT,
    vulnerable_location TEXT,
    overview TEXT,
    impact TEXT,
    prerequisites TEXT,
    exploitation_steps TEXT,
    raw_json TEXT,
    UNIQUE(scan_id, finding_ref)
);

CREATE TABLE IF NOT EXISTS agents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id TEXT,
    agent TEXT,
    attempt INTEGER,
    status TEXT,
    duration_ms INTEGER,
    cost_usd REAL,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cache_read_tokens INTEGER,
    turns INTEGER,
    model TEXT
);

CREATE INDEX IF NOT EXISTS idx_findings_scan ON findings(scan_id);
CREATE INDEX IF NOT EXISTS idx_findings_sev ON findings(severity);
CREATE INDEX IF NOT EXISTS idx_agents_scan ON agents(scan_id);
"""


def db_upsert_scan(conn, scan_id, scan):
    conn.execute(
        """INSERT OR REPLACE INTO scan_runs
           (id, target_url, repo_path, status, created_at, completed_at,
            total_duration_ms, total_cost_usd, vuln_classes, exploit, model, report_path)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            scan_id,
            scan.get("target_url", ""),
            scan.get("repo_path", ""),
            scan.get("status", ""),
            scan.get("created_at", ""),
            scan.get("completed_at", ""),
            scan.get("total_duration_ms", 0),
            scan.get("total_cost_usd", 0),
            json.dumps(scan.get("vuln_classes", []), ensure_ascii=False),
            1 if scan.get("exploit") else 0,
            scan.get("model", ""),
            scan.get("report_path", ""),
        ),
    )


def process_workspace(workspace, conn=None, out_json=None):
    """处理单个 workspace，返回标准化的 dict。"""
    session_path = find_file(workspace, "session.json")
    session = load_json(session_path)
    if not session:
        raise RuntimeError(f"未找到 session.json: {workspace}")

    sess = session.get("session") or {}
    metrics = session.get("metrics") or {}
    scan_id = sess.get("id") or os.path.basename(workspace.rstrip("/"))

    # 报告文件
    report_path = find_file(workspace, "deliverables", "report.json") or find_file(workspace, "report.json")
    report = load_json(report_path)

    findings_rows = []
    if report:
        findings = report.get("findings") or []
        for idx, f in enumerate(findings):
            row = extract_finding(f, idx)
            if row:
                findings_rows.append(row)

    scan = {
        "id": scan_id,
        "target_url": sess.get("webUrl", ""),
        "repo_path": sess.get("repoPath", ""),
        "status": sess.get("status", ""),
        "created_at": sess.get("createdAt", ""),
        "completed_at": sess.get("completedAt", ""),
        "total_duration_ms": metrics.get("total_duration_ms", 0),
        "total_cost_usd": metrics.get("total_cost_usd", 0),
        "vuln_classes": (sess.get("scope") or {}).get("vulnClasses", []),
        "exploit": (sess.get("scope") or {}).get("exploit", True),
        "model": (metrics.get("agents") or {}).get("pre-recon", {}).get("model", "")
        or (metrics.get("agents") or {}).get("pre-recon", {}).get("attempts", [{}])[0].get("model", ""),
        "report_path": report_path or "",
    }

    agents_rows = collect_agents(session)

    if conn is not None:
        db_upsert_scan(conn, scan_id, scan)
        for f in findings_rows:
            conn.execute(
                """INSERT OR IGNORE INTO findings
                   (scan_id, finding_ref, title, category, severity, status,
                    vulnerable_location, overview, impact, prerequisites,
                    exploitation_steps, raw_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    scan_id, f["id"], f["title"], f["category"], f["severity"], f["status"],
                    f["vulnerable_location"], f["overview"], f["impact"], f["prerequisites"],
                    f["exploitation_steps"], f["raw_json"],
                ),
            )
        for a in agents_rows:
            conn.execute(
                """INSERT INTO agents
                   (scan_id, agent, attempt, status, duration_ms, cost_usd,
                    input_tokens, output_tokens, cache_read_tokens, turns, model)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    scan_id, a["agent"], a["attempt"], a["status"], a["duration_ms"],
                    a["cost_usd"], a["input_tokens"], a["output_tokens"],
                    a["cache_read_tokens"], a["turns"], a["model"],
                ),
            )
        conn.commit()

    result = {"scan": scan, "findings": findings_rows, "agents": agents_rows}

    if out_json:
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"[OK] 标准化 JSON → {out_json}")

    return result


def list_workspaces(root):
    """列出 ~/.shannon/workspaces 下的所有扫描。"""
    if not os.path.isdir(root):
        print(f"workspace 目录不存在: {root}")
        return
    for name in sorted(os.listdir(root)):
        ws = os.path.join(root, name)
        if not os.path.isdir(ws):
            continue
        session_path = find_file(ws, "session.json")
        session = load_json(session_path)
        if not session:
            continue
        sess = session.get("session") or {}
        metrics = session.get("metrics") or {}
        print(
            f"  {name:<40} {sess.get('status','?'):<10} "
            f"${metrics.get('total_cost_usd',0):.3f} "
            f"{sess.get('webUrl','')}"
        )


def main():
    parser = argparse.ArgumentParser(description="Shannon 扫描结果落库工具")
    parser.add_argument("workspace", nargs="?", help="workspace 目录路径")
    parser.add_argument("--db", default="shannon.db", help="SQLite 输出路径")
    parser.add_argument("--json", help="同时输出标准化 JSON 文件")
    parser.add_argument("--list", action="store_true",
                        help="列出所有扫描（参数传 workspaces 根目录）")
    args = parser.parse_args()

    if args.list:
        list_workspaces(args.workspace or os.path.expanduser("~/.shannon/workspaces"))
        return

    if not args.workspace:
        parser.error("需要提供 workspace 目录（或用 --list）")

    conn = sqlite3.connect(args.db)
    try:
        conn.executescript(SCHEMA)
        result = process_workspace(args.workspace, conn=conn, out_json=args.json)
        conn.commit()
    finally:
        conn.close()

    s = result["scan"]
    print(f"[OK] 落库 → {args.db}")
    print(f"  扫描: {s['id']} | {s['target_url']}")
    print(f"  状态: {s['status']} | 成本: ${s['total_cost_usd']:.3f}")
    print(f"  发现: {len(result['findings'])} 条 | agents: {len(result['agents'])} 条")
    if result["findings"]:
        from collections import Counter
        sev = Counter(f["severity"] for f in result["findings"])
        print(f"  严重度分布: {dict(sev)}")


if __name__ == "__main__":
    main()
