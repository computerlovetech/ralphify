---
description: How ralphify assembles prompts, runs checks, and creates a self-healing feedback loop. Covers the iteration lifecycle, placeholder resolution, and output truncation.
---

# How It Works

This page explains what ralphify does under the hood during each iteration, how the prompt gets assembled, and how the feedback loop keeps the agent on track. Read this if you want to customize your loop beyond the basics or debug unexpected behavior.

## The iteration lifecycle

Each time the loop runs an iteration, ralphify follows these steps in order:

``` mermaid
flowchart TD
    A["📄 Read PROMPT.md from disk"] --> B["Run context commands"]
    B --> C["Inject context output into prompt"]
    C --> D["Inject instruction content"]
    D --> E{"Check failures\nfrom previous\niteration?"}
    E -- Yes --> F["Append failure output to prompt"]
    E -- No --> G["🤖 Pipe assembled prompt\nto agent via stdin"]
    F --> G
    G --> H["Wait for agent to finish\n(or timeout)"]
    H --> I["Run checks against\ncurrent project state"]
    I --> J["Store check failures\nfor next iteration"]
    J --> K{"More\niterations?"}
    K -- Yes --> L{"Delay\nset?"}
    K -- No --> M(["Print summary and exit"])
    L -- Yes --> N["⏳ Wait --delay seconds"]
    L -- No --> A
    N --> A

    style A fill:#7c4dff,color:#fff
    style B fill:#7c4dff,color:#fff
    style C fill:#7c4dff,color:#fff
    style D fill:#7c4dff,color:#fff
    style E fill:#7c4dff,color:#fff
    style F fill:#7c4dff,color:#fff
    style G fill:#00897b,color:#fff
    style H fill:#00897b,color:#fff
    style I fill:#1565c0,color:#fff
    style J fill:#1565c0,color:#fff
```

The lifecycle has three phases:

- :material-file-edit:{ .lg } **Prompt assembly** (purple) — read the prompt, resolve contexts and instructions, append check failures
- :material-play:{ .lg } **Execution** (green) — pipe the assembled prompt to the agent and wait
- :material-check-circle:{ .lg } **Validation** (blue) — run checks and store failures for the next iteration

The combination of validation and injection creates a self-healing feedback loop.

### What's fresh and what's fixed

The prompt file is re-read from disk at the start of **every** iteration, and context commands re-run each time. But primitive *configurations* are loaded once when the loop starts.

| What | When it's loaded | Can you change it while running? |
|---|---|---|
| `PROMPT.md` | Re-read every iteration | Yes — edits take effect next iteration |
| Context command output | Re-run every iteration | Yes — commands always produce fresh data |
| Context static content | Loaded at startup | No — restart the loop to pick up changes |
| Instruction content | Loaded at startup | No — restart the loop to pick up changes |
| Check commands/config | Loaded at startup | No — restart the loop to pick up changes |
| New/removed primitives | Discovered at startup | No — restart the loop to pick up changes |

This means:

- You can edit `PROMPT.md` while the loop is running, and changes take effect on the next iteration — this is the primary way to steer the agent in real time
- Context commands run fresh each iteration, so the agent always sees current data (latest git log, current test status, etc.)
- But if you add a new check, modify a check's command, change an instruction's content, or toggle a primitive's `enabled` flag, you need to stop the loop (`Ctrl+C`) and restart it
- The agent has no memory of previous iterations — all continuity comes from the codebase, git history, and any plan files the agent reads

## Prompt assembly

Ralphify builds the final prompt in three layers, applied in this order:

``` mermaid
flowchart LR
    A["PROMPT.md"] --> B["1. Context\nresolution"]
    B --> C["2. Instruction\nresolution"]
    C --> D["3. Check failure\ninjection"]
    D --> E["Assembled\nprompt"]
    F[(".ralph/contexts/")] --> B
    G[(".ralph/instructions/")] --> C
    H["Previous iteration\nfailures"] --> D
    E --> I["stdin → agent"]

    style E fill:#00897b,color:#fff
    style I fill:#00897b,color:#fff
```

### 1. Context resolution

