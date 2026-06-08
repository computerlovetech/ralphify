# Diary: Simplify docs around the five jobs and the ralph loops format

Drastically simplify the README and MkDocs documentation so newcomers can understand ralphify fast. Two positioning shifts: (1) ralphify is the **runtime for the ralph loops format** (the open spec at [ralphloops.io](https://ralphloops.io/)), not "an AI tool"; (2) center everything on the five things you actually *do* with ralphify, rather than a sprawl of example use cases.

## Step 1: Reframe README and docs landing around the five jobs

**Author:** main

### Prompt Context

**Verbatim prompt:** "Okay so we need to drastically simplify the documentation, the mkdocs documentation and the readme file. We need to center around the five most valuable jobs to be done that Ralph can do. We also need to make it clear to people that it is using ralphloops.io not AI. Ralph loops that I owe in the standard format. Please identify the five jobs to be done that Ralph can help with and make them very clear and upfront in the documentation because there's way too much now. Simplify it so people can understand it and it will be easy to understand and get started with. Please go do"

**Interpretation:** Cut the documentation down and make it center on five clearly-stated jobs-to-be-done, presented upfront. Stop marketing ralphify as a generic "AI tool" and make clear it runs ralph loops — a standardized, portable format.

**Inferred intent:** Lower the comprehension barrier for new users. The docs had grown heavy with "autonomous AI coding agent" SEO phrasing and eight cookbook recipes, which buried the simple core: ralphify runs ralph loops, and there are only a handful of things you do with it.

### What I did

Started by surveying the existing docs surface: `mkdocs.yml` nav, `/README.md`, `/docs/index.md`, `/docs/getting-started.md`, `/docs/how-it-works.md`, and `/docs/cookbook.md`.

I initially assumed the "five jobs" were five example *use cases* (grow coverage, fix bugs, migrate, etc.) and asked the user to confirm a set via `AskUserQuestion`. The user corrected two things that changed the whole approach:

1. The five jobs are **not** example use cases — they're the five things you do to *create and run ralph loops* (the mechanics of using the tool).
2. The format is the one defined at **https://ralphloops.io/** — a standard format the user owns. Ralphify *uses* that format.

I fetched ralphloops.io via `WebFetch` to ground the framing: the ralph loops format is "a lightweight specification for packaging autonomous agent workflows as portable directories," centered on a single required `RALPH.md` file with agent definition, commands, arguments, and instructions.

With that, I defined the five jobs as the spine of the docs:

1. **Write a ralph** — scaffold a `RALPH.md`
2. **Feed it live data** — `commands` → `{{ commands.<name> }}` placeholders (self-healing feedback)
3. **Run the loop** — `ralph run`
4. **Steer it while it runs** — edit the prompt mid-run
5. **Share and install ralphs** — portable directories / `agr`

Then I rewrote:
- `/README.md` — rewrote around "Ralphify runs ralph loops" + the five jobs, with a link to ralphloops.io as the format spec. Stripped "autonomous AI coding agent" SEO phrasing.
- `/docs/index.md` — rewrote the landing page; the five jobs are now a card grid, each linking to the relevant page. Title/description/keywords reframed around "ralph loops" and ralphloops.io.
- `/docs/getting-started.md` — retitled and reframed the intro around the five jobs; dropped AI-heavy SEO from frontmatter.
- `/docs/cookbook.md` — reframed the intro so recipes are clearly *secondary* starting points you reach for after learning the five jobs.

Verified with `uv run mkdocs build --strict` — exit 0.

### Why

The user's two corrections are positioning decisions: ralphify is a *runtime for an open format*, and the docs should teach the *mechanics* of that format rather than parade use cases. Leading both the README and the docs home with the same five-job structure gives a single, repeated mental model. Linking ralphloops.io in both places makes the "it's a format, not just a tool" point concrete.

### What worked

The card-grid layout in `index.md` (reusing the existing `grid cards` Material extension already used on the page) maps cleanly to five jobs with one icon + one CTA each. The strict build passed first try after the rewrites, so no broken internal links or snippet references.

### What didn't work

My first `AskUserQuestion` call failed validation:

```
InputValidationError: Too big: expected array to have <=4 items (path: questions[0].options)
```

I had put 8 options on the "which five jobs" question; the tool caps options at 4. I reworked it into preset bundles. More importantly, the *premise* of that question was wrong — the user rejected the "example use cases" framing entirely, which is the real lesson, not the validation error.

### What I learned

The "five jobs to be done" are a product-narrative device, not a feature list: they're the verbs of using ralphify (write / feed / run / steer / share). The user thinks of ralphify as an implementation of the ralphloops.io format — that ownership of the format is central to how it should be marketed.

### What was tricky

The original prompt was voice-transcribed and garbled: "it is using ralphloops.io not AI. Ralph loops that I owe in the standard format." Decoding that into "ralphify uses the ralph loops format (ralphloops.io), a standard format the user owns — don't market it as a generic AI tool" required a clarifying round. Worth the round-trip; guessing wrong would have meant rewriting the rewrite.

### What warrants review

Look at `/README.md` and `/docs/index.md` first — they carry the new positioning and the five-job structure; check the framing reads the way the user wants. Confirm the five chosen jobs are the right five (write / feed / run / steer / share). The deeper reference pages (`how-it-works.md`, `cli.md`, `api.md`, `quick-reference.md`, `troubleshooting.md`) were left intact and are now secondary — verify nothing in them contradicts the new lead narrative. The nav in `mkdocs.yml` was not pruned.

### Future work

Potential follow-ups that fell out of the work but were not done: pruning/restructuring the `mkdocs.yml` nav to match the five-job spine; possibly folding `how-it-works.md` into getting-started; trimming the cookbook to fewer recipes. The `ralphs/example/` untracked directory present in the working tree is unrelated to this change and was left alone.
