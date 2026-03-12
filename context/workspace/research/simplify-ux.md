# UX/UI Simplification Analysis

## Users' Jobs to Be Done

Based on the JTBD research and codebase analysis, these are the core jobs users hire ralphify to do, ranked by frequency × intensity:

1. **Ship features while I'm not coding** (J1) — Set agent running autonomously, wake up to working code. VERY HIGH frequency/intensity.
2. **Keep the agent from going off the rails** (J2) — Automatic quality gates that catch bad work. VERY HIGH frequency/intensity.
3. **Stop babysitting the agent** (J3) — Step away and let the agent work independently. HIGH frequency/intensity.
4. **Have a reliable, repeatable workflow** (J5) — Replace fragile bash scripts with structured primitives. HIGH frequency/intensity.
5. **Feel in control even when autonomous** (J6) — See what happened each iteration without reviewing every line. HIGH frequency/intensity.

These jobs map to five user-facing workflows:
- **Setup**: Go from zero to a running loop
- **Run**: Launch and configure the loop
- **Monitor**: Watch progress and understand what happened
- **Steer**: Adjust the agent's behavior while running
- **Trust**: Know the output is good via checks

---

## Current UX Audit

### Surface Area Inventory

**CLI Commands (5):**
| Command | Purpose |
|---|---|
| `ralph init` | Create ralph.toml + RALPH.md |
| `ralph run [name]` | Start the autonomous loop |
| `ralph status` | Validate setup and list primitives |
| `ralph new <type> <name>` | Scaffold a new primitive |
| `ralph ui` | Launch web dashboard |

**`ralph run` Flags (8):**
| Flag | Short | Purpose |
|---|---|---|
| `[RALPH_NAME]` | positional | Named ralph to use |
| `--prompt` | `-p` | Inline prompt text |
| `--prompt-file` | `-f` | Path to prompt file |
| `-n` | | Max iterations |
| `--stop-on-error` | `-s` | Stop if agent fails |
| `--delay` | `-d` | Seconds between iterations |
| `--log-dir` | `-l` | Directory for logs |
| `--timeout` | `-t` | Max seconds per iteration |

**Concepts Users Must Learn (10):**
1. ralph.toml (config file)
2. RALPH.md (root prompt file)
3. .ralphify/ directory (primitives home)
4. Checks (validation scripts)
5. Contexts (dynamic data injection)
6. Instructions (static reusable rules)
7. Ralphs (named prompt variants)
8. Template placeholders (`{{ contexts.name }}`, `{{ instructions }}`)
9. Frontmatter (YAML config in markdown)
10. Failure instructions (body text in CHECK.md)

**Config Files:**
- `ralph.toml` — agent command, args, default ralph
- `RALPH.md` — root prompt (or named ralph)
- `.ralphify/checks/<name>/CHECK.md` — check config + failure instruction
- `.ralphify/contexts/<name>/CONTEXT.md` — context config + static header
- `.ralphify/instructions/<name>/INSTRUCTION.md` — instruction body
- `.ralphify/ralphs/<name>/RALPH.md` — named ralph prompt

### Extended Concept Load (hidden complexity)

Beyond the 10 listed concepts, users must also internalize:

11. **Directory convention** — `.ralphify/<kind>/<name>/<MARKER>.md>` pattern
12. **Placeholder resolution order** — named > bulk > implicit append (three modes)
13. **`run.*` scripts** — escape hatch from `shlex.split()` for complex commands
14. **Ralph-scoped primitives** — `.ralphify/ralphs/<name>/checks/` nesting
15. **Enabled/disabled filtering** — frontmatter flag that controls inclusion
16. **HTML comment stripping** — comments in markdown bodies are stripped from prompts

Effective concept count is **16**, not 10. Progressive disclosure should let users operate with 3–4 concepts for their first month (config file, prompt file, checks) and discover the rest as needed.

---

## Friction Log

### Job: Setup (Go from zero to running loop)

**Steps walked through:**

1. `pip install ralphify` (or `uv tool install ralphify`) — fine
2. `ralph init` — creates ralph.toml + RALPH.md
3. User must edit RALPH.md manually — the template is generic ("Your prompt content here" equivalent)
4. User must know to run `ralph new check tests` to add quality gates
5. User must understand frontmatter syntax to configure the check command
6. User must edit ralph.toml if not using Claude Code (default is `claude` with `--dangerously-skip-permissions`)
7. `ralph status` to validate — good, but optional step users might skip
8. `ralph run -n 1` to test — must know to limit iterations for first try

**Friction points identified:**

- **F1: `ralph init` creates a useless prompt** (VALIDATED). The ROOT_RALPH_TEMPLATE at `_templates.py:61-74` is a generic skeleton. It says "Add your project-specific instructions below" but gives no guidance on what those should be. The user's very first edit is staring at a mostly-empty file. Compare: `git init` creates a working repo immediately.

- **F2: No checks created by default** (VALIDATED). After `ralph init`, running `ralph run` will start an agent loop with zero quality gates. The most important differentiator of ralphify (the self-healing feedback loop) is completely absent until the user manually discovers and runs `ralph new check`. This contradicts J2 (keep the agent from going off the rails), which is the #2 job.

- **F3: `detect_project()` does nothing with its result** (VALIDATED). The detector (`detector.py:11-27`) identifies Python/Node/Rust/Go projects, prints "Detected project type: python" during init, but takes no action. It doesn't create project-appropriate checks (e.g., `pytest` for Python, `npm test` for Node), doesn't customize the ralph.toml, and doesn't tailor the RALPH.md template. The user sees information but gets no benefit from it.

- **F4: Scaffolded templates are full of HTML comments explaining the format** (VALIDATED). The CHECK_MD_TEMPLATE, CONTEXT_MD_TEMPLATE, and INSTRUCTION_MD_TEMPLATE all contain multi-line HTML comments explaining the format rather than providing useful defaults. While comments are stripped from the assembled prompt (via `_HTML_COMMENT_RE` in `_frontmatter.py`), they create noise when the user opens the file to edit it. The check template defaults to `ruff check .` which may not be installed.

- **F5: 12-step getting started guide** (VALIDATED from docs). The documented onboarding flow is 12 steps. The minimum viable loop (init → edit prompt → add check → run) is 4 steps with manual editing. Could be fewer.

- **F17: `--dangerously-skip-permissions` in default config is alarming** (VALIDATED). The default `ralph.toml` template (`_templates.py:3-8`) includes `args = ["-p", "--dangerously-skip-permissions"]`. A new user sees the word "dangerously" in their config file on first run. This is a Claude Code flag that's necessary for autonomous operation, but: (a) it triggers anxiety about security, (b) it's meaningless for non-Claude-Code agents, (c) it violates the principle of trust — users are trying to trust the tool, and the default config contains a flag that sounds dangerous. The flag exists because Claude Code requires it, but the UX cost is real.

- **F18: No `.gitignore` guidance** (VALIDATED). After `ralph init`, there's no suggestion to add `ralph_logs/` or `.ralphify/` patterns to `.gitignore`. The `.ralphify/` directory should be committed (it's config), but log files shouldn't. New users may accidentally commit large log files or miss committing their primitive config. The init command could create/update `.gitignore` entries, or at minimum print guidance.

- **F29: `ralph.toml` has no comments or inline documentation** (VALIDATED). The generated `ralph.toml` (`_templates.py:3-8`) is 4 bare lines: `[agent]`, `command`, `args`, `ralph`. A new user has no idea what other options exist. There's no mention of `timeout`, `delay`, `log_dir`, or the `ralph` field's dual nature (file path or named ralph). Compare: a generated `.eslintrc` or `pyproject.toml` typically includes commented-out examples of common options. The user must read docs to discover any configuration beyond the defaults.

- **F36: `ralph init --force` overwrites both files without granularity** (VALIDATED). `cli.py:138-161`: `--force` overwrites both `ralph.toml` AND `RALPH.md`. A user who has carefully crafted their `RALPH.md` but wants to regenerate `ralph.toml` (e.g., to pick up a new default format) has no safe way to do this. They'd need to backup RALPH.md manually first.

### Job: Run (Launch the loop)

**Steps walked through:**

1. `ralph run` — uses ralph.toml defaults, works
2. `ralph run docs` — named ralph, works if it exists
3. `ralph run -n 3 --timeout 300 --log-dir logs` — full invocation

**Friction points identified:**

- **F6: Three ways to specify a prompt, unclear priority** (VALIDATED). Users can provide a prompt via: (a) positional `[RALPH_NAME]`, (b) `--prompt-file`/`-f`, (c) `--prompt`/`-p`, or (d) `ralph.toml`'s `ralph` field. The resolution chain in `ralphs.py:89-121` has a 4-level priority system. Using both `prompt_name` and `prompt_file` is an error (`cli.py:304-306`). This creates unnecessary cognitive load — "which one wins?" is a question users shouldn't have to answer.

