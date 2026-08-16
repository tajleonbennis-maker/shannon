# Shannon DeepSeek 兼容改造补丁

针对非 Claude 模型（DeepSeek 等）的两处适配，解除 Shannon 官方"仅推荐 Claude"的隐性限制。

## 根因与修复

1. **agent 零工具调用即终止**：部分模型（DeepSeek chat-completions 通道）首轮只输出
   计划文本不调用工具，pi 运行时将其判定为任务完成，触发 OutputValidationError。
   修复：`apps/worker/src/ai/pi/pi-executor.ts` 增加续跑循环——agent 结束时若全程
   零工具调用且无交付物，自动注入 steering 指令继续执行（最多 5 次）。

2. **max_tokens 缺省截断工具参数**：走 `openai:` 通用通道时模型定义不带 max_tokens，
   DeepSeek 按默认 4096 截断响应，工具调用参数丢失。
   修复：改用 pi-ai 原生 `deepseek:` 提供商（`deepseek:deepseek-v4-flash`），
   模型目录自带 maxTokens=384000 与 reasoning 兼容标志。

## 文件说明

- `pi-executor.ts` 的修改已直接应用在 `apps/worker/src/ai/pi/pi-executor.ts`
- `patch_pi_executor.py`：对官方镜像内编译产物 dist JS 打补丁（热补丁路线）
- `patch_pi_executor_ts.py`：对 TS 源码打补丁（本仓库已应用，留作对照）
- `Dockerfile.patch`：派生镜像构建文件（FROM 官方镜像 + COPY 补丁后 JS）

## 热补丁构建（不跑全量构建的轻量路线）

```bash
docker run --rm --entrypoint cat keygraph/shannon:2.4.0 \
  /app/apps/worker/dist/ai/pi/pi-executor.js > pi-executor.js
python3 patch_pi_executor.py pi-executor.js
docker build -f Dockerfile.patch -t keygraph/shannon:2.4.0 .
```

## 配置（~/.shannon/config.toml）

```toml
[core]
model = "deepseek:deepseek-v4-flash"

[provider]
api_key = "sk-..."
```
