# Shannon - Autonomous AI Pentester (CN Edition)

<div align="center">

**English** | [中文](README_CN.md)

</div>


<div align="center">

Shannon is an autonomous, AI-driven penetration testing framework for web applications and APIs.
It analyzes your source code, identifies attack paths, and executes real exploits to prove
vulnerabilities before they reach production.

**This is a customized distribution of Shannon** — built for Chinese LLM providers
(DeepSeek / Qwen / GLM) with companion tooling for real-time monitoring, result
persistence, and one-shot configuration.

</div>

---

> [!TIP]
> **AI agents and LLMs:** start with [llms.txt](llms.txt) for a concise map of this repository, or use [llms-full.txt](llms-full.txt) for the README and docs combined into one file.

## Table of Contents

- [What is Shannon?](#what-is-shannon)
- [What's Different in This Fork](#whats-different-in-this-fork)
- [Shannon in Action](#shannon-in-action)
- [Quick Start](#quick-start)
- [Chinese Model Support](#chinese-model-support)
- [Companion Tools](#companion-tools)
- [Key Capabilities](#key-capabilities)
- [Architecture](#architecture)
- [Documentation](#documentation)
- [Upstream Sync](#upstream-sync)
- [Safety, Scope, and Limitations](#safety-scope-and-limitations)
- [License](#license)

## What is Shannon?

Shannon is an autonomous AI pentester. It performs security testing of web applications and
their underlying APIs by combining **source-code analysis** with **live exploitation**.

Shannon analyzes your web application's source code to identify potential attack vectors, then
uses browser automation and command-line tools to execute real exploits against the running
application and its APIs. **Only vulnerabilities with a working proof-of-concept are included
in the final report.**

### Why Shannon Exists

Thanks to tools like Claude Code and Cursor, your team ships code non-stop. But your
penetration test? That happens once a year. This creates a massive security gap. For the other
364 days, you could be unknowingly shipping vulnerabilities to production.

Shannon closes that gap by providing on-demand, automated penetration testing that can run
against every build or release.

## What's Different in This Fork

This distribution adds three things on top of the upstream Shannon:

1. **First-class Chinese LLM support** — DeepSeek is curated as a native provider, and
   Qwen / GLM work through an OpenAI-compatible gateway (Aliyun MaaS, etc.) with a verified
   configuration path. No more "Claude only" lock-in.
2. **Real-time attack visualization** — an SSE dashboard (`shannon_monitor.py`) and a
   self-contained HTML snapshot generator (`shannon_snapshot.py`) let you watch what the
   agents are doing live: pipeline stage, tool calls, LLM turns, and cost.
3. **Result persistence** — `shannon_export.py` normalizes scan output (scan runs, findings,
   agent executions) into SQLite for downstream querying, reporting, or SIEM ingestion.

## Shannon in Action

<p align="center">
  <img src="assets/shannon-action.gif" alt="Shannon running an autonomous pentest" width="100%">
</p>

Sample penetration test reports from intentionally vulnerable applications, produced by Shannon:

| Target | Summary | Report |
| --- | --- | --- |
| OWASP Juice Shop | 20+ vulnerabilities, including authentication bypass, SQL injection, IDOR, and SSRF. | [View report](sample-reports/shannon-report-juice-shop.md) |
| c{api}tal API | Approximately 15 critical and high-severity API findings, including command injection, auth bypass, and mass assignment. | [View report](sample-reports/shannon-report-capital-api.md) |
| OWASP crAPI | 15+ critical and high-severity findings across JWT, injection, SSRF, and API authorization paths. | [View report](sample-reports/shannon-report-crapi.md) |

## Quick Start

### ⚠️ Important: use this repo's build, not the upstream npm package

The upstream `npx @keygraph/shannon` package and Docker Hub image do **not** contain this
fork's CN patches (DeepSeek curation, `deepseek-compat` continuation fix, sub-agent cost
optimization). Running `npx @keygraph/shannon ...` against this README's instructions would
silently give you the upstream behavior — your CN configuration would not take effect.

**To use this fork, build from source:**

```bash
# Prerequisites: Docker, Node.js 18+, pnpm (corepack enable)
git clone https://github.com/tajleonbennis-maker/shannon.git
cd shannon
pnpm install
pnpm build              # turborepo: builds apps/cli, apps/worker, etc.
docker build -t keygraph/shannon:cn .   # self-built worker image with CN patches
```

Then configure credentials and run:

```bash
# Interactive wizard (source build)
pnpm --filter @keygraph/shannon setup

# One-shot CN model config (see Chinese Model Support below)
python3 scripts/shannon_cn_config.py aliyun --key sk-xxx --model glm-5.2

# Run a pentest against a source-available target
pnpm --filter @keygraph/shannon start -u https://your-app.com -r /path/to/your-repo
```

> [!WARNING]
> Shannon actively executes exploits. Run it only against applications and environments you own
> or have explicit written authorization to test. Do not run Shannon against production systems.

## Chinese Model Support

This fork adds first-class support for Chinese LLM providers.

### Supported Chinese Models

| Model | Provider prefix | Gateway | Status |
| --- | --- | --- | --- |
| DeepSeek V4 Flash | `deepseek:` | DeepSeek official | Verified (pre-recon passes) |
| GLM-5.2 | `openrouter:` | Aliyun MaaS (Chat Completions) | Verified (preflight passes) |
| Qwen 3.8 Max | `openrouter:` | Aliyun MaaS (Chat Completions) | Verified (recon progressing) |

> **Key insight**: pi's `openai:` provider hardcodes the **Responses API** (`/v1/responses`),
> which most Chinese gateways do not serve for non-Qwen models. Use the **`openrouter:`**
> prefix instead — pi's openrouter provider speaks **Chat Completions**, which gateways
> like Aliyun MaaS accept. See [supported Chinese models](docs/supported-models-cn.md).

### CN Configuration

```toml
# ~/.shannon/config.toml
[core]
model = "openrouter:glm-5.2"          # or deepseek:deepseek-v4-flash / openrouter:qwen3.8-max
base_url = "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"

[provider]
api_key = "sk-..."
```

> Note: for `deepseek:` models the key lives in the **`[deepseek]`** section
> (maps to `DEEPSEEK_API_KEY`), not `[provider]`. See `docs/supported-models-cn.md`.

One-shot setup: `python3 scripts/shannon_cn_config.py <deepseek|aliyun|gateway> --key sk-xxx`

Optional cost optimization — run `task` sub-agents on a cheaper model
(`core.sub_model` / `SHANNON_AI_SUBMODEL`, must be same provider as the main model):

```toml
[core]
model = "deepseek:deepseek-v4-pro"
sub_model = "deepseek:deepseek-v4-flash"
```

## Companion Tools

| Tool | Purpose |
| --- | --- |
| `shannon_monitor.py` | Real-time SSE dashboard — watch agents work live (pipeline stages, tool calls, LLM turns, cost). Defaults to `127.0.0.1`; add `--token` for public exposure |
| `shannon_snapshot.py` | Self-contained HTML snapshot of scan progress (no server needed) |
| `shannon_export.py` | Persist scan results (scan_runs / findings / agents) into SQLite |
| `shannon_cn_config.py` | One-shot Chinese-model config generator (`--dry-run` supported) |

## Key Capabilities

- **Proof-by-exploitation reports**: Shannon reports validated findings with reproducible
  proof-of-concept steps instead of speculative warnings.
- **White-box attack planning**: Shannon uses source-code analysis to guide dynamic testing
  and focus on realistic attack paths.
- **Autonomous execution**: Shannon launches reconnaissance, vulnerability analysis,
  exploitation, and report generation from a single command.
- **Authenticated testing**: configuration files can describe login flows, test credentials,
  TOTP, email-based login flows, focus areas, and rules of engagement.
- **OWASP-focused coverage**: Shannon targets exploitable Injection, XSS, SSRF, Broken
  Authentication, and Broken Authorization issues.
- **Resumable workspaces**: Shannon can resume interrupted runs without re-running completed
  agents.

## Architecture

Shannon uses a multi-agent workflow that combines source-code analysis with live exploitation:

```text
        ┌──────────────────────┐
        │   Pre-Reconnaissance │
        │   (source code scan) │
        └──────────┬───────────┘
                   │
                   ▼
        ┌──────────────────────┐
        │   Reconnaissance     │
        │  (attack surface     │
        │   mapping)           │
        └──────────┬───────────┘
                   │
                   ▼
        ┌──────────┴───────────┐
        │          │           │
        ▼          ▼           ▼
  ┌───────────┐ ┌───────────┐ ┌───────────┐
  │ Vuln      │ │ Vuln      │ │   ...     │
  │(Injection)│ │  (XSS)    │ │           │
  └─────┬─────┘ └─────┬─────┘ └─────┬─────┘
        │              │             │
        ▼              ▼             ▼
  ┌───────────┐ ┌───────────┐ ┌───────────┐
  │ Exploit   │ │ Exploit   │ │   ...     │
  │(Injection)│ │  (XSS)    │ │           │
  └─────┬─────┘ └─────┬─────┘ └─────┬─────┘
        │              │             │
        └──────┬───────┴─────────────┘
               │
               ▼
        ┌──────────────────────┐
        │      Reporting       │
        └──────────────────────┘
```

At a high level:

- **Pre-reconnaissance** identifies frameworks, entry points, data flows, and likely attack surfaces from the repository.
- **Reconnaissance** explores the live application and correlates runtime behavior with code-level context.
- **Vulnerability analysis** runs specialized agents for Injection, XSS, SSRF, Authentication, and Authorization.
- **Exploitation** attempts real proof-of-concept attacks and discards hypotheses that cannot be proven.
- **Reporting** compiles validated findings, evidence, and remediation guidance into a final Markdown report.

Each scan runs in an ephemeral Docker container with an isolated workspace and per-invocation orchestration.

## Documentation

Use these guides for operational detail:

| Guide | Use it for |
| --- | --- |
| [Source build and CLI commands](docs/development.md) | Cloning, building, common commands, output paths, and local development. |
| [Configuration](docs/configuration.md) | Authenticated testing, login flows, rules of engagement, and report filters. |
| [AI providers](docs/ai-providers.md) | Selecting the model, the supported providers (Anthropic, OpenAI, xAI, AWS Bedrock, and any other Pi-supported provider), and custom gateways. |
| [Chinese models](docs/supported-models-cn.md) | Supported Chinese LLM providers (DeepSeek / GLM / Qwen), config templates, and gateway caveats. |
| [Dev deliverables](docs/DEV-DELIVERABLES-CN.md) | CN-patch deliverables: model adaptation, SSE monitoring, snapshot, SQLite export. |
| [Platforms and networking](docs/platforms.md) | Windows/WSL2, Linux, macOS, Docker networking, local apps, and custom hostnames. |
| [Workspaces and resuming](docs/workspaces.md) | Naming workspaces, resuming interrupted scans, and workspace storage. |
| [Safety and limitations](docs/safety.md) | Authorized-use requirements, non-production guidance, mutative effects, cost, and model caveats. |
| [Coverage and roadmap](docs/coverage-roadmap.md) | Current vulnerability coverage and planned work. |

## Upstream Sync

This repository is a customized fork of [KeygraphHQ/shannon](https://github.com/KeygraphHQ/shannon).

- **Baseline**: `2.4.0` (upstream commit `9f22ef2`), with the `deepseek-compat` hot patch applied.
- **Local changes are deliberately small and concentrated** so merges stay cheap:
  - `apps/worker/src/ai/models.ts` — DeepSeek curated provider, sub-model resolution
  - `apps/worker/src/ai/pi/pi-executor.ts` — deepseek-compat continuation fix, sub-model wiring
  - `apps/cli/src/config/resolver.ts` / `writer.ts` / `model-spec.ts` / `setup.ts` — `[deepseek]` TOML section
  - `scripts/` — companion tools (monitor / snapshot / export / cn_config)
  - `patches/` — hot-patch scripts to re-apply CN fixes onto upstream images
- **Re-applying patches**: see [patches/README.md](patches/README.md) for the `patch_pi_executor.py`
  flow (hot-patch a released image without a full rebuild).
- **Sync rhythm**: we plan to rebase against upstream monthly. Prefer contributing generic fixes
  (e.g. `deepseek-compat`) back upstream to shrink the local patch surface over time.

## Safety, Scope, and Limitations

Shannon is not a passive scanner. Its exploitation agents can create users, submit forms,
mutate application state, trigger outbound requests, and otherwise affect the target system.
Use sandboxed, staging, or local development environments with disposable data.

You are responsible for using Shannon legally and ethically. Do not point Shannon at systems,
repositories, or applications you do not own or do not have explicit authorization to test.

Important limitations:

- Shannon focuses on actively exploitable issues such as Injection, XSS, SSRF, Broken
  Authentication, and Broken Authorization.
- Findings still require human review. LLM-generated reports can contain weakly supported
  or incorrect details.
- Claude models are the best-supported option; Chinese models (DeepSeek / Qwen / GLM) are
  verified but may be less reliable on complex tool-use chains — the included
  `deepseek-compat` patch mitigates the most common failure mode (agents ending a turn
  without calling tools).
- A full run can take roughly 1 to 1.5 hours and may incur LLM API costs depending on model
  pricing and application complexity.
- Do not scan untrusted or adversarial codebases. AI-powered tools that read source code can
  be exposed to prompt injection.

Read the full [Safety and limitations](docs/safety.md) guide before running Shannon in a new
environment.

## License

This project is licensed under the [GNU Affero General Public License v3.0](LICENSE).

The upstream Shannon is developed by [Keygraph](https://keygraph.io) and is licensed under
AGPL-3.0. This repository is a customized fork: it adds Chinese LLM provider support and
companion tooling while keeping the same license.