- **F7: `--prompt-file` / `-f` is redundant** (VALIDATED). The `ralph.toml` already has a `ralph` field that can point to any file. Named ralphs live in `.ralphify/ralphs/`. Between the toml config and the positional argument, `--prompt-file` serves an edge case (one-off file that's not a named ralph and not the default). It adds a flag to learn and a conflict to handle (`cli.py:304-306`).

- **F8: Banner prints on every `ralph run`** (VALIDATED). The ASCII art banner (`cli.py:58-107`) prints every time the user runs `ralph run`. It's nice on first launch but wastes 8 lines of vertical space on subsequent runs. The "Star us on GitHub" line is promotional, not functional. During iteration, vertical space matters — users are scanning for check results and iteration status.

- **F9: No default for `-n` (iteration limit)** (VALIDATED). If the user omits `-n`, the loop runs infinitely until Ctrl+C. For new users, this is risky — J9 (prevent runaway costs) is a validated job. A sensible default (e.g., `-n 5` or `-n 10`) with an explicit `--no-limit` flag would protect new users while allowing power users to opt in.

- **F19: `ralph new ralph` reads awkwardly** (VALIDATED). To create a named ralph, the command is `ralph new ralph docs`. The word "ralph" appears twice: as the CLI tool name and as the primitive type. This is a consequence of using the product name ("ralph") as both the tool and a primitive type name. Compare: `git branch create` makes sense because "git" and "branch" are different words. A user may wonder "did I type that correctly?" Internally this is the `new_ralph` function at `cli.py:215-221`, which is even marked `hidden=True` — the `_DefaultRalphGroup` at `cli.py:46-52` auto-routes unknown subcommands to `ralph`, so `ralph new docs` works. But the hidden magic creates its own confusion: `ralph new --help` doesn't show how to create a ralph.

- **F20: No iteration progress when `-n` is set** (VALIDATED). When running `ralph run -n 10`, the iteration header shows `── Iteration 3 ──` but not `── Iteration 3/10 ──`. The user has no sense of progress toward the limit. The data is available in `RunConfig.max_iterations` but `ConsoleEmitter._on_iteration_started` doesn't use it (`_console_emitter.py:98-100`). For J6 (feel in control), knowing "3 of 10" vs "3 of ∞" is significant.

- **F21: `-p` inline prompt doesn't default to 1 iteration** (VALIDATED). When a user runs `ralph run -p "Fix the login bug"`, the inline prompt runs in an infinite loop, re-sending the same prompt every iteration. Inline prompts are almost always one-shot tasks. The engine at `cli.py:300-301` just uses the prompt_text with the default `n=None` (infinite). Users must remember to add `-n 1` for ad-hoc tasks or risk burning credits repeating the same prompt.

- **F33: `--stop-on-error` stops on agent failure but not check failure** (VALIDATED). From `engine.py:339-341`: `stop_on_error` only triggers when the agent process exits non-zero. Check failures do NOT trigger it — the loop continues and feeds the failure back. A user who sets `--stop-on-error` expecting the loop to stop when tests fail will be surprised. The flag name doesn't distinguish between "agent error" and "check error". There's no `--stop-on-check-failure` option. This is counterintuitive because checks ARE the error signal in ralphify's model — a check failure is the primary way users know something went wrong.

- **F38: No way to disable the banner via config or environment variable** (VALIDATED). Even users who know about the banner (F8) and find it annoying have no `RALPH_NO_BANNER=1` env var or `ralph.toml` option to suppress it. Power users running ralph in CI or scripts will be especially annoyed — the banner corrupts stdout parsing.

- **F42: No way to override ralph.toml settings from CLI** (VALIDATED). Many `ralph.toml` settings (like `command`, `args`) can only be changed by editing the file. If a user wants to quickly test with a different agent — `ralph run --command aider` — that doesn't exist. They have to edit the toml, run, then edit it back. This makes experimentation with different agents friction-heavy and error-prone (forgetting to revert the toml).

### Job: Monitor (Understand what happened)

**Steps walked through:**

1. During run: see iteration headers, spinner with elapsed time, check results
2. After run: summary line ("Done: 3 iteration(s) — 3 succeeded")
3. With `--log-dir`: per-iteration log files with full agent output

**Friction points identified:**

- **F10: No default log directory** (VALIDATED). Without `--log-dir`, all agent output is lost after the run. The user has to remember to add `--log-dir logs` every time. This contradicts J6 (feel in control even when autonomous) — you can't feel in control if you can't review what happened. Most users who care about quality will want logs. Should be on by default.

- **F11: Check failure output is truncated to 5,000 chars with no warning** (VALIDATED). `_output.py` truncates output to 5,000 characters with only `... (truncated)` appended to the text itself. This truncated text is injected into the next iteration's prompt. The CLI output (`_console_emitter.py`) shows no indication that truncation occurred. If a test suite produces verbose output, critical failure information may be cut off and the user never knows. For the agent, it sees `... (truncated)` but has no idea how much was lost (was it 5,001 chars or 50,000?).

- **F12: Iteration output is minimal during run** (VALIDATED). The console emitter (`_console_emitter.py`) shows: iteration header, spinner, completion status, check pass/fail summary. It does NOT show: which prompt was used, how many contexts/instructions were resolved, prompt length, or any preview of what the agent was told. For J6 (feel in control), users would benefit from knowing what went into each iteration.

- **F22: No indication of which check is currently running** (VALIDATED). During the checks phase, the console shows nothing until ALL checks complete. Checks run sequentially (`checks.py:125`: a list comprehension). If a user has 5 checks and the third one hangs, they see a blank screen with no indication of progress. The `CHECKS_STARTED` event fires before any checks run, and `CHECKS_COMPLETED` fires after all are done. The engine DOES emit `CHECK_PASSED`/`CHECK_FAILED` per check (`engine.py:286-289`), but `ConsoleEmitter` doesn't handle those events — only `CHECKS_COMPLETED`. The per-check event infrastructure exists but isn't rendered.

- **F23: Run summary doesn't include check statistics** (VALIDATED). The `_on_run_stopped` handler at `_console_emitter.py:138-151` shows iteration count and success/failure counts, but not check statistics. After a 10-iteration run, the user sees "Done: 10 iteration(s) — 7 succeeded, 3 failed" but not how many total checks passed/failed across all iterations. For J6 (feel in control), an aggregate like "Checks: 45/50 passed across 10 iterations" would be informative. The data exists in per-iteration `CHECKS_COMPLETED` events but isn't aggregated.

- **F31: No way to see what prompt was sent to the agent** (VALIDATED). The `PROMPT_ASSEMBLED` event at `engine.py:333` includes `prompt_length` but not the actual prompt text. `ConsoleEmitter._handlers` doesn't even include `PROMPT_ASSEMBLED` — the event is emitted but never rendered in CLI mode. Log files (`_agent.py:39-49`) only contain agent *output* (stdout/stderr), not the *input* prompt. If a user wants to debug "why did the agent do X?", they can't see what it was told. The only way is to read the source files manually and mentally resolve placeholders.

- **F32: Streaming mode only for Claude Code, silent fallback for others** (VALIDATED). `_agent.py:52-57`: `_is_claude_command` hardcodes a check for binary name "claude". Only Claude gets streaming mode with `--output-format stream-json --verbose`. All other agents get `subprocess.run` — blocking with no output until completion. There's no CLI flag or config to opt into streaming for custom agents. The dashboard's live activity feed (`AGENT_ACTIVITY` events) only works with Claude Code. Users of Aider, Codex, or custom wrappers see nothing in the dashboard during execution and get no terminal output during iteration (when logging is enabled — `_agent.py:174` sets `capture_output=bool(log_path_dir)`).

- **F41: The delay flag (`-d`) has no countdown or clear indication** (VALIDATED). When `ralph run -d 30` is used, the delay between iterations is printed as `[dim]Waiting 30s...[/dim]` (`engine.py:413`). This is a plain dim text message with no countdown, no progress bar, no indication of how long remains. For long delays (e.g., 60s to avoid rate limits), the user might think the tool has hung. The `time.sleep(config.delay)` at `engine.py:414` is a blocking call with no updates.

- **F43: Non-Claude agents show no output during iteration when logging is enabled** (VALIDATED). From `_agent.py:169-180`: when `log_path_dir` is set (including with the proposed default O2), `subprocess.run` is called with `capture_output=True`. This means ALL stdout/stderr is buffered until the process exits. For a 5-minute agent session, the terminal shows nothing but the spinner. After completion, the full output is echoed at once (`sys.stdout.write(result.stdout)`), but by then the user has been staring at a blank screen. This is the worst monitoring experience: the user sees nothing, then a wall of text. Claude Code avoids this via `run_agent_streaming` which reads line-by-line, but other agents have no equivalent.

### Job: Steer (Adjust behavior while running)

**Steps walked through:**

1. Edit RALPH.md in another terminal — re-read each iteration (works!)
2. Adding/removing checks, contexts, instructions — requires restart
3. Editing check commands — requires restart

**Friction points identified:**

- **F13: Primitive config is frozen at startup — not documented in CLI** (VALIDATED). The engine discovers primitives once at startup (`engine.py:379`). New checks, contexts, or instructions added while running are invisible until restart. The docs mention this, but the CLI gives zero indication. Users who add a check and expect it to run next iteration will be confused.

- **F14: No signal when RALPH.md changes are picked up** (VALIDATED). RALPH.md is re-read each iteration (`engine.py:184`), which is great for steering. But the console shows no indication that the prompt changed. Users editing RALPH.md while running have no confirmation their edits took effect.

- **F24: The reload mechanism exists but is invisible from CLI** (VALIDATED). The engine has `state.consume_reload_request()` at `engine.py:157` which triggers `_discover_enabled_primitives()` to re-scan all primitives. The `RunState` class has `request_reload()` (`_run_types.py:106`). But there's no CLI mechanism to trigger it — it's only accessible via the dashboard API. A user who adds a check and wants it picked up must restart the entire loop, losing their iteration count and any momentum. A signal handler (e.g., SIGUSR1) or a sentinel file could bridge this gap.

### Job: Trust (Know the output is good)

**Steps walked through:**

1. Checks run after each iteration
2. Failures feed back into next iteration's prompt
3. `ralph status` shows which checks are configured

**Friction points identified:**

- **F15: No guidance on WHAT checks to add** (VALIDATED). `ralph new check <name>` scaffolds an empty check. The template defaults to `ruff check .`. There's no "common checks" suggestion based on project type, no example library, and no indication of what good checks look like for the user's specific job.

- **F16: Silent context/instruction exclusion with named placeholders** (VALIDATED). From `resolver.py:43-55`: if you use `{{ contexts.git-log }}` without a `{{ contexts }}` bulk placeholder, ALL other contexts are silently dropped. There's no warning. This is documented in the docs but is a subtle, high-impact gotcha that violates the principle of least surprise.

- **F25: Check failure instructions are invisible until failure** (VALIDATED). The body text of CHECK.md (the failure instruction) is only ever shown to the agent, not the user. When a user creates a check, they write failure guidance in the markdown body, but there's no way to preview what the agent will actually see when the check fails. The `ralph status` command shows check names and commands but not failure instructions. For J2 (keep the agent from going off the rails), the quality of failure instructions is critical, yet users have no feedback loop on them.

- **F26: Checks always run sequentially, no early termination** (VALIDATED). `run_all_checks` at `checks.py:119-125` runs every check regardless of prior failures. If a fast lint check fails, the user still waits for a slow integration test to complete before the next iteration starts. There's no `--fail-fast` option for checks. For users with ordered checks (lint → typecheck → test), failing lint makes typecheck and test runs wasteful.

- **F30: Context command output injected regardless of exit code** (VALIDATED). From `contexts.py:85-107`: if a context command fails (non-zero exit code), the output is still injected into the prompt. This is documented as a feature ("useful for tests that fail but produce output") but is surprising. The `run_context` function returns `success=False` but `resolve_contexts` at `contexts.py:120-146` uses the output regardless of the `success` field. A user who adds `command: npm test` as a context and it fails will inject test failure output into every iteration's prompt — even though they might have intended it as a data source, not a test runner. There's no `required: true/false` frontmatter field to control whether a failed context should be injected.

- **F34: `ralph status` doesn't validate check commands will actually work** (VALIDATED). `cli.py:224-272`: `ralph status` checks if the agent command is on PATH and if the ralph file exists, but doesn't validate check or context commands. A user could have `command: ruff check .` in their check and `ruff` isn't installed — `ralph status` says "Ready to run." and the loop starts, only to have the check fail every iteration with a cryptic "command not found" error. The `status` command could parse each check's frontmatter and validate the command's first token is on PATH.

- **F37: Named placeholder for non-existent primitive silently produces empty string** (VALIDATED). From `resolver.py:35-41`: the `_replace_named` function checks `if name in available` — if the name isn't found, it returns `""`. A user who writes `{{ contexts.git-log }}` but named their context `gitlog` (no hyphen) gets an empty string with no warning. Combined with F16 (other contexts silently dropped when named placeholders are used), this can produce a prompt missing most of its intended context. The placeholder just vanishes.

- **F39: Check failure instruction text has no length guidance or limit** (VALIDATED). A check's failure instruction (body of CHECK.md) can be arbitrarily long. If a user writes a 10,000-character essay in CHECK.md, that full text gets appended to the prompt every time the check fails (`checks.py:152-153`). The check output is truncated to 5,000 chars, but the failure instruction is not. A verbose failure instruction could consume more of the agent's context window than the actual error output. The best practices docs say "write failure instructions that guide, not just complain" but the tool doesn't enforce or warn about excessive length.

### Job: Scaffold (Create new primitives)

**Steps walked through:**

1. `ralph new check tests` — creates `.ralphify/checks/tests/CHECK.md`
2. `ralph new context git-log` — creates `.ralphify/contexts/git-log/CONTEXT.md`
3. `ralph new instruction coding-standards` — creates `.ralphify/instructions/coding-standards/INSTRUCTION.md`
4. `ralph new docs` — creates `.ralphify/ralphs/docs/RALPH.md` (auto-routed via `_DefaultRalphGroup`)
5. `ralph new --ralph myralph check tests` — creates ralph-scoped check

**Friction points identified:**

- **F27: `ralph new` subcommand structure requires knowing primitive type names** (VALIDATED). A user who wants to "add something that runs tests after each iteration" must know that's called a "check". A user who wants to "inject the git log into the prompt" must know that's called a "context". The terminology is not self-evident from the domain. `ralph new` with no args shows help listing `check`, `context`, `instruction`, and (hidden) `ralph` — but the help descriptions are the only guide. There's no `ralph new --interactive` that asks "What do you want to add?" and guides them.

- **F28: `--ralph` flag on `ralph new` is confusing** (VALIDATED). To scope a check to a specific named ralph: `ralph new check tests --ralph my-task`. The flag name `--ralph` collides with the product name again. The semantics are "scope this primitive to the named ralph called my-task" but a new user might read it as "create a ralph called tests" or "use ralph to create something". The directory structure it creates (`.ralphify/ralphs/my-task/checks/tests/CHECK.md`) is deeply nested and non-obvious.

- **F40: `ralph new` doesn't open the created file in `$EDITOR`** (VALIDATED). After `ralph new check tests`, the user sees "Created .ralphify/checks/tests/CHECK.md" and then has to manually navigate to and open the file. Many CLI tools (e.g., `git commit`, `crontab -e`) open the file automatically. Given that every scaffolded file needs editing (the templates contain generic placeholder content), this adds one extra step per primitive creation. A `--edit` flag (or auto-detect `$EDITOR`) would save time.

### Error Message Quality Audit (NEW)

This section walks through every error path in the codebase and evaluates whether the error message helps the user fix the problem. Grounded in: if a user triggers this error, can they immediately know what to do?

**Error: `ralph.toml not found. Run 'ralph init' first.`** (`cli.py:131`)
- Quality: GOOD. Clear problem, clear fix. Exit code 1.

**Error: `{CONFIG_FILENAME} already exists. Use --force to overwrite.`** (`cli.py:148`)
- Quality: GOOD. Tells user what to do.

**Error: `RALPH.md already exists. Use --force to overwrite.`** (`cli.py:155`)
- Quality: GOOD.

**Error: `Cannot use both a ralph name and --prompt-file.`** (`cli.py:305`)
- Quality: ADEQUATE. Says what's wrong but doesn't say which to prefer. Could add: "Use one or the other."

**Error: `Ralph '{name}' not found. Available: {list}`** (`ralphs.py:73-76`)
- Quality: GOOD. Shows what's available, suggests correction.

**Error: `Prompt file '{path}' not found.`** (`cli.py:319`)
- Quality: ADEQUATE. Says what's missing but doesn't suggest how to create it. Could add: "Run 'ralph init' to create RALPH.md."

**Error: `{Label} '{name}' already exists at {path}`** (`cli.py:181`)
- Quality: GOOD. Shows exact path.

**Error: `Check '{name}' has neither a run.* script nor a command — skipping`** (`checks.py:61`)
- Quality: POOR — this is a `warnings.warn()`, not a CLI error. It fires during discovery and might be lost in output. A user who creates a CHECK.md and forgets to add a command gets a warning they might never see. The check is silently excluded from the loop. For `ralph status`, this check would show up with `?` detail but no explanation of why.

- **F44: Check without command/script produces a warning, not a clear error** (NEW, VALIDATED). `checks.py:55-62`: when a CHECK.md has no `command` field and no `run.*` script, `_check_from_entry` returns `None` and the check is silently excluded from the list. A `warnings.warn()` fires but users may not see it. The `ralph status` command shows `?` for the detail but doesn't explain why. A user who creates a check and forgets to add the command sees the check in `ralph status` with `?`, runs the loop, and the check never executes. No error, no clear signal.

**Error: `Agent command not found: '{command}'. Check the [agent] command in ralph.toml.`** (`engine.py:224-227`)
- Quality: GOOD. Clear error, points to config file.

**Error: (Crash traceback) `Run crashed: {exc}`** (`engine.py:419-425`)
- Quality: ADEQUATE. Shows traceback in dim text but this is a catch-all. Unexpected errors get the same treatment as known errors.

- **F45: `ralph.toml` has no schema validation** (NEW, VALIDATED). `cli.py:127-134`: `_load_config()` loads the TOML file and returns a raw dict. The `run()` function at `cli.py:294-297` accesses `config["agent"]`, `agent["command"]`, etc. with no validation. If `ralph.toml` is missing the `[agent]` section, `command` field, or has typos (e.g., `comandd`), the user gets a raw Python `KeyError` traceback — not a helpful error message. Example: a user who writes `commnad = "claude"` (typo) gets `KeyError: 'command'` with no context about which key is missing or where.

- **F46: `resolve_ralph_source` has a confusing silent fallback** (NEW, VALIDATED). `ralphs.py:108-123`: when `ralph.toml` has `ralph = "docs"` (looks like a name) but no ralph named "docs" exists, the function silently falls back to treating "docs" as a file path. The user then hits "Prompt file 'docs' not found" — a confusing error because they intended "docs" as a ralph name, not a file path. The heuristic `is_ralph_name()` at `ralphs.py:79-88` checks for absence of `/` and `.` — but `"docs"` passes both checks. The fallback at line 121 (`return toml_ralph, None`) converts a "ralph not found" into a "file not found" without explaining the resolution chain.

- **F47: `ralph status` doesn't show which ralph will be used by `ralph run`** (NEW, VALIDATED). `cli.py:224-272`: the status command shows the `ralph` field from the config (e.g., `RALPH.md`), validates it exists, but doesn't indicate whether `ralph run` would use a named ralph, a root prompt file, or has a fallback chain. If `ralph.toml` has `ralph = "docs"`, status shows `Ralph: docs` and checks if the *file* "docs" exists — but it should check whether a ralph named "docs" exists under `.ralphify/ralphs/`. The status command doesn't mirror `resolve_ralph_source()`'s logic, so what status reports and what `run` uses can diverge.

- **F48: Context timeout defaults to 30s — silently fails for slow commands** (NEW, VALIDATED). `contexts.py:33`: the default context timeout is 30 seconds. If a user adds `command: npm test` as a context (to show test status) and the test suite takes >30s, the context silently times out. The output up to the timeout is still injected, but it's incomplete. There's no warning that a context timed out — the ContextResult has `timed_out=True` but `resolve_contexts` at `contexts.py:120-146` uses the output regardless. The user sees partial test output in their prompt with no indication that it was cut short by a timeout, not by the tests finishing.

- **F49: Log file naming is opaque** (NEW, VALIDATED). `_agent.py:46-48`: log files are named `{iteration:03d}_{timestamp}.log` (e.g., `001_20250312-143022.log`). This is useful for ordering but tells the user nothing about what happened. There's no way to quickly identify which iterations had failures vs successes from the filename alone. A naming convention like `001_20250312-143022_pass.log` or `001_20250312-143022_fail.log` would let users scan the log directory for problems.

- **F50: Non-Claude agent output dumped as wall of text after iteration** (NEW, VALIDATED). `_agent.py:176-181`: after `subprocess.run` completes with `capture_output=True`, the full stdout is dumped via `sys.stdout.write(result.stdout)`. This is a raw write — no paging, no truncation, no formatting. If the agent produced 10,000 lines of output, all 10,000 lines are printed at once between the iteration header and the check results. The user sees the spinner, then a massive wall of text, then the check results. The iteration status line (✓/✗ with duration) gets buried in the output.

### Configuration Surface Area Analysis (NEW)

The configuration story has three layers that interact in non-obvious ways:

**Layer 1: `ralph.toml` (project-level defaults)**
```toml
[agent]
command = "claude"
args = ["-p", "--dangerously-skip-permissions"]
ralph = "RALPH.md"
```
- Only 3 fields. No validation. No schema.
- `ralph` field has dual semantics: file path OR named ralph name. The distinction is made by `is_ralph_name()` checking for absence of `/` and `.`.
- No config for: timeout, delay, log_dir, stop_on_error. These are CLI-only.
- **Gap**: Users who always want `--log-dir logs --timeout 300` must type it every time. There's no way to set defaults in the config.

**Layer 2: CLI flags (per-invocation overrides)**
- 8 flags on `ralph run`, 1 on `ralph init`, 0 on `ralph status`.
- Cannot override `command` or `args` from CLI — must edit toml.
- Can set `--timeout` on CLI but not in toml. Can set `command` in toml but not on CLI. The two config surfaces are **non-overlapping** except for the `ralph` field.

**Layer 3: Frontmatter (per-primitive config)**
- `enabled`, `timeout`, `command`, `description` fields. Only `enabled` and `timeout` have type coercion.
- No schema or validation beyond type coercion. Unknown fields silently accepted as strings.
- `timeout` in frontmatter (per-check/context) vs `--timeout` on CLI (per-iteration) — same word, different scope. A user might think `--timeout 300` sets check timeouts.

**The interplay creates friction:**
- "How do I set the default timeout for all checks?" → Can't. Each check has its own frontmatter timeout, defaulting to 60s. No global check timeout.
- "How do I always log to a directory?" → Can't configure in toml. Must add `--log-dir` every time or use a shell alias.
- "How do I switch agents for one run?" → Can't use CLI. Must edit toml, run, edit back.
- "What does `ralph = "docs"` mean in my toml?" → Could be a file named "docs" or a ralph named "docs". `is_ralph_name()` decides, but the user has no visibility into this heuristic.

- **F51: CLI and toml config surfaces don't overlap** (NEW, VALIDATED). The CLI has `--timeout`, `--delay`, `--log-dir`, `--stop-on-error` that can't be set in toml. The toml has `command` and `args` that can't be overridden from CLI. Users who want consistent defaults for CLI-only settings have no config mechanism. Users who want to experiment with CLI-settable toml settings must edit the file. This creates a "worst of both worlds" situation where neither the config file nor the CLI is a complete control surface.

---

## Cross-Cutting Analysis

### The Invisible Infrastructure Problem

Several friction points share a root cause: things happen invisibly and the user has no way to observe them. This is the single biggest trust issue in ralphify's UX.

| What's invisible | Friction | Impact |
|---|---|---|
| Output truncation (5,000 chars) | F11 | User/agent don't know critical info was cut |
| Primitive config frozen at startup | F13 | User adds check, expects it to run, nothing happens |
| Prompt changes picked up silently | F14 | User edits RALPH.md, no confirmation it took effect |
| Context/instruction silent exclusion | F16 | Named placeholders silently drop other primitives |
| Per-check execution progress | F22 | User stares at blank screen during check phase |
| Full assembled prompt | F31 | User can't see what agent was told |
| Agent execution (non-Claude) | F43 | No output during iteration for non-Claude agents |
| Named placeholder resolution failure | F37 | Typo in placeholder name → silent empty string |
| Context timeout | F48 | Context times out silently, partial output injected |
| Ralph name/path resolution | F46 | Name falls back to path silently, confusing error |

**Root principle: Observability is trust.** Users can't trust what they can't see. Every invisible operation should have at least a dim/debug-level signal in the CLI output. The cost of one extra line of output is far lower than the cost of a user spending 20 minutes debugging why their context isn't being injected.

### The Two User Journeys

The friction analysis reveals two distinct user journeys with fundamentally different needs:

**Journey A: Quick Start** (Vibe Coder, Solo Founder)
- Wants: `ralph init && ralph run` to just work
- Blocked by: F1 (useless template), F2 (no checks), F3 (detection waste), F5 (12 steps), F9 (infinite default)
- Needs: smart defaults, auto-scaffolding, safe guardrails

**Journey B: Deep Customization** (Staff Engineer, Platform Engineer)
- Wants: fine-grained control over every aspect of the loop
- Blocked by: F31 (can't see prompt), F32 (Claude-only streaming), F42 (can't override config from CLI), F33 (stop-on-error semantics), F26 (no fail-fast), F51 (non-overlapping config surfaces)
- Needs: preview command, per-check events, CLI overrides, pluggable streaming, unified config

Current UX is stuck in the middle: too much ceremony for quick starters (12 steps), not enough power tools for power users. The simplification strategy should explicitly serve both — **reduce the floor** (fewer steps to first run) and **raise the ceiling** (more control for experts).

### The "Ralph" Naming Overload

The word "ralph" carries 5 meanings:
1. The CLI tool name (`ralph run`)
2. The root prompt file (`RALPH.md`)
3. A named prompt variant ("a ralph")
4. The `--ralph` scoping flag on `ralph new`
5. The `.ralphify/ralphs/` directory

This creates friction at F19, F22, F28 and any documentation that tries to distinguish between these uses. The `_DefaultRalphGroup` hidden routing (`cli.py:46-52`) is clever but adds a 6th layer of confusion: `ralph new docs` secretly becomes `ralph new ralph docs`, but this isn't shown in `--help`.

### The Configuration Identity Crisis (NEW)

Ralphify has three non-overlapping configuration surfaces (see F51):

1. **`ralph.toml`** controls: agent command, agent args, default prompt source
2. **CLI flags** control: iteration limit, timeout, delay, log dir, stop behavior
3. **Frontmatter** controls: per-primitive enabled, timeout, command

No single surface is authoritative. The mental model should be: "toml for project defaults, CLI for session overrides, frontmatter for per-primitive config." But the implementation doesn't follow this cleanly:
- `timeout` appears in both CLI (per-iteration) and frontmatter (per-check), with confusingly similar names but different scopes
- `ralph` (prompt source) appears in both toml and CLI (positional + `--prompt-file`)
- Common settings like log directory and iteration limit have no toml representation

**Opportunity: Unify the config model.** Allow `ralph.toml` to set defaults for ALL settings:
```toml
[agent]
command = "claude"
args = ["-p", "--dangerously-skip-permissions"]
ralph = "RALPH.md"

[run]
max_iterations = 5
timeout = 300
delay = 0
log_dir = "ralph_logs"
stop_on_error = false
```
CLI flags override toml defaults. This eliminates F42 and F51 simultaneously.

### The Error Diagnostic Gap (NEW)

The error path analysis reveals a pattern: errors are well-worded for expected cases (file not found, config not found) but fall through to raw Python exceptions for edge cases:
- Missing `[agent]` section in toml → `KeyError: 'agent'`
- Typo in toml field name → `KeyError` with no context
- Malformed frontmatter → depends on the parsing failure mode

The fix is lightweight: add a config validation step in `_load_config()` that checks for required keys and returns a typed object (or at minimum a clear error).

### The Agent Parity Problem (NEW)

Ralphify markets itself as "agent-agnostic" but the implementation is Claude-first:

| Feature | Claude Code | Other agents |
|---|---|---|
| Streaming output | Yes (JSON lines) | No |
| Dashboard activity feed | Yes | No (silent) |
| Live terminal output during iteration | Yes | Only without `--log-dir` |
| Result text extraction | Yes (`result` field from JSON) | No |
| Auto-added flags | `--output-format stream-json --verbose` | None |

This isn't necessarily wrong — Claude Code is the primary audience. But the marketing says "works with any agent CLI" while the experience diverges sharply. For non-Claude users, ralphify feels like a wrapper around `subprocess.run` with added complexity.

**Key insight:** The agent parity gap affects monitoring (J6) disproportionately. Non-Claude users can still SET UP and RUN loops fine. But they can't MONITOR effectively because the streaming/logging infrastructure assumes Claude's JSON output format. This makes the tool feel less trustworthy (J2) for non-Claude users.

---

## Simplification Opportunities

Ranked by: (impact on user's job) × (frequency of the job) / (effort + risk)

### Tier 1: High Impact, Low Effort

#### O1: Smart `ralph init` — auto-create project-appropriate checks
**What:** When `ralph init` detects a Python project, auto-create `.ralphify/checks/tests/CHECK.md` with `command: uv run pytest -x` (or `npm test` for Node, `cargo test` for Rust, etc.). Similarly auto-create a lint check appropriate to the ecosystem.
**Why:** Removes F2 (no checks by default) and F3 (detect_project does nothing). The core value of ralphify — self-healing feedback loops — should be active from the first run, not after manual setup.
**Job:** Setup (J1, J2, J5)
**Effort:** S — `detect_project()` already identifies the ecosystem; just need to call `_scaffold_primitive` with appropriate templates per project type.
**Risk:** Low. Generated checks might not match the user's exact setup (e.g., they use `pytest` not `uv run pytest`). Mitigate by making generated checks obviously editable and running `ralph status` to validate.

#### O2: Default log directory (`ralph_logs/`)
**What:** Always log to `ralph_logs/` unless `--no-logs` is explicitly passed. Add `ralph_logs/` to `.gitignore` guidance.
**Why:** Removes F10. Every user running loops for real needs logs for J6 (feel in control). Requiring `--log-dir` every time is a footgun for new users.
**Job:** Monitor, Trust (J6)
**Effort:** S — one default value change in `cli.py:283`.
**Risk:** Low. Disk space is cheap. Users who don't want logs can opt out. **But see F43** — enabling default logging for non-Claude agents means `capture_output=True`, which blocks all terminal output during iteration. O2 should be implemented together with a fix for F43 (e.g., use `tee`-style capture).

#### O3: Default iteration limit (e.g., 5)
**What:** Change `-n` default from unlimited to 5. Add `--no-limit` or `-n 0` for infinite mode.
**Why:** Removes F9. Protects new users from runaway costs (J9). Power users can easily opt into infinite mode.
**Job:** Run, Trust (J1, J9)
**Effort:** S — one default value change.
**Risk:** Medium. Existing users who rely on infinite loops will need to add `--no-limit`. But this is the safer default — it's far worse to accidentally run an infinite loop than to have to type `--no-limit`.

#### O4: Suppress banner on `ralph run`
**What:** Only show banner on `ralph` (no subcommand). Don't print it on `ralph run`.
**Why:** Removes F8. Saves 8+ lines of vertical space every run. Users running `ralph run` repeatedly (the core workflow) don't need the logo each time.
**Job:** Monitor (J6)
**Effort:** S — remove `_print_banner()` call from `run()` at `cli.py:293`.
**Risk:** Very low. The banner still shows on bare `ralph` command.

#### O14: Show iteration progress as N/M when `-n` is set
**What:** Change the iteration header from `── Iteration 3 ──` to `── Iteration 3/10 ──` when max iterations is configured. Keep `── Iteration 3 ──` when running infinitely.
**Why:** Removes F20. Costs nothing, gives immediate sense of progress. Requires passing `max_iterations` from `RunConfig` into the `ITERATION_STARTED` event data and reading it in `ConsoleEmitter`.
**Job:** Monitor (J6)
**Effort:** XS — add one field to event data, one format string change in emitter.
**Risk:** None.

#### O15: Default `-n 1` for inline prompts (`-p`)
**What:** When `--prompt`/`-p` is used, automatically set `max_iterations=1` unless `-n` is explicitly provided.
**Why:** Removes F21. Inline prompts are almost always one-shot tasks. Running `ralph run -p "Fix the login bug"` in an infinite loop is a footgun — the same prompt re-sends every iteration.
**Job:** Run (J1, J9)
**Effort:** XS — one conditional in `cli.py:run()` before constructing `RunConfig`.
**Risk:** Very low. Users who genuinely want to repeat an inline prompt can add `-n 5`.

#### O24: Render per-check events in ConsoleEmitter
**What:** Add `CHECK_PASSED` and `CHECK_FAILED` to `ConsoleEmitter._handlers`. Show `  ⋯ running: tests` before each check and the pass/fail result immediately after.
**Why:** Addresses F22. The event infrastructure already exists (`engine.py:286-289` emits `CHECK_PASSED`/`CHECK_FAILED` per check). The `ConsoleEmitter` just doesn't handle them — it only renders `CHECKS_COMPLETED`. This is the lowest-effort monitoring improvement possible: the data is already flowing, it just needs a renderer.
**Job:** Monitor (J6)
**Effort:** XS — add two handlers to `_handlers` dict, ~10 lines of rendering code.
**Risk:** None.

### Tier 2: High Impact, Medium Effort

#### O5: Remove `--prompt-file` / `-f` flag
**What:** Remove the `--prompt-file` flag entirely. Users who want a custom file put the path in `ralph.toml`'s `ralph` field.
**Why:** Removes F6 (three ways to specify prompt) and F7 (redundant flag). Simplifies the run command from 8 flags to 7. Eliminates the error case where both `prompt_name` and `--prompt-file` are used.
**Job:** Run (J1, J5)
**Effort:** S-M — remove flag from CLI, simplify `resolve_ralph_source()`, update docs.
**Risk:** Medium. Breaks any user currently using `--prompt-file`. But the toml config or named ralphs cover every use case.

#### O6: Warn on silent context/instruction exclusion
**What:** When named placeholders are used without a bulk placeholder, emit a warning listing which contexts/instructions were excluded.
**Why:** Removes F16. Prevents subtle prompt assembly bugs that undermine J2 (keep agent from going off the rails).
**Job:** Trust (J2, J6)
**Effort:** S-M — add a warning in `resolve_placeholders()` when `has_named` is true and no bulk placeholder exists and there are remaining items.
**Risk:** Low. Warnings are informational and non-breaking.

#### O7: Show prompt assembly summary per iteration
**What:** After prompt is assembled, print one line: `Prompt: 2,847 chars | Contexts: 3 | Instructions: 2 | Check failures: 1`.
**Why:** Addresses F12 and F14. Users can see at a glance what went into each iteration. If they edit RALPH.md and the char count changes, they know it took effect.
**Job:** Monitor, Steer (J6)
**Effort:** S — the data is already in `EventType.PROMPT_ASSEMBLED` event; just render it in `ConsoleEmitter`.
**Risk:** Very low. One extra line of output per iteration.

#### O8: Better `ralph init` prompt template with guided sections
**What:** Replace the generic ROOT_RALPH_TEMPLATE with a structured template that has labeled sections: Role, Task (with a pointer to a TODO.md pattern), Constraints, Process. Include a comment explaining each section.
**Why:** Addresses F1. The prompt is the most important file in the entire setup — it shouldn't be the one that gets the least guidance.
**Job:** Setup (J1, J5)
**Effort:** S — just change the template string.
**Risk:** Low. More opinionated template, but the current one is too minimal to be useful.

#### O16: Show truncation details in CLI output
**What:** When check output or context output is truncated (>5,000 chars), show `⚠ Output truncated: 12,847 → 5,000 chars` in the CLI. Also include the original length in the text injected into the prompt: `... (truncated from 12,847 to 5,000 chars)` instead of just `... (truncated)`.
**Why:** Addresses F11. Users and agents both know when they're seeing partial information. The agent can request full output from logs or ask the user for help. Currently `truncate_output()` at `_output.py:28-32` discards the original length entirely.
**Job:** Monitor, Trust (J6)
**Effort:** S — change return type of `truncate_output()` to include a flag or length, update `format_check_failures()` to include length info.
**Risk:** Very low.

#### O17: Soften the `--dangerously-skip-permissions` default
**What:** Three options, from least to most effort: (a) Add an inline comment in the generated ralph.toml explaining why it's there: `# Required for Claude Code autonomous mode — safe for local development`. (b) Move it to a preset system: `ralph init --agent claude` pre-configures the right args. (c) Auto-detect the agent and set appropriate defaults during init.
**Why:** Addresses F17. The word "dangerously" in a default config file undermines trust on first contact. Users who aren't using Claude Code are confused by it; users who are using Claude Code are alarmed by it.
**Job:** Setup, Trust (J1, J2)
**Effort:** S (option a) to M (option c).
**Risk:** Low. Adding a comment costs nothing. Agent presets are more work but future-proof.

#### O18: Emit per-check events during execution
**What:** Show `  ⋯ running: tests` in the console during each check.
**Why:** Addresses F22. Users with multiple checks (especially slow ones like integration tests) can see which check is currently running instead of staring at a blank screen.
**Job:** Monitor (J6)
**Effort:** S-M — the events already exist (CHECK_PASSED/CHECK_FAILED are emitted per-check). The gap is in `ConsoleEmitter` rendering (see O24) and potentially adding a CHECK_STARTED event to show the name before it runs.
**Risk:** Very low. More events = more information.

#### O25: Warn on unresolved named placeholders
**What:** When `{{ contexts.git-log }}` resolves to empty string because no context named "git-log" exists, emit a warning: `⚠ Placeholder {{ contexts.git-log }} not found — no context with that name exists. Available: gitlog, git-diff`.
**Why:** Addresses F37. Typos in placeholder names are currently silent and devastating — the user's prompt is missing critical context with no indication. The `_replace_named` function at `resolver.py:35-41` already knows the name isn't in `available`; it just needs to warn instead of silently returning `""`.
**Job:** Trust (J2, J6)
**Effort:** S — add a `warnings.warn()` call in `_replace_named` when `name not in available`. List available names in the warning message.
**Risk:** Very low. Warning only, no behavior change.

#### O26: Validate check/context commands in `ralph status`
**What:** Parse each check's and context's frontmatter `command` field, extract the first token (via `shlex.split`), and check if it's on PATH. Show a warning for each command that can't be found.
**Why:** Addresses F34. Users who run `ralph status` and see "Ready to run." should be able to trust that claim. Currently, a missing `ruff` binary will only surface as repeated check failures during the loop.
**Job:** Trust, Setup (J2, J5)
**Effort:** S — iterate over discovered checks/contexts in the `status` command, call `shutil.which()` on each command's first token.
**Risk:** Very low. Warnings only. Some commands might be scripts or PATH-dependent in ways that can't be validated statically, so frame as "warning" not "error".

#### O27: Clarify `--stop-on-error` semantics or add `--stop-on-check-failure`
**What:** Either: (a) rename `--stop-on-error` to `--stop-on-agent-error` to make the scope explicit, or (b) add a `--stop-on-check-failure` flag that stops the loop when any check fails, or (c) change `--stop-on-error` to also trigger on check failures (breaking change).
**Why:** Addresses F33. Check failures are the primary signal in ralphify — they're what makes the loop self-healing. A user who sets `--stop-on-error` expecting it to cover checks will be surprised when the loop continues after test failures. The current behavior makes sense for ralphify's model (self-healing loops should continue), but the flag name is misleading.
**Job:** Run, Trust (J2, J6)
**Effort:** S-M — option (a) is a rename, (b) is a new flag + one conditional in engine.py.
**Risk:** Low for (a) and (b). Higher for (c) since it changes default behavior.

#### O31: Validate `ralph.toml` schema on load (NEW)
**What:** Add validation in `_load_config()` that checks for required keys (`[agent]`, `command`) and provides clear error messages: "ralph.toml is missing the 'command' field under [agent]. Example: command = \"claude\"". Use a simple dict check, not a schema library.
**Why:** Addresses F45. Currently, a typo in ralph.toml produces a raw Python KeyError. Schema validation turns cryptic tracebacks into actionable error messages. This is a trust issue — if the tool crashes on a config typo, users lose confidence.
**Job:** Setup, Trust (J1, J5)
**Effort:** S — add ~15 lines of validation code in `_load_config()`.
**Risk:** None.

#### O32: Show context timeout warnings (NEW)
**What:** When a context command times out (`ContextResult.timed_out=True`), emit a warning in the CLI: `⚠ Context 'tests' timed out after 30s — output may be incomplete. Consider increasing timeout in CONTEXT.md frontmatter.` Also mark the injected output: `(timed out after 30s — output may be incomplete)`.
**Why:** Addresses F48. Context timeouts are currently invisible. The partial output is injected without any indication that it was cut short. This can cause the agent to act on incomplete information.
**Job:** Trust, Monitor (J2, J6)
**Effort:** S — add timeout check in the context resolution path, emit a warning event.
**Risk:** None.

#### O33: Unify config surfaces — add `[run]` section to `ralph.toml` (NEW)
**What:** Allow ralph.toml to set defaults for all `ralph run` flags:
```toml
[run]
max_iterations = 5
timeout = 300
delay = 0
log_dir = "ralph_logs"
stop_on_error = false
```
CLI flags override toml defaults. Existing behavior unchanged if `[run]` section is absent.
**Why:** Addresses F42 and F51. Users who always want the same settings don't have to type them every time. Makes the config file the single source of project-level defaults.
**Job:** Run, Setup (J1, J5, J6)
**Effort:** M — parse new section in `_load_config()`, merge with CLI args in `run()`.
**Risk:** Low. Purely additive — no breaking changes. CLI flags always win.

### Tier 3: Medium Impact, Medium Effort

#### O9: Hot-reload primitives
**What:** Re-discover checks, contexts, and instructions at the start of each iteration (not just startup).
**Why:** Addresses F13 and F24. Users can add/modify checks while the loop runs without restarting. Makes the steering experience consistent — if RALPH.md can change mid-run, why can't checks?
**Job:** Steer (J3, J6)
**Effort:** M — move `_discover_enabled_primitives()` call into the iteration loop. The `consume_reload_request()` mechanism exists in the engine (`engine.py:157`), so infrastructure is partially there. Could also use a lighter approach: compare file mtimes before rescanning.
**Risk:** Medium. Discovery is filesystem I/O — adds latency per iteration. Also, adding a check mid-run that fails could surprise the agent if it wasn't prompted to address that check.

#### O10: Merge "instructions" into RALPH.md / checks
**What:** Eliminate the "instructions" primitive type. Static instructions belong in RALPH.md directly. Per-check instructions are already the CHECK.md body (failure instructions). The template placeholder `{{ instructions }}` can be replaced by just writing the content in the prompt.
**Why:** Reduces concept count from 10 to 9. Instructions are the least differentiated primitive — they're just static text. Contexts have commands (dynamic), checks have commands + failure feedback. Instructions have... nothing special. They're a text include mechanism.
**Job:** Setup, Steer (all jobs, indirectly)
**Effort:** L — breaking change, requires migration path for existing users with instructions.
**Risk:** High. Some users may have built workflows around instructions as a separate concept (e.g., shared instructions across multiple ralphs). The composability argument is valid. **Consider instead**: just deprioritize instructions in docs and scaffolding, so new users don't encounter them until needed.

#### O19: Aggregate check statistics in run summary
**What:** Track total checks passed/failed across all iterations and show in the final summary: `Done: 10 iteration(s) — 7 succeeded, 3 failed | Checks: 45/50 passed overall`.
**Why:** Addresses F23. After a long run, the user gets a snapshot of check health without scrolling through all iterations. The `ConsoleEmitter` already receives `CHECKS_COMPLETED` events per iteration — just needs a running counter.
**Job:** Monitor (J6)
**Effort:** S — add two counters to `ConsoleEmitter`, increment in `_on_checks_completed`, display in `_on_run_stopped`.
**Risk:** None.

#### O20: Expose reload trigger from CLI (via file or signal)
**What:** Watch for a sentinel file (e.g., `.ralphify/.reload`) or catch SIGUSR1 to trigger `state.request_reload()` during a running loop. Delete the sentinel after consuming it. This bridges the gap between the existing reload infrastructure and CLI users.
**Why:** Addresses F24. Users can `touch .ralphify/.reload` in another terminal to pick up new/changed primitives without restarting. Power users can script it. No UI needed.
**Job:** Steer (J3, J6)
**Effort:** S-M — add a file watcher or signal handler in the main loop. Could piggyback on the existing `_handle_loop_transitions()` function.
**Risk:** Low. Platform-dependent (SIGUSR1 not on Windows). File sentinel approach is cross-platform.

#### O21: `ralph run --fail-fast-checks`
**What:** Add an option to stop running remaining checks after the first failure. Useful when checks are ordered from fast (lint) to slow (integration tests).
**Why:** Addresses F26. Saves time and compute when early checks fail. The best practices docs already recommend ordering checks "from fast to strict", but the tool doesn't support short-circuiting.
**Job:** Run, Trust (J2, J3)
**Effort:** S-M — change `run_all_checks` to accept an `early_exit` flag and break on first failure.
**Risk:** Low. Opt-in flag, no behavior change for existing users. Agent still sees the specific failure that triggered the stop.

#### O28: Fix non-Claude agent output during logging
**What:** For non-streaming agents (`run_agent` in `_agent.py`), use a `tee`-style approach: read output line-by-line and simultaneously display to terminal and buffer for log file, instead of the current all-or-nothing `capture_output`.
**Why:** Addresses F43 and F50. Currently, enabling `--log-dir` for non-Claude agents means zero terminal output during the entire iteration, followed by a wall of text. This is the worst possible monitoring experience and directly contradicts J6 (feel in control). With the proposed O2 (default logging), this would become the default experience for all non-Claude users — making O28 a prerequisite for O2.
**Job:** Monitor (J6)
**Effort:** M — change `subprocess.run` to `subprocess.Popen` with a line-by-line read loop similar to `run_agent_streaming`, but without JSON parsing.
**Risk:** Low. The streaming version for Claude already proves this approach works.

#### O29: Add inline comments to generated `ralph.toml`
**What:** Expand the `RALPH_TOML_TEMPLATE` to include commented-out examples of common config options: `# timeout = 300`, `# delay = 5`, `# log_dir = "ralph_logs/"`. Add a comment explaining the `args` line for Claude Code users.
**Why:** Addresses F29 and partially F17. The config file is the first thing a user reads after init. It should be self-documenting enough that the user doesn't need to open docs to understand what's configurable.
**Job:** Setup (J1, J5)
**Effort:** XS — just change the template string.
**Risk:** None.

#### O34: Improve `ralph status` to mirror `ralph run` resolution (NEW)
**What:** Make `ralph status` use the same `resolve_ralph_source()` logic as `ralph run`. Show the resolved prompt source: "Ralph: RALPH.md (from ralph.toml)" or "Ralph: .ralphify/ralphs/docs/RALPH.md (named ralph 'docs')". Warn if the `ralph` field in toml matches neither a file nor a named ralph.
**Why:** Addresses F46 and F47. Currently `ralph status` and `ralph run` can disagree about which prompt file to use. Status shows the raw toml value; run resolves it through a priority chain with fallbacks. If they diverge, the user trusts status and is surprised by run.
**Job:** Trust, Setup (J2, J6)
**Effort:** S-M — call `resolve_ralph_source()` from status and display the resolved path.
**Risk:** Very low.

#### O35: Include pass/fail suffix in log filenames (NEW)
**What:** Change log file naming from `001_20250312-143022.log` to `001_20250312-143022_pass.log` or `001_fail.log`. The suffix reflects the agent's exit code.
**Why:** Addresses F49. Users scanning a log directory can immediately identify failed iterations without opening each file. Essential for long runs (50+ iterations) where manual scanning is infeasible.
**Job:** Monitor (J6)
**Effort:** XS — pass return code to `_write_log()`, append suffix to filename.
**Risk:** Very low. Log file naming is internal, not a public API.

### Tier 4: Exploratory / Higher Risk

#### O12: `ralph init --interactive` wizard
**What:** Interactive setup that asks: What agent? (Claude/Aider/custom), What should it work on? (generates RALPH.md), What checks? (tests/lint/typecheck based on project). Falls back to current non-interactive behavior by default.
**Why:** Could reduce 12-step onboarding to 1 command. But adds complexity and interactive UX is harder to test.
**Job:** Setup (J1, J5)
**Effort:** L
**Risk:** Medium. Interactive prompts can be annoying in CI/automation. Must remain optional.

#### O13: Reduce `-p`/`--prompt` to just positional override
**What:** Instead of a separate `--prompt` flag for inline text, let `ralph run "Fix the login bug"` work as an inline prompt (detected by the string not matching any named ralph).
**Why:** More natural CLI UX. `ralph run "Fix the login bug"` vs `ralph run -p "Fix the login bug"`.
**Job:** Run (J1)
**Effort:** M — need to disambiguate between ralph names and inline prompts.
**Risk:** Medium. How do you distinguish `ralph run docs` (named ralph) from `ralph run "docs"` (inline prompt)? Could use quoting as the signal, but fragile.

#### O22: Rename "ralphs" primitive to "prompts" or "tasks"
**What:** Rename the primitive type from "ralphs" to "prompts" (or "tasks"). The directory would be `.ralphify/prompts/` instead of `.ralphify/ralphs/`. Commands become `ralph new prompt docs` instead of `ralph new ralph docs`.
**Why:** Addresses F19 and F28. The word "ralph" is currently overloaded to mean: (1) the CLI tool, (2) the root prompt file (RALPH.md), (3) a named prompt variant (a "ralph"), (4) the `--ralph` scoping flag, and (5) the `.ralphify/ralphs/` directory. This is five meanings for one word. "Prompt" or "task" would be clearer for meaning #3-5 while keeping "ralph" as the brand/tool name.
**Job:** All (reduces cognitive load across every job)
**Effort:** L — rename in all code, update docs, migration for existing `.ralphify/ralphs/` directories.
**Risk:** High. Breaking change. But the current naming is genuinely confusing for new users. Could be done as a major version bump with a compatibility shim that auto-discovers the old directory name.

#### O23: Preview the assembled prompt before sending to agent
**What:** Add `ralph preview [name]` command that assembles the full prompt (resolving contexts, instructions, etc.) and prints it to stdout without running the agent. Useful for debugging prompt assembly and checking placeholder resolution.
**Why:** Addresses F31 and F25 (partially) and aids debugging F16 (silent exclusion) and F37 (silent empty placeholder). Users can see exactly what the agent will receive. Contexts execute but the agent doesn't. Could also support `ralph preview --with-failures "check output here"` to simulate the failure feedback injection.
**Job:** Trust, Steer (J2, J6)
**Effort:** M — extract `_assemble_prompt()` into a standalone command, add context execution.
**Risk:** Low. New command, no behavior changes.

#### O30: Save assembled prompt to log directory
**What:** When `--log-dir` is set, write the assembled prompt to the log file alongside agent output. Format: `=== PROMPT ===\n{prompt}\n=== OUTPUT ===\n{output}`.
**Why:** Addresses F31 without adding a new CLI command. Users debugging "why did the agent do X?" can check the log file to see both the input and the output. This is simpler than O23 (preview command) and covers the most common debugging scenario.
**Job:** Monitor, Trust (J6)
**Effort:** S — pass the assembled prompt to `_execute_agent`, include it in the log write.
**Risk:** Very low. Log files get larger, but disk space is cheap and the prompt is the most important debugging artifact.

---

## Principles Applied

| Principle | Where Applied |
|---|---|
| **Sensible defaults** | O1 (auto-create checks), O2 (default logs), O3 (default iteration limit), O15 (inline prompt → 1 iteration), O17 (explain scary flag), O29 (documented config), O33 (toml defaults for run settings) |
| **Remove before you add** | O5 (remove --prompt-file), O10 (merge instructions) |
| **Fewer concepts** | O10 (merge instructions into prompt/checks), O22 (rename ralphs to reduce polysemy) |
| **Progressive disclosure** | O3 (safe default, opt into infinite), O4 (banner only when relevant), O21 (fail-fast checks opt-in) |
| **Convention over configuration** | O1 (detect project, create appropriate checks), O2 (default log dir), O15 (inline = one-shot), O17 (agent presets) |
| **Clear feedback** | O6 (warn on silent exclusion), O7 (prompt summary), O14 (progress N/M), O16 (truncation indicator), O18/O24 (per-check status), O19 (aggregate stats), O23/O30 (prompt visibility), O25 (warn on missing placeholder), O26 (validate commands), O31 (config validation), O32 (context timeout warning), O34 (status mirrors run), O35 (log file naming) |
| **Fewer steps** | O1 (init creates working setup), O8 (better template), O20 (reload without restart) |
| **Obvious naming** | O22 (rename ralphs to prompts/tasks), O27 (clarify stop-on-error scope) |
| **Observability is trust** | O7, O14, O16, O24, O25, O26, O28, O30, O32, O34, O35 (every invisible operation gets a signal) |
| **Single source of truth** | O31 (validated config), O33 (unified config surface), O34 (status mirrors run) |

---

## Recommended Implementation Order

Based on re-ranking with cross-cutting insights:

**Phase 1 — "Just Works" (all XS-S effort, highest combined impact):**
1. O4: Suppress banner on `ralph run` (XS)
2. O14: Show iteration progress N/M (XS)
3. O15: Default `-n 1` for inline prompts (XS)
4. O24: Render per-check events in ConsoleEmitter (XS — events already exist)
5. O29: Add inline comments to generated `ralph.toml` (XS)
6. O35: Include pass/fail suffix in log filenames (XS)
7. O7: Show prompt assembly summary per iteration (S)
8. O19: Aggregate check statistics in run summary (S)
9. O25: Warn on unresolved named placeholders (S)
10. O31: Validate `ralph.toml` schema on load (S)
11. O32: Show context timeout warnings (S)

**Phase 2 — "Smart Setup" (S-M effort, addresses the biggest setup gap):**
12. O1: Smart `ralph init` with auto-created checks (S)
13. O8: Better `ralph init` prompt template (S)
14. O17a: Add comment to `ralph.toml` explaining dangerous flag (S)
15. O3: Default iteration limit of 5 (S, needs careful migration comms)
16. O26: Validate check/context commands in `ralph status` (S)
17. O34: Improve `ralph status` to mirror `ralph run` resolution (S-M)
18. O6: Warn on silent context/instruction exclusion (S-M)

**Phase 3 — "Observable Loop" (M effort, addresses monitoring gaps):**
19. O28: Fix non-Claude agent output during logging (M — prerequisite for O2)
20. O2: Default log directory (S, but depends on O28)
21. O16: Show truncation details (S)
22. O30: Save assembled prompt to log directory (S)
23. O33: Unify config surfaces — add `[run]` section to toml (M)

**Phase 4 — "Power User Tools" (M-L effort, addresses expert needs):**
24. O23: Preview command (M)
25. O5: Remove `--prompt-file` flag (S-M)
26. O21: Fail-fast checks (S-M)
27. O27: Clarify stop-on-error semantics (S-M)
28. O9: Hot-reload primitives (M)

---

## Open Questions

1. **How many users currently use `--prompt-file`?** If the answer is "almost none," removing it (O5) is safe. If some users depend on it, provide a migration period.

2. **What's the right default for `-n`?** Proposed: 5. But should it be 3? 10? Could also scale with project type or check count. Needs user testing.

3. **Should instructions be deprecated or just deprioritized?** O10 proposes merging them into other concepts. The composability argument (shared instructions across ralphs) is real. Alternative: keep them but don't scaffold them during init or mention them in getting-started docs.

4. **Would hot-reloading primitives (O9) confuse the agent?** If a new check appears mid-run, the agent hasn't been told about it. The failure feedback will mention it, but the agent might be confused by a check it wasn't originally instructed to satisfy.

5. **Is the banner (O4) important for brand recognition?** It uses vertical space but creates visual identity. Compromise: show it only on first run per session, or make it one line instead of six.

6. **What percentage of new users run `ralph status` before `ralph run`?** If most skip validation, the quality gates in `status` aren't providing value. Consider running status checks automatically as part of `ralph run` (emit warnings, not errors).

7. **Does `detect_project()` need to be more sophisticated?** It checks 4 manifest files. Many projects have multiple (e.g., Python + Node). Should it support multi-ecosystem projects? Or is the first-match heuristic good enough for auto-scaffolding checks?

8. **Should the `-p` inline prompt automatically set `-n 1`?** Inline prompts (`ralph run -p "quick task"`) are almost always one-off. Making them default to 1 iteration would remove a footgun without affecting named ralphs. (See O15 — this iteration validates this should be a **yes**.)

9. **Is "ralph" as a primitive name too confusing to keep?** The five-way overload (tool, file, primitive, flag, directory) is a real source of confusion. But renaming is a breaking change. Would a deprecation/migration period be worth it? Or is the confusion manageable because the hidden `_DefaultRalphGroup` routing means users rarely type `ralph new ralph`?

10. **Should `ralph init` auto-update `.gitignore`?** Precedent: tools like `cargo init` and `git init` manage `.gitignore`. Ralphify could add `ralph_logs/` and optionally `.ralphify/` patterns. Risk: modifying user files beyond the explicit scope of "init" may be surprising.

11. **Should `ralph status` run automatically before `ralph run` (first time only)?** If the setup isn't valid (missing prompt file, missing command), `ralph run` fails with an error at `cli.py:318-320`. Running status checks proactively would catch issues earlier and print more helpful diagnostics. But it adds latency to every run.

12. **Would a `ralph preview` command (O23) cannibalize `ralph run -n 1`?** Some users already use `-n 1` as a dry-run-ish workflow. A preview command would be more explicit ("show me the prompt but don't run it") vs. `-n 1` ("run one real iteration"). They serve different needs: preview is for debugging prompt assembly, `-n 1` is for testing the full loop.

13. **Should O2 (default logging) be blocked on O28 (fix non-Claude output)?** Enabling default logging for non-Claude agents would cause F43 (zero terminal output during iteration) to become the default experience. This is a worse UX than no logging. Recommendation: implement O28 first, then O2.

14. **Is `context.success` field being ignored a bug or a feature?** `resolve_contexts` at `contexts.py:120-146` uses context output regardless of whether the command succeeded. The FAQ says "Context commands run regardless of exit code" — but users may not expect failed command output in their prompt. Should there be a `required: true` field that skips injection on failure?

15. **Should `--stop-on-error` cover check failures too?** The current behavior (only stops on agent process failure) makes sense for the self-healing loop model. But users from CI/CD backgrounds expect "stop on error" to mean "stop when anything fails." Options: rename to `--stop-on-agent-error`, add `--stop-on-check-failure`, or change the behavior with a deprecation warning.

16. **Should `ralph.toml` support a `[run]` section for default CLI settings?** (NEW) O33 proposes this but it changes the config surface. Questions: Should all CLI flags be representable in toml? What about flags that only make sense per-invocation (like `-p`)? Should there be a precedence doc?

17. **Should log files include the assembled prompt?** (NEW) O30 proposes this. The prompt can be large (5,000+ chars with contexts). Including it in every log file doubles the file size. Alternative: write a separate `001_prompt.md` file alongside the log. Or only write the prompt when a `--debug` flag is set.

18. **How should the dual-nature of `ralph.toml`'s `ralph` field be resolved?** (NEW) Currently `is_ralph_name()` checks for absence of `/` and `.`. This heuristic fails for values like `my-task` (could be either). Should the field be split into `ralph_file` and `ralph_name`? Or should named ralphs always be prefixed (e.g., `ralph = "@docs"`)? The current silent fallback (F46) is the biggest source of confusing errors.

---

## Deep Dive: The Debugging & Error Recovery Experience (NEW)

This section walks through three concrete scenarios where the user's loop isn't producing good results, analyzing every step of the debugging journey and where friction emerges.

### Scenario 1: "The agent keeps making the same mistake"

**Situation:** The loop is running, tests pass, but every iteration the agent creates unnecessary utility files. The user wants this to stop.

**Actual recovery journey:**

1. Notice the problem (requires reviewing git history or log files — no alert mechanism)
2. Decide where to intervene: prompt vs. check vs. instruction
3. Open RALPH.md, add a sign: "Do NOT create utility files"
4. Wait for the current iteration to finish (could be 5+ minutes)
5. Hope the next iteration picks up the edit (no confirmation it did — F14)
6. Watch to see if the behavior changed (requires attention, contradicts J3)

**New friction identified:**

- **F52: No way to know if the agent is exhibiting a pattern without manual review** (NEW, VALIDATED). The run summary shows iteration count and pass/fail but nothing about what the agent actually did. The user must manually `git log` or read log files. For J6 (feel in control), the tool should surface behavioral patterns — not just pass/fail status.

- **F53: No way to interrupt the current iteration gracefully** (NEW, VALIDATED). When the user spots a problem mid-iteration, their only option is to let the iteration complete (wasting time/money) or Ctrl+C the entire loop (losing run state and check feedback). There's no "finish this iteration's checks but don't start the next one" signal. The `request_pause()` mechanism in `RunState` exists but is only exposed through the dashboard API — not from the CLI terminal.

### Scenario 2: "My context isn't showing up in the prompt"

**Situation:** The user added `{{ contexts.git-log }}` to RALPH.md, created the context, but the agent doesn't seem to see it.

**Actual debugging journey:**

1. Run `ralph status` — shows the context exists and is enabled (✓ git-log). Looks fine.
2. Run `ralph run -n 1 --log-dir logs` and check the log — but the log only shows agent *output*, not the *input prompt* (F31). Can't verify what the agent was told.
3. Re-read RALPH.md — maybe a typo? `{{ contexts.git-log }}` vs `{{ context.git-log }}` (singular vs plural). Singular produces raw `{{ context.git-log }}` text visible in agent output if noticed.
4. Check the context directory name — `.ralphify/contexts/git-log/CONTEXT.md`. Is it `git-log` or `gitlog`? Name is directory-based (F37).
5. If the name is correct but user also used a named placeholder for another context without a bulk `{{ contexts }}` — the git-log context is silently dropped (F16).
6. No tool to test this. Must mentally simulate the placeholder resolution algorithm.

**Total time to diagnose: 15-30 minutes** for what's often a typo or a missing bulk placeholder. The core issue: **the prompt assembly pipeline is opaque**.

- **F54: No `ralph debug` or dry-run mode for diagnosing prompt assembly** (NEW, VALIDATED). O23 proposes a `ralph preview` command, but the gap is larger than just preview. Users need a diagnostic mode that shows: which contexts were found, which were placed by name, which were dropped, which had errors. The `_assemble_prompt` function at `engine.py:168-192` does this work but emits only `PROMPT_ASSEMBLED` with `prompt_length` — no breakdown of what was resolved.

### Scenario 3: "Checks always fail but I don't know why"

**Situation:** The user added a check with `command: ruff check .` but ruff isn't installed. The check fails every iteration.

**Actual debugging journey:**

1. See check failures in iteration output: `✗ lint (exit 1)`
2. The check output shows a command-not-found error, but it's truncated at 5,000 chars and mixed with other output
3. `ralph status` says "Ready to run." — no validation of check commands (F34)
4. User eventually runs `ruff check .` manually and sees "command not found"
5. Install ruff, restart loop

**Key insight:** `ralph status` saying "Ready to run." when check commands don't exist is a trust violation. The user ran the validation step and was told everything was fine.

- **F55: No distinction between "check command failed" vs. "check found issues"** (NEW, VALIDATED). When a check exits non-zero, the CLI shows `✗ lint (exit 1)`. Exit code 1 means the same thing whether ruff found lint errors (working as intended) or ruff itself crashed (broken setup). The user can't tell from the CLI output whether the check is doing its job. The check output (which would distinguish these) is only shown to the *next iteration's agent*, not to the user in the terminal. The `_on_checks_completed` handler at `_console_emitter.py:112-125` shows name + exit code but never shows any check output to the user.

---

## Deep Dive: The Cookbook Copy-Paste Gap (NEW)

The cookbook (`docs/cookbook.md`) is the best onboarding resource — it gives complete, working setups. But there's a significant gap between reading a recipe and having it work.

### The Setup Tax

Every cookbook recipe follows this pattern:
1. Run `ralph init` (creates generic config)
2. Run `ralph new check X` (creates template with wrong defaults)
3. Run `ralph new context Y` (creates template with wrong defaults)
4. **"Edit each file to match the contents above"** ← this is the bottleneck

For the Python library recipe, the user must manually edit **5 files** after scaffolding: `ralph.toml`, `RALPH.md`, `CHECK.md` (×2), `CONTEXT.md`. Each file starts with generic template content that must be replaced with the recipe's specific content.

- **F56: Cookbook recipes require editing 5+ files after scaffolding** (NEW, VALIDATED). The `ralph new` command creates files with generic template content (`_templates.py:10-59`). The CHECK_MD_TEMPLATE defaults to `command: ruff check .`, the CONTEXT_MD_TEMPLATE defaults to `command: git log --oneline -10`. These are often close to what the user wants but not exact. The user must open each file, delete the HTML comment boilerplate, and paste in the recipe's version. This is 5 context switches and 5 file edits for a "copy-paste" recipe.

- **F57: No `ralph init --recipe <name>` or template system** (NEW, HYPOTHESIZED). If `ralph init` could accept a recipe/preset name — `ralph init --preset python`, `ralph init --preset node-typescript` — it could scaffold the complete cookbook setup in one command. The `detect_project()` function already identifies the project type; the gap is connecting detection to scaffold templates.

### The `run.*` Script Tax

Three cookbook recipes (coverage check, migration status, integration tests) require `run.sh` scripts. The setup instructions for these are particularly friction-heavy:

1. Create the `run.sh` file (no scaffold command for this)
2. Write the script content (must be correct syntax)
3. `chmod +x` the script (easy to forget; failure mode is a permissions error the user must debug)
4. No validation that the script is executable until the check/context actually runs

- **F58: `ralph new` doesn't scaffold `run.*` scripts, only marker files** (NEW, VALIDATED). `_scaffold_primitive()` at `cli.py:164-185` only creates the marker file (`CHECK.md`, `CONTEXT.md`). If the user needs a script (for shell features like pipes), they must create and `chmod` the file manually. The cookbook works around this with inline `cat > ... << 'EOF'` commands, which feel fragile and out-of-character for a tool that scaffolds everything else.

- **F59: No validation that `run.*` scripts are executable** (NEW, VALIDATED). `find_run_script()` at `_discovery.py:43-52` finds `run.*` files but doesn't check if they're executable. A non-executable `run.sh` produces a permissions error at runtime. The `_runner.py:50` call `subprocess.run(cmd, ...)` will raise `PermissionError` which surfaces as an unhelpful error in the loop output. `ralph status` doesn't check script permissions either.

---

## Deep Dive: First-Run Anxiety (NEW)

What does the user experience the first time they run `ralph run`? This matters because first impressions determine whether a user continues.

### The Timeline

**T+0s**: User types `ralph run -n 3 --log-dir logs`
- ASCII art banner fills 8 lines of terminal (F8)
- Config summary in dim text: "Checks: 2 enabled, Contexts: 1 enabled"
- `── Iteration 1 ──` appears

**T+1s**: Spinner with elapsed time appears. Nothing else.
- User sees: `⠋ 1.2s` ... `⠋ 15.0s` ... `⠋ 45.0s`
- **For Claude Code**: structured streaming happens internally, AGENT_ACTIVITY events fire, but `ConsoleEmitter` ignores them — the spinner is all the user sees
- **For other agents**: complete silence during execution (F43)
- The user has no idea: Is it working? Is it stuck? What is it doing?

**T+60s**: Iteration completes
- `✓ Iteration 1 completed (60.2s) → logs/001_20250312-142301.log`
- `  Checks: 2 passed`
- `    ✓ lint`
- `    ✓ tests`
- Relief! But the user waited 60 seconds with zero feedback about what was happening.

**T+61s**: `── Iteration 2 ──` starts. Same spinner. Same silence.

### The Anxiety Points

1. **"Is it even doing anything?"** — During the spinner phase, the user has zero confirmation the agent is working. For a first-time user who just connected their API key, this is high anxiety. They're paying per token and see nothing.

2. **"What did it just do?"** — After iteration 1 completes, the user sees "completed (60.2s)" and check results. But what changed? No git diff summary, no files-modified list, no preview of what the agent did. The user must manually `git diff` or read the log file.

3. **"Did my prompt work?"** — The user carefully crafted RALPH.md but has no confirmation that contexts were injected, placeholders resolved, or instructions included. The dim summary says "Contexts: 1 enabled" at run start but doesn't confirm per-iteration resolution.

- **F60: No indication of what the agent is doing during an iteration** (NEW, VALIDATED). The `AGENT_ACTIVITY` events from Claude Code's streaming output are emitted by the engine (`engine.py:217`) but `ConsoleEmitter` has no handler for `AGENT_ACTIVITY` — it's only used by the web dashboard. The CLI user sees nothing between `── Iteration 1 ──` and the completion message. For non-Claude agents, there's truly nothing to show (F43). Even a simple "Running agent..." message would help. A richer experience could show Claude Code's tool usage: "Reading file: src/main.py", "Editing: tests/test_main.py".

- **F61: No post-iteration diff summary** (NEW, VALIDATED). After each iteration, the user sees duration and check results but nothing about what changed in the codebase. A one-line summary like `  Files: 3 modified, 1 created | Commits: 1` would dramatically improve J6 (feel in control). This could be as simple as running `git diff --stat HEAD~1..HEAD` after each iteration and emitting the result. The data is free (git is always available).

---

## Deep Dive: Documentation UX Friction (NEW)

The documentation itself is a product with its own UX. Users frustrated by the CLI often turn to docs for help — if the docs have friction, the entire experience compounds.

### Structure Issues

- **F62: Getting-started guide buries "verify the basic loop works" at step 4** (NEW, VALIDATED). The getting-started guide at `docs/getting-started.md` has 11 steps. Steps 1-3 are install/init/write-prompt (reasonable). But steps 4-8 (test run, add checks, add context, verify, run again) are all setup before the user sees real value. The first time the user sees the self-healing feedback loop in action is step 9 — at which point they've been reading docs for 15+ minutes. Reordering to put "run a single iteration" immediately after init would let users feel value faster.

- **F63: Troubleshooting and FAQ have significant overlap** (NEW, VALIDATED). `docs/troubleshooting.md` and `docs/faq.md` both answer "What if a check always fails?", "Can I edit while running?", "What about permissions?". A user searching for help must check both pages. These should be merged or one should explicitly reference the other for each topic.

- **F64: The "how it works" page reveals critical gotchas mid-document** (NEW, VALIDATED). The placeholder resolution rules table at `docs/how-it-works.md:338-347` is the single most important UX footnote in the entire tool: "Named-only means remaining are dropped." But it's buried on line 349 of a technical deep-dive page. Users encounter this rule only after they've hit F16 (silent context exclusion) and gone searching. It should be surfaced earlier — in the getting-started guide or at minimum in the ralphs/primitives page under a warning callout.

### Terminology Confusion

- **F65: Four docs pages explain placeholders redundantly** (NEW, VALIDATED). Placeholder syntax (`{{ contexts.name }}`, `{{ contexts }}`) is explained in: `docs/primitives.md` (lines 183-197), `docs/ralphs.md` (lines 86-128), `docs/how-it-works.md` (lines 103-128 and 338-347), and `docs/getting-started.md` (lines 203-221). Each explanation is slightly different in depth and examples. When the user has a placeholder question, they find four overlapping sources and must determine which is authoritative. This violates single source of truth for documentation.

---

## Deep Dive: The `run.*` Script Escape Hatch (NEW)

When a check or context needs shell features (pipes, redirections, `&&`), the user must create a `run.*` script. This is well-documented but has its own friction chain.

### The Friction Chain

1. **Discovery**: User writes `command: pytest -x 2>&1 | tail -20` in CHECK.md
2. **Silent failure**: The `shlex.split()` at `_runner.py:47` splits `2>&1` as a literal argument. The `|` becomes a literal pipe argument to pytest. No error — just wrong behavior.
3. **Confusion**: The check "works" but produces unexpected output. pytest may even exit 0 because `|` and `tail` are interpreted as test file arguments that don't exist, and pytest defaults to running nothing.
4. **Diagnosis**: User must realize that `shlex.split()` doesn't support shell features. This is documented in `docs/primitives.md:64-69` but easy to miss.
5. **Migration**: User creates `run.sh`, moves the command there, adds `#!/bin/bash`, makes it executable.
6. **Gotcha**: If CHECK.md still has the `command:` field, the user might not realize that `run.*` takes precedence. Or they might remove the `command:` field and leave CHECK.md with just frontmatter + body, which works but is non-obvious.

- **F66: Shell-incompatible commands fail silently, not with an error** (NEW, VALIDATED). `_runner.py:44-48`: when `command` is split via `shlex.split()`, shell operators (`|`, `&&`, `>`, `2>&1`) become literal arguments to the first command. This never produces a "you used shell features in a command" error — it produces unexpected behavior. The tool could detect common shell operators in the `command` field and warn: "Your command contains '|' — commands are run directly, not through a shell. Use a run.sh script for shell features."

- **F67: Removing `command:` from CHECK.md when switching to `run.*` is non-obvious** (NEW, VALIDATED). `_runner.py:44-45`: if both `script` and `command` exist, `script` wins. But a user who adds a `run.sh` might not realize they should remove the `command:` field from frontmatter. The silent precedence means the check works correctly, but the CHECK.md still has a `command:` field that's never used — confusing if someone else reads the config. Conversely, if a user removes the `command:` field but forgets to create the script, the check is silently excluded (via `_check_from_entry` returning `None` at `checks.py:60-61`).

---

## New Simplification Opportunities (Iteration 3)

### Tier 1: High Impact, Low Effort (NEW)

#### O36: Show agent activity in CLI from Claude Code streaming (NEW)
**What:** Add an `AGENT_ACTIVITY` handler to `ConsoleEmitter` that shows a dim one-line summary of what Claude Code is doing: `  ⋯ reading: src/main.py` or `  ⋯ editing: tests/test_api.py`. Extract the tool name and file path from the JSON stream events.
**Why:** Addresses F60. The agent activity events are already flowing (`engine.py:217`). The `ConsoleEmitter` just doesn't handle them. This transforms the "staring at a spinner for 60 seconds" experience into "watching the agent work." Directly serves J6 (feel in control) and reduces first-run anxiety.
**Job:** Monitor (J6)
**Effort:** S — add one handler to `_handlers` dict, ~15 lines of rendering code. Must filter `AGENT_ACTIVITY` events to show only tool-use events (not every JSON line).
**Risk:** Low. Dim text, non-blocking. Only fires for Claude Code — other agents continue to see the spinner only (which is still better than before).

#### O37: Post-iteration git diff summary (NEW)
**What:** After each iteration completes, run `git diff --stat HEAD~1..HEAD 2>/dev/null` and show a one-line summary: `  Files: 3 modified, 1 created | Commits: 1`. If no commits were made, show `  No commits this iteration`.
**Why:** Addresses F61. The user instantly knows what the agent did without opening log files or running git manually. This is the highest-value, lowest-effort monitoring improvement after O24 (per-check events). Git is always available in ralphify's target environment.
**Job:** Monitor (J6)
**Effort:** S — run one git command after iteration completion, parse output, emit event.
**Risk:** Very low. The git command is read-only and fast. Falls back gracefully if not in a git repo.

#### O38: Warn on shell operators in `command` field (NEW)
**What:** During primitive discovery, scan the `command` field for common shell operators (`|`, `&&`, `||`, `>`, `>>`, `2>&1`, `$(`, `` ` ``). If found, emit a warning: `⚠ Check 'lint': command contains '|' — commands are run directly, not through a shell. Use a run.sh script for shell features.`
**Why:** Addresses F66. This is the most common gotcha for users writing checks and contexts. The warning prevents the user from spending 20 minutes debugging why their piped command produces wrong output.
**Job:** Trust, Setup (J2, J5)
**Effort:** XS — add a regex check in `_check_from_entry()` and `_context_from_entry()`. ~5 lines.
**Risk:** None. Warning only.

#### O39: Validate `run.*` script permissions in `ralph status` (NEW)
**What:** When `ralph status` discovers a check or context with a `run.*` script, check if the script is executable (`os.access(path, os.X_OK)`). If not, show: `⚠ Check 'integration': run.sh is not executable. Run: chmod +x .ralphify/checks/integration/run.sh`
**Why:** Addresses F59. A non-executable script produces a cryptic `PermissionError` at runtime. Catching it in `ralph status` (which users run to validate setup) prevents a completely avoidable failure mode.
**Job:** Trust, Setup (J2, J5)
**Effort:** XS — add `os.access()` check in the `_print_primitives_section` logic or during discovery.
**Risk:** None. Warning only.

#### O40: Show check output snippet to user in CLI (NEW)
**What:** When a check fails, show the first 3 lines of check output in the CLI beneath the `✗ name (exit N)` line. Currently the user sees only the check name and exit code; the actual output is only fed to the agent.
**Why:** Addresses F55. Users can't distinguish "check found issues" from "check command is broken" without reading log files. Showing `    FAILED tests/test_api.py::test_create_user - AssertionError` immediately tells the user what happened.
**Job:** Monitor (J6)
**Effort:** S — the check output is already in the `CHECK_FAILED` event data (`output` field at `engine.py:283`). Add a handler to `ConsoleEmitter` that shows first 3 lines.
**Risk:** Very low. More terminal output, but only on failures where the user wants information.

### Tier 2: High Impact, Medium Effort (NEW)

#### O41: `ralph init --preset <type>` for cookbook recipes (NEW)
**What:** Add preset support to `ralph init`. Running `ralph init --preset python` creates the full Python cookbook setup: `ralph.toml` with correct config, `RALPH.md` with the plan-file pattern, checks for pytest and ruff, context for git-log — all with correct commands, timeouts, and failure instructions. Presets available: `python`, `node`, `rust`, `go`, `docs`.
**Why:** Addresses F56 and F57. Eliminates the cookbook copy-paste gap entirely. A new user goes from zero to a working, opinionated setup in one command. This is the single biggest "time to first productive run" improvement.
**Job:** Setup (J1, J5)
**Effort:** M — requires preset data structures, multiple file writes, and integration with `detect_project()` for auto-detection. Could be implemented as: `ralph init` auto-detects and uses the appropriate preset, `ralph init --preset python` forces a specific one.
**Risk:** Low-medium. Opinionated defaults may not match every project's toolchain (e.g., `pytest` vs `unittest`). Mitigate by making generated files obviously editable and running `ralph status` to validate.

#### O42: CLI pause signal (e.g., press 'p' to pause after current iteration) (NEW)
**What:** During a running loop, listen for keypress 'p' (or a signal like SIGUSR1) to trigger `state.request_pause()`. The loop finishes the current iteration's checks, then pauses. Press 'p' again (or send signal) to resume.
**Why:** Addresses F53. Users can pause the loop to review what happened, edit the prompt, add checks, then resume — without losing run state. The `request_pause()`/`request_resume()` infrastructure already exists in `RunState` (`_run_types.py:95-103`). The gap is purely in the CLI input handling.
**Job:** Steer, Monitor (J3, J6)
**Effort:** M — requires a non-blocking stdin reader or signal handler running alongside the main loop. Thread-based on Unix, more complex on Windows.
**Risk:** Low. Opt-in behavior (user must actively press a key). Falls back gracefully on platforms without signal support.

#### O43: Diagnostic mode for prompt assembly (NEW)
**What:** `ralph preview [name] --diagnostic` shows the full prompt assembly pipeline with annotations: which contexts were found, which were placed by named placeholder, which went into bulk, which were excluded, whether any named placeholders were unresolved, the final prompt length, and the prompt itself.
**Why:** Addresses F54. Goes beyond O23 (preview) by adding a step-by-step breakdown. When a user suspects a context is missing from their prompt, one command answers every question. The `_assemble_prompt()` function at `engine.py:168-192` already does the work; this would add observability wrappers.
**Job:** Trust, Steer (J2, J6)
**Effort:** M — extract and annotate each step of the assembly pipeline, render as a structured report.
**Risk:** None. New command, read-only.

---

## Updated Principles Applied

| Principle | New Applications (Iteration 3) |
|---|---|
| **Clear feedback** | O36 (agent activity in CLI), O37 (git diff summary), O38 (shell operator warning), O39 (script permission validation), O40 (check output snippet), O43 (assembly diagnostics) |
| **Observability is trust** | O36, O37, O40 (make invisible operations visible at zero user cost) |
| **Convention over configuration** | O41 (presets eliminate manual config for common setups) |
| **Fewer steps** | O41 (one command replaces 5+ file edits) |
| **Progressive disclosure** | O42 (pause key is invisible until needed, then immediately useful) |

---

## Updated Recommended Implementation Order

Adding iteration 3 opportunities to the existing phased plan:

**Phase 1 — "Just Works" (add to existing):**
- O38: Warn on shell operators in commands (XS) — prevents most common check gotcha
- O39: Validate `run.*` script permissions in status (XS)
- O40: Show check output snippet in CLI on failure (S)

**Phase 2 — "Smart Setup" (add to existing):**
- O41: `ralph init --preset <type>` for cookbook recipes (M) — biggest setup time reduction

**Phase 3 — "Observable Loop" (add to existing):**
- O36: Show agent activity in CLI from Claude streaming (S) — transforms first-run experience
- O37: Post-iteration git diff summary (S)

**Phase 4 — "Power User Tools" (add to existing):**
- O42: CLI pause signal (M)
- O43: Diagnostic mode for prompt assembly (M)

---

## Updated Open Questions

19. **Should `ralph init` auto-detect project type and use a preset without asking?** If `pyproject.toml` exists, should `ralph init` automatically scaffold Python-appropriate checks? Or should it require `--preset python` explicitly? Auto-detection is more magical but may surprise users who have unusual setups (e.g., a Python project that uses `unittest` not `pytest`).

20. **Should the agent activity display be opt-in or opt-out?** O36 proposes showing Claude Code tool usage in the CLI. Some users may find this noisy. Options: on by default (with `--quiet` to suppress), off by default (with `--verbose` to show), or adaptive (show only when iteration exceeds 30s).

21. **Should `ralph preview` and `ralph run --dry-run` be the same thing?** O23 proposes a `preview` command; O43 proposes a `--diagnostic` flag on it. An alternative is `ralph run --dry-run` which assembles the prompt and runs contexts but doesn't execute the agent. This keeps the CLI surface smaller (no new command) but overloads `ralph run` further.

22. **Should check output be shown in the CLI for passing checks too?** O40 proposes showing output only on failure. But some users might want to see passing check output for verification. A `--verbose-checks` flag could show all output, while the default shows only failures.

23. **Should the git diff summary (O37) detect "going in circles"?** If the same file is modified in 3 consecutive iterations, the summary could add a warning: `⚠ src/main.py modified in last 3 iterations — agent may be going in circles`. This directly addresses the best-practices doc's red flag: "Commits that undo previous commits."

24. **How should presets (O41) handle existing files?** If `ralph init --preset python` is run in a project that already has a `ralph.toml`, should it fail, merge, or overwrite? Current `ralph init --force` overwrites everything — but presets create many more files (checks, contexts) that are harder to recreate.

---

## Deep Dive: The Multi-Ralph Workflow (NEW — Iteration 4)

Users who outgrow a single RALPH.md prompt and create named ralphs (e.g., `docs`, `refactor`, `add-tests`) enter a workflow with its own distinct friction chain. This section walks through that journey.

### The Progression

1. **Day 1**: User has root `RALPH.md` — one prompt for everything. Works fine.
2. **Week 2**: User wants different prompts for different tasks. Discovers `ralph new docs` to create a named ralph.
3. **Week 3**: User has 3-5 named ralphs. Wants ralph-scoped checks (e.g., `docs` ralph doesn't need `pytest`). Discovers `--ralph` flag on `ralph new`.
4. **Month 2**: User has a complex setup with global and scoped primitives. Debugging which primitives apply to which ralph becomes non-trivial.

### Friction Points

- **F68: No `ralph list` command to show available ralphs** (NEW, VALIDATED). To see available named ralphs, the user must run `ralph status` and scroll to the "Ralphs" section at the bottom. There's no quick `ralph list` or `ralph ralphs` command that shows just the ralphs with their descriptions and enabled/disabled status. For a user with 5+ ralphs, `ralph status` buries the ralph list below checks, contexts, and instructions. The most common question when switching tasks — "what ralphs do I have?" — requires the most verbose command.

- **F69: Ralph-scoped primitives create 5+ levels of directory nesting** (NEW, VALIDATED). A ralph-scoped check lives at `.ralphify/ralphs/docs/checks/lint/CHECK.md` — that's 6 directory levels. Creating, finding, and editing these files is friction-heavy. Tab completion helps but `cd .ralphify/ralphs/docs/checks/lint/` is tedious. Compare: global checks at `.ralphify/checks/lint/CHECK.md` are 4 levels — already deep, but manageable. Scoped primitives add 2 more levels for the `ralphs/<name>/` prefix.

- **F70: `enabled` field on ralphs is confusing — disabled ralphs can still be run** (NEW, VALIDATED). A ralph with `enabled: false` is excluded from `ralph status`'s ralph list (filtered by `_print_primitives_section` at `cli.py:85`). But `resolve_ralph_name()` at `ralphs.py:57-76` iterates ALL discovered ralphs (from `discover_ralphs` which returns both enabled and disabled). So `ralph run disabled-ralph` works! The `enabled` field on ralphs has an inconsistent meaning: it hides the ralph from `status` but doesn't prevent it from being used. For checks/contexts/instructions, `enabled: false` means "don't run this" — clear semantics. For ralphs, it means "don't show this in status" — confusing semantics. A user who disables a ralph expects it to be unavailable.

- **F71: No way to promote root RALPH.md to a named ralph** (NEW, VALIDATED). A common progression: user starts with root `RALPH.md`, customizes it heavily, then wants to add a second prompt. They must: (1) `ralph new docs` to create a named ralph, (2) copy content from `RALPH.md` to `.ralphify/ralphs/docs/RALPH.md`, (3) decide what to do with root `RALPH.md` (keep as default? delete?), (4) update `ralph.toml` if needed. This is 4 manual steps for a natural workflow progression. A `ralph promote RALPH.md --name general` command could do this in one step.

- **F72: No way to switch the default ralph without editing `ralph.toml`** (NEW, VALIDATED). If a user has ralphs named `docs`, `tests`, and `refactor`, switching the default requires opening `ralph.toml` and changing `ralph = "docs"` to `ralph = "tests"`. This is friction for a frequent operation. `ralph run tests` works for one-off runs, but the user who wants to run 50 iterations on `tests` must either type `ralph run tests -n 50` every time or edit the toml. A `ralph use tests` command that updates the toml's `ralph` field would be simpler.

- **F73: No visibility into which primitives apply to a named ralph** (NEW, VALIDATED). When running `ralph run docs`, the user sees "Checks: 3 enabled" but doesn't know if those are global checks, docs-scoped checks, or a mix. The `merge_by_name()` function at `_discovery.py:103-113` merges global and local primitives (local wins on name collision), but the result is opaque. If a user has global `lint` check and docs-scoped `lint` check (overriding with a docs-specific config), they can't see this from `ralph status` or the run output. The `RUN_STARTED` event data includes counts but not origins.

- **F74: Ralph-scoped primitives that disable a global primitive are invisible** (NEW, VALIDATED). A powerful but non-obvious pattern: create a ralph-scoped check with `enabled: false` and the same name as a global check to suppress it for that ralph. The `merge_by_name` function replaces the global with the local, and then the `enabled` filter at `engine.py:94` removes it. This works correctly but is completely invisible — there's no `ralph status --ralph docs` to show the merged result. A user trying to debug "why isn't my lint check running for the docs ralph?" has no tool to answer this.

### The Mental Model Gap

The multi-ralph workflow requires users to understand a layering system:
1. Global primitives (`.ralphify/checks/`, etc.)
2. Ralph-scoped primitives (`.ralphify/ralphs/<name>/checks/`, etc.)
3. Merge behavior (local wins on name collision)
4. Enabled filtering (happens after merge)

This is a 4-layer mental model just for understanding which primitives run. It's powerful for platform engineers but overwhelming for the target persona (solo founders who want to "ship features while not coding"). Most users would be better served by a simpler model where each ralph is self-contained.

---

## Deep Dive: Frontmatter Authoring Pitfalls (NEW — Iteration 4)

Frontmatter is the primary configuration mechanism for primitives. Every check, context, instruction, and ralph has frontmatter. The current parser (`_frontmatter.py`) is intentionally minimal — flat `key: value` pairs, no YAML library. This simplicity has benefits (no dependency, no YAML surprises) but creates its own failure modes.

### Validated Failure Modes

- **F75: Missing colon in frontmatter silently drops the line** (NEW, VALIDATED). `_parse_kv_lines()` at `_frontmatter.py:44-45` skips lines without `:`. Writing `command ruff check .` (missing colon) silently drops the command field. The check then has no command and no script → silently excluded from the loop (via `_check_from_entry` returning `None` at `checks.py:60-61`). The user sees the check in `ralph status` with `?` detail but no explanation. This is a 3-step silent failure chain: (1) frontmatter parser drops the line, (2) check constructor returns None, (3) check is excluded from the loop.

- **F76: Typos in frontmatter field names are silently accepted** (NEW, VALIDATED). Writing `tiemout: 60` (typo) is accepted as a string-valued field called "tiemout". It's never used — `_check_from_entry` at `checks.py:69` does `prim.frontmatter.get("timeout", _DEFAULT_TIMEOUT)` which falls through to the default because "tiemout" ≠ "timeout". The check runs with the default 60s timeout. The user thinks they set a custom timeout but the default applies. No warning. The same applies to `comamnd` (typo for `command`), `eanbled` (typo for `enabled`), etc.

- **F77: Invalid type coercion produces an unhandled Python exception** (NEW, VALIDATED). Writing `timeout: abc` triggers `int("abc")` in `_FIELD_COERCIONS` at `_frontmatter.py:32`, raising `ValueError: invalid literal for int() with base 10: 'abc'`. This propagates as an unhandled exception during primitive discovery, crashing the entire `ralph run` or `ralph status` command with a traceback. The error message doesn't indicate which file caused the problem — the user sees a raw Python traceback pointing to `_frontmatter.py:50`.

- **F78: Inline comments after values become part of the value** (NEW, VALIDATED). Writing `command: ruff check . # lint only` in frontmatter results in `command = "ruff check . # lint only"`. The `_parse_kv_lines` function at `_frontmatter.py:46-48` uses `line.partition(":")` and takes everything after the first colon as the value, stripping only leading/trailing whitespace. The `#` is not treated as a comment in the value position — only as a line-start comment (line 42). When this command runs via `shlex.split("ruff check . # lint only")`, it produces `['ruff', 'check', '.', '#', 'lint', 'only']`, passing `#`, `lint`, and `only` as literal arguments to ruff. Ruff interprets these as file paths and probably fails with "file not found" — a confusing error for a comment the user thought was harmless.

- **F79: No frontmatter at all is indistinguishable from intentional no-config** (NEW, VALIDATED). A CHECK.md that's just a markdown body with no `---` delimiters works — `parse_frontmatter` returns `({}, text)`. The check gets all defaults: `timeout=60`, `enabled=True`, `command=None`, `script=None`. But with no command and no script, it's excluded. A user who writes a CHECK.md with just failure instructions (body text) and no frontmatter — intending to add the command field later — gets no error, no warning, just a silently excluded check. The same file structure would be valid for an instruction (which has no command), so the file format gives no signal about what's missing.

- **F80: Frontmatter `enabled: true` is the only reliable truthy value — others silently work but are undocumented** (NEW, VALIDATED). The coercion `lambda v: v.lower() in ("true", "yes", "1")` at `_frontmatter.py:33` means `enabled: True` (capital T) → `"True".lower()` → `"true"` → True. But `enabled: TRUE` → True, `enabled: Yes` → True, `enabled: 1` → True. For falsy values: `enabled: false` → False, `enabled: no` → False, `enabled: 0` → False. But also: `enabled: anything-else` → False. So `enabled: flase` (typo) → False, silently disabling the primitive. There's no way to distinguish between intentional `false` and a typo.

### The Bigger Picture

Frontmatter is configuration-as-markdown, which trades machine-parsability for human-readability. The parser's simplicity is a feature for the common case but creates a "pit of failure" for edge cases. Every field that's silently dropped or mistyped creates a debugging session where the user must trace through the parse → discover → filter → run pipeline to find the problem.

The root cause: **frontmatter errors are silent at parse time and only surface as behavioral anomalies at run time** — often many minutes later, after the user has started a loop and noticed something isn't working.

---

## Deep Dive: CI/CD & Automation Gaps (NEW — Iteration 4)

Ralphify's primary use case is interactive (developer at a terminal), but automated/CI use cases are a natural extension: "run the agent in CI to fix failing tests," "nightly cleanup agent," "PR review agent." This section analyzes how well ralphify serves non-interactive execution.

### The Exit Code Problem

- **F81: `ralph run` always exits 0 regardless of outcome** (NEW, VALIDATED — CRITICAL). Traced through the code: `cli.py:run()` at line 340 calls `run_loop(config, state, emitter)` which returns `None`. The `run()` function then returns normally — no exit code is set. The `state` object has `state.status` (COMPLETED/FAILED/STOPPED) and `state.completed`/`state.failed` counters, but none of these influence the process exit code. This means:
  - `ralph run -n 1` where the agent crashes → exit 0
  - `ralph run -n 1` where all checks fail → exit 0
  - `ralph run -n 1` where the agent times out → exit 0
  - Only an unhandled Python exception produces non-zero exit

  For CI/CD, this is a showstopper. A CI step of `ralph run -n 3 && echo "All good"` always prints "All good." There's no way for a calling script to know if the agent succeeded. This undermines J2 (trust the output) in automated contexts.

- **F82: No machine-readable output format** (NEW, VALIDATED). All CLI output goes through Rich console formatting (colors, Unicode, spinners). There's no `--json` flag to produce structured output. A CI pipeline that wants to parse iteration results (how many passed, which checks failed, total duration) must parse Rich-formatted terminal output — fragile and version-dependent. The event system (`_events.py`) already produces structured data with `Event.to_dict()`, but this serialization is only used by the WebSocket/UI layer, not the CLI.

- **F83: Banner and spinner output in non-interactive contexts** (NEW, VALIDATED). When running in CI (no TTY), Rich's `Live` display (spinner) degrades, but the ASCII art banner still prints. There's no detection of `sys.stdout.isatty()` to suppress interactive-only output. The banner adds 8 lines of noise to CI logs. The spinner's transient rendering may produce garbled output in log files.

- **F84: No `--quiet` / `--verbose` flags for controlling output verbosity** (NEW, VALIDATED). The CLI has no global verbosity control. Every `ralph run` produces the same output: banner, config summary, iteration headers, check results, run summary. In CI, users want minimal output (just pass/fail). In debugging, users want maximal output (prompt content, context resolution, per-check output). Currently, the only axis of control is `--log-dir` for capturing agent output — but this doesn't affect the CLI's own output.

- **F85: `ralph.toml` `command` field is user-specific but committed to git** (NEW, VALIDATED). The `command` and `args` fields in `ralph.toml` specify the agent binary and its flags. This is project-level config committed to the repo. But different team members may use different agents (Claude Code vs Aider vs custom wrapper). A team repo with `command = "claude"` breaks for a member using Aider. There's no concept of personal overrides (e.g., `.ralph.local.toml`, environment variables like `RALPH_COMMAND`, or per-user config in `~/.config/ralphify/`). Every agent switch requires editing the shared config file.

- **F86: No environment variable overrides for config** (NEW, VALIDATED). CI systems commonly configure tools via environment variables (`RALPH_COMMAND=claude`, `RALPH_MAX_ITERATIONS=5`, `RALPH_LOG_DIR=logs`). Ralphify has no environment variable support — all configuration comes from `ralph.toml` (project-level) or CLI flags (per-invocation). This means CI pipelines must either: (a) modify `ralph.toml` before running (fragile, leaves dirty git state), (b) pass all settings via CLI flags (verbose, easy to miss), or (c) use a wrapper script.

### CI/CD Usage Pattern Analysis

A typical CI integration would look like:
```yaml
- name: Run agent
  run: ralph run -n 3 --timeout 600 --log-dir logs --stop-on-error
- name: Check result
  run: ??? # No way to check if ralph succeeded
```

The minimum viable CI story requires:
1. Non-zero exit code on failure (F81) — BLOCKING
2. Quiet mode for clean logs (F84) — HIGH VALUE
3. Environment variable overrides (F86) — MEDIUM VALUE
4. JSON output for parsing (F82) — NICE TO HAVE

---

## Deep Dive: The Prompt Lifecycle Edge Cases (NEW — Iteration 4)

What happens when the prompt is empty, too large, or contains unexpected content?

### Validated Edge Cases

- **F87: Empty RALPH.md produces empty prompt with no warning** (NEW, VALIDATED). If `RALPH.md` contains only whitespace or only frontmatter with no body, `parse_frontmatter` returns an empty body string. `_assemble_prompt` at `engine.py:184-185` reads the file and strips frontmatter, getting `""`. If there are no contexts, no instructions, and no check failures, the agent receives an empty string as stdin. No warning is emitted. The agent may do nothing (best case) or do something random (worst case). An empty prompt should at minimum produce a warning.

- **F88: No prompt size tracking or warning** (NEW, VALIDATED). The `PROMPT_ASSEMBLED` event at `engine.py:327` includes `prompt_length` (character count), but nobody acts on it. A prompt with 5 contexts, 10 instructions, and verbose check failures could easily reach 50,000+ characters — potentially exceeding the agent's context window. The tool produces no warning. The agent silently truncates or errors. For Claude Code, the context window is ~200K tokens — usually fine. For smaller models or cost-sensitive users, prompt size matters. A configurable warning threshold (e.g., `warn_prompt_size: 10000` in ralph.toml) would catch accidental bloat.

- **F89: Instruction content that references context placeholders resolves as literal text** (NEW, VALIDATED). The prompt assembly pipeline at `engine.py:186-189` resolves in fixed order: contexts first, then instructions. If an instruction contains `{{ contexts.git-log }}`, this text is injected during instruction resolution — but context resolution already happened. The `{{ contexts.git-log }}` appears as literal text in the final prompt. This is correct behavior (avoiding circular resolution) but non-obvious. A user who writes `{{ contexts.git-log }}` in an instruction expecting it to resolve will get the raw placeholder text with no warning.

- **F90: Check failure text accumulates but never resets on success** (NEW, VALIDATED). Looking at `engine.py:397-398`: `check_failures_text` is returned from `_run_iteration` and passed to the next iteration. When all checks pass, `format_check_failures` returns `""` (empty string). So the failure text IS reset on success — this is correct. But there's a subtlety: if iteration N fails checks, iteration N+1 gets the failure text. If the agent in N+1 fixes some but not all failures, iteration N+2 gets ONLY the failures from N+1's check run — not the union of N and N+1's failures. This is correct behavior but could be surprising: a failure that the agent "ignored" (didn't fix, but the check still passes) disappears from the feedback. This is actually fine — the check results reflect current state, not history.

---

## New Simplification Opportunities (Iteration 4)

### Tier 1: High Impact, Low Effort (NEW)

#### O44: Non-zero exit code when run has failures (NEW — CRITICAL for CI)
**What:** After `run_loop()` completes in `cli.py:run()`, check `state.status` and `state.failed`. If `state.failed > 0` or `state.status == RunStatus.FAILED`, exit with code 1. Only exit 0 when all iterations completed and all checks passed.
**Why:** Addresses F81. This is the single most important fix for any non-interactive use case. Without meaningful exit codes, ralphify cannot be used in CI/CD, scripts, or any automated pipeline. Every other CI improvement depends on this.
**Job:** Trust (J2), Run (J1)
**Effort:** XS — add 4 lines after `run_loop()` in `cli.py:run()`: check `state.failed > 0`, call `raise typer.Exit(1)`.
**Risk:** Low. Only changes exit behavior — current users running interactively rarely check exit codes. Could be surprising for users who have `ralph run` in a `set -e` script where check failures are expected (the self-healing loop model assumes some failures). Mitigate by: exit 0 when the loop completed its full `-n` iterations regardless of individual check failures, exit 1 only when the run was cut short by `--stop-on-error` or agent crash.

#### O45: Validate known frontmatter field names with typo detection (NEW)
**What:** In `_parse_kv_lines()`, after parsing, check each key against the set of known fields (`command`, `timeout`, `enabled`, `description`). If an unknown field is found, emit a warning suggesting the closest known field: `⚠ Unknown field 'tiemout' in CHECK.md — did you mean 'timeout'?` Use a simple Levenshtein distance check (stdlib has `difflib.get_close_matches`).
**Why:** Addresses F76. Frontmatter typos are currently 100% silent. A simple spell-check on field names would catch the most common configuration errors at discovery time, before the user starts a loop and wonders why their timeout isn't working.
**Job:** Trust, Setup (J2, J5)
**Effort:** S — add ~10 lines to `_parse_kv_lines()` using `difflib.get_close_matches`. The set of valid fields varies by primitive type, but a superset (`command`, `timeout`, `enabled`, `description`) covers all cases.
**Risk:** Very low. Warning only. Unknown fields still accepted (they're used as arbitrary metadata in some workflows).

#### O46: Handle frontmatter type coercion errors gracefully (NEW)
**What:** Wrap the `coerce(value)` call at `_frontmatter.py:50` in a try/except. On `ValueError`, emit a warning: `⚠ Invalid value for 'timeout': 'abc' — expected an integer. Using default.` Return the raw string value so the caller can fall through to its default.
**Why:** Addresses F77. Currently `timeout: abc` crashes the entire tool with a Python traceback. A graceful fallback with a clear warning is strictly better.
**Job:** Trust, Setup (J2, J5)
**Effort:** XS — add 3 lines of try/except in `_parse_kv_lines`.
**Risk:** None.

#### O47: Warn on empty prompt file (NEW)
**What:** In `_assemble_prompt()` at `engine.py:184-185`, after reading and parsing the prompt file, check if the body is empty (after frontmatter stripping). If so, emit a warning event: `⚠ Prompt file 'RALPH.md' is empty — the agent will receive no instructions.`
**Why:** Addresses F87. An empty prompt is almost always an error (user created the file but hasn't written content yet, or frontmatter is malformed). A warning prevents a wasted iteration.
**Job:** Trust (J2)
**Effort:** XS — add 2 lines after `parse_frontmatter` call.
**Risk:** None.

#### O48: `ralph list` command for quick ralph overview (NEW)
**What:** Add a `ralph list` (or `ralph ls`) command that shows only the available named ralphs in a compact format: name, description, enabled/disabled, and whether it's the current default (from ralph.toml).
**Why:** Addresses F68. The most common multi-ralph question — "what ralphs do I have?" — currently requires `ralph status` which buries ralphs at the bottom under 3 other primitive sections. A dedicated command serves the frequent use case directly.
**Job:** Run, Steer (J1, J3)
**Effort:** XS — add ~15 lines: discover ralphs, print name + description.
**Risk:** None.

### Tier 2: High Impact, Medium Effort (NEW)

#### O49: Environment variable overrides for ralph.toml settings (NEW)
**What:** Support `RALPH_COMMAND`, `RALPH_ARGS`, `RALPH_MAX_ITERATIONS`, `RALPH_TIMEOUT`, `RALPH_DELAY`, `RALPH_LOG_DIR` environment variables that override ralph.toml and CLI defaults. Precedence: CLI flags > env vars > ralph.toml > hardcoded defaults.
**Why:** Addresses F85 and F86. Enables CI/CD integration without modifying ralph.toml or passing verbose CLI flags. Enables per-user agent selection without editing shared config. This is the standard pattern for CLI tools (Docker, Terraform, kubectl all support env var overrides).
**Job:** Run, Setup (J1, J5)
**Effort:** M — add env var lookup in `_load_config()` and `run()`, document precedence.
**Risk:** Low. Purely additive. Env vars are only used when set — existing behavior unchanged.

#### O50: `ralph use <name>` to switch the default ralph (NEW)
**What:** Add `ralph use <name>` command that updates `ralph.toml`'s `ralph` field to the specified named ralph. Validates the ralph exists before updating. Shows a confirmation: `Default ralph set to 'docs'. Run 'ralph run' to use it.`
**Why:** Addresses F72. Switching the default ralph is a frequent operation for multi-ralph users (weekly or daily for some). Currently requires opening and editing ralph.toml. A one-command switch is more ergonomic and less error-prone (no risk of toml syntax errors from manual editing).
**Job:** Steer, Run (J3, J1)
**Effort:** S-M — read toml, update the `ralph` field, write back. Requires TOML write support (currently only reads).
**Risk:** Low. Only modifies the `ralph` field. Could use `tomli-w` for writing or simple string replacement.

#### O51: `--quiet` and `--verbose` output modes (NEW)
**What:** Add global flags `--quiet` / `-q` (suppress banner, spinner, show only errors and final summary) and `--verbose` / `-v` (show prompt assembly details, per-check output, context resolution). Default behavior unchanged.
**Why:** Addresses F83 and F84. Quiet mode is essential for CI. Verbose mode is essential for debugging. Currently there's no way to control output level. This is the standard CLI pattern for tools that serve both interactive and automated use cases.
**Job:** Monitor, Run (J6, J1)
**Effort:** M — add global flags, pass verbosity to `ConsoleEmitter`, conditionally render events based on verbosity level.
**Risk:** Low. Purely additive. Default behavior unchanged.

#### O52: Detect and warn on inline comments in frontmatter values (NEW)
**What:** In `_parse_kv_lines()`, after extracting a value, check if it contains ` #` (space-hash). If so, warn: `⚠ Value for 'command' contains ' #' — comments within values are not supported. The entire string after ':' is used as the value. Use a separate line for comments.`
**Why:** Addresses F78. Inline comments are a natural YAML expectation that silently produces wrong behavior in ralphify's simplified parser. The warning prevents commands that fail in confusing ways.
**Job:** Trust, Setup (J2, J5)
**Effort:** XS — add ~5 lines of detection in `_parse_kv_lines`.
**Risk:** None. Warning only. Users who intentionally have `#` in values (unlikely but possible) still get the correct behavior.

#### O53: `ralph status --ralph <name>` to show merged primitive state (NEW)
**What:** Add a `--ralph` flag to `ralph status` that shows the fully merged view: which global primitives apply, which are overridden by ralph-scoped primitives, and which are suppressed. Format: `  ✓ lint       ruff check . (global)`, `  ✓ tests      pytest -x (scoped to docs)`, `  ○ typecheck  (disabled by docs-scoped override)`.
**Why:** Addresses F73 and F74. The merge behavior is powerful but completely invisible. Users debugging "why doesn't my check run for this ralph?" need visibility into the merge result. This is the multi-ralph equivalent of `ralph preview` for prompt assembly.
**Job:** Trust, Steer (J2, J3)
**Effort:** M — call `_discover_enabled_primitives(root, prompt_dir)` and annotate each result with its origin (global vs scoped).
**Risk:** Very low. Read-only, additive to status output.

### Tier 3: Medium Impact, Lower Effort (NEW)

#### O54: Detect missing colon in frontmatter with warning (NEW)
**What:** In `_parse_kv_lines()`, for lines that don't contain `:` but do contain a space and look like `key value` (where `key` is a known field name), warn: `⚠ Line 'command ruff check .' appears to be missing a colon. Expected: 'command: ruff check .'`
**Why:** Addresses F75. The most devastating silent failure: a missing colon drops the most important field (command), causing the entire check to be silently excluded. A heuristic warning for lines that look like they should be key-value pairs catches the most common case.
**Job:** Trust, Setup (J2, J5)
**Effort:** S — check first word of non-colon lines against known field names.
**Risk:** Very low. Warning only. False positives possible for body text that starts with a known field name, but this only triggers inside the frontmatter block (between `---` delimiters).

---

## Updated Principles Applied (Iteration 4)

| Principle | New Applications |
|---|---|
| **Clear feedback** | O44 (exit codes), O45 (typo detection), O46 (coercion errors), O47 (empty prompt), O52 (inline comment warning), O54 (missing colon warning) |
| **Convention over configuration** | O49 (env var overrides follow standard CLI patterns) |
| **Fewer steps** | O48 (quick ralph listing), O50 (one-command ralph switch) |
| **Progressive disclosure** | O51 (quiet/verbose modes), O53 (ralph-scoped status for advanced users) |
| **Observability is trust** | O44 (exit code is the most basic observable), O53 (merge visibility) |
| **Single source of truth** | O53 (status and run should agree on primitives) |

---

## Updated Recommended Implementation Order (Iteration 4)

**CRITICAL — implement before any other CI/CD or automation work:**
- O44: Non-zero exit code on failures (XS) — everything else in CI depends on this

**Phase 1 — "Just Works" (add to existing):**
- O45: Validate known frontmatter field names (S)
- O46: Handle type coercion errors gracefully (XS)
- O47: Warn on empty prompt file (XS)
- O48: `ralph list` command (XS)
- O52: Detect inline comments in frontmatter values (XS)
- O54: Detect missing colon in frontmatter (S)

**Phase 2 — "Smart Setup" (add to existing):**
- O50: `ralph use <name>` to switch default ralph (S-M)
- O49: Environment variable overrides (M) — enables CI/CD without config modification

**Phase 3 — "Observable Loop" (add to existing):**
- O51: `--quiet` and `--verbose` output modes (M) — essential for CI logs
- O53: `ralph status --ralph <name>` for merged primitive view (M)

---

## Updated Open Questions (Iteration 4)

25. **What should the exit code semantics be?** O44 proposes non-zero on failure, but the self-healing loop model expects some check failures (that's how the loop learns). Options: (a) exit 1 if ANY check ever failed (too strict — almost every run has early failures), (b) exit 1 if the LAST iteration had check failures (useful — "did it converge?"), (c) exit 1 only on agent crash or `--stop-on-error` trigger (most compatible with current model), (d) exit code = number of failed checks in last iteration (informative but non-standard). Recommendation: (b) with an option to select (c) via flag.

26. **Should `ralph list` show disabled ralphs?** If yes, mark them clearly. If no, users can't discover ralphs that are disabled. Recommendation: show all, with `[disabled]` tag.

27. **Should frontmatter validation be per-primitive-type?** Currently all primitives share the same parser. But `command` is valid for checks and contexts but not instructions. `description` is valid for ralphs but not checks. Type-specific validation would catch more errors (e.g., "instructions don't support the 'command' field") but adds coupling between the parser and each primitive type. Recommendation: start with a universal known-field set, refine per-type later.

28. **Should `ralph use` modify ralph.toml in-place?** TOML modification risks losing comments and formatting. Options: (a) use a TOML library that preserves formatting (e.g., `tomlkit`), (b) use simple regex replacement for the `ralph = "..."` line, (c) store the "current ralph" in a separate file (e.g., `.ralphify/.current`). Recommendation: (b) for simplicity — the ralph field is a single line.

29. **Should environment variables use `RALPH_` or `RALPHIFY_` prefix?** The CLI command is `ralph` but the package is `ralphify`. `RALPH_COMMAND` is shorter but could conflict with other tools. `RALPHIFY_COMMAND` is unambiguous but verbose. Recommendation: `RALPH_` — shorter, matches the CLI command, and conflicts are unlikely.

30. **Is the frontmatter parser intentionally minimal or accidentally limited?** The simplified `key: value` format avoids YAML's complexity, but it can't express: lists (for args), nested config (for structured settings), or multiline values (for long commands). Should it stay minimal (with `run.*` scripts as the escape hatch) or grow toward a subset of YAML? Recommendation: stay minimal — the escape hatches exist and complexity breeds more edge cases.

---

## Correction: Surface Area Inventory (from Iteration 1)

The UX Audit lists `ralph ui` as a CLI command that launches a web dashboard. **This command does not exist.** The `dashboard.md` documentation is a design preview for a future feature, not documentation of an implemented feature. The actual CLI has 4 commands, not 5: `ralph init`, `ralph run`, `ralph status`, `ralph new`. The UI event infrastructure exists in the codebase (`QueueEmitter`, `FanoutEmitter`, `RunManager`) to support a future dashboard, but no CLI entry point exposes it. This correction affects the concept count: the effective surface area is smaller than reported, which is good — but the dashboard.md doc creates expectations the tool can't meet.

---

## Deep Dive: Interrupt, Lifecycle & Resilience (NEW — Iteration 5)

This section traces what happens when the user's run doesn't end cleanly. Every run ends one of four ways: natural completion, Ctrl+C interrupt, agent/system crash, or dashboard-initiated stop. Each path has distinct UX characteristics.

### Path 1: Natural Completion (happy path)

When `-n` iterations complete or the loop finishes normally:
- `state.status` remains `RUNNING` → set to `COMPLETED` at `engine.py:420-421`
- `RUN_STOPPED` event emitted with `reason="completed"` (line 428)
- `ConsoleEmitter._on_run_stopped` renders summary: "Done: N iteration(s) — X succeeded, Y failed" (line 145-151)
- **UX: Good.** User sees a clean summary.

### Path 2: Ctrl+C Interrupt

When the user presses Ctrl+C during a run:

**During agent execution:**
- `KeyboardInterrupt` propagates through `_run_iteration` → `execute_agent`
- In streaming mode (`_run_agent_streaming`), the `finally` block at `_agent.py:132-135` kills and waits for the subprocess — good cleanup
- In blocking mode (`_run_agent_blocking`), `subprocess.run()` receives the signal and the child process may or may not be killed depending on OS behavior
- The exception propagates to the main loop's `except KeyboardInterrupt: pass` at `engine.py:409-410`

**During delay between iterations:**
- `time.sleep(config.delay)` at `engine.py:407` is interrupted by `KeyboardInterrupt`
- Falls to the same `except` handler

**During check execution:**
- `subprocess.run()` in `_runner.py` receives the signal
- Check may produce partial output

**After interrupt is caught:**
- Line 409-410: `pass` — no state update, no "interrupted" flag
- Line 420-421: `if state.status == RunStatus.RUNNING: state.status = RunStatus.COMPLETED`
- **The status is set to COMPLETED, not STOPPED or INTERRUPTED**
- Line 423-427: `reason` resolves to `"completed"`
- Line 140: Summary renders as "Done: N iteration(s)..."

- **F91: Ctrl+C reports as "completed" instead of "interrupted"** (NEW, VALIDATED). `engine.py:409-410`: `KeyboardInterrupt` is caught with `pass`, then `state.status` falls through to `COMPLETED` (line 420-421). The `RUN_STOPPED` event has `reason="completed"`. The console summary says "Done" — indistinguishable from a natural `-n` completion. For CI pipelines and log analysis, there's no way to tell if a run was deliberately interrupted. The `RunStatus` enum (in `_run_types.py`) has a `STOPPED` variant that would be more accurate, but nothing sets it during Ctrl+C handling. Fix: add `state.status = RunStatus.STOPPED` inside the `except KeyboardInterrupt` block.

- **F92: Partial iteration state after Ctrl+C is ambiguous** (NEW, VALIDATED). If Ctrl+C fires during the agent phase of iteration 5, the iteration counter `state.iteration` is already 5 (set at `engine.py:392`), but the iteration hasn't completed checks. The summary reports `total = state.completed + state.failed` which might be 4, but `state.iteration` is 5. The user sees "Done: 4 iteration(s)" but the agent may have made changes during the interrupted 5th iteration that weren't validated by checks. There's no indication that an iteration was in-progress when interrupted, and no guidance to the user that they should review uncommitted changes.

### Path 3: Crash / Exception

When an unhandled exception occurs:
- `engine.py:411-418`: caught by `except Exception`, status set to `FAILED`
- `LOG_MESSAGE` event emitted with traceback
- Falls through to `RUN_STOPPED` with `reason="error"`
- `ConsoleEmitter._on_run_stopped`: line 140 checks `reason == "completed"` — this is **NOT "completed"**, so the `if` block is skipped
- **Result: NO summary is printed for crashed runs**

- **F93: No run summary printed for crashed or stopped runs** (NEW, VALIDATED). `_console_emitter.py:138-151`: the `_on_run_stopped` handler only renders the summary when `reason == "completed"`. For `reason == "error"` or `reason == "user_requested"`, the handler only calls `_stop_live()` and returns — no output. For crashes, the traceback is printed via the `LOG_MESSAGE` handler (line 127-136), but the iteration statistics (completed/failed/timed_out) are lost. A 50-iteration run that crashes on iteration 47 shows the crash error but never tells the user "46 iterations completed, 1 crashed." The data is in the `RUN_STOPPED` event (lines 428-434) but `ConsoleEmitter` discards it for non-completed runs.

### Path 4: Dashboard-initiated stop

When the dashboard UI calls `RunManager.stop_run()`:
- `state.request_stop()` is called (`_run_types.py:108-110`)
- On next iteration boundary, `_handle_loop_transitions` at `engine.py:139-146` detects the stop request
- `state.status` set to `STOPPED`
- Loop breaks, `RUN_STOPPED` emitted with `reason="user_requested"`
- Same F93 applies — no summary printed in CLI

### The Pause Lifecycle

The pause mechanism exists (`RunState.request_pause()` / `request_resume()` at `_run_types.py:95-103`) but has timing issues:

- **F94: Pause requests are only processed at iteration boundaries** (NEW, VALIDATED). `_handle_loop_transitions()` at `engine.py:139-152` checks `state.consume_pause_request()` once per iteration, at the TOP of the next iteration — not during agent execution or checks. If a user triggers pause (via dashboard) while the agent is running a 5-minute task, the pause doesn't take effect until that iteration completes. Combined with the fact that there's no CLI mechanism to trigger pause (only dashboard API), this feature is inaccessible to most users. The `_pause_event.wait()` at `engine.py:146-152` then blocks the engine thread until resume, emitting `RUN_PAUSED` and `RUN_RESUMED` events — but `ConsoleEmitter` has no handlers for these events, so CLI users see nothing.

- **F95: Pause/resume during delay sleep is completely ignored** (NEW, VALIDATED). `time.sleep(config.delay)` at `engine.py:407` is a blocking call that doesn't check for pause/resume/stop requests. If delay is 60 seconds and the user requests pause at second 5, the request is queued but not processed until after the full 60-second sleep completes AND the next iteration starts. The sleep cannot be interrupted by the dashboard API.

### The Resilience Model

Ralphify's resilience model is surprisingly thin:

| Failure type | Recovery | User signal |
|---|---|---|
| Agent crash (non-zero exit) | Counter incremented, loop continues | `✗ Iteration N failed (exit 1)` |
| Agent timeout | Counter incremented, loop continues | `⏱ Iteration N timed out` |
| Check crash | Check treated as failed | `✗ checkname (exit N)` |
| Context crash | Output used regardless (F30) | None — silent |
| Context timeout | Partial output used (F48) | None — silent |
| RALPH.md deleted during run | `FileNotFoundError` → run crashes | Traceback |
| `ralph.toml` deleted during run | Not re-read, no impact | None |
| `.ralphify/` deleted during run | Primitives frozen at startup (F13), no impact | None |
| Disk full during logging | `OSError` → run crashes | Traceback |
| Agent binary disappears during run | `FileNotFoundError` → run crashes | Traceback |

**Key insight:** Ralphify handles the **expected** failure modes well (agent crash, check failure — these are the self-healing loop's core strength) but handles **unexpected** failure modes poorly (filesystem errors, deleted files, resource exhaustion). Every unexpected failure produces a raw Python traceback rather than a user-friendly error.

- **F96: No graceful handling of filesystem errors during run** (NEW, VALIDATED). If `RALPH.md` is deleted while the loop is running, `Path(config.prompt_file).read_text()` at `engine.py:184` raises `FileNotFoundError`. This propagates to the generic exception handler at line 411, which prints a traceback. The user sees a crash with no context about what happened. A more robust approach: catch `FileNotFoundError` in `_assemble_prompt`, emit a clear error ("RALPH.md was deleted — cannot assemble prompt"), and let the user decide whether to stop or retry.

---

## Deep Dive: The Cost & Resource Awareness Gap (NEW — Iteration 5)

J9 (prevent runaway costs) is validated as VERY HIGH intensity. The JTBD research documents that a single agent caught in a "semantic infinite loop" can rack up thousands of dollars, and power users hit $200-500/month in API costs. Yet ralphify has **zero** cost-related features. This section analyzes the gap.

### What Users Want

From the JTBD research, cost concerns manifest as:
1. **Spend limits** — "stop the loop if I've spent more than $X"
2. **Cost estimation** — "roughly how much will 10 iterations cost?"
3. **Cost visibility** — "how much did that run cost?"
4. **Cost optimization** — "is my prompt wastefully long? Am I repeating context?"

### What Ralphify Provides

**Exactly zero cost features.** The tool has:
- `-n` (iteration limit) — indirect cost control via iteration cap
- `--timeout` (per-iteration timeout) — indirect cost control via time cap
- `--delay` (inter-iteration delay) — indirect rate limiting

These are **time-based** proxies for cost, not cost-aware features. The relationship between iterations/time and actual cost depends entirely on the agent, prompt length, and task complexity — none of which ralphify tracks.

### The Fundamental Constraint

Ralphify can't know the cost because:
1. It pipes stdin to the agent — the agent decides how many tokens to use
2. Different agents have different pricing models
3. The same prompt length can produce wildly different agent effort (and cost)

However, ralphify DOES know things that correlate with cost:
- **Prompt length** — larger prompts = more input tokens
- **Iteration count** — more iterations = more API calls
- **Agent execution time** — longer runs generally = more output tokens
- **Accumulated context** — growing prompts over iterations = cost escalation

### Friction Points

- **F97: No prompt size trend tracking** (NEW, VALIDATED). The `PROMPT_ASSEMBLED` event at `engine.py:327` includes `prompt_length` (character count), but nobody aggregates it across iterations. A prompt that grows from 3,000 chars (iteration 1) to 15,000 chars (iteration 10) — because check failures accumulate long output — is a cost escalation signal. The tool emits the data per-iteration but never computes the trend. For J9 (prevent runaway costs), a simple "prompt size doubled since iteration 1" warning would catch the most common cost escalation pattern.

- **F98: No cost estimation or token count** (NEW, VALIDATED). Ralphify knows the exact prompt text sent to the agent. For Claude Code, the token count could be estimated cheaply (rough estimate: chars / 4). A one-line display like `  Prompt: ~3,200 tokens (est. $0.02 input)` per iteration would give users the cost visibility J9 demands. This doesn't require integration with billing APIs — just a rough estimate based on the prompt size and publicly available pricing. Even a rough estimate is infinitely more useful than the current nothing.

- **F99: No cumulative resource tracking in run summary** (NEW, VALIDATED). The run summary (`_on_run_stopped` at `_console_emitter.py:145-151`) shows iteration counts but no aggregate resource metrics: total prompt characters sent, total agent execution time, total check execution time. These are easy to compute from existing event data and would give users a rough sense of run cost/efficiency. Example: "Total: 10 iterations in 23m 15s | ~85K prompt chars | Agent: 18m 40s | Checks: 4m 35s"

- **F100: `-n` default of unlimited makes J9 (cost control) the user's problem** (NEW, VALIDATED — reinforces F9). The default behavior of `ralph run` is infinite iterations. Combined with no cost tracking, no spend limits, and no prompt size warnings, a first-time user can trivially start an unbounded cost loop. Ralphify's own JTBD research calls out the "$50,000 contract completed for $297" story — but the flip side is a developer who runs `ralph run` without `-n`, goes to lunch, and comes back to a $500 API bill. The tool's #2 validated job (J2: keep the agent from going off the rails) should apply to cost rails too.

### The Claude Code Cost Opportunity

For Claude Code specifically, ralphify has a unique advantage: the streaming JSON output includes structured event data. While exact cost data may not be in the stream, token counts or model info might be. If Claude Code emits token usage in its JSON events, ralphify could extract and display real cost data — not just estimates. This would make ralphify the only loop harness with actual cost tracking, directly addressing J9.

- **F101: Claude Code JSON stream may contain cost/token data that's being discarded** (NEW, HYPOTHESIZED). `_agent.py:114-124`: the streaming reader parses every JSON line but only extracts `type == "result"` events (line 121). All other JSON event types are forwarded as raw dicts to the `on_activity` callback. If Claude Code emits token usage or cost information in non-result events, ralphify has access to it but doesn't use it. Needs verification: what fields does Claude Code's `--output-format stream-json` actually include?

---

## Deep Dive: Team Adoption & Configuration Sharing (NEW — Iteration 5)

J4 (multiply team output) and J8 (standardize AI workflows) are validated JTBD targeting engineering leads and platform engineers. But ralphify's configuration model is designed for solo use. This section analyzes the friction when a team tries to share a ralphify setup.

### The Sharing Model

Ralphify's config is git-native: `ralph.toml` and `.ralphify/` are committed to the repo. This is great for sharing — anyone who clones the repo gets the full harness setup. But several friction points emerge at team scale.

### Configuration That Should Be Shared vs. Personal

| Config | Should be shared? | Currently shared? | Conflict? |
|---|---|---|---|
| `.ralphify/checks/` | Yes | Yes (committed) | No |
| `.ralphify/contexts/` | Yes | Yes (committed) | No |
| `.ralphify/instructions/` | Yes | Yes (committed) | No |
| `.ralphify/ralphs/` | Yes | Yes (committed) | No |
| `RALPH.md` | Depends on team | Yes (committed) | Medium |
| `ralph.toml` `command` | No (personal) | Yes (committed) | **HIGH** |
| `ralph.toml` `args` | No (personal) | Yes (committed) | **HIGH** |
| `ralph.toml` `ralph` | Depends | Yes (committed) | Low |

The conflict is at `ralph.toml`: the agent command and args are highly personal. A team member using Aider can't use `command = "claude"`. A member who hasn't set up `--dangerously-skip-permissions` can't use those args. But `ralph.toml` is the project config — it should be committed.

### The Personal Override Gap

- **F102: No mechanism for personal overrides of shared config** (NEW, VALIDATED). Other tools solve this with: (a) local override files (`.ralph.local.toml`, gitignored), (b) environment variables (`RALPH_COMMAND=aider`), (c) user-level config (`~/.config/ralphify/config.toml`). Ralphify has none of these. A team that commits `ralph.toml` with `command = "claude"` forces every member to use Claude Code, or every member must locally modify the file and avoid committing the change. This is fragile — `git stash`/`git checkout` cycles around the config file are error-prone.

- **F103: No `.gitignore` entries created by `ralph init`** (NEW, VALIDATED — reinforces F18). `ralph init` at `cli.py:138-161` creates `ralph.toml` and `RALPH.md` but doesn't create or update `.gitignore`. For teams, this means: (a) `ralph_logs/` might be accidentally committed, (b) there's no convention for ignoring personal override files, (c) `.ralphify/` is implicitly expected to be committed but this isn't documented or enforced. A `ralph init` that adds `ralph_logs/` to `.gitignore` (or at minimum prints guidance) would prevent the most common team-sharing mistake.

### The "Golden Setup" Pattern

Platform engineers (persona 6) want to create a reusable ralphify configuration that other team members can adopt without understanding the internals. The ideal pattern:

1. Platform engineer creates `.ralphify/` with checks, contexts, instructions
2. Commits to repo
3. Team members run `ralph init` (or just `ralph run`)
4. Everything works with their personal agent

Currently this breaks at step 4 because `ralph.toml` has a hardcoded agent command. The fix requires either:
- O49 (environment variable overrides) — each member sets `RALPH_COMMAND=their-agent`
- A new local override file mechanism
- Agent auto-detection based on what's installed

- **F104: No "I just cloned this repo, how do I run ralph?" onboarding** (NEW, VALIDATED). When a new team member clones a repo with `.ralphify/` config, there's no `ralph setup` or similar command that detects the existing configuration and guides them through personal setup (which agent to use, any env vars needed). They must read the README, find the ralph config, and manually set up `ralph.toml` with their agent. For J8 (standardize workflows), the tool should recognize "this repo has ralphify config" and help the user get running.

### Team Workflow Patterns

**Pattern A: Shared RALPH.md, individual runs**
- Each engineer runs their own loop on their branch
- `RALPH.md` is shared but may be edited per-task
- Merge conflicts in `RALPH.md` are common and annoying
- Better pattern: use named ralphs (`.ralphify/ralphs/`) and keep `RALPH.md` generic

**Pattern B: CI-driven loops**
- GitHub Actions runs `ralph run -n 3` on PRs or nightly
- Requires F81 fix (non-zero exit codes) and F86 fix (env var overrides)
- Currently impossible to implement correctly

**Pattern C: Shared checks, personal prompts**
- The `.ralphify/` directory is committed, personal prompt files are gitignored
- Requires `ralph.toml` to point to a gitignored file or named ralph
- Works today but requires manual setup and documentation

---

## Deep Dive: The Event System's Untapped Potential (NEW — Iteration 5)

The event system (`_events.py`) is the most architecturally sophisticated part of ralphify, but its potential is largely unrealized in the CLI. This creates a paradox: the infrastructure for rich monitoring exists, but users experience a minimal, information-sparse interface.

### Events Emitted vs. Rendered

| Event Type | Emitted by Engine | Rendered in CLI | Gap |
|---|---|---|---|
| `RUN_STARTED` | Yes | Yes (config summary) | — |
| `RUN_STOPPED` | Yes | Partial (only "completed" reason) | F93 |
| `RUN_PAUSED` | Yes | No | Silent |
| `RUN_RESUMED` | Yes | No | Silent |
| `ITERATION_STARTED` | Yes | Yes (header) | — |
| `ITERATION_COMPLETED` | Yes | Yes (status line) | — |
| `ITERATION_FAILED` | Yes | Yes (status line) | — |
| `ITERATION_TIMED_OUT` | Yes | Yes (status line) | — |
| `CHECKS_STARTED` | Yes | No | F22 |
| `CHECK_PASSED` | Yes | No (only in CHECKS_COMPLETED) | F22 |
| `CHECK_FAILED` | Yes | No (only in CHECKS_COMPLETED) | F22, F55 |
| `CHECKS_COMPLETED` | Yes | Yes (summary) | — |
| `CONTEXTS_RESOLVED` | Yes | No | Invisible |
| `PROMPT_ASSEMBLED` | Yes | No | F31, F12 |
| `AGENT_ACTIVITY` | Yes (Claude only) | No | F60 |
| `PRIMITIVES_RELOADED` | Yes | No | Invisible |
| `LOG_MESSAGE` | Yes | Yes | — |

**7 of 16 event types are silently discarded by ConsoleEmitter.** This is the root cause of the "invisible infrastructure problem" identified in the cross-cutting analysis. The data exists — it's just not shown.

- **F105: ConsoleEmitter silently discards 7 of 16 event types** (NEW, VALIDATED). `_console_emitter.py:51-60`: the `_handlers` dict maps only 8 event types to handler methods. The remaining 8 (`RUN_PAUSED`, `RUN_RESUMED`, `CHECKS_STARTED`, `CHECK_PASSED`, `CHECK_FAILED`, `CONTEXTS_RESOLVED`, `PROMPT_ASSEMBLED`, `AGENT_ACTIVITY`) hit the `else: pass` at line 68 and are discarded. Every one of these discarded events carries useful information: which contexts resolved, how long the prompt is, what the agent is doing, which check is running. The infrastructure cost to emit these events has already been paid — the rendering cost is ~5-10 lines per handler. This is the highest-leverage observability improvement: zero engine changes, just CLI rendering.

### The Verbosity Opportunity

The event system naturally supports a tiered verbosity model:

- **Quiet** (`-q`): Only `RUN_STOPPED` (pass/fail) + `LOG_MESSAGE` (errors)
- **Normal** (default): Current behavior + `PROMPT_ASSEMBLED` (one-line summary) + `CHECK_PASSED`/`CHECK_FAILED` (per-check status)
- **Verbose** (`-v`): All events rendered, including `AGENT_ACTIVITY`, `CONTEXTS_RESOLVED`, `PRIMITIVES_RELOADED`
- **Debug** (`-vv`): Full prompt content, full check output, context resolution details

This maps cleanly to the two user journeys: Quick Start users want quiet/normal, Deep Customization users want verbose/debug. The event system already provides the data — verbosity is purely a `ConsoleEmitter` filtering concern.

---

## Deep Dive: The `detect_project()` Extension Opportunity (NEW — Iteration 5)

`detector.py` currently checks for 4 manifest files and returns a string. It's called once during `ralph init` and its result is printed but never used. This is the foundation for O1 (smart init) but the detector itself has limitations worth analyzing.

### Current Detection (detector.py:11-27)

```
package.json → "node"
pyproject.toml → "python"
Cargo.toml → "rust"
go.mod → "go"
(none) → "generic"
```

First match wins. No multi-type support.

### Missing Project Types

| Manifest | Type | Typical checks | Priority |
|---|---|---|---|
| `Gemfile` | Ruby | `bundle exec rspec`, `rubocop` | Medium |
| `pom.xml` / `build.gradle` | Java | `mvn test`, `gradle test` | Medium |
| `mix.exs` | Elixir | `mix test`, `mix credo` | Low |
| `composer.json` | PHP | `phpunit`, `phpstan` | Medium |
| `*.sln` / `*.csproj` | .NET | `dotnet test`, `dotnet build` | Medium |
| `CMakeLists.txt` | C/C++ | `cmake --build . && ctest` | Low |
| `deno.json` | Deno | `deno test`, `deno lint` | Low |

### Multi-Ecosystem Projects

Many real-world projects have both `package.json` AND `pyproject.toml` (e.g., a Python API with a React frontend). Current detection returns "node" (first match) and misses Python. For O1 (smart init), this matters: auto-scaffolded checks should cover BOTH ecosystems.

- **F106: Project type detection is first-match-wins, misses multi-ecosystem projects** (NEW, VALIDATED). `detector.py:17-22`: the `for filename, project_type in markers.items()` loop returns on first match. A repo with both `pyproject.toml` and `package.json` is classified as "node" (because `package.json` is checked first in the dict). For O1 (smart init auto-creating checks), this means a full-stack project would only get Node checks, not Python checks. The fix: return a list of detected types instead of a single string.

### Deeper Detection Opportunities

Beyond manifest files, detection could identify:
- **Test framework**: `pytest.ini` / `setup.cfg [tool:pytest]` → pytest; `jest.config.js` → jest
- **Linter**: `ruff.toml` / `pyproject.toml [tool.ruff]` → ruff; `.eslintrc` → eslint
- **Type checker**: `pyrightconfig.json` → pyright; `tsconfig.json` → TypeScript
- **CI system**: `.github/workflows/` → GitHub Actions; `.gitlab-ci.yml` → GitLab CI

This deeper detection would make O1 (smart init) dramatically more accurate — instead of guessing "Python project → pytest", it could confirm "Python project with pytest and ruff already configured."

---

## New Simplification Opportunities (Iteration 5)

### Tier 1: High Impact, Low Effort (NEW)

#### O55: Show run summary for ALL stop reasons, not just "completed" (NEW)
**What:** In `_on_run_stopped`, render the summary (iteration counts, pass/fail stats) for ALL reasons: "completed", "error", and "user_requested". Differentiate with color/label: "Done" (green) for completed, "Interrupted" (yellow) for user_requested, "Crashed" (red) for error. The data is already in the event — just render it unconditionally.
**Why:** Addresses F93. Currently, crashed and stopped runs produce no summary at all. A 50-iteration run that crashes on iteration 47 tells the user nothing about the 46 successful iterations. The most anxious moment (a crash) is also the moment with the least information.
**Job:** Monitor (J6)
**Effort:** XS — change the `if data.get("reason") == "completed"` condition at `_console_emitter.py:140` to always render, with a label that varies by reason.
**Risk:** None.

#### O56: Set `state.status = RunStatus.STOPPED` on Ctrl+C (NEW)
**What:** In the `except KeyboardInterrupt` block at `engine.py:409`, set `state.status = RunStatus.STOPPED` instead of letting it fall through to `COMPLETED`. This makes the `RUN_STOPPED` event have `reason="user_requested"` for interrupts.
**Why:** Addresses F91. Ctrl+C should be distinguishable from natural completion. This is one line of code with high impact for log analysis and CI.
**Job:** Trust, Monitor (J2, J6)
**Effort:** XS — add one line: `state.status = RunStatus.STOPPED`
**Risk:** Very low. Changes the reported reason but not behavior. With O55, users would see "Interrupted" instead of "Done".

#### O57: Warn about unvalidated iteration changes on Ctrl+C (NEW)
**What:** After Ctrl+C, if `state.iteration > state.completed + state.failed` (i.e., an iteration was in progress), print a warning: `⚠ Iteration {N} was interrupted before checks ran. Review uncommitted changes with 'git diff'.`
**Why:** Addresses F92. An interrupted iteration may have left the codebase in a partially-modified state. The user should know to review before committing or starting another run.
**Job:** Trust (J2)
**Effort:** XS — add 3 lines after the `except KeyboardInterrupt` block, before status finalization.
**Risk:** None. Warning only.

#### O58: Track and display cumulative prompt size trend (NEW)
**What:** In `ConsoleEmitter`, maintain a list of prompt lengths from `PROMPT_ASSEMBLED` events. If prompt length grows >50% from iteration 1, show a warning: `⚠ Prompt size growing: 3,200 → 8,400 chars (+163%). Consider reviewing check failure verbosity.`
**Why:** Addresses F97. Prompt size growth is the primary leading indicator of cost escalation. A one-time warning when the trend exceeds a threshold costs nothing and catches the most common cost spiral.
**Job:** Trust, Monitor (J6, J9)
**Effort:** S — add a `PROMPT_ASSEMBLED` handler to `ConsoleEmitter`, track min/max prompt length, warn on growth.
**Risk:** Very low. Warning only.

#### O59: Show estimated token count per iteration (NEW)
**What:** In the prompt assembly summary (O7), include a rough token estimate: `Prompt: 3,847 chars (~960 tokens)`. Use the simple heuristic of chars/4 for English text. For Claude models, this is a reasonable approximation.
**Why:** Addresses F98. Users need a mental model of cost per iteration. Even a rough estimate anchors their expectations. "960 tokens" is a number users can multiply by their API pricing to get cost-per-iteration.
**Job:** Monitor, Trust (J6, J9)
**Effort:** XS — add `~{prompt_length // 4} tokens` to the prompt summary line.
**Risk:** Very low. Labeled as estimate. The chars/4 heuristic is well-known and approximate but useful.

#### O60: Add aggregate resource metrics to run summary (NEW)
**What:** Track total prompt chars sent, total agent execution time, and total check execution time across all iterations. Include in the run summary: `Total: 10 iterations in 23m 15s | ~85K prompt chars (~21K tokens) | Agent: 18m 40s | Checks: 4m 35s`
**Why:** Addresses F99. After a long run, users need to understand where time and resources went. Was it mostly agent time? Check time? Was the prompt bloating? These are the basic questions for cost optimization and the data already flows through events.
**Job:** Monitor (J6, J9)
**Effort:** S — track running totals in `ConsoleEmitter` from existing events, display in `_on_run_stopped`.
**Risk:** None.

### Tier 2: High Impact, Medium Effort (NEW)

#### O61: Interruptible delay with countdown and early-resume (NEW)
**What:** Replace `time.sleep(config.delay)` at `engine.py:407` with a loop that sleeps in 1-second increments, checking for pause/stop/resume requests each second. Display a countdown: `Waiting: 45s remaining...` (updated each second via `LOG_MESSAGE` or a new event). Allow Ctrl+C during delay to cleanly stop the run.
**Why:** Addresses F95 (pause ignored during delay) and F41 (no countdown). Long delays (30-60s for rate limiting) currently make the tool appear frozen. A countdown + interruptible sleep makes delays feel responsive.
**Job:** Monitor, Steer (J6, J3)
**Effort:** S-M — replace one `time.sleep()` with a polling loop, add countdown rendering in `ConsoleEmitter`.
**Risk:** Very low. Only changes delay implementation.

#### O62: Environment variable override for agent command (NEW — CI priority)
**What:** Support `RALPH_COMMAND` and `RALPH_ARGS` environment variables that override `ralph.toml`'s `command` and `args` fields. Precedence: env var > toml. Print the effective command at run start: `Agent: aider (from $RALPH_COMMAND)`
**Why:** Addresses F102 (no personal overrides) and F85 (command is user-specific but committed). This is the minimum viable team adoption enabler: commit `ralph.toml` with Claude Code defaults, each team member sets `RALPH_COMMAND=their-agent` in their shell profile. Also enables CI where the agent is configured per-environment. Separated from O49 (full env var support) because just command/args covers 80% of the team friction.
**Job:** Setup, Run (J1, J4, J8)
**Effort:** S — add 5 lines of `os.environ.get()` in `_load_config()` or `run()`.
**Risk:** Very low. Purely additive. Env vars only used when set.

#### O63: Render `PROMPT_ASSEMBLED` and `CONTEXTS_RESOLVED` events in CLI (NEW)
**What:** Add handlers for `PROMPT_ASSEMBLED` and `CONTEXTS_RESOLVED` to `ConsoleEmitter`. Show one line per event: `  Contexts: 3 resolved | Prompt: 4,832 chars` This replaces the separate O7 proposal with a simpler event-handler approach.
**Why:** Addresses F105 (ConsoleEmitter discards 7 event types), F12 (minimal iteration output), and F14 (no signal when prompt changes). Uses existing event infrastructure — zero engine changes.
**Job:** Monitor (J6)
**Effort:** XS-S — add two handler methods, ~15 lines total.
**Risk:** None. One extra line of output per iteration.

#### O64: Detect TTY and suppress interactive elements in non-TTY mode (NEW)
**What:** In `ConsoleEmitter.__init__`, detect `sys.stdout.isatty()`. When not a TTY (piped output, CI): suppress the ASCII banner, disable Rich Live display (spinner), disable color output, use simple text instead of Unicode symbols. Respect `NO_COLOR` environment variable per the convention.
**Why:** Addresses F83 (banner/spinner in CI). The Rich library already has `Console(no_color=True, force_terminal=False)` options. This is the minimum viable CI output improvement — clean, parseable logs instead of ANSI-garbled output.
**Job:** Run, Monitor (J1, J6)
**Effort:** S-M — conditional `Console` construction, conditional `_IterationSpinner` usage.
**Risk:** Low. TTY detection is standard. `NO_COLOR` is a widely adopted convention.

### Tier 3: Medium Impact, Medium Effort (NEW)

#### O65: Local override file (`.ralph.local.toml`) for personal config (NEW)
**What:** If `.ralph.local.toml` exists, merge its values over `ralph.toml`. The local file overrides any keys present. Add `.ralph.local.toml` to the suggested `.gitignore` entries from `ralph init`. This lets teams commit `ralph.toml` with shared defaults while each member has personal agent config.
**Why:** Addresses F102 more completely than O62 (env vars alone). The local file pattern is established (`.env.local`, `docker-compose.override.yml`, `settings.local.py`). It handles all config overrides, not just command/args.
**Job:** Setup, Run (J4, J8)
**Effort:** M — add file detection and dict merge in `_load_config()`, update init to mention it.
**Risk:** Low. Purely additive — only used when the file exists. Potential confusion: "which config file am I actually using?" Mitigate with `ralph status` showing resolved config origin.

#### O66: Claude Code JSON stream token extraction (NEW — EXPLORATORY)
**What:** In `_run_agent_streaming` at `_agent.py:114-124`, check if Claude Code JSON events contain token usage data (look for `usage`, `tokens`, `input_tokens`, `output_tokens` fields). If found, accumulate per-iteration and include in `ITERATION_COMPLETED` event data. Display in CLI: `  Tokens: 12,450 input / 3,200 output (~$0.18)`
**Why:** Addresses F101 and F98. If Claude Code reports token usage in its stream, this would make ralphify the only loop harness with actual (not estimated) cost tracking. For J9 (prevent runaway costs), real token data >> estimated token data.
**Job:** Monitor, Trust (J6, J9)
**Effort:** M — requires investigating Claude Code's stream-json format, adding extraction logic, and rendering.
**Risk:** Medium. Depends on Claude Code's output format, which could change. Should be implemented defensively (extract if available, skip if not).

---

## Updated Principles Applied (Iteration 5)

| Principle | New Applications |
|---|---|
| **Clear feedback** | O55 (summary for all stop reasons), O56 (Ctrl+C distinction), O57 (interrupted iteration warning), O58 (prompt size trend), O59 (token estimate), O60 (resource metrics), O61 (delay countdown) |
| **Observability is trust** | O55, O56, O58, O59, O60, O63 (make existing events visible), O64 (clean CI output), O66 (cost tracking) |
| **Convention over configuration** | O62 (env var override follows standard pattern), O64 (NO_COLOR convention), O65 (local override file follows .local convention) |
| **Progressive disclosure** | O63 (context/prompt events shown at normal verbosity), O66 (cost data shown when available) |
| **Fewer steps** | O62 (one env var vs editing toml), O65 (clone → set personal config → run) |

---

## Updated Recommended Implementation Order (Iteration 5)

**CRITICAL — prerequisite for reliable tool behavior:**
- O44: Non-zero exit code on failures (XS) — CI depends on this
- O55: Show run summary for ALL stop reasons (XS) — crashed runs need feedback
- O56: Set STOPPED status on Ctrl+C (XS) — one-line fix, high trust impact

**Phase 1 — "Just Works" (add to existing):**
- O57: Warn about unvalidated changes on Ctrl+C (XS)
- O59: Show estimated token count per iteration (XS)
- O63: Render PROMPT_ASSEMBLED and CONTEXTS_RESOLVED events (XS-S)
- O58: Track prompt size trend with growth warning (S)
- O60: Aggregate resource metrics in run summary (S)

**Phase 2 — "Smart Setup" (add to existing):**
- O62: Environment variable override for agent command (S) — minimum team enabler
- O64: TTY detection for CI environments (S-M) — minimum CI enabler

**Phase 3 — "Observable Loop" (add to existing):**
- O61: Interruptible delay with countdown (S-M)
- O65: Local override file for personal config (M) — full team support

**Phase 4 — "Power User Tools" (add to existing):**
- O66: Claude Code token extraction (M) — exploratory, high value if feasible

---

## Updated Open Questions (Iteration 5)

31. **Should Ctrl+C during agent execution kill the agent immediately or wait for it to finish?** Current behavior: streaming mode kills, blocking mode depends on OS signal handling. The right answer probably depends on the user's intent — "stop everything now" vs "finish this thought but don't start the next iteration." A double-Ctrl+C pattern (first = pause after iteration, second = kill immediately) would serve both needs.

32. **Should the prompt size warning threshold be configurable?** O58 proposes warning at >50% growth. But some workflows intentionally accumulate context (e.g., a conversation-style prompt that grows by design). A configurable threshold (or disable) in `ralph.toml` would prevent false alerts.

33. **Should token estimation use a more sophisticated model?** O59 proposes chars/4 as a rough estimate. For non-English text, this is less accurate. For code-heavy prompts, tokenization is different. The estimate could be improved by using `tiktoken` (if installed) or a per-model heuristic. But even chars/4 is better than nothing.

34. **Should `.ralph.local.toml` override ALL keys or just specific sections?** Full override is simpler but could lead to drift (local file silently ignores a new required key). Section-level override (only `[agent]` can be overridden locally) is safer but more complex. Recommendation: full override with `ralph status` showing effective config.

35. **Should ralphify auto-detect Claude Code's stream format or require opt-in?** O66 proposes extracting token data from Claude Code's JSON stream. If the format changes, extraction fails silently. Should this be `--track-cost` (opt-in) or automatic (with graceful fallback)? Recommendation: automatic with graceful fallback — if the fields exist, use them; if not, skip silently.

36. **What happens to the in-progress iteration's changes on Ctrl+C?** O57 warns the user, but should ralphify do anything about it? Options: (a) just warn (proposed), (b) auto-run `git stash` to save in-progress changes, (c) auto-run checks on the interrupted iteration before stopping. (a) is safest; (b) and (c) are opinionated and could surprise users.

37. **Should `ralph init` create `.gitignore` entries?** Teams need `ralph_logs/` and `.ralph.local.toml` ignored. Options: (a) create a new `.gitignore` if none exists, (b) append to existing `.gitignore`, (c) print guidance ("Add these to your .gitignore"). (b) risks surprising users who have a carefully curated `.gitignore`. (c) is safest. Recommendation: (c) with a `ralph init --gitignore` flag for (b).

---

## Consolidated Priority Matrix (All Iterations)

This matrix combines all opportunities across 5 iterations, ranked by a composite score:
**Score = (job_impact × job_frequency) / (effort + risk)**

### CRITICAL (implement immediately)
| ID | What | Effort | Addresses |
|---|---|---|---|
| O44 | Non-zero exit code on failures | XS | F81 (CI showstopper) |
| O55 | Run summary for all stop reasons | XS | F93 (crashed runs silent) |
| O56 | Ctrl+C reports as STOPPED | XS | F91 (misleading status) |

### Phase 1: Quick Wins (XS-S effort, high impact)
| ID | What | Effort | Addresses |
|---|---|---|---|
| O4 | Suppress banner on `ralph run` | XS | F8 |
| O14 | Show iteration progress N/M | XS | F20 |
| O15 | Default `-n 1` for inline prompts | XS | F21 |
| O24 | Render per-check events in CLI | XS | F22 |
| O29 | Inline comments in generated toml | XS | F29 |
| O35 | Pass/fail suffix in log filenames | XS | F49 |
| O38 | Warn on shell operators in commands | XS | F66 |
| O39 | Validate `run.*` script permissions | XS | F59 |
| O46 | Handle type coercion errors gracefully | XS | F77 |
| O47 | Warn on empty prompt file | XS | F87 |
| O48 | `ralph list` command | XS | F68 |
| O52 | Detect inline comments in frontmatter | XS | F78 |
| O57 | Warn about unvalidated changes on Ctrl+C | XS | F92 |
| O59 | Estimated token count per iteration | XS | F98 |
| O63 | Render PROMPT_ASSEMBLED/CONTEXTS_RESOLVED | XS-S | F105, F12 |
| O7 | Show prompt assembly summary | S | F12, F14 |
| O19 | Aggregate check stats in run summary | S | F23 |
| O25 | Warn on unresolved named placeholders | S | F37 |
| O31 | Validate `ralph.toml` schema on load | S | F45 |
| O32 | Show context timeout warnings | S | F32 |
| O40 | Show check output snippet on failure | S | F55 |
| O45 | Validate frontmatter field names | S | F76 |
| O54 | Detect missing colon in frontmatter | S | F75 |
| O58 | Track prompt size trend | S | F97 |
| O60 | Aggregate resource metrics in summary | S | F99 |

### Phase 2: Smart Setup (S-M effort)
| ID | What | Effort | Addresses |
|---|---|---|---|
| O1 | Smart `ralph init` with auto checks | S | F2, F3 |
| O3 | Default iteration limit | S | F9, F100 |
| O8 | Better init prompt template | S | F1 |
| O17 | Soften dangerous flag in config | S | F17 |
| O26 | Validate check commands in status | S | F34 |
| O62 | Env var override for agent command | S | F102, F85 |
| O6 | Warn on silent context exclusion | S-M | F16 |
| O34 | Status mirrors run resolution | S-M | F46, F47 |
| O50 | `ralph use <name>` | S-M | F72 |
| O64 | TTY detection for CI | S-M | F83 |
| O41 | `ralph init --preset` | M | F56, F57 |

### Phase 3: Observable Loop (M effort)
| ID | What | Effort | Addresses |
|---|---|---|---|
| O28 | Fix non-Claude agent output | M | F43, F50 |
| O2 | Default log directory | S (after O28) | F10 |
| O16 | Show truncation details | S | F11 |
| O30 | Save prompt to log directory | S | F31 |
| O33 | Unified config (`[run]` in toml) | M | F42, F51 |
| O36 | Agent activity in CLI | S | F60 |
| O37 | Post-iteration git diff summary | S | F61 |
| O51 | `--quiet` and `--verbose` modes | M | F83, F84 |
| O61 | Interruptible delay with countdown | S-M | F41, F95 |

### Phase 4: Power User Tools (M-L effort)
| ID | What | Effort | Addresses |
|---|---|---|---|
| O5 | Remove `--prompt-file` flag | S-M | F6, F7 |
| O9 | Hot-reload primitives | M | F13, F24 |
| O21 | Fail-fast checks | S-M | F26 |
| O23 | Preview command | M | F31, F25 |
| O27 | Clarify stop-on-error | S-M | F33 |
| O42 | CLI pause signal | M | F53 |
| O43 | Diagnostic mode for assembly | M | F54 |
| O49 | Full env var overrides | M | F85, F86 |
| O53 | `ralph status --ralph` | M | F73, F74 |
| O65 | Local override file | M | F102 |
| O66 | Claude Code token extraction | M | F101 |

### Deferred (L effort, high risk)
| ID | What | Effort | Addresses |
|---|---|---|---|
| O10 | Merge instructions into prompt | L | Concept count |
| O12 | Interactive init wizard | L | F5 |
| O22 | Rename "ralphs" to "prompts" | L | F19, F28 |

---

## Deep Dive: The Self-Healing Feedback Loop Quality (NEW — Iteration 6)

The self-healing feedback loop is ralphify's core value proposition: checks fail → failure output is injected into the next iteration's prompt → the agent fixes the issue. This is what makes ralphify more than a `while true; do claude -p < prompt; done` script. Yet the UX of this loop — how failures are presented to both the agent and the user — has not been deeply analyzed.

### Walking Through the Feedback Cycle

**Step 1: Check runs and fails** (`checks.py:98-117`)
The check command runs via `run_command()`. Output (stdout + stderr) is captured as a single string via `collect_output()`. The `CheckResult` has: `passed`, `exit_code`, `output`, `timed_out`.

**Step 2: Failure is formatted** (`checks.py:129-157`)
`format_check_failures()` produces markdown:
```markdown
## Check Failures

The following checks failed after the last iteration. Fix these issues:

### tests
**Exit code:** 1

```
FAILED tests/test_api.py::test_create_user - AssertionError: ...
```

Fix all failing tests. Do not skip or delete tests.
```

**Step 3: Failure text is injected into next prompt** (`engine.py:190-191`)
The formatted failure text is appended to the end of the assembled prompt via string concatenation: `prompt = prompt + "\n\n" + check_failures_text`.

**Step 4: Agent reads the prompt and (hopefully) fixes the issue**
The agent receives the full prompt with check failures at the very end.

### Where the Feedback Loop Degrades

- **F107: Check failure output is undifferentiated — stdout and stderr are merged** (NEW, VALIDATED). `collect_output()` at `_output.py:12-25` concatenates stdout and stderr into a single string with no separator. When a test runner produces both test results (stdout) and deprecation warnings (stderr), the agent receives an interleaved mess. The critical failure information (which test failed, with what assertion) may be buried among noisy warnings. The agent can't distinguish "this is the error to fix" from "this is noise." Compare: a human would naturally filter out deprecation warnings and focus on the `FAILED` line.

- **F108: Failure injection position (end of prompt) may be suboptimal for agent attention** (NEW, VALIDATED). `engine.py:190-191`: check failures are always appended to the END of the prompt. Research on LLM attention patterns shows that information at the beginning and end of context windows gets disproportionate attention ("lost in the middle" effect). End-of-prompt placement is good for attention, but it means check failures always appear AFTER the user's instructions. For prompts that end with specific constraints ("Do NOT create utility files"), the check failure text displaces those constraints from the final position. The user's carefully ordered instructions lose their trailing position to check output every time a check fails. An alternative: inject failures BEFORE the user's prompt so the user's instructions always have the last word.

- **F109: Multiple check failures are concatenated without prioritization** (NEW, VALIDATED). `format_check_failures()` at `checks.py:134-157` iterates through failures in list order (which is alphabetical by check name, from `_discover_and_filter_enabled`). If both `lint` and `tests` fail, the agent sees lint errors first (alphabetically), then test failures. But often the causal chain is reversed: the agent introduced a bug (test fails) AND left some linting issues (lint fails). The agent might fix the lint issues first (because they appear first) but the lint fix might not address the underlying bug. There's no way to specify check priority or failure ordering. The best-practices docs recommend "Order checks from fastest to most important" but this ordering only affects execution speed (via potential O21 fail-fast), not feedback injection order.

- **F110: Failure instruction quality varies wildly and there's no guidance in templates** (NEW, VALIDATED). The CHECK_MD_TEMPLATE at `_templates.py:10-22` includes a comment placeholder: `"Optional instructions for the agent when this check fails."` The real `.ralphify/checks/` in this project show the spectrum: `ruff-lint/CHECK.md` has no failure instruction at all (just the command), while cookbook examples have good ones ("Fix all failing tests. Do not skip or delete tests."). The failure instruction is the single most important piece of text for the self-healing loop — it tells the agent HOW to fix the problem. Yet the default template provides no guidance on how to write a good one, and `ralph new check` creates a check with no failure instruction by default.

- **F111: No feedback loop metrics — user can't tell if the loop is actually self-healing** (NEW, VALIDATED). The core promise is "the loop fixes its own problems." But there's no metric for this. The user can't tell: "How often do checks fail and then pass on the next iteration?" (success rate), "How many iterations does it take to fix a failure on average?" (convergence speed), or "Are there checks that always fail?" (stuck checks). The data exists in the event stream (CHECK_PASSED/CHECK_FAILED per iteration) but isn't aggregated or analyzed. A simple "Check 'tests': failed 3 times, self-healed 2 times, currently failing" in the run summary would validate the core value proposition.

- **F112: Truncation at 5,000 chars can split error messages mid-line** (NEW, VALIDATED). `truncate_output()` at `_output.py:28-32` truncates at exact character position. If the 5,000th character falls in the middle of a stack trace, the agent receives a partial error message. Example: `File "src/main.py", line 42, in crea...` — the function name is cut. The agent can't determine which function to fix. Character-based truncation should at minimum break at a newline boundary. Even better: truncate at the end of the last complete line before the limit.

- **F113: Check failure text includes raw exit code which is noise for the agent** (NEW, VALIDATED). `format_check_failures()` at `checks.py:146`: `parts.append(f"**Exit code:** {r.exit_code}")`. For test runners, exit code 1 means "tests failed" — the agent already knows this from the output. For linters, exit code 1 means "violations found" — again, obvious from output. The exit code is machine-readable metadata that adds noise to the agent's prompt without adding information. The agent never needs to know the exit code — it needs the failure output and instructions. This is 15-20 characters of noise per failing check.

- **F114: All-checks-pass produces zero feedback — no positive reinforcement** (NEW, VALIDATED). When all checks pass, `format_check_failures()` returns `""` and nothing is appended to the next iteration's prompt. The agent has no signal that its previous work was good. It re-reads the same prompt without any indication of progress. Compare: a human reviewer would say "All tests pass, great work — move on to the next task." Positive feedback could improve agent behavior by confirming the previous approach was correct. Even a simple `## Previous Iteration: All checks passed` would provide useful signal.

### The Format Quality Problem

The check failure format is designed for readability but has structural issues:

```markdown
## Check Failures

The following checks failed after the last iteration. Fix these issues:

### tests
**Exit code:** 1

```
FAILED tests/test_api.py::test_create_user - AssertionError: expected 200 got 404
```

Fix all failing tests. Do not skip or delete tests.

### lint
**Exit code:** 1

```
src/main.py:42:1 F401 `os` imported but unused
```

Fix all lint errors. Do not suppress warnings with noqa comments.
```

**Issues with this format:**
1. The header "The following checks failed after the last iteration. Fix these issues:" is 11 words of boilerplate repeated every time. The agent has read this thousands of times and gains nothing from it.
2. The exit code is noise (F113).
3. There's no indication of which check is most important.
4. The failure instruction appears AFTER the output — the agent reads the error before knowing how to approach the fix. Better: instruction first, then evidence.
5. No check execution time or timeout status — the agent can't tell if a check timed out (partial output) vs. completed with errors.

---

## Deep Dive: CLI Help & Feature Discoverability (NEW — Iteration 6)

How do users discover features they don't know exist? The CLI `--help` output is often the first (and sometimes only) documentation users read. This section audits every help surface for quality and discoverability.

### `ralph --help` Analysis

```
Usage: ralph [OPTIONS] COMMAND [ARGS]...
  Harness toolkit for autonomous AI coding loops.
Options:
  --version / -V    Show version and exit.
  --install-completion   Install completion for the current shell.
  --show-completion      Show completion for the current shell.
  --help            Show this message and exit.
Commands:
  init    Initialize ralph config and prompt template.
  status  Show current configuration and validate setup.
  run     Run the autonomous coding loop.
  new     Scaffold new ralph primitives.
```

**Assessment:** Adequate. The tagline "Harness toolkit for autonomous AI coding loops" orients the user. Commands are clear. But:

- **F115: No suggested workflow in top-level help** (NEW, VALIDATED). A new user sees 4 commands and must figure out the order. Adding a one-line note like "Quick start: ralph init → edit RALPH.md → ralph run" would orient users immediately. Tools like `cargo` and `docker` include workflow hints in their help text.

- **F116: `--install-completion` and `--show-completion` are prominent but rarely used** (NEW, VALIDATED). These Typer-default options appear in every `--help` output, taking up 4 lines of space. They're useful for power users but distracting for new users who are scanning for the essential commands. They push the actual commands further down the screen. These can't be easily removed (they're Typer defaults), but could be suppressed with a Typer configuration.

### `ralph run --help` Analysis

```
Usage: ralph run [OPTIONS] [PROMPT_NAME]
  Run the autonomous coding loop.
  ...description...
Arguments:
  [PROMPT_NAME]   Name of a ralph in .ralphify/ralphs/.
Options:
  -n      INTEGER   Max number of iterations. Infinite if not set.
  --prompt / -p     Ad-hoc prompt text. Overrides the prompt file.
  --prompt-file / -f  Path to prompt file. Overrides ralph.toml.
  --stop-on-error / -s  Stop if the agent exits with non-zero.
  --delay / -d      Seconds to wait between iterations.
  --log-dir / -l    Save iteration output to log files in this directory.
  --timeout / -t    Max seconds per iteration. Kill agent if exceeded.
```

**Assessment:** Functional but with discoverability gaps:

- **F117: `PROMPT_NAME` help text says "Name of a ralph" which is circular** (NEW, VALIDATED). A new user who doesn't know what "a ralph" is gets no help. The help text should say something like "Name of a saved prompt in .ralphify/ralphs/ (e.g., 'docs', 'tests')". Currently it only makes sense if you already know the ralphify vocabulary.

- **F118: No examples in `--help` output** (NEW, VALIDATED). The help text describes each flag but shows no complete command examples. A user reading `--help` can't see how the flags combine. Adding 2-3 examples at the bottom would dramatically improve usability:
  ```
  Examples:
    ralph run                  # Use default prompt, infinite iterations
    ralph run -n 5 -l logs     # 5 iterations, save logs
    ralph run docs             # Use named ralph 'docs'
    ralph run -p "Fix the bug" # One-shot inline prompt
  ```
  Typer supports an `epilog` parameter for this, but it's not used.

- **F119: `-n` has no hint about safe defaults for new users** (NEW, VALIDATED). The help says "Max number of iterations. Infinite if not set." For a new user, "infinite" is intimidating. A note like "(recommended: start with -n 1 to test)" would guide new users toward the safe path documented in best practices. The best-practices page explicitly says "Never start with `ralph run` (infinite iterations)" but the help text doesn't warn.

- **F120: `--stop-on-error` description doesn't clarify that it means agent error, not check error** (NEW, VALIDATED). Help says "Stop if the agent exits with non-zero." This is accurate but doesn't pre-empt the confusion documented in F33. Adding "(does not trigger on check failures)" would prevent the most common misconception about this flag.

### `ralph new --help` Analysis

```
Commands:
  check        Create a new check. Checks are scripts that run after each
               iteration to validate the agent's work (e.g. tests, linters).
  instruction  Create a new instruction. Instructions are template-based
               prompts injected into the agent's context each iteration.
  context      Create a new context. Contexts are dynamic data sources
               (scripts or static text) injected before each iteration.
```

**Assessment:** The descriptions are good — they explain WHAT each primitive does, not just its name. But:

- **F121: `ralph new ralph` is hidden from `--help`** (NEW, VALIDATED). Creating a named ralph is a core workflow, but `ralph new --help` doesn't list it. The `new_ralph` command at `cli.py:215` is `hidden=True` because `_DefaultRalphGroup` at `cli.py:46-52` auto-routes `ralph new docs` → `ralph new ralph docs`. This clever routing means users never see "ralph" as a primitive type in help. But when the user asks "how do I create a named ralph?", the help offers no answer. The only way to discover this is through docs or experimentation. `ralph new docs` works but the user has no way to know this from the CLI alone.

- **F122: No `ralph new --help` suggestion of common names or patterns** (NEW, VALIDATED). When a user runs `ralph new check`, they must provide a name. The help says `name: Name of the new check.` but suggests no common patterns. A note like "Common check names: tests, lint, typecheck, build" would orient new users toward conventions. Similarly for contexts: "Common context names: git-log, test-status, plan".

### `ralph status --help` Analysis

Minimal: just "Show current configuration and validate setup." No options, no examples.

- **F123: `ralph status` has no flags for filtering or detail level** (NEW, VALIDATED). The command always shows everything: config, ralph path validation, agent command validation, all primitives. For a user with 15 checks and 10 contexts, the output can be 40+ lines. There's no `--checks-only` or `--summary` flag. For the common "did I set this up right?" question, a compact view would be better: "Ready to run: 5 checks, 2 contexts, 1 instruction, 3 ralphs."

### The Feature Discovery Funnel

How does a user discover each feature?

| Feature | Discovery path | Steps to discover |
|---|---|---|
| `ralph run` | `ralph --help` | 1 |
| Named ralphs (`ralph run docs`) | Docs, or try `ralph run --help` → see PROMPT_NAME | 2 |
| Checks | `ralph new --help` | 2 |
| Contexts | `ralph new --help` | 2 |
| Instructions | `ralph new --help` | 2 |
| Ralph-scoped primitives | Docs only — `ralph new check --help` mentions `--ralph` but doesn't explain the concept | 3+ |
| Failure instructions (CHECK.md body) | Docs or read the template | 3+ |
| Placeholder syntax (`{{ contexts.name }}`) | Docs only | 3+ |
| Named vs bulk vs implicit resolution | Docs only (how-it-works.md line 338+) | 5+ |
| `run.*` script escape hatch | Docs only (primitives.md or error discovery) | 4+ |
| Hot-reload via dashboard | Dashboard docs (feature doesn't exist in CLI) | N/A |

**Key insight:** The first 2 levels (commands and primitive types) are discoverable from the CLI. Everything from level 3 onwards requires reading docs. For users who prefer learning-by-doing, there's a hard cliff: you can figure out `ralph init && ralph run` from help text alone, but configuring checks, writing placeholders, or understanding resolution rules requires docs.

- **F124: No `ralph help <topic>` or guided learning path from CLI** (NEW, VALIDATED). Many CLI tools provide built-in topic help: `git help rebase`, `cargo help build`, `kubectl explain`. Ralphify has no topic-based help beyond `--help` on each command. A user who types `ralph help checks` gets "No such command." When the user hits a wall (e.g., "how do placeholders work?"), the CLI offers no guidance — they must find the docs site. A `ralph help` command that lists common topics with brief explanations (or links to docs) would bridge the docs-CLI gap.

- **F125: Error messages don't link to relevant documentation** (NEW, VALIDATED). When something goes wrong, error messages describe the problem but never point to docs. Examples: "ralph.toml not found. Run 'ralph init' first." is good but could add "See: https://ralphify.dev/getting-started". "Cannot use both a ralph name and --prompt-file." could add "See: ralph run --help for prompt resolution rules." This is a low-effort, high-value way to connect frustrated users with the answers they need.

### Tab Completion as Discovery

Typer supports shell completion (`--install-completion`). With completion installed:
- `ralph <TAB>` shows commands: init, new, run, status
- `ralph run <TAB>` should show available named ralphs — **but does it?**

- **F126: Tab completion for ralph names is not implemented** (NEW, HYPOTHESIZED). Typer's completion for positional arguments requires a callback function that returns suggestions. The `prompt_name` argument at `cli.py:277` has `typer.Argument(None, ...)` with no `autocompletion` callback. This means `ralph run <TAB>` likely shows nothing useful. Implementing completion for ralph names would make the multi-ralph workflow dramatically more discoverable: the user types `ralph run <TAB>` and sees `docs  refactor  tests` — immediately knowing what ralphs are available without running `ralph status`.

---

## Deep Dive: The Power User's Daily Workflow (NEW — Iteration 6)

The `.ralphify/` directory in this project contains 7 named ralphs and 3 global checks — this IS a power user's setup. Analyzing it reveals the patterns and friction that accumulate over weeks of daily use.

### The Actual Setup

**Global checks (apply to all ralphs):**
- `ruff-lint` — `ruff check .` (60s timeout, no failure instruction)
- `mkdocs-build` — `uv run mkdocs build --strict` (60s timeout, no failure instruction)
- `ty-type-check` — `ty check .` (60s timeout, no failure instruction)

**Named ralphs (7):**
- `docs` — Documentation writing agent
- `improve-codebase` — Autonomous refactoring agent
- `research-growth-hacking` — Research agent
- `research-harness-engineering` — Research agent
- `research-jobs-to-be-done` — Research agent
- `simplify-ux` — UX research agent (this ralph)
- `ui` — Dashboard UI agent

### Observations from Real Usage

**1. None of the global checks have failure instructions**
All three CHECK.md files are just frontmatter — no body text telling the agent how to fix failures. This means when ruff finds lint errors, the agent receives:
```markdown
### ruff-lint
**Exit code:** 1

```
src/foo.py:10:1 F401 `os` imported but unused
```
```
...and nothing else. No guidance like "Fix all lint errors. Do not add noqa comments." This is the most common setup (user copies the scaffold, fills in the command, doesn't write failure instructions) and it works — but it leaves value on the table. The agent is smart enough to fix lint errors from the output alone, but explicit instructions would prevent edge-case behaviors (like adding noqa comments).

**2. Research ralphs (4 of 7) have no checks applicable to them**
The ralphs named `research-*` and `simplify-ux` produce markdown research documents, not code. The global checks (ruff, mkdocs, ty) are code-oriented. These ralphs run all 3 global checks every iteration even though:
- `ruff check .` is irrelevant (research agent doesn't write Python)
- `ty check .` is irrelevant
- `mkdocs build --strict` is relevant only for the `docs` ralph

This is wasted time and confusing feedback. If ruff fails because of a pre-existing issue, the research agent gets feedback about lint errors it didn't cause and can't fix.

- **F127: Global checks run for ralphs where they're irrelevant — no per-ralph check filtering without scoped overrides** (NEW, VALIDATED). The global check model assumes all checks are relevant to all ralphs. For codebases with diverse ralph types (code, docs, research), this produces irrelevant feedback. The workaround is ralph-scoped primitives (`.ralphify/ralphs/simplify-ux/checks/ruff-lint/CHECK.md` with `enabled: false`), but: (a) users must know about scoped primitives, (b) it's 5+ levels of directory nesting (F69), (c) they must create a disable-override for every irrelevant check for every non-code ralph. For 4 research ralphs × 3 irrelevant checks, that's 12 override files, each requiring a directory and a CHECK.md with `enabled: false`.

- **F128: No check "tags" or categories to match checks to ralph types** (NEW, HYPOTHESIZED). An alternative to per-ralph scoping: checks could have a `tags: [code, python]` frontmatter field, and ralphs could have `check_tags: [code]` to filter. This is more scalable than directory-based scoping for the common case of "this check only applies to code ralphs."

**3. The ralph switching workflow is frequent but clunky**

With 7 ralphs, the user frequently switches between them. The workflow is:
```bash
ralph run docs -n 5 --log-dir logs      # work on docs for a while
ralph run improve-codebase -n 3 --log-dir logs  # switch to refactoring
ralph run simplify-ux -n 1 --log-dir logs       # run UX research iteration
```

Every invocation repeats `--log-dir logs`. The flags don't change between ralphs, only the name. This is the exact use case for O33 (unified `[run]` config in toml) — a `log_dir = "logs"` default would eliminate the most-typed flag.

- **F129: Power users repeat the same flags on every `ralph run` invocation** (NEW, VALIDATED — reinforces F42/F51). Looking at the actual workflow: `--log-dir logs` is typed on every run. `--timeout 300` is likely desired on every run. `-n` varies but has a typical range (1-10). The common pattern for a power user is: `ralph run <name> -n <N> --log-dir logs --timeout 300` — that's 40+ characters of flags that never change. A `[run]` section in ralph.toml would reduce this to `ralph run <name> -n <N>`.

**4. Research ralphs output to context/ files, not code**

The research ralphs (`simplify-ux`, `research-jobs-to-be-done`, etc.) write to `context/workspace/research/` files. They don't modify source code or run tests. Yet the loop's entire feedback mechanism is designed for code: checks validate code quality, failure feedback assumes the agent wrote code.

- **F130: The check-based feedback loop assumes code output — non-code ralphs have no feedback mechanism** (NEW, VALIDATED). Research ralphs have no meaningful checks: ruff doesn't apply, tests don't apply, mkdocs doesn't apply (unless the research writes docs). The loop runs, the agent writes research, checks run (and may pass or fail for unrelated reasons), and the cycle repeats without useful feedback. The self-healing loop — ralphify's core value proposition — provides zero value for non-code workflows. A content-quality check (e.g., word count, structure validation, or even a second LLM reviewing the output) would extend the feedback loop to knowledge work.

**5. Long ralph prompts are the norm for experienced users**

The `improve-codebase` ralph is 89 lines of detailed instructions. The `simplify-ux` ralph is 121 lines. These are substantially longer than the generic ROOT_RALPH_TEMPLATE (14 lines). Experienced users invest heavily in prompt quality — the prompt becomes the primary work product of harness engineering. Yet the tooling provides no support for prompt development:

- **F131: No prompt linting or structural validation** (NEW, VALIDATED). There's no check that validates the prompt itself — only checks that validate the agent's output. A prompt-level check could verify: all referenced contexts exist (no `{{ contexts.doesnt-exist }}`), placeholders use correct syntax, prompt length is reasonable, the prompt ends with clear instructions (not mid-paragraph). This would catch F37 (typo in placeholder name) at validation time rather than run time.

**6. The `ralph_logs/` convention is implicit, not enforced**

Multiple cookbook recipes and best-practices docs reference `--log-dir ralph_logs` or `--log-dir logs`. The actual project appears to use `logs`. There's no convention enforcement — each user/project picks their own name.

### The Power User's Wishlist (inferred from patterns)

Based on analyzing this project's actual `.ralphify/` setup:

1. **Per-ralph default flags** — different ralphs need different `-n`, `--timeout`, and especially different checks
2. **Check categories** — "run ruff only for code ralphs" without 12 override directories
3. **Prompt-level validation** — catch placeholder typos before wasting an iteration
4. **Quick ralph switching** — `ralph run docs` should just work with all the right defaults
5. **Research/non-code feedback** — the loop should be useful for knowledge work too

---

## New Simplification Opportunities (Iteration 6)

### Tier 1: High Impact, Low Effort (NEW)

#### O67: Truncate check output at line boundary, not character boundary (NEW)
**What:** In `truncate_output()` at `_output.py:28-32`, when the text exceeds `max_len`, find the last newline before the limit and truncate there. Include the truncation indicator with both lengths: `\n... (truncated from 12,847 to 4,980 chars at line boundary)`.
**Why:** Addresses F112. Character-mid-line truncation can split error messages, stack traces, and assertion output at the most confusing point. Line-boundary truncation ensures the agent receives complete lines.
**Job:** Trust (J2)
**Effort:** XS — change one line: `return text[:text.rfind('\n', 0, max_len)] + "\n... (truncated)"` (with edge case handling).
**Risk:** None. The output is slightly shorter (up to one line's worth fewer chars) but always well-formed.

#### O68: Remove exit code from check failure format (NEW)
**What:** Remove the `**Exit code:** {exit_code}` line from `format_check_failures()` at `checks.py:146`. The exit code provides no information the agent doesn't already have from the output.
**Why:** Addresses F113. Reduces noise in the agent's prompt. Every failing check saves ~20 characters of wasted context. Over multiple failures across many iterations, this adds up.
**Job:** Trust (J2)
**Effort:** XS — delete one line.
**Risk:** Very low. Exit code is still available in the event data for CLI display and logging.

#### O69: Add failure instructions to default CHECK.md template (NEW)
**What:** Change the CHECK_MD_TEMPLATE at `_templates.py:10-22` to include a default failure instruction: `Fix all issues reported by this check. Do not suppress or ignore warnings.` Remove the HTML comment boilerplate.
**Why:** Addresses F110. The current template creates checks with NO failure instruction — the most important text for self-healing is omitted by default. The html comment says "Optional instructions for the agent" which signals that failure instructions are optional. They're not optional for a good feedback loop — they're essential.
**Job:** Trust, Setup (J2, J5)
**Effort:** XS — change the template string.
**Risk:** Very low. Existing checks are unaffected. Only new checks get the default instruction.

#### O70: Add suggested workflow to `ralph --help` epilog (NEW)
**What:** Add an epilog to the main Typer app: `Quick start: ralph init → edit RALPH.md → ralph run -n 1`. Typer supports `app = typer.Typer(epilog="...")`.
**Why:** Addresses F115. New users see the workflow immediately after the command list. One line, zero code complexity.
**Job:** Setup (J1)
**Effort:** XS — add one string to the Typer constructor.
**Risk:** None.

#### O71: Add usage examples to `ralph run --help` (NEW)
**What:** Add an epilog to the `run` command showing 3-4 common usage patterns:
```
Examples:
  ralph run                  Use default prompt, infinite iterations
  ralph run -n 5 -l logs     5 iterations with logging
  ralph run docs             Use named ralph 'docs'
  ralph run -p "Fix bug"     One-shot inline prompt
```
**Why:** Addresses F118. Help text with examples is dramatically more useful than help text without. Users scan for patterns that match their intent.
**Job:** Run (J1)
**Effort:** XS — add epilog string to the `@app.command()` decorator.
**Risk:** None.

#### O72: Clarify `PROMPT_NAME` argument help text (NEW)
**What:** Change the help for `prompt_name` at `cli.py:277` from "Name of a ralph in .ralphify/ralphs/." to "Name of a saved prompt (e.g., 'docs', 'tests'). See .ralphify/ralphs/ or run ralph status."
**Why:** Addresses F117. The current text is circular for users who don't know the ralphify vocabulary.
**Job:** Run (J1)
**Effort:** XS — change one help string.
**Risk:** None.

#### O73: Add per-check execution name in failure format (NEW)
**What:** Before each check's failure section in `format_check_failures()`, add the failure instruction BEFORE the output, and include whether the check timed out:
```markdown
### tests (failed)
Fix all failing tests. Do not skip or delete tests.
**Output:**
```
FAILED tests/test_api.py::test_create_user - AssertionError
```
```
**Why:** Addresses the feedback format quality issues identified in this deep dive. Instruction-first ordering helps the agent approach the output with the right mindset. The `(failed)` / `(timed out)` label gives context.
**Job:** Trust (J2)
**Effort:** S — reorder lines in `format_check_failures()`.
**Risk:** Very low. Changes the format seen by the agent but the information content is the same.

### Tier 2: High Impact, Medium Effort (NEW)

#### O74: Tab completion for ralph names (NEW)
**What:** Add a Typer `autocompletion` callback to the `prompt_name` argument that returns available ralph names from `discover_ralphs()`.
**Why:** Addresses F126. `ralph run <TAB>` showing available ralphs is the single best discoverability improvement for multi-ralph users. Users discover available ralphs without running any command.
**Job:** Run, Steer (J1, J3)
**Effort:** S — add a completion callback function that calls `discover_ralphs()` and returns names.
**Risk:** Very low. Completion callbacks only fire during tab completion, not normal execution.

#### O75: Self-healing loop metrics in run summary (NEW)
**What:** Track per-check across iterations: how many times each check failed, how many times a failure was followed by a pass ("self-healed"), and whether a check is currently failing. Include in run summary:
```
Self-healing: tests failed 3×, self-healed 2×, currently passing
             lint failed 1×, self-healed 1×, currently passing
```
**Why:** Addresses F111. This is the metric that validates ralphify's core value proposition. Users can see at a glance whether the feedback loop is working.
**Job:** Trust, Monitor (J2, J6)
**Effort:** M — track per-check state across iterations in `ConsoleEmitter` or a new aggregation layer, compute self-heal rate from successive CHECK_PASSED/CHECK_FAILED events.
**Risk:** Low. New output only, no behavior changes.

#### O76: Positive feedback injection when all checks pass (NEW)
**What:** When all checks pass, inject a brief message into the next iteration's prompt: `## Previous Iteration\nAll checks passed. Continue with the next task from your plan.` Configurable — can be disabled via ralph.toml.
**Why:** Addresses F114. Positive reinforcement gives the agent signal that its approach is working. Without it, the agent receives identical prompts regardless of whether it succeeded or failed (when checks pass). The asymmetry — detailed feedback on failure, silence on success — may cause the agent to be unnecessarily cautious or uncertain.
**Job:** Trust (J2)
**Effort:** S — add a conditional in `_assemble_prompt()` at `engine.py:190-191`: if `check_failures_text` is empty AND previous iteration had checks, append positive message.
**Risk:** Low. Adds a small amount of prompt text. Could be seen as "noise" by some users — make it configurable.

#### O77: Check relevance filtering via tags (NEW)
**What:** Add an optional `tags` field to check and ralph frontmatter. Checks have `tags: code, python`. Ralphs have `check_tags: code` to filter which checks run. If a ralph has no `check_tags`, all checks run (backward compatible). If a check has no `tags`, it runs for all ralphs.
**Why:** Addresses F127 and F128. The current global-or-scoped model is too coarse (global = runs everywhere) or too tedious (scoped = 12 override directories for 4 ralphs × 3 checks). Tags provide a middle ground.
**Job:** Trust, Steer (J2, J3)
**Effort:** M — add `tags` to frontmatter parsing, filter checks in `_discover_enabled_primitives` based on ralph tags.
**Risk:** Medium. New frontmatter field, new filtering logic. Must be backward compatible (no tags = current behavior).

### Tier 3: Medium Impact, Medium Effort (NEW)

#### O78: Prompt validation check (built-in) (NEW)
**What:** Add a built-in prompt validation step that runs before the agent (or as a `ralph validate` command): verify all `{{ contexts.X }}` placeholders reference existing contexts, all `{{ instructions.X }}` reference existing instructions, warn about potential issues (very long prompt, duplicate placeholders, placeholder in the wrong format like singular `{{ context.X }}`).
**Why:** Addresses F131. Catches the most common prompt authoring errors before wasting an agent iteration.
**Job:** Trust, Setup (J2, J5)
**Effort:** M — parse the prompt for placeholders, cross-reference against discovered primitives, report mismatches.
**Risk:** Low. Validation only, never modifies anything.

#### O79: Add `--clarify-stop-on-error` hint to help text (NEW)
**What:** Change the `--stop-on-error` help text from "Stop if the agent exits with non-zero." to "Stop if the agent process exits with non-zero (does not trigger on check failures — checks feed back into the next iteration)."
**Why:** Addresses F120. Pre-empts the most common misconception about this flag, as documented in F33.
**Job:** Run, Trust (J1, J2)
**Effort:** XS — change one help string.
**Risk:** None.

#### O80: Add `-n` safety hint to help text (NEW)
**What:** Change the `-n` help text from "Max number of iterations. Infinite if not set." to "Max number of iterations. Infinite if not set. (Tip: start with -n 1 for new setups)"
**Why:** Addresses F119. Guides new users toward the safe pattern recommended in best practices.
**Job:** Run (J1, J9)
**Effort:** XS — change one help string.
**Risk:** None.

---

## Updated Principles Applied (Iteration 6)

| Principle | New Applications |
|---|---|
| **Clear feedback** | O67 (line-boundary truncation), O68 (remove noise), O69 (default failure instructions), O73 (reformat check failures), O75 (self-healing metrics), O76 (positive feedback) |
| **Observability is trust** | O75 (metrics validate core value prop), O78 (prompt validation) |
| **Sensible defaults** | O69 (failure instructions by default), O76 (positive feedback) |
| **Progressive disclosure** | O70/O71 (workflow hints in help), O74 (tab completion for discovery), O78 (validation catches errors early) |
| **Obvious naming** | O72 (clearer argument description), O79/O80 (self-documenting help text) |
| **Convention over configuration** | O77 (check tags as lightweight category system) |

---

## Updated Recommended Implementation Order (Iteration 6)

**Phase 1 — "Just Works" (add to existing):**
- O67: Truncate at line boundary (XS) — prevents most confusing truncation artifacts
- O68: Remove exit code from failure format (XS) — reduces noise
- O69: Default failure instructions in CHECK.md template (XS) — improves all new setups
- O70: Workflow hint in `ralph --help` (XS) — orients new users immediately
- O71: Examples in `ralph run --help` (XS) — best CLI improvement per character
- O72: Clearer PROMPT_NAME description (XS) — removes circular definition
- O79: Clarify `--stop-on-error` scope (XS)
- O80: Add `-n` safety hint (XS)

**Phase 2 — "Smart Setup" (add to existing):**
- O73: Instruction-first check failure format (S) — better feedback quality
- O74: Tab completion for ralph names (S) — discoverability step change

**Phase 3 — "Observable Loop" (add to existing):**
- O75: Self-healing loop metrics (M) — validates core value proposition
- O76: Positive feedback injection (S)

**Phase 4 — "Power User Tools" (add to existing):**
- O77: Check tags for per-ralph filtering (M) — solves the multi-ralph check problem
- O78: Prompt validation (M)

---

## Updated Open Questions (Iteration 6)

38. **Should failure instructions appear before or after check output?** O73 proposes instruction-first. Argument for: the agent reads the guidance before seeing the error, approaching diagnosis with the right mindset. Argument against: the error is the primary information; the instruction is supplementary guidance. Many prompt engineering guides recommend putting the most important information last. Need A/B testing with real agent behavior.

39. **Should positive feedback (O76) be on by default?** Some users may find "All checks passed" in the prompt to be noise — the absence of failure is sufficient signal. Others may find it valuable for guiding agent behavior. Options: on by default (simple, can be disabled), off by default (conservative), or configurable per-ralph.

40. **How should check tags (O77) interact with ralph-scoped primitives?** If a ralph has `check_tags: [code]` AND a ralph-scoped check exists, should the scoped check always run (regardless of tags)? Or should tags filter scoped checks too? The simplest model: tags filter global checks only; scoped checks always run for their ralph.

41. **Should `ralph --help` link to the docs site?** Adding "Docs: https://ralphify.dev" to the help output is zero effort and connects CLI users to the full documentation. But it's a URL that could rot, and it's promotional in a help context. Tools like `gh` (GitHub CLI) include docs links in help.

42. **Is the self-healing metric (O75) useful as a run-time display or only in the summary?** Showing "tests: failed 2×, self-healed 1×" per-iteration would be noisy. But showing it only in the final summary means the user doesn't see the pattern until the run ends. A middle ground: show it at verbose level during the run, always show in summary.

43. **Should `ralph validate` be a standalone command or part of `ralph status`?** O78 proposes prompt validation. If it's part of `ralph status`, every `ralph status` invocation runs validation (which requires discovering and potentially running contexts). If it's a standalone command, it's more explicit but adds to the CLI surface. Recommendation: part of `ralph status --validate` to keep the command count down.

---

## Consolidated Priority Matrix (Updated with Iteration 6)

### CRITICAL (implement immediately)
| ID | What | Effort | Addresses |
|---|---|---|---|
| O44 | Non-zero exit code on failures | XS | F81 (CI showstopper) |
| O55 | Run summary for all stop reasons | XS | F93 (crashed runs silent) |
| O56 | Ctrl+C reports as STOPPED | XS | F91 (misleading status) |

### Phase 1: Quick Wins (XS-S effort, high impact) — 28 items
| ID | What | Effort | Addresses |
|---|---|---|---|
| O4 | Suppress banner on `ralph run` | XS | F8 |
| O14 | Show iteration progress N/M | XS | F20 |
| O15 | Default `-n 1` for inline prompts | XS | F21 |
| O24 | Render per-check events in CLI | XS | F22 |
| O29 | Inline comments in generated toml | XS | F29 |
| O35 | Pass/fail suffix in log filenames | XS | F49 |
| O38 | Warn on shell operators in commands | XS | F66 |
| O39 | Validate `run.*` script permissions | XS | F59 |
| O46 | Handle type coercion errors gracefully | XS | F77 |
| O47 | Warn on empty prompt file | XS | F87 |
| O48 | `ralph list` command | XS | F68 |
| O52 | Detect inline comments in frontmatter | XS | F78 |
| O57 | Warn about unvalidated changes on Ctrl+C | XS | F92 |
| O59 | Estimated token count per iteration | XS | F98 |
| O67 | Truncate at line boundary | XS | F112 |
| O68 | Remove exit code from failure format | XS | F113 |
| O69 | Default failure instructions in template | XS | F110 |
| O70 | Workflow hint in `ralph --help` | XS | F115 |
| O71 | Examples in `ralph run --help` | XS | F118 |
| O72 | Clearer PROMPT_NAME description | XS | F117 |
| O79 | Clarify `--stop-on-error` scope in help | XS | F120 |
| O80 | Add `-n` safety hint in help | XS | F119 |
| O63 | Render PROMPT_ASSEMBLED/CONTEXTS_RESOLVED | XS-S | F105, F12 |
| O7 | Show prompt assembly summary | S | F12, F14 |
| O19 | Aggregate check stats in run summary | S | F23 |
| O25 | Warn on unresolved named placeholders | S | F37 |
| O31 | Validate `ralph.toml` schema on load | S | F45 |
| O32 | Show context timeout warnings | S | F32 |
| O40 | Show check output snippet on failure | S | F55 |
| O45 | Validate frontmatter field names | S | F76 |
| O54 | Detect missing colon in frontmatter | S | F75 |
| O58 | Track prompt size trend | S | F97 |
| O60 | Aggregate resource metrics in summary | S | F99 |

### Phase 2: Smart Setup (S-M effort) — 13 items
| ID | What | Effort | Addresses |
|---|---|---|---|
| O1 | Smart `ralph init` with auto checks | S | F2, F3 |
| O3 | Default iteration limit | S | F9, F100 |
| O8 | Better init prompt template | S | F1 |
| O17 | Soften dangerous flag in config | S | F17 |
| O26 | Validate check commands in status | S | F34 |
| O62 | Env var override for agent command | S | F102, F85 |
| O73 | Instruction-first check failure format | S | F108, F109 |
| O74 | Tab completion for ralph names | S | F126 |
| O6 | Warn on silent context exclusion | S-M | F16 |
| O34 | Status mirrors run resolution | S-M | F46, F47 |
| O50 | `ralph use <name>` | S-M | F72 |
| O64 | TTY detection for CI | S-M | F83 |
| O41 | `ralph init --preset` | M | F56, F57 |

### Phase 3: Observable Loop (M effort) — 11 items
| ID | What | Effort | Addresses |
|---|---|---|---|
| O28 | Fix non-Claude agent output | M | F43, F50 |
| O2 | Default log directory | S (after O28) | F10 |
| O16 | Show truncation details | S | F11 |
| O30 | Save prompt to log directory | S | F31 |
| O76 | Positive feedback injection | S | F114 |
| O33 | Unified config (`[run]` in toml) | M | F42, F51 |
| O36 | Agent activity in CLI | S | F60 |
| O37 | Post-iteration git diff summary | S | F61 |
| O51 | `--quiet` and `--verbose` modes | M | F83, F84 |
| O61 | Interruptible delay with countdown | S-M | F41, F95 |
| O75 | Self-healing loop metrics | M | F111 |

### Phase 4: Power User Tools (M-L effort) — 15 items
| ID | What | Effort | Addresses |
|---|---|---|---|
| O5 | Remove `--prompt-file` flag | S-M | F6, F7 |
| O9 | Hot-reload primitives | M | F13, F24 |
| O21 | Fail-fast checks | S-M | F26 |
| O23 | Preview command | M | F31, F25 |
| O27 | Clarify stop-on-error | S-M | F33 |
| O42 | CLI pause signal | M | F53 |
| O43 | Diagnostic mode for assembly | M | F54 |
| O49 | Full env var overrides | M | F85, F86 |
| O53 | `ralph status --ralph` | M | F73, F74 |
| O65 | Local override file | M | F102 |
| O66 | Claude Code token extraction | M | F101 |
| O77 | Check tags for per-ralph filtering | M | F127, F128 |
| O78 | Prompt validation | M | F131 |

### Deferred (L effort, high risk)
| ID | What | Effort | Addresses |
|---|---|---|---|
| O10 | Merge instructions into prompt | L | Concept count |
| O12 | Interactive init wizard | L | F5 |
| O22 | Rename "ralphs" to "prompts" | L | F19, F28 |

---

## Implementation Progress Check (Iteration 7)

Before adding new analysis, noting changes observed in the current codebase vs. previous iteration findings:

**O56 (Ctrl+C reports as STOPPED) — IMPLEMENTED.** `engine.py:406-407` now has `except KeyboardInterrupt: state.status = RunStatus.STOPPED`. This was identified as XS effort CRITICAL in iteration 5. The code no longer falls through to COMPLETED on Ctrl+C. The `RUN_STOPPED` event now correctly reports `reason="user_requested"` for interrupts.

**F91 — RESOLVED** by O56 implementation above.

**F93 (No summary for non-completed runs) — STILL PRESENT.** `_console_emitter.py:140` still checks `if data.get("reason") == "completed"` — stopped and crashed runs still show no summary. O55 remains unimplemented.

---

## Deep Dive: The Prompt Iteration Workflow (NEW — Iteration 7)

The "harness engineering" inner loop is the most frequent workflow for experienced ralphify users: write/edit RALPH.md → run 1-3 iterations → review results → refine prompt → repeat. This is the core craft of using ralphify effectively, yet the tooling provides almost no support for it.

### The Actual Workflow

**Phase 1: Write the initial prompt**
1. Open `RALPH.md` (or a named ralph's `RALPH.md`) in editor
2. Write the prompt — role, task, constraints, process
3. Add placeholder references to contexts (`{{ contexts.git-log }}`)
4. Save

**Phase 2: Test with one iteration**
1. `ralph run -n 1 --log-dir logs` (or `ralph run docs -n 1 -l logs`)
2. Wait 30-120 seconds (spinner, no feedback about what's happening)
3. See iteration result and check results
4. Open log file to see full agent output
5. Run `git diff` or `git log --oneline -1` to see what changed

**Phase 3: Evaluate and refine**
1. Was the output good? → If yes, scale up to more iterations
2. Was it bad? → Diagnose: was the prompt unclear? Were checks wrong? Was context missing?
3. Edit RALPH.md to add constraints/signs
4. Go to Phase 2

### Friction in Each Phase

**Phase 1 friction — prompt authoring has no feedback:**

- **F132: No syntax highlighting or validation for placeholder syntax** (NEW, VALIDATED). Users write `{{ contexts.git-log }}` in their editor with no feedback about whether this references an existing context. A typo (`{{ contexts.git_log }}` — underscore vs hyphen) silently produces an empty string at run time (F37). IDE extensions or a `ralph validate` command could catch this instantly, but neither exists. The closest thing is `ralph status`, which lists available context names but doesn't cross-reference them against the prompt file.

- **F133: No "prompt preview" without running an iteration** (NEW, VALIDATED — reinforces O23). To see the fully assembled prompt (with contexts resolved, instructions injected), the user must actually run an iteration. There's no `ralph preview` or `ralph run --dry-run`. The O23 opportunity was proposed in iteration 3 but hasn't been implemented. For prompt iteration, this is the single biggest time sink: each test costs 30-120 seconds of agent execution time when the user only wanted to verify "did my context placeholder resolve correctly?"

- **F134: No diff between iterations' prompts** (NEW, VALIDATED). When the user edits RALPH.md between iterations, there's no way to see what changed in the assembled prompt. The `PROMPT_ASSEMBLED` event includes `prompt_length` but not the prompt text, and there's no comparison between consecutive iterations. A user who adds one line to RALPH.md has no confirmation that (a) the change was picked up, and (b) the assembled prompt changed as expected. The closest signal is F14 (no indication prompt was re-read), which remains unaddressed.

**Phase 2 friction — testing is expensive:**

- **F135: Every prompt test costs a full agent execution** (NEW, VALIDATED). There's no lightweight "did the prompt assemble correctly?" check that doesn't involve spinning up the full agent subprocess. The minimum cost of verifying a prompt change is: run contexts (subprocess I/O, 1-30 seconds each) + run agent (30-120+ seconds, API cost) + run checks (5-60 seconds each). For a prompt iteration cycle, this means 1-4 minutes and $0.05-$0.50 per test. If a user is iterating on prompt wording (not checking agent behavior), this is dramatically overpriced. A `ralph assemble` command that resolves contexts and prints the prompt would cost only the context execution time.

- **F136: Log file review requires leaving the terminal** (NEW, VALIDATED). After `ralph run -n 1 -l logs`, the user sees `→ logs/001_20250312-143022.log` in the output. To review what the agent did, they must either: (a) open the file in an editor (`vim logs/001_...`), (b) `cat` the file, or (c) use `less`. None of these are integrated into the ralph workflow. A `ralph log` command that shows the most recent log file (or `ralph log 001` for a specific iteration) would reduce the context-switch cost. Even better: after each iteration, show the last N lines of agent output in the CLI (configurable, e.g., `--tail 20`).

**Phase 3 friction — diagnosis is manual:**

- **F137: No way to correlate agent output with check results** (NEW, VALIDATED). When a check fails, the user wants to know "what did the agent do that caused this check to fail?" The check output and agent output are in separate streams: check results are in the CLI output, agent output is in the log file. There's no cross-referencing. A user must: read the check failure output (in CLI or in next iteration's prompt) → open the log file → mentally correlate the agent's actions with the check's error. For `git diff --stat` post-iteration, the user must run it manually. O37 (post-iteration git diff summary) would help but isn't implemented.

- **F138: No per-ralph iteration history** (NEW, VALIDATED). When iterating on a named ralph (e.g., `ralph run docs -n 1` multiple times), there's no record of which prompt version produced which results. Log files are numbered sequentially within a single `--log-dir` but there's no separation by ralph name. If the user runs `ralph run docs -n 1 -l logs` and then `ralph run tests -n 3 -l logs`, the log directory has files 001-004 with no indication which iterations belong to which ralph. A `logs/docs/001.log`, `logs/tests/001.log` structure (or metadata in the log file) would make post-hoc analysis dramatically easier.

### The Prompt Engineering Tax

The total cost of one prompt iteration cycle:

| Step | Time | Cost |
|---|---|---|
| Edit RALPH.md | 30-120s | Free |
| `ralph run -n 1 -l logs` | 30-180s | $0.05-0.50 API |
| Review CLI output | 10-30s | Free |
| Open and read log file | 20-60s | Free |
| Run `git diff` | 5-10s | Free |
| Diagnose issues | 30-300s | Free |
| **Total** | **2-12 minutes** | **$0.05-0.50** |

For 5-10 prompt iterations to get a ralph working well, that's 10-120 minutes and $0.25-$5.00. The time cost is dominated by agent execution (unavoidable for testing agent behavior) and diagnosis (avoidable with better tooling). The diagnosis step could be nearly eliminated with: prompt preview (O23), per-iteration git diff (O37), and prompt assembly summary (O7/O63).

---

## Deep Dive: Loop Convergence & "Going in Circles" (NEW — Iteration 7)

The self-healing feedback loop's success depends on convergence: check failures decrease over iterations as the agent fixes issues. But what happens when the loop doesn't converge? This is the most frustrating user experience in ralphify — watching the agent fail, "fix," and fail again in the same way.

### Convergence Patterns

**Pattern A: Fast convergence (ideal)** — Iteration 1: 3 checks fail. Iteration 2: 1 check fails. Iteration 3: 0 checks fail. The user sees green checkmarks and moves on.

**Pattern B: Slow convergence** — Iteration 1-3: Same check fails each time. Iteration 4: Agent finds a different approach. Iteration 5: All pass. The user needs patience but the loop eventually works.

**Pattern C: Oscillation** — Iteration 1: Test A fails. Iteration 2: Agent fixes A, breaks test B. Iteration 3: Agent fixes B, breaks A again. The user watches a ping-pong pattern without realizing it.

**Pattern D: Stuck loop** — Iteration 1-10: Same check fails with the same error. The agent can't fix the problem (wrong approach, missing context, or fundamentally unable). The user pays for 10 wasted iterations.

**Pattern E: Semantic loop** — All checks pass every iteration, but the agent is doing the same thing over and over. It commits work, then the next iteration re-does the same work differently. No check fails because the work is "valid" — it's just not making progress. This is the most expensive pattern because there's no check-failure signal to alert the user.

### What the User Sees

For Pattern C (oscillation) and Pattern D (stuck), the user's CLI experience is:

```
── Iteration 3 ──
✓ Iteration 3 completed (45.2s)
  Checks: 1 passed, 1 failed
    ✓ lint
    ✗ tests (exit 1)

── Iteration 4 ──
✓ Iteration 4 completed (52.1s)
  Checks: 1 passed, 1 failed
    ✓ lint
    ✗ tests (exit 1)

── Iteration 5 ──
✓ Iteration 5 completed (48.7s)
  Checks: 1 passed, 1 failed
    ✓ lint
    ✗ tests (exit 1)
```

Every iteration looks the same. There's no signal that the pattern is repeating. The user must recognize it visually — "I've seen `✗ tests (exit 1)` three times in a row." For long runs (overnight or during meetings), the user isn't watching the output and discovers the stuck loop only when they check in later.

### Friction Points

- **F139: No detection of repeated check failures (stuck loop)** (NEW, VALIDATED). The engine at `engine.py:292-337` runs checks every iteration and formats failures, but never compares failures across iterations. There's no "this check has failed 5 times in a row" warning. The `ConsoleEmitter` receives `CHECKS_COMPLETED` events per iteration but doesn't track cross-iteration patterns. The `RunState` dataclass at `_run_types.py:62-145` has aggregate counters (`completed`, `failed`) but no per-check history. A simple heuristic: if the same check fails 3+ consecutive iterations, emit a warning `⚠ Check 'tests' has failed 3 consecutive iterations — the agent may be stuck. Consider editing your prompt or check failure instruction.`

- **F140: No convergence metrics during the run** (NEW, VALIDATED). There's no real-time display of whether the loop is converging. Users rely on pattern recognition in the terminal output. O75 (self-healing metrics in run summary) was proposed but only shows results at the END of the run. During the run, the user needs earlier signals. A per-check "trend arrow" would help: `✗ tests (exit 1) ↓` (getting worse) vs `✗ tests (exit 1) →` (stuck) vs `✗ tests (exit 1) ↑` (improving, e.g., fewer failures or shorter output). The check output length could serve as a rough convergence proxy (fewer errors = shorter output).

- **F141: No automatic circuit breaker for stuck loops** (NEW, VALIDATED). When a check fails N consecutive times, the loop should optionally stop (or at minimum warn loudly). Currently the only circuit breakers are: `-n` (iteration limit), `--timeout` (per-iteration), and `--stop-on-error` (agent crash only, not check failure — F33). There's no `--max-consecutive-failures 3` flag or equivalent. The self-healing loop philosophy says "keep trying" — but after 5 identical failures, the probability of self-healing on iteration 6 is near zero. The user is paying API costs for zero progress. A smart circuit breaker would save money (J9) and surface stuck states early.

- **F142: No comparison of check output across iterations** (NEW, VALIDATED). `format_check_failures()` at `checks.py:148-176` formats the CURRENT iteration's failures. The engine at `engine.py:289` returns the new `check_failures_text` and discards the previous one. There's no diff or comparison. If the check output is identical across 3 iterations (same test fails with the same error), this is a strong signal the agent is stuck — but the tool never computes this comparison. Even a rough heuristic (check output similarity > 90%) would catch the most common stuck patterns.

- **F143: Semantic loops (Pattern E) are completely invisible** (NEW, VALIDATED). When all checks pass but the agent isn't making meaningful progress, there's zero signal from ralphify. The agent might be: re-implementing the same feature differently each iteration, making tiny cosmetic changes that pass tests, or "implementing" tasks that are already done. The only way to detect this is reviewing git history manually (`git log --stat`). O37 (post-iteration git diff summary) would help by making the changes visible, but even that doesn't detect the pattern of redundant changes. A `git diff --stat HEAD~1..HEAD` that shows the same files modified in consecutive iterations could trigger a warning: `⚠ Same files modified in last 3 iterations: src/main.py, tests/test_main.py`

- **F144: No feedback escalation for persistent failures** (NEW, VALIDATED). When a check fails on iteration 1, the agent gets the check output + failure instruction. When the same check fails on iteration 2, the agent gets the EXACT SAME format: check output + failure instruction. There's no escalation: "I already told you about this failure and you didn't fix it." The failure instruction is static text from CHECK.md — it doesn't adapt to repeated failures. A more sophisticated approach: after N consecutive failures of the same check, inject additional context like "This check has failed the last N iterations. Your previous approaches have not worked. Consider a fundamentally different approach."

### The "Going in Circles" Cost

For a stuck loop running overnight:
- 10 iterations × 60s per iteration = 10 minutes of agent time
- 10 iterations × $0.10 per iteration = $1.00 (conservative estimate)
- 10 iterations × 60s check time = 10 minutes of compute time
- Total: 20 minutes, $1.00 — for zero productive output

For a 50-iteration overnight run where 40 iterations are stuck:
- 40 wasted iterations × $0.10 = $4.00 wasted
- 40 × 120s = 80 minutes of wasted time (extends total run by 80 minutes)

A simple 3-consecutive-failure circuit breaker would save 70-90% of wasted cost in stuck loop scenarios.

---

## Deep Dive: The Git State Contract (NEW — Iteration 7)

Ralphify's documentation says "progress lives in git" and recommends agents commit after each iteration. But ralphify has no git awareness beyond what the user configures manually. This section analyzes what git-related UX is missing.

### What Ralphify Assumes About Git

1. The project is in a git repo (recommended, not required)
2. The agent makes commits during each iteration
3. Users review progress via `git log`
4. Progress survives between iterations because it's committed

### What Ralphify Actually Does With Git

**Nothing.** The tool never interacts with git. It doesn't:
- Check if the working directory is a git repo
- Check for uncommitted changes before starting
- Check for uncommitted changes after each iteration
- Detect if the agent made commits
- Show git diff summaries
- Warn about dirty working tree state
- Handle merge conflicts
- Create branches

### Friction Points

- **F145: No pre-run working tree check** (NEW, VALIDATED). A user with uncommitted changes runs `ralph run -n 5`. The agent starts modifying files on top of the user's uncommitted work. If something goes wrong, `git stash` or `git checkout .` would discard BOTH the agent's changes AND the user's pre-existing changes. There's no way to separate them. A pre-run check — `git status --porcelain` → "You have uncommitted changes. Commit or stash before running?" — would prevent this common mistake. Tools like `git rebase` already do this ("Cannot rebase: You have unstaged changes").

- **F146: No post-iteration git awareness** (NEW, VALIDATED). After each iteration, the engine doesn't check whether the agent made any commits. The `ITERATION_COMPLETED` event at `engine.py:233-236` reports duration and exit code but nothing about git state. The user has no way to know from the CLI output whether the agent committed work, left uncommitted changes, or did nothing. O37 (git diff summary) was proposed but isn't implemented. Even a simple `  Commits: 1 new | Files: 3 modified` per iteration would transform the monitoring experience.

- **F147: Interrupted iterations leave orphaned changes** (NEW, VALIDATED — reinforces F92). When Ctrl+C fires during an iteration, the agent may have modified files but not committed them. O57 (warn about unvalidated changes) was proposed but isn't implemented. The user runs `ralph run`, presses Ctrl+C during iteration 5, and sees "Interrupted" (with the O56 fix). But what about the files the agent modified during iteration 5? They're now uncommitted changes in the working tree, mixed with any work from completed iterations. There's no `ralph clean` or rollback mechanism.

- **F148: No branch isolation for agent work** (NEW, VALIDATED). The agent works directly on the current branch. If the user is on `main` and runs `ralph run -n 10`, the agent commits directly to `main`. Best practices would suggest: create a branch like `ralph/docs-2025-03-12` → run the agent on that branch → review → merge to main. But `ralph init` doesn't suggest this, `ralph run` doesn't offer `--branch`, and there's no guidance about branch strategy in the CLI. The FAQ mentions "Run multiple loops in parallel on separate branches" but provides no tooling support.

- **F149: No detection of agent "un-doing" previous commits** (NEW, VALIDATED). A red flag mentioned in best practices (`docs/best-practices.md`): "Commits that undo previous commits." This is a strong signal of oscillation (Pattern C from the convergence analysis). But ralphify never checks for it. A simple `git diff HEAD~2..HEAD~1` compared to `git diff HEAD~1..HEAD` could detect when changes are being reversed. This is the git-level equivalent of the check-failure convergence detection (F139).

- **F150: No git-based progress tracking across iterations** (NEW, VALIDATED). The `RunState` tracks iteration count, completed, and failed — but these are counter-based, not outcome-based. Git history IS the outcome record, but ralphify doesn't read it. A post-run summary that shows `git log --oneline` for the commits made during the run would connect the abstract iteration counts to concrete work. Example: "Done: 5 iterations — 4 succeeded, 1 failed | 4 commits: abc123 'Add login endpoint', def456 'Add tests for login'..."

### The Branch Strategy Gap

The docs mention running "multiple loops in parallel on separate branches" but the tooling doesn't support this:

1. The user must manually `git checkout -b ralph/feature` before running
2. `ralph.toml` and `.ralphify/` are the same on all branches (unless manually diverged)
3. `--log-dir` doesn't namespace by branch — logs from different branches mix
4. No mechanism to start a run on a new branch automatically
5. No mechanism to PR the agent's work when done

- **F151: No `ralph run --branch <name>` for isolated agent work** (NEW, HYPOTHESIZED). A `--branch` flag that auto-creates and checks out a branch before starting the loop would: (a) isolate agent work from the user's current branch, (b) make cleanup easy (`git branch -D ralph/failed-attempt`), (c) enable parallel loops on different branches, (d) create a natural PR workflow when done. This is a common pattern in CI tools (GitHub Actions checks out branches automatically) but not available in ralphify's CLI.

---

## Deep Dive: The Terminal Output as Product Surface (NEW — Iteration 7)

The terminal output IS the product for CLI users. Every line printed is a design decision. This section does a line-by-line audit of the complete terminal output for a typical 3-iteration run, treating each line as a UI element with information density, visual hierarchy, and user value.

### Complete Output for `ralph run -n 3 -l logs`

```
████████╗... (6 lines of ASCII banner art)

  Harness toolkit for autonomous AI coding loops       ← tagline
                                                       ← blank line
  Run 'ralph --help' for usage information             ← help hint
  ⭐ Star us on GitHub: https://...                    ← promotional

Timeout: 5m 0s per iteration                           ← config dim
Checks: 3 enabled                                      ← config dim
Contexts: 1 enabled                                    ← config dim

── Iteration 1 ──                                      ← header
⠋ 23.4s                                               ← spinner (transient)
✓ Iteration 1 completed (45.2s) →                      ← result
logs/001_20250312-143022.log                           ← log path
  Checks: 3 passed                                     ← check summary
    ✓ ruff-lint                                        ← per-check
    ✓ mkdocs-build                                     ← per-check
    ✓ tests                                            ← per-check

── Iteration 2 ──
⠋ 12.1s
✗ Iteration 2 failed with exit code 1 (32.5s) →
logs/002_20250312-143108.log
  Checks: 2 passed, 1 failed
    ✓ ruff-lint
    ✗ tests (exit 1)
    ✓ mkdocs-build

── Iteration 3 ──
⠋ 8.3s
✓ Iteration 3 completed (52.1s) →
logs/003_20250312-143201.log
  Checks: 3 passed
    ✓ ruff-lint
    ✓ tests
    ✓ mkdocs-build

Done: 3 iteration(s) — 2 succeeded, 1 failed
```

### Line-by-Line Audit

| Lines | Content | Value | Issue |
|---|---|---|---|
| 1-6 | ASCII banner | Brand identity | Wastes 6 lines on every run (F8/O4) |
| 7 | Tagline | Orients new users | Unnecessary after first use |
| 8 | Blank line | Spacing | Wastes space |
| 9 | Help hint | Discoverability | Only useful on first use |
| 10 | Star us | Promotion | Wastes a line, not user-serving |
| 11 | Blank line | Spacing | Wastes space |
| 12-14 | Config summary | Validation | Good — confirms setup at a glance |
| 15 | Blank line | Spacing | Natural separator |
| 16 | Iteration header | Structure | Good but missing N/M (F20/O14) |
| 17 | Spinner | Activity signal | Only signal during 30-120s of execution (F60) |
| 18-19 | Result + log path | Outcome | Good but log path wraps to next line, breaking alignment |
| 20-23 | Check summary | Validation | Good but no check output (F55/O40) |

**Information density analysis:**
- **Banner block (lines 1-11):** 11 lines, ~1 useful line (tagline). Information density: ~9%. This block repeats on every `ralph run`.
- **Config block (lines 12-14):** 3 lines, all useful. Information density: 100%.
- **Iteration block (lines 16-23):** 8 lines, all useful. Information density: 100%.
- **Summary (last line):** 1 line, useful. 100%.

**The overhead:** For a 3-iteration run, the banner is 11 of ~40 total lines = 27.5% of the output is promotional/branding that provides no information. For a 30-iteration run, the banner drops to ~3% — but the first impression matters more.

### What's Missing From the Output

Each missing piece has been identified in previous iterations but seeing them together reveals the compound effect:

| What's missing | Where it would go | Impact | Related |
|---|---|---|---|
| Which ralph/prompt is being used | Config block | Medium — "am I running the right prompt?" | — |
| Iteration progress N/M | Iteration header | High — "how far along am I?" | O14 |
| Agent activity during iteration | Between header and result | Very High — "what is the agent doing?" | O36 |
| Prompt assembly summary | Before/after header | Medium — "what went into this iteration?" | O7/O63 |
| Git changes per iteration | After result | High — "what did the agent change?" | O37 |
| Check output on failure | After per-check line | Very High — "why did the check fail?" | O40 |
| Aggregate check stats | Summary | Medium | O19 |
| Resource metrics | Summary | Medium — "how much did this cost?" | O60 |

**The information gap:** Between the iteration header and the result (30-120 seconds of wall time), the user has ZERO information about what's happening. This is the longest information-void period in any CLI tool the user likely uses. For comparison: `npm install` shows packages being installed, `docker build` shows build steps, `cargo build` shows compilation units. Even `git push` shows transfer progress. Ralphify shows a spinner with elapsed time — that's it.

- **F152: The CLI output has a 30-120 second information void during each iteration** (NEW, VALIDATED). Between `── Iteration N ──` and the result line, the only output is the transient spinner showing elapsed time. The engine emits `AGENT_ACTIVITY` events during this period (for Claude Code) but `ConsoleEmitter` ignores them (F105). The user stares at `⠋ 45.3s` for up to two minutes. This is the primary anxiety-producing moment in the user experience, especially for new users (F60 "First-Run Anxiety"). Every second of silence is a second where the user wonders "is it working?" "is it stuck?" "is it burning money on nothing?"

- **F153: Log file path breaks line alignment in the output** (NEW, VALIDATED). `_console_emitter.py:105-106`: when a log file path is present, the status line is split: `✓ Iteration 1 completed (45.2s) →\nlogs/001_20250312-143022.log`. The `→` and newline break the visual scanning pattern — the user reads left-to-right and hits a line break in the middle of a semantic unit. The log path could be on the same line (if terminal width allows) or indented on the next line with consistent formatting: `  → logs/001_...` instead of bare `logs/001_...`.

- **F154: No indication which ralph/prompt is being used in the output** (NEW, VALIDATED). The config block shows "Checks: 3 enabled, Contexts: 1 enabled" but not which prompt file is being used. `RUN_STARTED` event data at `engine.py:371-379` includes `prompt_name` but `_on_run_started` at `_console_emitter.py:73-81` doesn't render it. When running `ralph run docs`, the user sees nothing confirming that the `docs` ralph was loaded. If `ralph.toml` has `ralph = "docs"` and the user runs `ralph run` (no argument), the output gives no indication which ralph was selected. For a project with 7 ralphs, knowing which one is running is critical context.

### The "Above the Fold" Problem

Terminal windows have limited visible lines (typically 24-80 rows). The banner consumes 11 lines — 14-46% of the visible area. When the first iteration starts, the banner may have already scrolled the config summary out of view. A user opening their terminal after the loop has been running sees only iteration output, with no context about which ralph, which checks, or what settings are active.

- **F155: Config summary scrolls out of view almost immediately** (NEW, VALIDATED). The config block (3 lines of dim text) is printed once at run start, immediately followed by iteration output. After 2-3 iterations, the config summary is likely scrolled off-screen. A user who switches to the terminal after the loop has been running for 10 iterations has no way to see the config without scrolling all the way back. For long runs, this is infeasible. Some CLI tools (like `docker-compose`) use a sticky header or periodic re-emission of key config info.

---

## Deep Dive: The Composability Model (NEW — Iteration 7)

Ralphify has four primitive types (checks, contexts, instructions, ralphs) that compose to produce a prompt. The composability model — how users build, combine, and reason about these pieces — is central to the power user experience. This section analyzes where the model works well and where it creates confusion.

### The Composition Pipeline

```
RALPH.md (prompt text)
  + {{ contexts.X }} ← run context commands, inject output
  + {{ instructions }} ← inject static instruction text
  + Check Failures   ← from previous iteration
  = Assembled Prompt → Agent stdin
```

This pipeline is elegant in concept: the prompt is a template, contexts bring dynamic data, instructions bring reusable rules, and check failures bring feedback. Each piece is independently authored and versioned.

### Where Composability Works

1. **Contexts as data sources**: `git log`, `test status`, `file tree` — these are genuinely useful dynamic data that changes every iteration.
2. **Checks as quality gates**: `pytest`, `ruff`, `mypy` — these validate independently of the prompt.
3. **Named ralphs as task switching**: different prompts for different tasks without rewriting.

### Where Composability Breaks Down

- **F156: Instructions are contexts without commands — the distinction is confusing** (NEW, VALIDATED — reinforces O10). An instruction is static text injected into the prompt. A context with no `command` field is... also static text injected into the prompt (via the `static_content` from CONTEXT.md body). The difference: instructions use `{{ instructions.X }}` placeholders, contexts use `{{ contexts.X }}` placeholders. Functionally, they do the same thing with different syntax. This was noted in O10 (merge instructions) but the analysis here is deeper: the overlap is not just conceptual — a user who creates a static context and a user who creates an instruction produce identical runtime behavior. The only structural difference is the primitive type name and placeholder kind.

  A user who asks "should I put my coding standards as an instruction or a context?" gets no clear answer. Both work. The convention "instructions are for rules, contexts are for data" is documented but not enforced — nothing stops a user from putting rules in a context or data in an instruction.

- **F157: The implicit append behavior creates a hidden dependency on placeholder absence** (NEW, VALIDATED). `resolver.py:51-54`: when no placeholders exist in the prompt, all contexts/instructions are appended to the end. This means a prompt that works fine (all contexts appended automatically) can break silently when the user adds their first named placeholder — because adding `{{ contexts.git-log }}` switches from "append all" mode to "named only" mode, silently dropping all other contexts (F16). The user's intent was "place git-log here AND keep everything else" but the behavior is "place git-log here INSTEAD OF everything else."

  This is the most dangerous silent behavior in the entire tool. The transition from "no placeholders" to "one named placeholder" is a breaking change that the user has no reason to expect. The fix in O6 (warn on silent exclusion) would catch this, but the root cause is the tri-modal resolution logic: append-all vs named-only vs named+bulk.

  **Simplification opportunity:** Replace the tri-modal system with: named placeholders for explicit placement, AND always append remaining content at the end. This eliminates the "named-only drops others" trap entirely. Users who don't want remaining content can use `{{ contexts }}` as the last line of their prompt (it would be empty if all contexts were named). The "silent drop" mode would simply not exist.

- **F158: Context resolution order is alphabetical, not dependency-ordered** (NEW, VALIDATED). `resolver.py:44`: `remaining = [content for name, content in sorted(available.items()) if name not in placed]`. When contexts are appended (no placeholders), they appear in alphabetical order. If a user has contexts `01-git-log`, `02-test-status`, `03-architecture`, the alphabetical order matches because of numeric prefixes. But if they have `git-log`, `test-status`, `architecture`, the order is `architecture`, `git-log`, `test-status` — which may not be the intended order. The naming-as-ordering pattern (prefix with numbers) is documented in best practices but is a workaround for lacking explicit ordering support.

- **F159: No visibility into what the assembled prompt actually looks like** (NEW, VALIDATED — consolidates F31, F133, F134). This friction has been identified from multiple angles (F31 in iteration 2, F133 above, O23/O30 proposed). The compound effect: users author 4 separate files (RALPH.md, contexts, instructions, check failure instructions), these are composed by an algorithm they can't observe, and the result is piped to an agent they can't inspect. The prompt is the most important artifact in the system — and it's the only artifact users never see. This is a fundamental trust gap.

### The Composability Complexity Budget

| Concept | Strictly necessary? | Simplification path |
|---|---|---|
| Checks | Yes — core value (self-healing feedback) | Keep |
| Contexts (dynamic) | Yes — fresh data per iteration is key | Keep |
| Contexts (static) | Redundant with instructions | Merge into instructions OR keep but document overlap |
| Instructions | Redundant with static contexts | Merge into static contexts OR keep but deprioritize |
| Named placeholders | Useful for control | Keep but fix silent-drop behavior (F157) |
| Bulk placeholders | Marginal — only saves explicit naming | Consider removing; always append remaining |
| Implicit append | Convenient but creates the F157 trap | Remove; require explicit bulk or named placement |
| Ralph-scoped primitives | Power feature | Keep but improve visibility (O53) |
| Enabled/disabled | Useful | Keep |

**The minimum viable primitive set:** Checks + dynamic contexts + the prompt file. Instructions could be merged into the prompt (they're just text), static contexts could be merged with instructions (both are static text). This reduces the concept count from 4 primitive types to 2 — dramatically simpler for new users. Power users who want composable static text could use contexts with no command (the existing mechanism).

---

## New Simplification Opportunities (Iteration 7)

### Tier 1: High Impact, Low Effort (NEW)

#### O81: Show which ralph/prompt is active in run output (NEW)
**What:** In `_on_run_started`, render the prompt source: `Ralph: docs (.ralphify/ralphs/docs/RALPH.md)` or `Prompt: RALPH.md`. The `prompt_name` field is already in the `RUN_STARTED` event data at `engine.py:378`.
**Why:** Addresses F154. Users with multiple ralphs need confirmation that the right one loaded. Without this, a user who runs `ralph run` (no argument) has no idea which prompt was selected from `ralph.toml`.
**Job:** Monitor, Trust (J6, J2)
**Effort:** XS — add 2 lines to `_on_run_started` in `ConsoleEmitter`.
**Risk:** None.

#### O82: Detect stuck loops — warn after 3 consecutive failures of the same check (NEW)
**What:** In `ConsoleEmitter`, track per-check consecutive failure count. When a check fails 3+ consecutive iterations, show a warning: `⚠ Check 'tests' has failed 3 consecutive iterations — consider editing your prompt or failure instruction.` Reset the counter when the check passes.
**Why:** Addresses F139 and F141. The simplest convergence signal. Catches Pattern C (oscillation) and Pattern D (stuck loop) early. Saves the user from watching and paying for iterations that won't self-heal.
**Job:** Trust, Monitor (J2, J6, J9)
**Effort:** S — add a dict tracking consecutive failures per check name in `ConsoleEmitter`, update on `CHECKS_COMPLETED`.
**Risk:** Very low. Warning only. The threshold (3) is conservative — users can ignore it if they know the agent needs more attempts.

#### O83: Indent log file path for consistent alignment (NEW)
**What:** Change `_console_emitter.py:105-106` from `status_msg += f" {_ICON_ARROW}\n{data['log_file']}"` to `status_msg += f" {_ICON_ARROW} {data['log_file']}"` (same line) when the terminal is wide enough, or `\n    {data['log_file']}` (indented) when it wraps.
**Why:** Addresses F153. The current bare newline breaks the visual scanning pattern. Every other line in the output is consistently indented; the log path is the only one that breaks alignment.
**Job:** Monitor (J6)
**Effort:** XS — change the format string in one line.
**Risk:** None.

#### O84: Add `ralph assemble [name]` command for prompt preview without agent execution (NEW)
**What:** Add a command that runs contexts, resolves placeholders, and prints the assembled prompt to stdout — without executing the agent or running checks. Essentially `_assemble_prompt()` exposed as a CLI command. Supports `ralph assemble` (root prompt), `ralph assemble docs` (named ralph), `ralph assemble --with-failures "test output"` (simulate failure injection).
**Why:** Addresses F133 and F135. The cheapest possible way to verify prompt assembly: only context commands execute (1-30 seconds total), no agent API cost. For prompt iteration cycles, this reduces verification time from 2-4 minutes to 5-30 seconds and cost from $0.05-0.50 to $0.00. This is the single highest-leverage improvement for experienced users.
**Job:** Steer, Trust (J3, J6)
**Effort:** S-M — extract `_assemble_prompt()` logic into a CLI command. Most of the code exists in `engine.py:171-195`; need to wire up context discovery+execution and emit to stdout.
**Risk:** Very low. Read-only command. Context commands still execute (they may have side effects, but that's also true during `ralph run`).

#### O85: Simplify placeholder resolution — always append remaining (NEW)
**What:** Change `resolver.py:51-54` to always append remaining (not-yet-placed) items to the end of the prompt, regardless of whether named placeholders were used. Remove the "named-only drops others" mode. If the user has `{{ contexts.git-log }}` in their prompt, git-log is placed inline AND all other contexts are still appended at the end.
**Why:** Addresses F157 (the most dangerous silent behavior). Eliminates the tri-modal resolution system (`append-all` / `named-only` / `named+bulk`). Under the new model, there are only two modes: `named-for-inline-placement` + `remaining-appended-at-end`, and `bulk-for-explicit-placement`. Users never lose content by adding a named placeholder.
**Job:** Trust (J2)
**Effort:** S — change ~3 lines in `resolve_placeholders()`. The `elif not has_named:` block becomes unconditional: always append remaining.
**Risk:** **Medium.** This is a behavior change. Users who intentionally use named-only mode to EXCLUDE certain contexts will now get all contexts appended. The trade-off: preventing silent content loss (very common, very confusing) vs. breaking intentional exclusion (rare, power-user behavior). Mitigate by: adding a `{{ contexts.none }}` or `{{ contexts.stop }}` placeholder that explicitly opts out of appending.

#### O86: Warn if working directory has uncommitted changes before `ralph run` (NEW)
**What:** At the start of `run_loop()`, run `git status --porcelain 2>/dev/null`. If output is non-empty, emit a warning: `⚠ Working directory has uncommitted changes. Consider committing or stashing before running.` Don't block — just warn.
**Why:** Addresses F145. Uncommitted changes mixed with agent changes are hard to separate. This warning catches the most common git hygiene issue at the cheapest possible moment (before any agent execution).
**Job:** Trust (J2, J6)
**Effort:** S — add `subprocess.run(["git", "status", "--porcelain"], ...)` and a conditional warning in `run_loop()` or `cli.py:run()`.
**Risk:** Very low. Warning only. Gracefully fails if not in a git repo (stderr captured, empty output treated as clean).

#### O87: Show per-iteration git change summary (NEW — concrete O37 refinement)
**What:** After each iteration completes, run `git log --oneline -1 --format="%h %s" 2>/dev/null` and `git diff --stat HEAD@{1}..HEAD 2>/dev/null` to show one line: `  Git: abc1234 "Add login endpoint" (3 files changed)`. If no new commit, show `  Git: no new commits`. Emit as a new `GIT_SUMMARY` event.
**Why:** Refines O37 with concrete implementation. The user instantly knows what the agent did without opening log files. This is the highest-value monitoring improvement for the "feel in control" job (J6).
**Job:** Monitor (J6)
**Effort:** S — run one git command after iteration, parse output, emit event, add handler.
**Risk:** Low. Git commands are read-only. Falls back gracefully.

#### O88: Feedback escalation for consecutive check failures (NEW)
**What:** Track check failure history in `run_loop()`. When a check fails 3+ consecutive times, prepend an escalation note to the failure section: `⚠ This check has failed the last {N} iterations. Your previous approaches have not resolved it. Consider a fundamentally different approach or ask for help.` This goes into the prompt, not just the CLI.
**Why:** Addresses F144. Gives the agent stronger signal that its current strategy isn't working. This is low-effort prompt engineering that the tool can do automatically instead of requiring the user to manually add "signs."
**Job:** Trust (J2)
**Effort:** S — track per-check failure counts in `_run_iteration` or engine-level state, pass to `format_check_failures`.
**Risk:** Low. Adds a few words to the agent prompt. Could be made configurable if users find it counterproductive.

### Tier 2: High Impact, Medium Effort (NEW)

#### O89: `ralph log [N]` — view iteration log files from CLI (NEW)
**What:** Add `ralph log` (shows most recent log file) and `ralph log 3` (shows log for iteration 3) commands. Detects `--log-dir` from ralph.toml or scans common directories (`logs/`, `ralph_logs/`). Outputs log content to stdout (pipeable to `less`, `grep`, etc.).
**Why:** Addresses F136. After running `ralph run -n 1 -l logs`, the user currently must manually navigate to and open the log file. `ralph log` is one command instead of `cat logs/001_20250312-143022.log` (which requires finding the exact filename).
**Job:** Monitor (J6)
**Effort:** S-M — find log directory, sort by name/timestamp, cat most recent or numbered iteration.
**Risk:** None. Read-only.

#### O90: Separate log files by ralph name (NEW)
**What:** When using named ralphs, create subdirectories in the log directory: `logs/docs/001_20250312.log`, `logs/tests/001_20250312.log`. When using root RALPH.md, use `logs/default/001_20250312.log`.
**Why:** Addresses F138. Power users running multiple ralphs share a single log directory where iterations from different ralphs are interleaved. Finding "all the logs from my docs ralph run last night" requires checking timestamps or opening each file. Subdirectories make this trivial.
**Job:** Monitor (J6)
**Effort:** S — pass `prompt_name` (or "default") to `_write_log()`, create subdirectory.
**Risk:** Low. Changes log directory structure. Existing log parsing tools might break if they assume flat structure.

#### O91: Add `--max-consecutive-failures N` circuit breaker (NEW)
**What:** Add a CLI flag (and `[run]` toml option) that stops the loop when any single check fails N consecutive iterations. Default: off (backward compatible). Recommended: 5. When triggered: `Stopping: check 'tests' has failed 5 consecutive iterations.`
**Why:** Addresses F141. This is the single most important cost-saving feature for unattended runs. A stuck loop running overnight with no circuit breaker wastes money and time. The user returns to find 50 iterations of the same failure. With `--max-consecutive-failures 5`, the loop stops after iteration 5 and the user's API bill is 90% lower.
**Job:** Trust, Run (J2, J9)
**Effort:** S-M — add per-check consecutive failure tracking in engine, add CLI flag, add stop condition.
**Risk:** Low. Opt-in. Default is off.

---

## Updated Principles Applied (Iteration 7)

| Principle | New Applications |
|---|---|
| **Clear feedback** | O81 (show active ralph), O82 (stuck loop warning), O83 (alignment fix), O87 (git summary), O88 (escalated failure feedback) |
| **Observability is trust** | O81, O82, O84 (prompt preview), O86 (pre-run git check), O87 |
| **Remove before you add** | O85 (simplify placeholder resolution by removing a mode) |
| **Convention over configuration** | O86 (git hygiene is a convention), O90 (log directory per ralph) |
| **Fewer steps** | O84 (verify prompt without running agent), O89 (view logs without navigating filesystem) |
| **Fewer concepts** | O85 (tri-modal → bi-modal resolution), F156 analysis (instructions ≈ static contexts) |
| **Progressive disclosure** | O91 (circuit breaker is opt-in but available for power users) |

---

## Updated Recommended Implementation Order (Iteration 7)

**CRITICAL — still the top priority:**
- O44: Non-zero exit code on failures (XS) — CI depends on this
- O55: Show run summary for ALL stop reasons (XS) — crashed runs need feedback

(O56 already implemented — Ctrl+C now sets STOPPED.)

**Phase 1 — "Just Works" (add to existing):**
- O81: Show active ralph/prompt in run output (XS) — orients the user immediately
- O83: Fix log file path alignment (XS) — visual polish
- O82: Detect stuck loops — warn after 3 consecutive check failures (S) — catches biggest cost waste
- O87: Per-iteration git change summary (S) — transforms monitoring experience

**Phase 2 — "Smart Setup" (add to existing):**
- O86: Warn on uncommitted changes before run (S) — git hygiene
- O85: Simplify placeholder resolution — always append remaining (S) — eliminates worst silent trap
- O88: Feedback escalation for consecutive failures (S) — makes self-healing smarter

**Phase 3 — "Observable Loop" (add to existing):**
- O84: `ralph assemble` command for prompt preview (S-M) — fastest prompt iteration
- O89: `ralph log [N]` for viewing logs (S-M) — reduces context-switching
- O90: Separate log files by ralph name (S) — power user organization
- O91: `--max-consecutive-failures N` circuit breaker (S-M) — cost protection for unattended runs

---

## Updated Open Questions (Iteration 7)

44. **Should O85 (always append remaining) be the default or opt-in?** The behavior change could surprise users who intentionally exclude contexts via named-only mode. Options: (a) change default, add `{{ contexts.stop }}` to opt out, (b) add `--strict-placeholders` flag to opt INTO the old named-only behavior, (c) make it a ralph.toml setting. Recommendation: (a) — the new behavior is safer and more intuitive. The old behavior was a trap, not a feature.

45. **Should the stuck-loop detection (O82) be per-check or aggregate?** Per-check: "tests has failed 3 times" catches a single stuck check. Aggregate: "2 of 3 checks have failed every iteration" catches broader patterns. Recommendation: per-check — it's simpler and the warning is more actionable ("fix THIS check").

46. **Should `ralph assemble` (O84) execute context commands or just show placeholders?** If it executes commands, the preview is accurate but takes time. If it doesn't, it shows `{{ contexts.git-log }}` literally — not useful for verifying resolution. Recommendation: execute by default, add `--no-contexts` flag to skip.

47. **How should the git change summary (O87) handle non-git projects?** The tool should gracefully degrade: if not in a git repo, skip the git summary silently. If in a git repo but no commits were made, show "no new commits." If the agent made uncommitted changes, show `git diff --stat` instead.

48. **Should the consecutive failure circuit breaker (O91) be configurable per-check?** A slow integration test might reasonably fail 5 times before the fix stabilizes. A lint check failing 5 times is definitely stuck. Per-check thresholds in frontmatter would be more flexible but add configuration complexity. Recommendation: start with a global threshold, add per-check later if needed.

49. **Should feedback escalation (O88) include the previous iteration's approach?** Currently the agent gets the same failure output each time. Including "Previous approach: [summary of what you tried]" would help the agent avoid repeating strategies. But this requires extracting agent intent from output, which is model-dependent and unreliable. Recommendation: keep it simple — just the escalation note, let the agent figure out what it tried.

50. **Is the instructions-contexts redundancy (F156) worth resolving?** O10 proposed merging them (deferred as high-risk). An alternative: document the equivalence explicitly and recommend instructions for static rules, contexts for dynamic or static data. Accept the overlap rather than breaking changes. The concept count drops from "must learn 4" to "must learn 3 + 1 optional."

---

## Consolidated Priority Matrix (Updated with Iteration 7)

### CRITICAL (implement immediately)
| ID | What | Effort | Addresses |
|---|---|---|---|
| O44 | Non-zero exit code on failures | XS | F81 (CI showstopper) |
| O55 | Run summary for all stop reasons | XS | F93 (crashed runs silent) |
| ~~O56~~ | ~~Ctrl+C reports as STOPPED~~ | ~~XS~~ | ~~F91~~ — **IMPLEMENTED** |

### Phase 1: Quick Wins (XS-S effort, high impact) — 36 items
| ID | What | Effort | Addresses |
|---|---|---|---|
| O4 | Suppress banner on `ralph run` | XS | F8 |
| O14 | Show iteration progress N/M | XS | F20 |
| O15 | Default `-n 1` for inline prompts | XS | F21 |
| O24 | Render per-check events in CLI | XS | F22 |
| O29 | Inline comments in generated toml | XS | F29 |
| O35 | Pass/fail suffix in log filenames | XS | F49 |
| O38 | Warn on shell operators in commands | XS | F66 |
| O39 | Validate `run.*` script permissions | XS | F59 |
| O46 | Handle type coercion errors gracefully | XS | F77 |
| O47 | Warn on empty prompt file | XS | F87 |
| O48 | `ralph list` command | XS | F68 |
| O52 | Detect inline comments in frontmatter | XS | F78 |
| O57 | Warn about unvalidated changes on Ctrl+C | XS | F92 |
| O59 | Estimated token count per iteration | XS | F98 |
| O67 | Truncate at line boundary | XS | F112 |
| O68 | Remove exit code from failure format | XS | F113 |
| O69 | Default failure instructions in template | XS | F110 |
| O70 | Workflow hint in `ralph --help` | XS | F115 |
| O71 | Examples in `ralph run --help` | XS | F118 |
| O72 | Clearer PROMPT_NAME description | XS | F117 |
| O79 | Clarify `--stop-on-error` scope in help | XS | F120 |
| O80 | Add `-n` safety hint in help | XS | F119 |
| O81 | Show active ralph/prompt in run output | XS | F154 |
| O83 | Fix log file path alignment | XS | F153 |
| O63 | Render PROMPT_ASSEMBLED/CONTEXTS_RESOLVED | XS-S | F105, F12 |
| O7 | Show prompt assembly summary | S | F12, F14 |
| O19 | Aggregate check stats in run summary | S | F23 |
| O25 | Warn on unresolved named placeholders | S | F37 |
| O31 | Validate `ralph.toml` schema on load | S | F45 |
| O32 | Show context timeout warnings | S | F32 |
| O40 | Show check output snippet on failure | S | F55 |
| O45 | Validate frontmatter field names | S | F76 |
| O54 | Detect missing colon in frontmatter | S | F75 |
| O58 | Track prompt size trend | S | F97 |
| O60 | Aggregate resource metrics in summary | S | F99 |
| O82 | Detect stuck loops (3 consecutive failures) | S | F139, F141 |
| O87 | Per-iteration git change summary | S | F146, F143 |

### Phase 2: Smart Setup (S-M effort) — 16 items
| ID | What | Effort | Addresses |
|---|---|---|---|
| O1 | Smart `ralph init` with auto checks | S | F2, F3 |
| O3 | Default iteration limit | S | F9, F100 |
| O8 | Better init prompt template | S | F1 |
| O17 | Soften dangerous flag in config | S | F17 |
| O26 | Validate check commands in status | S | F34 |
| O62 | Env var override for agent command | S | F102, F85 |
| O73 | Instruction-first check failure format | S | F108, F109 |
| O74 | Tab completion for ralph names | S | F126 |
| O85 | Simplify placeholder resolution | S | F157 |
| O86 | Warn on uncommitted changes | S | F145 |
| O88 | Feedback escalation for consecutive failures | S | F144 |
| O6 | Warn on silent context exclusion | S-M | F16 |
| O34 | Status mirrors run resolution | S-M | F46, F47 |
| O50 | `ralph use <name>` | S-M | F72 |
| O64 | TTY detection for CI | S-M | F83 |
| O41 | `ralph init --preset` | M | F56, F57 |

### Phase 3: Observable Loop (M effort) — 14 items
| ID | What | Effort | Addresses |
|---|---|---|---|
| O28 | Fix non-Claude agent output | M | F43, F50 |
| O2 | Default log directory | S (after O28) | F10 |
| O16 | Show truncation details | S | F11 |
| O30 | Save prompt to log directory | S | F31 |
| O76 | Positive feedback injection | S | F114 |
| O84 | `ralph assemble` for prompt preview | S-M | F133, F135 |
| O89 | `ralph log [N]` command | S-M | F136 |
| O90 | Separate logs by ralph name | S | F138 |
| O91 | Max consecutive failures circuit breaker | S-M | F141 |
| O33 | Unified config (`[run]` in toml) | M | F42, F51 |
| O36 | Agent activity in CLI | S | F60, F152 |
| O37 | Post-iteration git diff summary | S | F61 |
| O51 | `--quiet` and `--verbose` modes | M | F83, F84 |
| O61 | Interruptible delay with countdown | S-M | F41, F95 |
| O75 | Self-healing loop metrics | M | F111 |

### Phase 4: Power User Tools (M-L effort) — 15 items
| ID | What | Effort | Addresses |
|---|---|---|---|
| O5 | Remove `--prompt-file` flag | S-M | F6, F7 |
| O9 | Hot-reload primitives | M | F13, F24 |
| O21 | Fail-fast checks | S-M | F26 |
| O23 | Preview command | M | F31, F25 |
| O27 | Clarify stop-on-error | S-M | F33 |
| O42 | CLI pause signal | M | F53 |
| O43 | Diagnostic mode for assembly | M | F54 |
| O49 | Full env var overrides | M | F85, F86 |
| O53 | `ralph status --ralph` | M | F73, F74 |
| O65 | Local override file | M | F102 |
| O66 | Claude Code token extraction | M | F101 |
| O77 | Check tags for per-ralph filtering | M | F127, F128 |
| O78 | Prompt validation | M | F131 |

### Deferred (L effort, high risk)
| ID | What | Effort | Addresses |
|---|---|---|---|
| O10 | Merge instructions into prompt | L | Concept count |
| O12 | Interactive init wizard | L | F5 |
| O22 | Rename "ralphs" to "prompts" | L | F19, F28 |