For each enabled context, ralphify runs its command (if it has one) and combines the static content with the command output. Then it resolves placeholders in the prompt:

- **Named placeholders** like `{{ contexts.git-log }}` are replaced first with that specific context's content
- **Bulk placeholder** `{{ contexts }}` is replaced with all remaining contexts (those not already placed by name), sorted alphabetically
- **No placeholders** — if the prompt contains neither named nor bulk context placeholders, all context content is appended to the end

```markdown
# My Prompt

{{ contexts.git-log }}        ← this specific context goes here

Do the work.

{{ contexts }}                ← all other contexts go here
```

### 2. Instruction resolution

The same placeholder rules apply to instructions:

- `{{ instructions.code-style }}` places a specific instruction
- `{{ instructions }}` places all remaining instructions
- No placeholders means instructions are appended to the end

Instructions are resolved **after** contexts, so you can freely mix both types of placeholders in your prompt.

### 3. Check failure injection

If any checks failed on the **previous** iteration, their output is appended to the end of the prompt as a `## Check Failures` section. This always goes at the end — there's no placeholder for it.

The failure section includes:

- The check name
- The exit code (or timeout indicator)
- The command's stdout/stderr output (truncated to 5,000 characters)
- The check's failure instruction (the body text from `CHECK.md`)

Here's what the agent sees:

````markdown
## Check Failures

The following checks failed after the last iteration. Fix these issues:

### tests
**Exit code:** 1

```
FAILED tests/test_api.py::test_create_user - AssertionError: expected 201, got 400
```

Fix all failing tests. Do not skip or delete tests.
````

