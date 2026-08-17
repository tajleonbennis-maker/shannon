#!/usr/bin/env python3
"""
Shannon 扫描进度可视化快照生成器（轻量方案）

读取 workspace 的 session.json + workflow.log，生成一个自包含的 HTML
快照页面（无外部依赖，单文件），展示：
  - 扫描元信息（目标/状态/成本/模型）
  - 管线阶段进度（Pre-recon → Recon → 5×Vuln → 5×Exploit → Report）
  - Agent 执行明细（每个 agent 的状态/耗时/成本/token）
  - 实时活动流（最近工具调用 + LLM 轮次，来自 workflow.log）

用法:
  python3 shannon_snapshot.py <workspace_dir> [--out report.html] [--live]
  --live: 每 30 秒刷新页面（适合挂后台持续监控）
"""

import argparse
import html
import json
import os
import re
import sys
from datetime import datetime, timezone

# ---------- 阶段定义 ----------

PIPELINE_STAGES = [
    ("pre-recon", "Pre-Recon", "源码分析"),
    ("recon", "Recon", "攻击面测绘"),
    ("injection", "Vuln: Injection", "注入分析"),
    ("xss", "Vuln: XSS", "XSS 分析"),
    ("auth", "Vuln: Auth", "认证分析"),
    ("authz", "Vuln: Authz", "授权分析"),
    ("ssrf", "Vuln: SSRF", "SSRF 分析"),
    ("exploit-injection", "Exploit: Injection", "注入利用"),
    ("exploit-xss", "Exploit: XSS", "XSS 利用"),
    ("exploit-auth", "Exploit: Auth", "认证利用"),
    ("exploit-authz", "Exploit: Authz", "授权利用"),
    ("exploit-ssrf", "Exploit: SSRF", "SSRF 利用"),
    ("report", "Report", "报告生成"),
]

# agent 名到阶段名的映射（session-manager 里 AGENTS 的 key 格式）
AGENT_PHASE = {
    "pre-recon": "pre-recon",
    "recon": "recon",
    "vuln-injection": "injection",
    "vuln-xss": "xss",
    "vuln-auth": "auth",
    "vuln-authz": "authz",
    "vuln-ssrf": "ssrf",
    "exploit-injection": "exploit-injection",
    "exploit-xss": "exploit-xss",
    "exploit-auth": "exploit-auth",
    "exploit-authz": "exploit-authz",
    "exploit-ssrf": "exploit-ssrf",
    "report": "report",
}


# ---------- 数据读取 ----------

def load_json(path):
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def find_file(base, *rel):
    for c in [
        os.path.join(base, *rel),
        os.path.join(base, ".shannon", *rel),
    ]:
        if os.path.exists(c):
            return c
    return None


def read_workflow_log(workspace):
    """读取 workflow.log 最近 N 行活动流。"""
    log_path = find_file(workspace, "workflow.log")
    if not log_path:
        return []
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return []
    events = []
    for line in lines[-200:]:
        line = line.strip()
        if not line or line.startswith("="):
            continue
        m = re.match(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] \[(\w+)\] \[(\w+)\](?:: (.*))?", line)
        if m:
            events.append({
                "time": m.group(1),
                "agent": m.group(2),
                "type": m.group(3),
                "detail": (m.group(4) or "")[:200],
            })
    return events[-80:]


def collect_agents(session):
    agents = None
    if isinstance(session, dict):
        agents = session.get("agents") or (session.get("metrics") or {}).get("agents")
    rows = []
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
                        "agent": name, "phase": AGENT_PHASE.get(name, name),
                        "attempt": at.get("attempt_number", 1),
                        "status": "success" if at.get("success") else "failed",
                        "duration_ms": at.get("duration_ms", 0),
                        "cost_usd": at.get("cost_usd", 0),
                        "input_tokens": at.get("input_tokens", 0),
                        "output_tokens": at.get("output_tokens", 0),
                        "turns": at.get("turns", 0),
                        "model": at.get("model", ""),
                    })
    return rows


# ---------- HTML 渲染 ----------

def severity_color(sev):
    return {
        "Critical": "#a32d2d", "High": "#d85a30", "Medium": "#ba7517", "Low": "#0f6e56",
    }.get(sev, "#5f5e5a")


