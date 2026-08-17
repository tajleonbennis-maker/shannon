#!/usr/bin/env python3
"""
Shannon 实时监控服务（SSE 推送版）

监控 workspace 下的 session.json + workflow.log + agents/*.log，
通过 Server-Sent Events (SSE) 实时推送给浏览器，实现"看着 agent 干活"。

技术栈：纯 Python 标准库（http.server + threading），零第三方依赖。

用法:
  python3 shannon_monitor.py <workspace_dir> [--port 8787] [--history 200] [--token TOKEN]
  然后浏览器打开 http://127.0.0.1:8787  （默认只监听本机）
  带 --token 时：浏览器访问 http://127.0.0.1:8787/?token=TOKEN

安全说明：
  - 默认 --host 127.0.0.1，仅本机可访问
  - 公网部署必须：--host 0.0.0.0 + --token，并在 nginx 反代层再加鉴权
  - /api/state 与 /stream 校验 token（Authorization: Bearer <token> 或 ?token=<token>）

页面功能：
  - 管线阶段进度条（13 个阶段实时变色）
  - Agent 执行明细表（状态/轮次/耗时/成本/模型）
  - 实时活动流（工具调用/LLM 轮次，SSE 推送，无刷新）
  - 元信息（目标/状态/成本/模型）
"""

import argparse
import html
import json
import os
import re
import sys
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

# ============ 阶段定义 ============

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

AGENT_PHASE = {
    "pre-recon": "pre-recon", "recon": "recon",
    "vuln-injection": "injection", "vuln-xss": "xss",
    "vuln-auth": "auth", "vuln-authz": "authz", "vuln-ssrf": "ssrf",
    "exploit-injection": "exploit-injection", "exploit-xss": "exploit-xss",
    "exploit-auth": "exploit-auth", "exploit-authz": "exploit-authz",
    "exploit-ssrf": "exploit-ssrf", "report": "report",
}

WORKSPACE = None
HISTORY = 200
AUTH_TOKEN = None
RUNNING_WINDOW_SEC = 300  # 最近事件在该窗口内 → 判定为 running


# ============ 数据读取 ============

def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def find_file(base, *rel):
    for c in [os.path.join(base, *rel), os.path.join(base, ".shannon", *rel)]:
        if os.path.exists(c):
            return c
    return None


def read_workflow_tail(workspace, limit=500):
    """读取 workflow.log 尾部，返回解析后的事件列表。"""
    log_path = find_file(workspace, "workflow.log")
    if not log_path:
        return []
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return []
    events = []
    for line in lines[-limit:]:
        line = line.strip()
        if not line or line.startswith("="):
            continue
        m = re.match(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] \[([\w-]+)\] \[(\w+)\](?:: (.*))?", line)
        if m:
            events.append({
                "time": m.group(1)[5:],  # MM-DD HH:MM:SS
                "ts": m.group(1),        # 完整 YYYY-MM-DD HH:MM:SS，用于 running 判定
                "agent": m.group(2),
                "type": m.group(3),
                "detail": (m.group(4) or "")[:240],
            })
    return events


def infer_running(events, status):
    """若最近 workflow.log 事件在 RUNNING_WINDOW_SEC 内，判定为 running。"""
    if status in ("running", "failed", "pending", "unknown"):
        for ev in reversed(events):
            ts = ev.get("ts")
            if not ts:
                continue
            try:
                t = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
            if (datetime.now() - t).total_seconds() <= RUNNING_WINDOW_SEC:
                return True
            break  # 最后一条已超时，无需继续
    return False


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
                        "turns": at.get("turns", 0),
                        "model": at.get("model", ""),
                    })
    return rows


def snapshot():
    """构建当前完整状态（JSON 结构，供 SSE 与页面共用）。"""
    session = load_json(find_file(WORKSPACE, "session.json")) or {}
    sess = session.get("session") or {}
    metrics = session.get("metrics") or {}

    # 计算阶段状态
    phase_status = {}
    for a in collect_agents(session):
        p = a["phase"]
        if p not in phase_status or a["status"] == "success":
            phase_status[p] = a["status"]

    status = sess.get("status", "unknown")
    # running 检测：status 还是 running，或 worker 容器活着
    events = read_workflow_tail(WORKSPACE)
    if infer_running(events, status):
        status = "running"

    return {
        "scan": {
            "id": sess.get("id", ""),
            "target": sess.get("webUrl", ""),
            "status": status,
            "created": str(sess.get("createdAt", ""))[:19],
            "cost": metrics.get("total_cost_usd", 0),
            "model": (metrics.get("agents") or {}).get("pre-recon", {}).get("model", ""),
        },
        "phases": [{"key": k, "name": n, "desc": d, "status": phase_status.get(k, "pending")}
                   for k, n, d in PIPELINE_STAGES],
        "agents": collect_agents(session),
        "events": events[-HISTORY:],
        "generated": time.strftime("%H:%M:%S"),
    }


# ============ SSE 广播 ============

