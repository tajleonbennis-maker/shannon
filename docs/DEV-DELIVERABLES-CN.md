# Shannon 定制开发交付清单（国产模型适配 + 可视化 + 落库）

> 项目：tajleonbennis-maker/shannon（定制版）  
> 基线：KeygraphHQ/shannon 2.4.0 + deepseek-compat 补丁（commit 9f22ef2）  
> 交付日期：2026-08-17

---

## 1️⃣ 国产大模型适配（代码 + 配置）

### 关键突破：破解 pi 的端点限制

| 现象                                      | 根因                                                                 | 解法                                                                            |
| --------------------------------------- | ------------------------------------------------------------------ | ----------------------------------------------------------------------------- |
| glm-5.2 走 `openai:` 报 Unsupported model | pi 的 openai provider **硬编码走 /v1/responses 端点**，阿里云网关只对 qwen 系开放该端点 | 改用 **`openrouter:` 前缀**（pi 的 openrouter provider 走 chat/completions，阿里云完全支持）✅ |
| qwen3.8-max 空 content 问题                | qwen 工具调用时返回 `content:""`+`reasoning_content`                      | deepseek-compat 续跑补丁兜底（零工具调用时强制续跑）✅                                           |

### 已验证可用模型

| 模型                | 配置前缀          | 网关          | 状态                        |
| ----------------- | ------------- | ----------- | ------------------------- |
| deepseek-v4-flash | `deepseek:`   | DeepSeek 官方 | ✅ pre-recon 通过            |
| glm-5.2           | `openrouter:` | 阿里云 MaaS    | ✅ preflight 通过（recon 有卡顿） |
| **qwen3.8-max**   | `openrouter:` | 阿里云 MaaS    | ✅ **recon 正常推进中**         |

### 代码改动（工作区已改，待 push）

- `apps/worker/src/ai/models.ts`：CURATED_PROVIDERS 加 `deepseek` + DEEPSEEK_API_KEY
- `apps/cli/src/model-spec.ts`：镜像同步
- `apps/cli/src/commands/setup.ts`：增加 DeepSeek 快捷选项 + 模型建议
- `apps/cli/src/config/resolver.ts` / `writer.ts`：支持 `[deepseek]` TOML 段
- `patches/`：deepseek-compat 热补丁（已有）

### 一键配置工具

```bash
# DeepSeek 官方
python3 shannon_cn_config.py deepseek --key sk-xxx
# 阿里云 MaaS（默认 glm-5.2）
python3 shannon_cn_config.py aliyun --key sk-sp-xxx
# 任意 OpenAI 兼容网关
python3 shannon_cn_config.py gateway --key sk-xxx --model my-model --base-url https://.../v1
```

---

## 2️⃣ 攻击过程可视化（SSE 实时监控）

**方案选型**（调研四类方案后）：借鉴 Aikido Attack 的"实时可见 agent 行为"思路，做轻量 SSE 服务，不引入重依赖。

### shannon_monitor.py（已在服务器 8787 端口运行）

- **管线进度条**：13 个阶段（Pre-Recon → Recon → 5×Vuln → 5×Exploit → Report）实时变色
- **Agent 明细表**：状态/轮次/耗时/成本/模型
- **实时活动流**：SSE 推送工具调用和 LLM 轮次，浏览器无需刷新
- 纯 Python 标准库，零第三方依赖，深色主题

```bash
# 启动
python3 shannon_monitor.py ~/.shannon/workspaces/deeptutor-scan --port 8787
# 浏览器访问
http://<服务器IP>:8787
```

### shannon_snapshot.py（定时快照版）

单文件 HTML 快照，适合不发实时流时用：

```bash
python3 shannon_snapshot.py <workspace> --out report.html --live  # --live 页面30s自动刷新
```

---

## 3️⃣ 支持的模型清单

已整理到 `docs/supported-models-cn.md`，包含：已验证模型表、配置模板、**关键坑说明**（openai 前缀陷阱）、环境变量方式、已知限制。

---

## 4️⃣ 代码审计产出落库

### shannon_export.py（SQLite 落库）

```bash
# 单次落库
python3 shannon_export.py <workspace> --db shannon.db --json out.json
# 列出所有扫描
python3 shannon_export.py --list
```

**表结构**：

- `scan_runs`：扫描元数据（目标/状态/成本/模型/时间）
- `findings`：漏洞发现（类型/严重度/位置/摘要/利用步骤/原始JSON）
- `agents`：各阶段 agent 执行记录（耗时/成本/token/模型）

**已验证**：成功提取 deeptutor-scan 的 4 条 agent 记录（含 deepseek pre-recon $0.33 + 3 次 recon 尝试及各自模型/成本）。

后续可平滑迁移 PostgreSQL（对接 165.154.226.119 现有 PG16）或接 SysReptor 做报告管理。

---

## 📁 文件清单

```
shannon/
├── docs/supported-models-cn.md     # 国产模型支持清单（需求3）
├── scripts/
│   ├── shannon_export.py           # 落库工具（需求4）
│   ├── shannon_monitor.py          # SSE 实时监控（需求2）
│   ├── shannon_snapshot.py         # HTML 快照（需求2 轻量版）
│   └── shannon_cn_config.py        # 国产模型一键配置（需求1 配套）
├── apps/worker/src/ai/models.ts    # deepseek provider 注册（需求1）
├── apps/cli/src/model-spec.ts      # CLI 镜像同步（需求1）
├── apps/cli/src/commands/setup.ts  # DeepSeek 选项（需求1）
├── apps/cli/src/config/            # [deepseek] TOML 支持（需求1）
└── patches/                        # deepseek-compat 热补丁（已有）
```

## ⏭️ 待办

- [x] 代码改动 commit + push 到 tajleonbennis-maker/shannon
- [x] 监控服务加 systemd 常驻 + nginx 反代（可公网访问）
- [x] DeepTutor 完整扫描跑完后，落库 + 生成最终报告
- [x] （可选）落库对接 PostgreSQL / SysReptor
