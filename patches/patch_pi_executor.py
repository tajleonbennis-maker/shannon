#!/usr/bin/env python3
"""Shannon DeepSeek 兼容补丁：agent 零工具调用结束时强制续跑。
同时适用于源码 .ts 和镜像编译产物 .js。
"""
import sys

OLD_DECL = "    let turnCount = 0;"
NEW_DECL = """    let turnCount = 0;
    let toolCallCount = 0;"""

OLD_CASE = """                case 'tool_execution_start': {
                    void auditLogger.logToolStart(event.toolName, event.args);"""
NEW_CASE = """                case 'tool_execution_start': {
                    toolCallCount += 1;
                    void auditLogger.logToolStart(event.toolName, event.args);"""

OLD_RUN_JS = """        // 6. Run the agent to completion (resolves at agent_end).
        await session.prompt(fullPrompt);
        session.dispose();"""
OLD_RUN_TS = """    // 6. Run the agent to completion (resolves at agent_end).
    await session.prompt(fullPrompt);
    session.dispose();"""

NEW_RUN = """    // 6. Run the agent to completion (resolves at agent_end).
    // PATCH(deepseek-compat): Providers like DeepSeek (OpenAI chat-completions
    // dialect) may end their first turn with plain text and no tool call, which
    // pi treats as task completion — the agent then dies in OutputValidation.
    // If the run finished without ever invoking a tool, steer it to continue.
    const MAX_CONTINUATIONS = 5;
    await session.prompt(fullPrompt);
    let continuations = 0;
    while (
      toolCallCount === 0 &&
      !pendingError &&
      continuations < MAX_CONTINUATIONS &&
      !(cancellationSignal?.aborted ?? false)
    ) {
      continuations += 1;
      logger.info(
        `[shannon-patch] runPiPrompt(${description}) ended with zero tool calls; steering continuation ${continuations}/${MAX_CONTINUATIONS}`,
      );
      await session.prompt(
        'You replied with text only and did not invoke any tools. Continue the task NOW by calling your tools (bash, read, grep, glob, etc.). Do not describe what you intend to do — execute it. Every response MUST include tool calls until the task is fully complete and the required deliverable file is written.',
      );
    }
    session.dispose();"""


def patch(path: str) -> None:
    with open(path) as f:
        src = f.read()
    for old, new, name in [
        (OLD_DECL, NEW_DECL, "decl"),
        (OLD_CASE, NEW_CASE, "case"),
        (OLD_RUN_TS, NEW_RUN, "run"),
        (OLD_RUN_JS, NEW_RUN.replace("    // 6.", "        // 6.", 1), "run"),
    ]:
        if new in src and old not in src:
            print(f"  [{name}] already patched")
            continue
        if old not in src:
            continue
        if old == NEW_RUN or old == NEW_RUN.replace("    // 6.", "        // 6.", 1):
            src = src.replace(old, new, 1)
            print(f"  [{name}] patched")
    # separately handle run block
    with open(path) as f:
        src = f.read()
    for old, new, name in [
        (OLD_DECL, NEW_DECL, "decl"),
        (OLD_CASE, NEW_CASE, "case"),
    ]:
        if old in src:
            src = src.replace(old, new, 1)
            print(f"  [{name}] patched")
        elif new in src:
            print(f"  [{name}] already patched")
        else:
            print(f"  [{name}] NOT FOUND")
            sys.exit(1)
    run_old = OLD_RUN_TS if ": " in path and path.endswith(".ts") else OLD_RUN_JS
    if run_old in src:
        src = src.replace(run_old, NEW_RUN if run_old == OLD_RUN_TS else NEW_RUN.replace("    // 6.", "        // 6.", 1), 1)
        print("  [run] patched")
    elif "shannon-patch" in src:
        print("  [run] already patched")
    else:
        print("  [run] NOT FOUND")
        sys.exit(1)
    with open(path, "w") as f:
        f.write(src)
    print(f"OK: {path}")


if __name__ == "__main__":
    patch(sys.argv[1])
