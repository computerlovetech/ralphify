# How the loop works

The lifecycle of one iteration — the format you write, and the runtime that
runs it.

## The six steps of each iteration

1. **Re-read the prompt from disk.** The body (everything below the
   frontmatter) is read **every iteration**, so you can edit the task while the
   loop runs. Frontmatter (`agent`, `commands`, `args`) is parsed once at
   startup — restart to change it.
2. **Run commands and capture output.** Each command runs in order and captures
   stdout + stderr **regardless of exit code**. Commands run from the project
   root by default; `./`-prefixed commands run from the ralph directory. Each
   has a 60s default timeout (override per command with `timeout`).
3. **Resolve placeholders.** `{{ commands.<name> }}`, `{{ args.<name> }}`, and
   `{{ ralph.* }}` are substituted. `{{ args.* }}` resolves both in the body and
   in command `run` strings.
4. **Assemble the final prompt.** The resolved body becomes one text string.
   HTML comments (`<!-- … -->`) are stripped. By default a co-author trailer
   instruction is appended asking the agent to add
   `Co-authored-by: Ralphify <noreply@ralphify.co>` to commits — disable with
   `credit: false`.
5. **Pipe the prompt to the agent** via stdin (`echo "<prompt>" | <agent>`).
   The agent works in the current directory and exits; ralphify waits. When the
   agent command starts with `claude`, ralphify auto-adds
   `--output-format stream-json --verbose` for structured streaming.
6. **Loop back with fresh context.** The next iteration starts at step 1 with a
   clean context window and fresh command output.

## What gets re-read vs. fixed

| What | When read | Why it matters |
|---|---|---|
| Prompt body | Every iteration | Edit the task live; the next iteration follows it |
| Command output | Every iteration | The agent always sees fresh data (git log, test status) |
| Frontmatter (`agent`, `commands`, `args`) | Once at startup | Restart to change |
| User arguments | Once at startup | Constant for the run |

## The self-healing feedback loop

When iteration 1 breaks a test, iteration 2's `{{ commands.tests }}` shows it:

```
FAILED tests/test_auth.py::test_login - AssertionError: expected 200, got 401
====================== 1 failed, 4 passed in 1.45s =======================

If tests are failing, fix them before starting new work.
```

The agent sees the failure plus the instruction to fix it first. The agent
breaks something, the command captures it, the agent fixes it next iteration.
This is why feeding a test/lint/build command back into the prompt is the
single highest-leverage thing you can do in a ralph.
