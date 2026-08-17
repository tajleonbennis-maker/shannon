# Shannon 国产大模型支持清单（Supported Models - CN）

> 定制版 Shannon（基于 KeygraphHQ/shannon 2.4.0 + deepseek-compat 补丁）
> 本文档列出已验证可用的国产模型、配置方法、注意事项。
> 最后更新：2026-08-17

---

## 快速选择

| 场景 | 推荐模型 | Provider 前缀 | 状态 |
|---|---|---|---|
| 默认国产首选 | **deepseek-v4-flash** | `deepseek:` | ✅ 已验证（pre-recon 通过） |
| 走阿里云 MaaS 网关 | **qwen3.8-max** | `openrouter:`（绕开 responses 限制） | ✅ preflight 通过 |
| 走阿里云 MaaS 网关（当前扫描用） | **glm-5.2** | `openrouter:` | ✅ **完整扫描验证中** |
| 走阿里云 MaaS 网关（备选） | **qwen3.7-plus / qwen3.6-flash** | `openrouter:` | ⚠️ 需实测 |

---

## 1. DeepSeek 官方 API（推荐首选）

**配置（~/.shannon/config.toml）：**
```toml
[core]
model = "deepseek:deepseek-v4-flash"

[deepseek]
api_key = "sk-你的DeepSeek-KEY"
```

**说明：**
- 走 pi-ai 原生 `deepseek:` 提供商，模型目录自带 maxTokens=384000 与 reasoning 兼容标志
- DeepSeek 是 curated provider，key 必须写在 **`[deepseek]` 段**（映射 `DEEPSEEK_API_KEY`，见 `apps/cli/src/config/resolver.ts`）
- 已通过 deepseek-compat 补丁修复"零工具调用即终止"问题（续跑循环最多 5 次）
- **前提**：必须使用带 `deepseek:` 前缀补丁的定制版镜像（`keygraph/shannon:2.4.0`），官方原版不支持
- 版本要求：API 余额充足（注意 402 Insufficient Balance）

> ⚠️ 不要写成 `[provider]` 段——那映射的是通用 `SHANNON_AI_API_KEY`，
> curated provider（deepseek）不会读取，CLI 校验会直接报 `[deepseek] requires api_key`。

---

## 2. 阿里云 MaaS 网关（Token Plan 通道）

**网关地址：**
```
https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1
```

### ⚠️ 关键坑（必读）

**不能用 `openai:` 前缀！** pi 的 `openai:` 提供商硬编码走 `/v1/responses`（Responses API）端点，而阿里云网关的 `/responses` 端点**只支持 qwen 系**（glm-5.2 会报 `Unsupported model`）。

**必须用 `openrouter:` 前缀**——pi 的 openrouter 提供商走 `/chat/completions`（Chat Completions）端点，阿里云网关完全支持。

### 配置模板

```toml
# glm-5.2（当前生产验证中）
[core]
model = "openrouter:glm-5.2"
base_url = "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"

[provider]
api_key = "sk-sp-你的阿里云KEY"
```

```toml
# qwen3.8-max（千问）
[core]
model = "openrouter:qwen3.8-max"
base_url = "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"

[provider]
api_key = "sk-sp-你的阿里云KEY"
```

> openrouter 前缀是非 curated 通道，key 走 `[provider]` 段（映射 `SHANNON_AI_API_KEY`）——这里写 `[provider]` 是正确的。

### 已验证模型

| 模型 | 端点 | preflight | 工具调用 | 扫描验证 |
|---|---|---|---|---|
| `glm-5.2` | chat/completions ✅ | ✅ | ✅ | ✅ recon 推进中 |
| `qwen3.8-max` | responses ✅ / completions ✅ | ✅ | ⚠️ 空 content 问题 | ⚠️ recon 曾失败 |
| `qwen3.7-plus` | completions ✅ | 未测 | ✅ curl 验证 | ⚠️ 待实测 |
| `qwen3.6-flash` | completions ✅ | 未测 | ✅ curl 验证 | ⚠️ 待实测 |
| `deepseek-v4-flash` | — | ❌ AccessDenied.Unpurchased | — | ❌ 网关未购买 |

---

## 3. 其他兼容网关（通用模板）

任何 **OpenAI Chat Completions 兼容** 的国产网关（硅基流动、智谱开放平台、MiniMax、通义百炼等）：

```toml
[core]
model = "openrouter:<模型ID>"        # ← 关键：用 openrouter 前缀走 completions
base_url = "https://你的网关地址/v1"  # 网关的 OpenAI 兼容端点

[provider]
api_key = "sk-你的KEY"
```

**注意：**
- 模型 ID 用网关侧的实际模型名（如 `glm-4-plus`、`deepseek-chat`、`qwen-plus`）
- 网关必须实现 OpenAI `chat/completions` 协议
- 若网关同时支持 `responses` 协议且目标模型支持，可尝试 `openai:` 前缀，但不推荐

---

## 4. 子代理成本优化（SHANNON_AI_SUBMODEL）

完整一次 recon 的 ~85% token 花在 8 个子代理各自重复读取源码上。子代理与主 agent 共用同一个贵模型，成本失控。

**让 `task` 子代理使用更便宜的模型**（主 agent 保持强模型），预计可降低 3–5 倍成本。

```toml
[core]
model = "deepseek:deepseek-v4-pro"      # 主 agent：强模型
sub_model = "deepseek:deepseek-v4-flash" # 子代理：便宜模型（SHANNON_AI_SUBMODEL）
```

或环境变量方式：

```bash
export SHANNON_AI_MODEL="deepseek:deepseek-v4-pro"
export SHANNON_AI_SUBMODEL="deepseek:deepseek-v4-flash"
```

**限制：**
- 子模型必须与主模型**同 provider**（共享凭据），跨 provider 配置会直接报错，防止静默回退
- 验证：设置后，子代理 metrics 的 `model` 字段应与主 agent 不同

---

## 5. 已知限制与注意事项

| 限制 | 说明 |
|---|---|
| **非 Claude 模型稳定性** | 官方标注"不推荐、未调优"，国产模型可能：只输出计划文本不调工具（已补丁修复）、拒绝部分安全指令、幻觉 PoC |
| **qwen 空 content 问题** | qwen 系工具调用时返回 `content:""`+`reasoning_content`，部分场景导致 pi 解析异常；glm 无此问题（推荐） |
| **成本** | deepseek-v4-flash 约 $0.33/19min（pre-recon）；glm-5.2 完整扫描成本待测 |
| **余额** | DeepSeek/阿里云均需预充值，余额不足会 402 中断（可续跑） |
| **输出校验** | 若 agent 结束仍无交付物，会 OutputValidation 失败；可续跑（resume）重试 |

---

## 6. 环境变量方式（等价配置）

```bash
export SHANNON_AI_MODEL="openrouter:glm-5.2"
export SHANNON_AI_BASE_URL="https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
export SHANNON_AI_API_KEY="sk-sp-..."
npx @keygraph/shannon start -u http://your-app -r /path/to/repo
```

---

*本文档基于内部验证环境实测（目标为自建测试应用）。*
