#!/usr/bin/env python3
"""
Shannon 国产模型一键配置工具（cn-models 定制版配套）

自动生成 ~/.shannon/config.toml，支持：
  1. DeepSeek 官方（deepseek: 前缀，pi 原生，key 写入 [deepseek] 段）
  2. 阿里云 MaaS 网关（openrouter: 前缀 + base_url，走 chat/completions，key 写入 [provider] 段）
  3. 任意 OpenAI 兼容网关

用法:
  python3 shannon_cn_config.py deepseek --key sk-xxx [--model deepseek-v4-flash]
  python3 shannon_cn_config.py aliyun   --key sk-sp-xxx [--model glm-5.2] [--base-url https://...]
  python3 shannon_cn_config.py gateway  --key sk-xxx --model my-model --base-url https://.../v1
  python3 shannon_cn_config.py --list
  python3 shannon_cn_config.py deepseek --key sk-xxx --dry-run   # 只打印不写文件
"""

import argparse
import os
import sys
import tomllib

SHANNON_HOME = os.path.expanduser("~/.shannon")
CONFIG_PATH = os.path.join(SHANNON_HOME, "config.toml")

# 已验证的国产模型
KNOWN_MODELS = {
    "deepseek": ["deepseek-v4-flash", "deepseek-v4-pro", "deepseek-r1"],
    "aliyun": ["glm-5.2", "qwen3.8-max", "qwen3.7-plus", "qwen3.6-flash"],
}

ALIYUN_DEFAULT_BASE = "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"

# TOML 段说明（与 apps/cli/src/config/resolver.ts 的 CONFIG_MAP 对齐）：
#   - deepseek 是 curated provider，key 必须写在 [deepseek].api_key（映射 DEEPSEEK_API_KEY）
#   - openrouter 前缀（aliyun/gateway）非 curated，key 写在 [provider].api_key（映射 SHANNON_AI_API_KEY）


def build_toml(spec, base, api_key, key_section):
    """构造 config.toml 内容。key_section: 'deepseek' 或 'provider'。"""
    lines = ["# Shannon 配置 - 国产模型 (cn-models patch)", "[core]", f'model = "{spec}"']
    lines.append(f'base_url = "{base}"' if base else "# 直连 DeepSeek 官方")
    lines.append("")
    lines.append(f"[{key_section}]")
    lines.append(f'api_key = "{api_key}"')
    return "\n".join(lines) + "\n"


def write_config(content):
    os.makedirs(SHANNON_HOME, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        f.write(content)
    os.chmod(CONFIG_PATH, 0o600)
    print(f"[OK] 已写入 {CONFIG_PATH}")


def show_current():
    if not os.path.exists(CONFIG_PATH):
        print("当前无配置")
        return
    with open(CONFIG_PATH, "rb") as f:
        try:
            d = tomllib.load(f)
        except Exception:
            print(f"(解析失败，原文如下) {CONFIG_PATH}:")
            with open(CONFIG_PATH, encoding="utf-8") as f2:
                print(f2.read())
            return
    print(f"model     : {d.get('core', {}).get('model', '-')}")
    print(f"base_url  : {d.get('core', {}).get('base_url', '(直连)')}")
    for section, val in d.items():
        if section == "core":
            continue
        keys = list(val.keys()) if isinstance(val, dict) else []
        print(f"{section:<10}: {keys}")


def main():
    parser = argparse.ArgumentParser(description="Shannon 国产模型一键配置")
    parser.add_argument("target", nargs="?", choices=["deepseek", "aliyun", "gateway", "list"],
                        help="deepseek=DeepSeek官方 | aliyun=阿里云MaaS | gateway=任意兼容网关 | list=查看当前")
    parser.add_argument("--key", help="API Key")
    parser.add_argument("--model", default=None, help="模型 ID")
    parser.add_argument("--base-url", default=None, help="网关地址（gateway 必填）")
    parser.add_argument("--dry-run", action="store_true", help="只打印生成的 TOML，不写文件")
    args = parser.parse_args()

    if args.target == "list" or args.target is None:
        show_current()
        return

    if not args.key:
        print("[ERR] 需要 --key", file=sys.stderr)
        sys.exit(1)

    if args.target == "deepseek":
        model = args.model or "deepseek-v4-flash"
        spec = f"deepseek:{model}"
        base = None
        key_section = "deepseek"   # curated provider：key 走 [deepseek] 段 → DEEPSEEK_API_KEY
    elif args.target == "aliyun":
        model = args.model or "glm-5.2"
        spec = f"openrouter:{model}"   # 关键：走 chat/completions
        base = args.base_url or ALIYUN_DEFAULT_BASE
        key_section = "provider"       # 非 curated：key 走 [provider] 段 → SHANNON_AI_API_KEY
    else:  # gateway
        if not args.model or not args.base_url:
            print("[ERR] gateway 需要 --model 和 --base-url", file=sys.stderr)
            sys.exit(1)
        spec = f"openrouter:{args.model}"
        base = args.base_url
        key_section = "provider"

    content = build_toml(spec, base, args.key, key_section)

    if args.dry_run:
        print(content, end="")
        print("[DRY-RUN] 未写入文件")
        return

    write_config(content)
    print(f"  model     : {spec}")
    if base:
        print(f"  base_url  : {base}")
    print(f"  key 段    : [{key_section}]")
    print("")
    print("提示: 本 fork 的补丁在源码/自建镜像中，需 clone 本仓库构建后使用（见 README Quick Start），")
    print("      官方 npm 包 npx @keygraph/shannon 不含 CN 改造。")


if __name__ == "__main__":
    main()
