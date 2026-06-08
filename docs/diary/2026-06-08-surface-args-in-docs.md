# Diary: Surface the `args` feature and tighten the ralph-directory framing in docs

The README and docs explained `agent` and `commands` thoroughly but never showed the third frontmatter field, `args`, so the parameterization story was invisible to a first-time reader. Separately, several surfaces described a ralph as just "a `RALPH.md`" when it's really a *directory* containing one, whose format is defined by the open spec at [ralphloops.io](https://ralphloops.io/). This task fixes both across the README and the docs site.

## Step 1: Add args illustrations and tighten directory/spec framing

**Author:** main

### Prompt Context

**Verbatim prompt:** "Okay so a couple of things for the documentation: - You mentioned that the only thing a Ralph loop for Ralphify needs is a ralph.md but it's not entirely true. It's a directory with ralph.md in it and linked to the format specification on Ralph loops that I owe. - In the README you do not highlight the args feature of the loop or of Ralph loops' format. - It would be nice to also have an example where it shows you can actually add arguments to the Ralph loops so you can actually parameterize them. You show the commands and you show the agent but also show the args. Is this clear? Do you have any clarifying questions?"

**Interpretation:** Correct the "all you need is a RALPH.md" framing to "a directory containing a RALPH.md" and link the format spec; make `args` visible in the README; add an illustration showing how `args` parameterizes a loop alongside `agent` and `commands`.

**Inferred intent:** New readers should understand that a ralph conforms to an open, portable format (not an ad-hoc file), and should discover that loops are parameterizable — a key reuse capability that was effectively hidden.

### What I did

Asked two clarifying questions up front via `AskUserQuestion`. The user clarified they did **not** want a real-world worked example — just a minimal snippet that demonstrates the *format* using `args` — and that changes should land in both the README and the docs site.

Then made docs-only edits:

- `/README.md` — "Write a ralph" job now states a ralph is a *directory* containing `RALPH.md` and links the [ralph loops format](https://ralphloops.io/). Added a minimal frontmatter illustration showing all three fields together (`agent` + `commands` + `args`) with a `ralph run my-ralph --focus src/auth` invocation.
- `/docs/index.md` — Reworded the hero to "a directory whose one required file is `RALPH.md`"; the "Write a ralph" card now mentions `args` / `{{ args.<name> }}`.
- `/docs/getting-started.md` — Manual-setup intro reframed as a directory and links the spec; added a "Parameterize a ralph with `args`" tip box with a minimal snippet, CLI invocation, and a cross-link to the CLI reference's user-arguments section.

Verified with `uv run mkdocs build --strict` (passes) and `uv run pytest -q` (627 passed, 1 xpassed).

### Why

The user owns the ralph loops format spec and wants the docs to consistently frame a ralph as a directory conforming to that open format, not a lone file. And `args` is a first-class format field that enables reuse, so it deserves visibility next to `agent` and `commands`.

### What worked

Clarifying first paid off — the initial instinct was to feature the untracked `ralphs/example/` research ralph, but the user wanted a *minimal format illustration*, not a real example. That steered the edits toward tight, copy-pasteable snippets rather than a heavier worked example.

### What didn't work

`uv run mkdocs build --strict` prints an alarming red block ("No migration path exists", "Closed contribution model", etc.). On inspection this is mkdocs-material's unrelated April-Fools "MkDocs 2.0" marketing banner printed to stderr, not a build warning. The build itself reports "Documentation built" with no strict failures.

### What I learned

The docs already had extensive `args` coverage in the reference pages (`cli.md`, `quick-reference.md`, `how-it-works.md`, `cookbook.md`) — the gap was purely in the *entry-point* surfaces (README, index hero, getting-started manual setup) where a newcomer first forms their mental model.

### What was tricky

The README is structured around a fixed "five things you do with ralphify" framing, so adding `args` couldn't introduce a sixth job. Folding the args illustration into job #1 ("Write a ralph") — since `args` is a format field, not a separate activity — kept the structure intact.

### What warrants review

Check that the three new snippets are internally consistent (they all use `{{ args.focus }}` with `--focus src/auth`) and that the cross-link `cli.md#user-arguments` resolves. Confirm the directory/spec framing reads naturally in each location rather than feeling repetitive across README and index hero.

### Future work

The untracked `ralphs/example/` directory (a research ralph using `agent` + `commands` + `args`) was left in place but not referenced. Decide whether to keep it as a shipped example, move it into the cookbook, or remove it.
