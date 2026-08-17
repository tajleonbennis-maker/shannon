# Shannon - 自主 AI 渗透测试框架（中文定制版 / CN Edition）

<div align="center">

[English](README.md) | **中文**

</div>


<div align="center">

Shannon 是一个自主 AI 驱动的 Web 应用与 API 渗透测试框架。
它分析你的源代码、识别攻击路径，并执行真实漏洞利用，在漏洞进入生产环境之前证明其存在。

**本仓库是 Shannon 的定制发行版** —— 面向国产大模型（DeepSeek / Qwen / GLM）深度适配，
并附带实时监控、结果落库、一键配置等配套工具。

</div>

---

> [!TIP]
> **AI 代理与 LLM：** 从 [llms.txt](llms.txt) 快速了解仓库结构，或使用 [llms-full.txt](llms-full.txt)（README 与全部文档合并版）。

## 目录

- [什么是 Shannon？](#什么是-shannon)
- [本分支的差异](#本分支的差异)
- [实战效果](#实战效果)
- [快速开始](#快速开始)
- [国产模型支持](#国产模型支持)
- [配套工具](#配套工具)
- [核心能力](#核心能力)
- [架构设计](#架构设计)
- [文档](#文档)
- [上游同步](#上游同步)
- [安全、范围与限制](#安全范围与限制)
- [许可证](#许可证)

## 什么是 Shannon？

Shannon 是一个自主 AI 渗透测试工具。它结合**源代码分析**与**在线漏洞利用**，
对 Web 应用及其底层 API 进行安全测试。

Shannon 分析目标应用的源代码以识别潜在攻击向量，随后使用浏览器自动化和命令行工具
对运行中的应用与 API 执行真实漏洞利用。**只有具备可复现 PoC（概念验证）的漏洞才会
被写入最终报告。**

### 为什么需要 Shannon？

得益于 Claude Code、Cursor 等工具，你的团队在持续不断地发布代码。但渗透测试呢？
一年一次。这造成了巨大的安全空窗——在剩下的 364 天里，你可能在不知不觉中把漏洞
带进了生产环境。

Shannon 通过提供**按需、自动化的渗透测试**来填补这个空窗，让每一次构建或发版
都能得到安全验证。

## 本分支的差异

本发行版在上游 Shannon 基础上增加了三大能力：

1. **国产大模型一等支持** — DeepSeek 已作为原生 provider 收录，Qwen / GLM 可通过
   OpenAI 兼容网关（阿里云百炼等）稳定运行，配置路径经过实战验证，摆脱"仅限 Claude"。
2. **攻击过程实时可视化** — SSE 实时看板（`shannon_monitor.py`）与自包含 HTML 快照
   生成器（`shannon_snapshot.py`），让你实时看到 agent 在做什么：管线阶段、工具调用、
   LLM 轮次、成本消耗。
3. **扫描结果持久化** — `shannon_export.py` 将扫描产出（扫描记录 / 漏洞发现 / agent
   执行明细）规范化写入 SQLite，便于下游查询、报告或对接安全平台。

## 实战效果

<p align="center">
  <img src="assets/shannon-action.gif" alt="Shannon 自主渗透测试演示" width="100%">
</p>

Shannon 在故意存在漏洞的靶场应用上的实测报告：

| 靶场 | 摘要 | 报告 |
| --- | --- | --- |
| OWASP Juice Shop | 20+ 漏洞，包括认证绕过、SQL 注入、IDOR、SSRF。 | [查看报告](sample-reports/shannon-report-juice-shop.md) |
| c{api}tal API | 约 15 个严重/高危 API 发现，包括命令注入、认证绕过、批量赋值。 | [查看报告](sample-reports/shannon-report-capital-api.md) |
| OWASP crAPI | 15+ 严重/高危发现，覆盖 JWT、注入、SSRF、API 授权路径。 | [查看报告](sample-reports/shannon-report-crapi.md) |

## 快速开始

### ⚠️ 重要：请用本仓库自建，不要直接跑上游 npm 包

官方 `npx @keygraph/shannon` 包与 Docker Hub 镜像**不包含本 fork 的 CN 改造**
（DeepSeek curated、deepseek-compat 续跑补丁、子代理成本优化等）。直接按本文档
跑 `npx @keygraph/shannon ...` 会静默得到上游行为——你的国产模型配置不会生效。

**使用本 fork 需要从源码构建：**

```bash
# 前置：Docker、Node.js 18+、pnpm（corepack enable）
git clone https://github.com/tajleonbennis-maker/shannon.git
cd shannon
pnpm install
pnpm build              # turborepo：构建 apps/cli、apps/worker 等
docker build -t keygraph/shannon:cn .   # 自建含 CN 补丁的 worker 镜像
```

然后配置凭据并运行：

```bash
# 交互式向导（源码构建）
pnpm --filter @keygraph/shannon setup

# 国产模型一键配置（见下方"国产模型支持"）
python3 scripts/shannon_cn_config.py aliyun --key sk-xxx --model glm-5.2

# 对源码可用的目标运行渗透测试
pnpm --filter @keygraph/shannon start -u https://your-app.com -r /path/to/your-repo
```

> [!WARNING]
> Shannon 会主动执行漏洞利用。请仅对**你拥有**或**已获得明确书面授权**的
> 应用运行，切勿对生产系统运行。

## 国产模型支持

本分支为国产大模型提供一等支持。

### 已验证的国产模型

| 模型 | Provider 前缀 | 网关 | 状态 |
| --- | --- | --- | --- |
| DeepSeek V4 Flash | `deepseek:` | DeepSeek 官方 | ✅ 已验证（pre-recon 通过） |
| GLM-5.2 | `openrouter:` | 阿里云 MaaS（Chat Completions） | ✅ 已验证（preflight 通过） |
| Qwen 3.8 Max | `openrouter:` | 阿里云 MaaS（Chat Completions） | ✅ 已验证（recon 正常推进） |

> **关键技巧**：pi 的 `openai:` provider 硬编码走 **Responses API**（`/v1/responses`），
> 而多数国产网关对非 Qwen 模型不提供该端点。请改用 **`openrouter:` 前缀**——
> pi 的 openrouter provider 走 **Chat Completions**，阿里云 MaaS 等网关完全兼容。
> 详见[国产模型支持指南](docs/supported-models-cn.md)。

### 国产模型配置

```toml
# ~/.shannon/config.toml
[core]
model = "openrouter:glm-5.2"          # 或 deepseek:deepseek-v4-flash / openrouter:qwen3.8-max
base_url = "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"

[provider]
api_key = "sk-..."
```

> 注意：`deepseek:` 模型的 key 写在 **`[deepseek]`** 段（映射 `DEEPSEEK_API_KEY`），
> 不是 `[provider]`。详见 `docs/supported-models-cn.md`。

一键配置：`python3 scripts/shannon_cn_config.py <deepseek|aliyun|gateway> --key sk-xxx`

可选成本优化——让 `task` 子代理用更便宜的模型（`core.sub_model` / `SHANNON_AI_SUBMODEL`，
须与主模型同 provider）：

```toml
[core]
model = "deepseek:deepseek-v4-pro"
sub_model = "deepseek:deepseek-v4-flash"
```

## 配套工具

| 工具 | 用途 |
| --- | --- |
| `shannon_monitor.py` | SSE 实时监控看板——实时观看 agent 工作（管线阶段 / 工具调用 / LLM 轮次 / 成本）。默认仅监听 127.0.0.1，公网暴露需 `--token` |
| `shannon_snapshot.py` | 自包含 HTML 进度快照（无需常驻服务） |
| `shannon_export.py` | 扫描结果落库 SQLite（scan_runs / findings / agents 三表） |
| `shannon_cn_config.py` | 国产模型一键配置生成器（支持 `--dry-run`） |

## 核心能力

- **利用证明式报告（Proof-by-exploitation）**：只报告经真实利用验证、含可复现 PoC 的发现，而非猜测性告警。
- **白盒攻击规划**：基于源代码分析指导动态测试，聚焦真实攻击路径。
- **自主执行**：单条命令完成侦察、漏洞分析、利用、报告生成全流程。
- **认证测试**：配置文件可描述登录流程、测试凭据、TOTP、邮箱登录、重点区域与交战规则。
- **OWASP 重点覆盖**：针对可利用的注入、XSS、SSRF、认证失效、授权失效。
- **可恢复工作区**：中断后可续跑，无需重跑已完成 agent。

## 架构设计

Shannon 采用**多代理工作流**，结合源码分析与在线利用：

```text
        ┌──────────────────────┐
        │   Pre-Reconnaissance │
        │   (源码扫描)          │
        └──────────┬───────────┘
                   │
                   ▼
        ┌──────────────────────┐
        │   Reconnaissance     │
        │  (攻击面测绘)         │
        └──────────┬───────────┘
                   │
                   ▼
        ┌──────────┴───────────┐
        │          │           │
        ▼          ▼           ▼
  ┌───────────┐ ┌───────────┐ ┌───────────┐
  │ Vuln      │ │ Vuln      │ │   ...     │
  │(注入)     │ │  (XSS)    │ │           │
  └─────┬─────┘ └─────┬─────┘ └─────┬─────┘
        │              │             │
        ▼              ▼             ▼
  ┌───────────┐ ┌───────────┐ ┌───────────┐
  │ Exploit   │ │ Exploit   │ │   ...     │
  │(注入)     │ │  (XSS)    │ │           │
  └─────┬─────┘ └─────┬─────┘ └─────┬─────┘
        │              │             │
        └──────┬───────┴─────────────┘
               │
               ▼
        ┌──────────────────────┐
        │      Reporting       │
        │      (报告生成)       │
        └──────────────────────┘
```

各阶段职责：

- **Pre-reconnaissance**：从仓库识别框架、入口点、数据流与潜在攻击面。
- **Reconnaissance**：探测运行中的应用，将运行时行为与代码上下文关联。
- **漏洞分析**：运行注入、XSS、SSRF、认证、授权专项 agent。
- **漏洞利用**：执行真实 PoC 攻击，丢弃无法证明的假设。
- **报告生成**：将验证后的发现、证据与修复建议整合为最终 Markdown 报告。

每次扫描运行在临时 Docker 容器中，拥有隔离工作区与独立编排。

## 文档

| 指南 | 用途 |
| --- | --- |
| [源码构建与 CLI 命令](docs/development.md) | 克隆、构建、常用命令、输出路径、本地开发。 |
| [配置说明](docs/configuration.md) | 认证测试、登录流程、交战规则、报告过滤。 |
| [AI 提供商](docs/ai-providers.md) | 模型选择与支持列表（Anthropic/OpenAI/xAI/Bedrock/其他）、自定义网关。 |
| [国产模型](docs/supported-models-cn.md) | 国产 LLM 提供商（DeepSeek / GLM / Qwen）、配置模板、网关避坑。 |
| [开发交付清单](docs/DEV-DELIVERABLES-CN.md) | 定制版交付物：模型适配、SSE 监控、快照、SQLite 落库。 |
| [平台与网络](docs/platforms.md) | Windows/WSL2、Linux、macOS、Docker 网络、本地应用与自定义域名。 |
| [工作区与续跑](docs/workspaces.md) | 工作区命名、中断续跑、工作区存储。 |
| [安全与限制](docs/safety.md) | 授权使用要求、非生产环境指引、变更影响、成本与模型注意事项。 |
| [覆盖范围与路线图](docs/coverage-roadmap.md) | 当前漏洞覆盖范围与后续规划。 |

## 上游同步

本仓库是 [KeygraphHQ/shannon](https://github.com/KeygraphHQ/shannon) 的定制 fork。

- **基线**：`2.4.0`（上游 commit `9f22ef2`），已应用 `deepseek-compat` 热补丁。
- **本地改动刻意小而集中**，保证合并不贵：
  - `apps/worker/src/ai/models.ts` — DeepSeek curated provider、子模型解析
  - `apps/worker/src/ai/pi/pi-executor.ts` — deepseek-compat 续跑修复、子模型接线
  - `apps/cli/src/config/resolver.ts` / `writer.ts` / `model-spec.ts` / `setup.ts` — `[deepseek]` TOML 段
  - `scripts/` — 配套工具（monitor / snapshot / export / cn_config）
  - `patches/` — 热补丁脚本，可对上游镜像重放 CN 修复
- **补丁重放**：见 [patches/README.md](patches/README.md) 的 `patch_pi_executor.py` 流程
  （对已发布镜像打热补丁，无需全量重建）。
- **同步节奏**：计划每月对上游 rebase 一次；优先把通用修复（如 `deepseek-compat`）
  贡献回上游，逐步缩小本地补丁面。

## 安全、范围与限制

Shannon 不是被动扫描器。其利用 agent 会创建用户、提交表单、变更应用状态、触发外联请求，
甚至影响目标系统。请使用沙箱、预发布或本地开发环境（可丢弃数据）。

你有责任合法、合规地使用 Shannon。**请勿**对你不拥有或未经明确授权的系统、仓库或应用运行。

重要限制：

- Shannon 聚焦于可利用的注入、XSS、SSRF、认证失效、授权失效等问题。
- 发现仍需人工复核。LLM 生成的报告可能包含证据不足或不准确的内容。
- Claude 模型是官方最优支持；国产模型（DeepSeek / Qwen / GLM）已验证可用，但在复杂
  工具调用链上可靠性可能略低——随附的 `deepseek-compat` 补丁已缓解最常见故障
  （agent 一轮结束未调用工具）。
- 完整扫描约需 1–1.5 小时，并产生 LLM API 费用（取决于模型定价与应用复杂度）。
- **请勿扫描不受信任或恶意的代码库**——读取源代码的 AI 工具可能遭受提示注入。

在新环境运行 Shannon 前，请先阅读完整版[安全与限制](docs/safety.md)指南。

## 许可证

本项目采用 [GNU Affero General Public License v3.0](LICENSE) 开源协议。

上游 Shannon 由 [Keygraph](https://keygraph.io) 开发，遵循 AGPL-3.0 协议。
本仓库是其定制分支：新增国产大模型支持与配套工具，并沿用同一许可证。