class Broadcaster:
    """SSE 客户端管理与事件广播。"""

    def __init__(self):
        self.clients = set()
        self.lock = threading.Lock()
        self._last_mtime = None

    def add(self, queue):
        with self.lock:
            self.clients.add(queue)

    def remove(self, queue):
        with self.lock:
            self.clients.discard(queue)

    def broadcast(self, data):
        with self.lock:
            for q in list(self.clients):
                try:
                    q.put(data)
                except Exception:
                    self.clients.discard(q)

    def watch(self):
        """轮询 workflow.log，变化时广播新事件。"""
        last_size = 0
        while True:
            log_path = find_file(WORKSPACE, "workflow.log")
            if log_path:
                try:
                    size = os.path.getsize(log_path)
                    if size > last_size:
                        events = read_workflow_tail(WORKSPACE, limit=10)
                        new = [e for e in events if e["time"] not in getattr(self, "_seen", set())]
                        self._seen = {e["time"] for e in events}
                        if new:
                            self.broadcast({"type": "events", "events": new})
                        last_size = size
                except OSError:
                    pass
            # 定期全量刷新（状态变化兜底）
            time.sleep(2)


broadcaster = Broadcaster()
broadcaster._seen = set()


# ============ HTTP 处理 ============

PAGE = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>Shannon 实时监控</title>
<style>
body{font-family:-apple-system,'PingFang SC','Microsoft YaHei',sans-serif;background:#0f1117;color:#e6e6e6;margin:0;padding:20px;}
.card{background:#1a1d27;border:1px solid #2a2e3d;border-radius:12px;padding:16px 18px;margin-bottom:14px;}
h1{font-size:17px;margin:0 0 6px;}
h2{font-size:14px;margin:0 0 10px;color:#9aa0b5;}
.meta{font-size:12px;color:#8a90a5;line-height:1.9;}
.badge{display:inline-block;padding:2px 10px;border-radius:20px;font-size:12px;font-weight:600;margin-left:6px;}
.stage{display:inline-block;min-width:120px;margin:5px;padding:9px 11px;border-radius:9px;font-size:12px;vertical-align:top;}
.stage .n{font-weight:600;margin-bottom:2px;}
.stage .d{font-size:10px;opacity:.75;}
.ok{background:#12331f;border:1px solid #1d9e75;color:#5dcaa5;}
.fail{background:#3a1517;border:1px solid #a32d2d;color:#f09595;}
.run{background:#12233d;border:1px solid #185fa5;color:#85b7eb;animation:pulse 1.6s infinite;}
.pend{background:#20232e;border:1px solid #3a3f52;color:#7a7f95;}
@keyframes pulse{50%{opacity:.55}}
table{border-collapse:collapse;width:100%;}
th{text-align:left;padding:5px 9px;font-size:11px;color:#8a90a5;border-bottom:1px solid #2a2e3d;}
td{padding:5px 9px;font-size:12px;border-bottom:1px solid #232734;font-family:monospace;}
#events{max-height:420px;overflow-y:auto;}
.ev{padding:4px 0;font-size:11px;border-bottom:1px solid #20232e;font-family:monospace;color:#9aa0b5;}
.ev b{font-weight:600;}
.ev .t{color:#4a5064;margin-right:6px;}
.LLM{color:#a78bfa}.TOOL{color:#34d399}.AGENT{color:#60a5fa}.PHASE{color:#fbbf24}
</style>
</head>
<body>
<div class="card">
  <h1>Shannon 实时监控 <span class="badge" id="statusBadge">加载中</span></h1>
  <div class="meta" id="meta">连接中...</div>
</div>
<div class="card"><h2>管线进度</h2><div id="stages">加载中...</div></div>
<div class="card"><h2>Agent 执行</h2><table><thead><tr><th>Agent</th><th>状态</th><th>轮次</th><th>耗时</th><th>成本</th><th>模型</th></tr></thead><tbody id="agents"><tr><td colspan="6">加载中...</td></tr></tbody></table></div>
<div class="card"><h2>实时活动流 <span style="color:#666;font-weight:400;" id="evCount"></span></h2><div id="events">连接中...</div></div>
<script>
const qs = new URLSearchParams(location.search);
const TOKEN = qs.get('token') || '';
const authQuery = TOKEN ? ('?token=' + encodeURIComponent(TOKEN)) : '';
const evtSource = new EventSource('/stream' + authQuery);
const seen = new Set();
evtSource.onmessage = (e) => {
  const msg = JSON.parse(e.data);
  if (msg.type === 'snapshot') render(msg);
  if (msg.type === 'events') appendEvents(msg.events);
};
evtSource.onerror = () => { document.getElementById('statusBadge').textContent = '重连中'; };

function render(d) {
  const s = d.scan;
  const badge = document.getElementById('statusBadge');
  badge.textContent = s.status;
  badge.style.background = s.status === 'running' ? '#12233d' : (s.status === 'success' ? '#12331f' : '#3a1517');
  badge.style.color = s.status === 'running' ? '#85b7eb' : (s.status === 'success' ? '#5dcaa5' : '#f09595');
  document.getElementById('meta').innerHTML =
    `目标: <b style="color:#e6e6e6">${s.target}</b>｜ 扫描: <code>${s.id}</code>｜ 成本: <b>$${s.cost.toFixed(3)}</b>｜ 开始: ${s.created}｜ 更新: ${s.generated}`;

  document.getElementById('stages').innerHTML = d.phases.map(p => {
    const cls = {success:'ok', failed:'fail', running:'run', pending:'pend'}[p.status] || 'pend';
    const icon = {success:'✓', failed:'✗', running:'●', pending:'○'}[p.status] || '○';
    return `<div class="stage ${cls}"><div class="n">${icon} ${p.name}</div><div class="d">${p.desc}</div></div>`;
  }).join('');

  document.getElementById('agents').innerHTML = d.agents.length ? d.agents.map(a =>
    `<tr><td>${a.agent}</td><td style="color:${a.status==='success'?'#34d399':'#f87171'}">${a.status}</td><td>${a.turns}</td><td>${(a.duration_ms/1000).toFixed(0)}s</td><td>$${a.cost_usd.toFixed(3)}</td><td>${a.model||'-'}</td></tr>`
  ).join('') : '<tr><td colspan="6" style="color:#555">暂无记录</td></tr>';

  if (d.events && !document.getElementById('events').dataset.loaded) {
    document.getElementById('events').innerHTML = '';
    appendEvents(d.events);
    document.getElementById('events').dataset.loaded = '1';
  }
}

function appendEvents(events) {
  const box = document.getElementById('events');
  events.forEach(ev => {
    const key = ev.time + ev.agent + ev.type;
    if (seen.has(key)) return;
    seen.add(key);
    const div = document.createElement('div');
    div.className = 'ev';
    div.innerHTML = `<span class="t">${ev.time}</span>[<b class="${ev.type}">${ev.type}</b>] ${ev.agent} — ${ev.detail}`;
    box.prepend(div);
  });
  while (box.children.length > 400) box.removeChild(box.lastChild);
  document.getElementById('evCount').textContent = `(${box.children.length} 条)`;
}
</script>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def authorized(self, parsed):
        """token 校验：未配置 token 则放行；配置后校验 Authorization 头或 ?token=。"""
        if not AUTH_TOKEN:
            return True
        auth = self.headers.get("Authorization", "")
        if auth == f"Bearer {AUTH_TOKEN}":
            return True
        qs = parse_qs(parsed.query)
        return qs.get("token", [None])[0] == AUTH_TOKEN

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            body = PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif parsed.path == "/api/state":
            if not self.authorized(parsed):
                self.send_response(401)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            data = json.dumps(snapshot()).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif parsed.path == "/stream":
            if not self.authorized(parsed):
                self.send_response(401)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self.handle_sse()
        else:
            self.send_response(404)
            self.end_headers()

    def handle_sse(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        import queue
        q = queue.Queue()
        broadcaster.add(q)
        try:
            # 初始快照
            self.wfile.write(f"data: {json.dumps({'type': 'snapshot', **snapshot()}, ensure_ascii=False)}\n\n".encode())
            self.wfile.flush()
            while True:
                try:
                    msg = q.get(timeout=15)
                    self.wfile.write(f"data: {json.dumps(msg, ensure_ascii=False)}\n\n".encode())
                    self.wfile.flush()
                except queue.Empty:
                    # 心跳 + 状态刷新
                    self.wfile.write(f": keepalive\n\n".encode())
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            broadcaster.remove(q)


def main():
    global WORKSPACE, HISTORY, AUTH_TOKEN
    parser = argparse.ArgumentParser(description="Shannon 实时监控（SSE）")
    parser.add_argument("workspace", help="workspace 目录")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--host", default="127.0.0.1", help="监听地址（默认 127.0.0.1；公网部署必须加 --token 并配反向代理鉴权）")
    parser.add_argument("--token", default=None, help="访问令牌：/api/state 与 /stream 需 Authorization: Bearer <token> 或 ?token=<token>")
    parser.add_argument("--history", type=int, default=200)
    args = parser.parse_args()

    if not os.path.exists(find_file(args.workspace, "session.json") or ""):
        print(f"[ERR] 未找到 session.json: {args.workspace}", file=sys.stderr)
        sys.exit(1)

    WORKSPACE = args.workspace
    HISTORY = args.history
    AUTH_TOKEN = args.token

    t = threading.Thread(target=broadcaster.watch, daemon=True)
    t.start()

    auth_note = f"（token 已启用，浏览器访问 /?token=<token>）" if AUTH_TOKEN else "（无鉴权，仅限本机）"
    print(f"[OK] Shannon 实时监控: http://{args.host}:{args.port} {auth_note}")
    print(f"  workspace: {WORKSPACE}")
    try:
        ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()
