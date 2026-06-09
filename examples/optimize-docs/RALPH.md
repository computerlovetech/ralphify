---
agent: claude -p --dangerously-skip-permissions
commands:
  - name: docs-build
    run: uv run mkdocs build --strict
  - name: git-log
    run: git log --oneline -20
---

# Optimize Docs

You are an autonomous coding agent running in a loop. Each iteration
starts with a fresh context. Your progress lives in the code and git.

## Docs build output

{{ commands.docs-build }}

If there are warnings or errors above, fix them first — that always
takes priority over everything else.

## Recent commits

{{ commands.git-log }}

## Task

Pick **one** small, concrete improvement per iteration from the
categories below. Rotate between categories — don't do the same
category twice in a row. Check recent commits to see what you already
did in previous iterations.

### Categories

**1. Page quality** — Find a page that is too long, dense, or hard to
scan. Break up walls of text, add examples, improve heading structure,
trim unnecessary content. Target: every page should be fast to consume.
Also:
- Add TL;DR summary boxes (`!!! tldr` admonition) at the top of guides
- Add "Prerequisites" sections before tutorials
- Replace generic headings ("Usage", "Example", "Overview") with
  descriptive ones that work in a table of contents and search results
- Use progressive disclosure (`??? note` collapsible blocks) for
  advanced or edge-case content
- Max 3 sentences before a code block — lead with the command, not
  the explanation

**2. Links and navigation** — Find broken internal or external links,
orphan pages not reachable from the nav, or dead-end pages with no
clear next step. Fix navigation so users always know where to go next.
Also:
- Add "Next steps" links at the bottom of every page (2-3 related pages)
- Link key terms to their reference page on first mention in each page
- Build a mental link graph — fix orphan pages (no incoming links) and
  dead-end pages (no outgoing internal links)
- Every page should have at least 3 internal links in the body content

**3. SEO and discoverability** — Do real SEO research for each page you
touch. Think about what developers would actually search to find this
content. Then:
- Rewrite page titles to match "how to X with Y" query patterns that
  developers actually type
- Add clear `description` and `keywords` to frontmatter — base these
  on actual search intent, not just the page content
- Research what terms competing tools (pi, cursor, claude-code,
  copilot) rank for and use relevant ones
- Target long-tail keywords around specific tasks ("run AI agent in
  loop", "automate coding agent prompts")
- Add Schema.org `TechArticle` structured data where appropriate

**4. Content freshness** — Cross-reference docs with the current code.
Find docs that describe behavior that has changed or features that have
been added. Update or remove stale content. Also:
- Check that error messages from the source code appear in the
  troubleshooting docs — developers google exact error strings
- Verify every RALPH.md example in docs has valid YAML frontmatter
- Ensure terminology is consistent across all pages ("ralph" vs "Ralph"
  vs "RALPH" — only the filename should be uppercase)

**5. Cross-surface consistency** — Check that features documented in
one place are also covered where relevant in: `docs/`, `README.md`,
`docs/quick-reference.md`, and `src/ralphify/skills/new-ralph/SKILL.md`.
Fix gaps, not duplications — each surface has its own purpose.

**6. Code example quality** — Find code examples that could be better.
- Ensure every code block has a language annotation (```yaml, ```bash)
- Show command output alongside commands, not just the command itself
- Replace placeholder values (`<your-thing-here>`) with realistic,
  copy-pasteable values
- Verify code examples are syntactically correct and actually work
- Add MkDocs Material code annotations for inline explanations

**7. LLM and AI optimization** — Make docs consumable by AI tools.
- Generate or update `llms.txt` at the site root — a structured
  markdown summary of the project for LLMs
- Generate or update `llms-full.txt` — all docs concatenated into one
  file with clear section headers
- Ensure each page is self-contained: defines its terms and doesn't
  assume context from other pages
- Use explicit Q&A format for FAQ-style content (literal questions as
  headings like "## How do I pass arguments to a ralph?")

**8. MkDocs config and DX** — Audit and improve the docs site config.
- Verify these MkDocs Material features are enabled: copy buttons
  (`content.code.copy`), dark mode toggle, feedback widget, "Edit this
  page" link (`edit_uri`), breadcrumbs, keyboard search (Cmd/Ctrl+K)
- Check that navigation hierarchy is max 2 levels deep
- Verify the site works on mobile (check for overly wide tables or
  code blocks)

## Principles

- **One thing per iteration.** Don't bundle multiple fixes.
- **Read before writing.** Always read the relevant code and existing
  docs before changing anything.
- **Don't gold-plate.** Good enough is good enough. Move on.
- **Jobs-to-be-done framing.** Frame docs around what the user is
  trying to accomplish, not feature descriptions.
- Ralphify's tone is direct, casual, and practical.

## Rules

- Run `mkdocs build --strict` and ensure zero warnings before committing
- Commit with a descriptive message and push
- Include which category (1-8) you worked on in the commit message
