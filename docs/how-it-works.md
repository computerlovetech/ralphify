# How It Works

This page explains what ralphify does under the hood during each iteration, how the prompt gets assembled, and how the feedback loop keeps the agent on track. Read this if you want to customize your loop beyond the basics or debug unexpected behavior.

## The iteration lifecycle

Each time the loop runs an iteration, ralphify follows these steps in order:

```
1. Read PROMPT.md from disk
2. Run context commands and inject their output
3. Inject instruction content
4. Append check failures from the previous iteration
5. Pipe the assembled prompt to the agent via stdin
6. Wait for the agent to finish (or timeout)
7. Run checks against the current state of the project
8. Store any check failures for the next iteration
9. Wait (if --delay is set), then go to step 1
```

Steps 2-4 are the **prompt assembly** phase. Steps 5-6 are the **execution** phase. Steps 7-8 are the **validation** phase. The combination of validation and injection creates a self-healing feedback loop.

### Fresh context every time

The prompt file is re-read from disk at the start of **every** iteration. This means:

- You can edit `PROMPT.md` while the loop is running, and changes take effect on the next iteration
- Context commands run fresh each iteration, so the agent always sees current data (latest git log, current test status, etc.)
- The agent has no memory of previous iterations — all continuity comes from the codebase, git history, and any plan files the agent reads

## Prompt assembly

Ralphify builds the final prompt in three layers, applied in this order:

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

When `--log-dir` is set, each iteration's stdout and stderr are captured and written to a timestamped log file (e.g., `001_20250115-142301.log`). The output is still printed to the terminal in real time.

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

```
Iteration N:
  Agent makes a change → check fails (tests broken)

Iteration N+1:
  Agent sees check failure output in prompt →
  fixes the broken tests → checks pass

Iteration N+2:
  No failures from previous iteration →
  agent moves on to the next task
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
- **`--stop-on-error`**: Stops if the agent exits with a non-zero code

When the loop ends, ralphify prints a summary:

```
Done: 12 iteration(s) — 10 succeeded, 2 failed
```

## Project type detection

When you run `ralph init`, ralphify detects your project type by looking for marker files:

| Files found | Detected type |
|---|---|
| `pyproject.toml`, `setup.py`, `setup.cfg` | Python |
| `package.json` | Node.js |
| `Cargo.toml` | Rust |
| `go.mod` | Go |
| None of the above | Generic |

The detected type is displayed during init but doesn't currently change the generated configuration. All project types get the same default `ralph.toml` and `PROMPT.md`.