def render(workspace, scan, agents, events, live):
    scan_id = scan.get("id", "?")
    status = scan.get("status", "?")
    status_color = {"running": "#185fa5", "success": "#0f6e56", "failed": "#a32d2d"}.get(status, "#5f5e5a")

    # 阶段状态
    phase_status = {}
    for agent in agents:
        phase = agent["phase"]
        if phase not in phase_status or agent["status"] == "success":
            phase_status[phase] = agent["status"]
    if scan.get("status") == "running":
        # 找出当前正在执行的阶段（最新 agent 日志）
        for p in [x[0] for x in PIPELINE_STAGES]:
            phase_status.setdefault(p, "pending")

    stages_html = []
    for key, name, desc in PIPELINE_STAGES:
        st = phase_status.get(key, "pending")
        colors = {
            "success": ("#EAF3DE", "#3B6D11"),
            "failed": ("#FCEBEB", "#A32D2D"),
            "running": ("#E6F1FB", "#185FA5"),
            "pending": ("#F1EFE8", "#888780"),
        }
        bg, fg = colors.get(st, colors["pending"])
        icon = {"success": "✓", "failed": "✗", "running": "●", "pending": "○"}.get(st, "○")
        stages_html.append(
            f'<div style="display:inline-block;min-width:128px;margin:6px;padding:10px 12px;'
            f'background:{bg};border:1px solid {fg}55;border-radius:10px;">'
            f'<div style="color:{fg};font-weight:600;font-size:13px;">{icon} {name}</div>'
            f'<div style="color:{fg}cc;font-size:11px;margin-top:2px;">{desc}</div>'
            f'</div>'
        )

    # Agent 表格
    agent_rows = ""
    for a in agents:
        sev = "success" if a["status"] == "success" else "failed"
        c = "#0f6e56" if sev == "success" else "#a32d2d"
        agent_rows += (
            f'<tr><td style="padding:6px 10px;border-bottom:1px solid #eee;font-family:monospace;font-size:12px;">{html.escape(a["agent"])}</td>'
            f'<td style="padding:6px 10px;border-bottom:1px solid #eee;color:{c};font-weight:600;">{a["status"]}</td>'
            f'<td style="padding:6px 10px;border-bottom:1px solid #eee;">attempt {a["attempt"]}</td>'
            f'<td style="padding:6px 10px;border-bottom:1px solid #eee;">{a["turns"]} turns</td>'
            f'<td style="padding:6px 10px;border-bottom:1px solid #eee;">{a["duration_ms"]/1000:.0f}s</td>'
            f'<td style="padding:6px 10px;border-bottom:1px solid #eee;">${a["cost_usd"]:.3f}</td>'
            f'<td style="padding:6px 10px;border-bottom:1px solid #eee;font-family:monospace;font-size:11px;">{html.escape(a["model"] or "-")}</td></tr>'
        )
    if not agent_rows:
        agent_rows = '<tr><td colspan="7" style="padding:12px;color:#888;">暂无 agent 执行记录</td></tr>'

    # 活动流
    event_html = ""
    for e in events:
        type_color = {
            "LLM": "#534ab7", "TOOL": "#0f6e56", "AGENT": "#185fa5",
            "PHASE": "#ba7517",
        }.get(e["type"], "#5f5e5a")
        event_html += (
            f'<div style="padding:4px 0;font-size:12px;border-bottom:1px solid #f0f0f0;">'
            f'<span style="color:#999;font-family:monospace;font-size:11px;">{e["time"]}</span> '
            f'<span style="color:{type_color};font-weight:600;margin:0 4px;">[{e["type"]}]</span> '
            f'<span style="color:#666;">{html.escape(e["agent"])}</span> '
            f'<span style="color:#333;">{html.escape(e["detail"])}</span></div>'
        )
    if not event_html:
        event_html = '<div style="color:#888;padding:8px;">暂无活动日志</div>'

    auto_refresh = '<meta http-equiv="refresh" content="30">' if live else ""
    generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
{auto_refresh}
<title>Shannon 扫描监控 — {html.escape(scan_id)}</title>
<style>
body{{font-family:-apple-system,'PingFang SC','Microsoft YaHei',sans-serif;background:#fafafa;color:#222;margin:0;padding:24px;}}
.card{{background:#fff;border:1px solid #e5e5e5;border-radius:14px;padding:18px 20px;margin-bottom:16px;box-shadow:0 1px 3px rgba(0,0,0,.04);}}
h1{{font-size:18px;margin:0 0 4px;}}
h2{{font-size:15px;margin:0 0 12px;color:#333;}}
.meta{{font-size:13px;color:#666;line-height:1.8;}}
table{{border-collapse:collapse;width:100%;}}
th{{text-align:left;padding:6px 10px;font-size:12px;color:#888;border-bottom:2px solid #eee;}}
</style>
</head>
<body>
<div class="card">
  <h1>Shannon 扫描监控 <span style="color:{status_color};">({html.escape(status)})</span></h1>
  <div class="meta">
    目标: <b>{html.escape(scan.get('target_url',''))}</b> ｜
    扫描 ID: <code>{html.escape(scan_id)}</code> ｜
    成本: <b>${scan.get('total_cost_usd',0):.3f}</b> ｜
    开始: {html.escape(str(scan.get('created_at',''))[:19])} ｜
    生成: {generated}
  </div>
</div>
<div class="card">
  <h2>管线进度</h2>
  <div>{''.join(stages_html)}</div>
</div>
<div class="card">
  <h2>Agent 执行明细</h2>
  <table>
    <tr><th>Agent</th><th>状态</th><th>尝试</th><th>轮次</th><th>耗时</th><th>成本</th><th>模型</th></tr>
    {agent_rows}
  </table>
</div>
<div class="card">
  <h2>实时活动流（最近 {len(events)} 条）</h2>
  <div style="max-height:420px;overflow-y:auto;">{event_html}</div>
</div>
</body>
</html>"""


# ---------- main ----------

def main():
    parser = argparse.ArgumentParser(description="Shannon 扫描可视化快照")
    parser.add_argument("workspace", help="workspace 目录")
    parser.add_argument("--out", default=None, help="HTML 输出路径")
    parser.add_argument("--live", action="store_true", help="页面 30 秒自动刷新")
    args = parser.parse_args()

    session = load_json(find_file(args.workspace, "session.json"))
    if not session:
        print(f"[ERR] 未找到 session.json: {args.workspace}", file=sys.stderr)
        sys.exit(1)

    sess = session.get("session") or {}
    metrics = session.get("metrics") or {}
    scan = {
        "id": sess.get("id", ""),
        "target_url": sess.get("webUrl", ""),
        "status": sess.get("status", ""),
        "created_at": sess.get("createdAt", ""),
        "total_cost_usd": metrics.get("total_cost_usd", 0),
    }
    agents = collect_agents(session)
    events = read_workflow_log(args.workspace)

    out = args.out or os.path.join(args.workspace, "shannon-snapshot.html")
    html_out = render(args.workspace, scan, agents, events, args.live)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html_out)
    print(f"[OK] 快照 → {out}")
    print(f"  状态: {scan['status']} | agents: {len(agents)} | 活动: {len(events)} 条")


if __name__ == "__main__":
    main()
