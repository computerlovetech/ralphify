# Diary: ralph-cli skill + replace Aider with Pi

Two related pieces of work in one session: (1) author a new `ralph-cli` agent
skill modeled on the existing `agr-cli` skill, install it via agr; (2) replace
every Aider suggestion across the project with Pi (pi.dev).

## Step 1: Create the ralph-cli skill

**Author:** main

### Prompt Context

**Verbatim prompt:** "look in ../agr/skills/agr-cli . I want to make a similar
skill for ralphif ralph-cli. Please write it and use agr to install it."
**Interpretation:** Study the `agr-cli` SKILL.md + references as a template, and
produce an analogous skill that teaches an agent to operate the `ralph` CLU /
ralphify, then register it with `agr add`.
**Inferred intent:** Ship a first-class, in-repo skill so any agent working in
ralphify (or a downstream consumer) can drive `ralph` correctly — scaffold,
write RALPH.md, run loops, pick agents, debug, use the Python API.

### What I did
Read `/Users/kasperjunge/Code/agr/skills/agr-cli/SKILL.md` to learn the
structure (frontmatter description, "When to use", mental model, numbered
workflows, boundaries, references index). Grounded the content in the real CLI
surface by running `ralph --help`, `ralph run --help`, `ralph scaffold --help`
and reading `/docs/cli.md` and the example `/ralphs/example/RALPH.md`.

Scaffolded with `agr init ralph-cli`, moved it under `/skills/ralph-cli/`, and
wrote `SKILL.md` plus six reference files: `writing-ralphs.md`, `running.md`,
`the-loop.md`, `agents.md`, `troubleshooting.md`, `python-api.md`. Registered it
with `agr add ./skills/ralph-cli`, which added `{path = "./skills/ralph-cli",
type = "skill"}` to `/agr.toml` and installed a copy into
`/.claude/skills/ralph-cli`.

### Why
The user explicitly asked for a sibling skill to `agr-cli`. Splitting depth into
`references/` keeps the top-level SKILL.md scannable while letting an agent load
detail on demand — the same pattern agr-cli uses.

### What worked
`ralph --help` and the existing `docs/cli.md` gave a complete, authoritative
surface, so the skill didn't need guesswork. `agr init` + `agr add ./path`
registered the in-repo skill cleanly on the first try.

### What didn't work
First `Write` of SKILL.md failed: "File has not been read yet" — `agr init` had
already created a scaffold SKILL.md, so it had to be `Read` before overwriting.
Re-read, then wrote successfully.

### What I learned
ralphify ships ralphs as an agr resource `type = "ralph"` (visible in
`agr.toml`), distinct from `type = "skill"`. The skill's boundaries call this
out so it defers install/sync mechanics to the `agr-cli` skill and keeps its own
scope on authoring + running ralphs.

### What was tricky
Scoping the description's trigger terms. "ralph", "RALPH.md", and "loop
engineering" are extremely common in this very repo, so the skill will activate
often here. I flagged that to the user rather than silently narrowing it.

### What warrants review
The SKILL.md description trigger breadth (over-activation risk in-repo). And the
factual accuracy of `references/python-api.md` against the actual `ralphify`
package exports — it was derived from `docs/cli.md`, which should be canonical,
but worth a sanity check.

### Future work
None required; the user immediately moved on to the Pi swap.

## Step 2: Replace Aider with Pi across the project

**Author:** main

### Prompt Context

**Verbatim prompt:** "remove suggestions about aider across the project.
Replace wiht Pi from pi.dev"
**Interpretation:** Every place the docs/skill/examples suggest Aider as an
agent option should instead suggest Pi (the coding agent at pi.dev), with
correct invocation.
**Inferred intent:** Standardize the recommended non-Claude/non-Codex agent on
Pi everywhere a reader might copy it.

### What I did
`grep -rin aider` to enumerate hits, then looked up Pi's real invocation via
WebFetch/WebSearch against pi.dev and `earendil-works/pi` docs before writing
any config — established that Pi's print mode (`-p`) reads piped stdin natively
and that `-a`/`--approve` trusts project-local config for unattended runs.

Replaced Aider with Pi in: `/README.md`, `/docs/index.md`, `/docs/cli.md` (agent
table row + the full `### Aider` → `### Pi` section), `/docs/llms.txt`,
`/docs/llms-full.txt` (taglines, table, the full Aider section incl. the
"specific model" variant and the standalone test snippet),
`/examples/optimize-docs/RALPH.md`, and the `ralph-cli` skill
(`SKILL.md`, `references/agents.md`, `references/running.md`). Used `sed` for the
one-line list swaps and `Edit` for the structural sections.

In `/tests/test_agent.py` and `/tests/test_console_emitter.py`, "aider" was only
a generic non-Claude placeholder agent in fixtures, so I swapped it to "pi"
(still non-Claude, non-stream-json — behavior unchanged). Left the two mentions
in `/tasks/done/` alone — those are archived completed-task write-ups, i.e.
historical narrative, not user-facing suggestions.

Reinstalled the skill with `agr add ./skills/ralph-cli --overwrite`.

### Why
The user wanted Aider gone "across the project." Pi is a genuine improvement to
document because, unlike Aider, it needs no `bash -c '... "$(cat -)"'` wrapper —
the config collapses to `agent: pi -p -a`.

### What worked
`pytest tests/test_agent.py tests/test_console_emitter.py` → 229 passed, 1
xpassed. `mkdocs build --strict` → clean, zero warnings. Final
`grep -rin aider` showed only the intentional `tasks/done/` leftovers.

### What didn't work
One `Edit` on `docs/llms-full.txt` failed with "File has been modified since
read" (a linter/formatter touched it between my Read and Edit). Re-read the
exact line range and re-applied — succeeded.

### What I learned
Pi install is `npm install -g --ignore-scripts @earendil-works/pi-coding-agent`
or `curl -fsSL https://pi.dev/install.sh | sh`. Print mode merges piped stdin
into the prompt, and `--approve`/`-a` governs trust of project-local
inputs/extensions (not tool-action auto-approval — non-interactive print mode is
inherently non-prompting). I verified this rather than guessing flags.

### What was tricky
Deciding scope of "across the project." I included the generated-but-committed
`llms*.txt` mirrors and the test fixtures, but deliberately excluded
`tasks/done/` history. Called that boundary out to the user.

### What warrants review
The `pi -p -a` recommendation — confirm `-a` is the desired default for
unattended loops vs. relying on a saved trust decision. Also the `llms-full.txt`
Pi section, which I rewrote by hand since there's no generator script in the repo
(`scripts/` only has `tui_dev/`).

### Future work
If ralphify later adds a generator for `llms.txt`/`llms-full.txt`, the
hand-edited Pi content should be reconciled with it.