On the **first** iteration, no check failures are injected (there's no previous iteration to have failed).

## Full example: what the agent receives

Here's a concrete example showing how all three layers combine into the final prompt. Given these files:

**`PROMPT.md`**

```markdown
# Prompt

{{ contexts.git-log }}

You are an autonomous coding agent. Each iteration starts fresh.

Read PLAN.md and implement the next task.

## Rules
{{ instructions.code-style }}

- One task per iteration
- Commit with a descriptive message
```

**`.ralph/contexts/git-log/CONTEXT.md`**

```markdown
---
command: git log --oneline -5
timeout: 10
enabled: true
---
## Recent commits
```

**`.ralph/instructions/code-style/INSTRUCTION.md`**

```markdown
---
enabled: true
---
<!-- Internal note: agreed on these rules in sprint retro -->
- Use type hints on all function signatures
- Keep functions under 30 lines
```

And suppose the previous iteration's test check failed with exit code 1.

The **assembled prompt** piped to the agent as stdin:

````markdown
# Prompt

## Recent commits
a1b2c3d feat: add user model
e4f5g6h fix: database connection timeout
i7j8k9l docs: update API reference
m0n1o2p refactor: extract validation logic
q3r4s5t test: add integration tests

You are an autonomous coding agent. Each iteration starts fresh.

Read PLAN.md and implement the next task.

## Rules
- Use type hints on all function signatures
- Keep functions under 30 lines

- One task per iteration
- Commit with a descriptive message

## Check Failures

The following checks failed after the last iteration. Fix these issues:

### tests
**Exit code:** 1

```
FAILED tests/test_api.py::test_create_user - AssertionError: expected 201, got 400
```

Fix all failing tests.
````

Notice:

- `{{ contexts.git-log }}` was replaced with the static content ("## Recent commits") plus the live `git log` output
- `{{ instructions.code-style }}` was replaced inline with the instruction body
- The HTML comment in the instruction file was stripped — you can leave notes in your primitive files that won't appear in the agent's prompt
- Check failures from the previous iteration were appended at the end automatically
- On the first iteration, the "Check Failures" section would not be present

## Execution

The assembled prompt is piped to the agent command as **stdin**. The agent command is configured in `ralph.toml`:

```toml
[agent]
command = "claude"
args = ["-p", "--dangerously-skip-permissions"]
prompt = "PROMPT.md"
```

This runs as:

```
echo "<assembled prompt>" | claude -p --dangerously-skip-permissions
```

Ralphify waits for the process to finish. If `--timeout` is set and the agent exceeds it, the process is killed and the iteration is marked as timed out.

### Logging

When `--log-dir` is set, each iteration's stdout and stderr are captured and written to a timestamped log file (e.g., `001_20250115-142301.log`). The output is replayed to the terminal after the iteration completes — you'll still see everything, but not until the agent finishes.

Without `--log-dir`, agent output goes directly to the terminal in real time.

## Validation

After the agent finishes, ralphify runs all enabled checks. Each check is either a shell command (from the `command` field in `CHECK.md` frontmatter) or an executable script (`run.sh`, `run.py`, etc.) in the check directory.

Checks run **sequentially** in alphabetical order by name. Each check:

1. Executes the command/script in the project root directory
2. Captures stdout and stderr
3. Records the exit code (0 = pass, non-zero = fail)
4. Enforces its timeout (kills the process if exceeded)

If a check fails, its output is stored and injected into the **next** iteration's prompt. If all checks pass, no failure text is injected.

### The self-healing loop

This is the core mechanism that makes autonomous loops productive:

``` mermaid
sequenceDiagram
    participant P as Prompt
    participant A as Agent
    participant C as Checks

    rect rgb(200, 230, 255)
    note over P,C: Iteration N
    P->>A: Assembled prompt (no failures)
    A->>A: Makes a change
    A->>C: Done — run checks
    C-->>P: ✗ tests failed (output stored)
    end

    rect rgb(255, 245, 200)
    note over P,C: Iteration N+1
    P->>A: Prompt + check failure output
    A->>A: Fixes the broken tests
    A->>C: Done — run checks
    C-->>P: ✓ All checks pass
    end

    rect rgb(200, 255, 200)
    note over P,C: Iteration N+2
    P->>A: Prompt (no failures)
    A->>A: Moves on to the next task
    A->>C: Done — run checks
    C-->>P: ✓ All checks pass
    end
```

The agent doesn't need to "remember" that it broke something. The check failure output tells it exactly what went wrong, and the failure instruction tells it how you want it handled.

## Output truncation

To prevent extremely long output from consuming the agent's context window, ralphify truncates check output and context output to **5,000 characters**. Truncated output ends with `... (truncated)`.

This limit applies to each individual check or context output, not to the total prompt.

## Placeholder resolution rules

Both contexts and instructions follow the same placeholder resolution logic. Here's the complete set of rules:

| Prompt contains | Behavior |
|---|---|
| `{{ contexts.name }}` only | Named content placed inline; remaining contexts are **not** included |
| `{{ contexts }}` only | All enabled contexts placed at that location |
| Both named and `{{ contexts }}` | Named placed inline, remaining go to bulk placeholder |
| Neither | All enabled contexts appended to the end of the prompt |

The same rules apply for `{{ instructions }}` and `{{ instructions.name }}`.

!!! note "Named-only means remaining are dropped"
    If you use a named placeholder like `{{ contexts.git-log }}` but don't include `{{ contexts }}`, any other contexts are silently excluded. Add `{{ contexts }}` somewhere to catch everything else.

## Shutdown

The loop runs until one of these conditions:

- **Iteration limit**: `-n 5` stops after 5 iterations
- **Ctrl+C**: Graceful shutdown — the current iteration is interrupted and a summary is printed
- **`--stop-on-error`**: Stops if the agent exits with a non-zero code or times out

When the loop ends, ralphify prints a summary:

```
Done: 12 iteration(s) — 10 succeeded, 2 failed
```

## Project type detection

When you run `ralph init`, ralphify detects your project type by looking for marker files:

| File found | Detected type |
|---|---|
| `package.json` | `node` |
| `pyproject.toml` | `python` |
| `Cargo.toml` | `rust` |
| `go.mod` | `go` |
| None of the above | `generic` |

Files are checked in the order shown above. If a project contains multiple manifest files (e.g. both `package.json` and `pyproject.toml`), the first match wins.

The detected type is displayed during init but doesn't currently change the generated configuration. All project types get the same default `ralph.toml` and `PROMPT.md`.
