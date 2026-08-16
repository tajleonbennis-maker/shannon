#!/usr/bin/env python3
"""给 TS 源码版打同一补丁（2 空格缩进）。"""
import sys

path = sys.argv[1]
with open(path) as f:
    src = f.read()

pairs = [
    (
        "  let turnCount = 0;",
        "  let turnCount = 0;\n  let toolCallCount = 0;",
    ),
    (
        "        case 'tool_execution_start': {\n          void auditLogger.logToolStart(event.toolName, event.args);",
        "        case 'tool_execution_start': {\n          toolCallCount += 1;\n          void auditLogger.logToolStart(event.toolName, event.args);",
    ),
    (
        "    // 6. Run the agent to completion (resolves at agent_end).\n    await session.prompt(fullPrompt);\n    session.dispose();",
        """    // 6. Run the agent to completion (resolves at agent_end).
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
    session.dispose();""",
    ),
]

for old, new in pairs:
    if new in src and old not in src:
        print("  already patched")
        continue
    assert old in src, f"NOT FOUND: {old[:60]!r}"
    src = src.replace(old, new, 1)
    print("  patched")

with open(path, "w") as f:
    f.write(src)
print(f"OK: {path}")
