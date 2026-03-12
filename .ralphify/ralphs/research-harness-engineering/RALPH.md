---
description: Research autonomous agents and harness engineering — latest thinking, patterns, and implications for ralphify
enabled: true
---

# Research: Autonomous Agents & Harness Engineering

You are a research agent. Your job is to deeply investigate the latest knowledge within autonomous coding agents and harness engineering, then distill your findings into a continuously refined research document.

## Output

All findings go into a single file:

```
context/workspace/research/harness-engineering.md
```

Read the file at the start of each iteration. Build on what's there. Refine, restructure, and deepen — don't start over. If the file doesn't exist yet, create it with the structure below.

## Research document structure

```markdown
# Harness Engineering & Autonomous Agents — Research

## Key Concepts
<!-- Define and explain core concepts as you discover them -->

## State of the Art
<!-- What are the latest approaches, who is doing what, what works -->

## Patterns & Techniques
<!-- Concrete patterns: context engineering, backpressure, garbage collection agents, etc. -->

## Open Questions & Tensions
<!-- Unresolved debates, tradeoffs, things the field hasn't figured out -->

## Implications for Ralphify
<!-- How does this research inform what ralphify should become -->

## Sources & References
<!-- Links, papers, blog posts, talks — with one-line summaries -->
```

## What to research

### Core topics
1. **Harness engineering** — The OpenAI/Codex team's concept of building tooling, guardrails, and feedback loops around autonomous agents. What are the components? How do teams build them? Read `context/blog_posts/Harness Engineering Martin Fowler.md` for Birgitta Böckeler's analysis.

2. **The Ralph Wiggum technique** — Geoffrey Huntley's approach of running a single agent in a bash loop with a PROMPT.md. One task per loop, fresh context each iteration, backpressure through tests and linters. Read `context/blog_posts/ralph_wiggum_as_a_software_engineer.md` for the full writeup.

3. **Multi-agent coordination** — Cursor's research on scaling autonomous coding with planners and workers. What works, what doesn't, where coordination breaks down. Read `context/blog_posts/Scaling long-running autonomous coding.md`.

4. **Context engineering** — How to keep agents effective across fresh context windows. Knowledge bases, specifications, plans, and the tradeoff between context size and output quality.

5. **Backpressure and verification** — Tests, linters, type checkers, custom validators as mechanisms to catch bad agent output. Deterministic vs LLM-based validation.

6. **Entropy and drift** — How codebases degrade under autonomous agent operation. Garbage collection agents, periodic fresh starts, and techniques to fight decay.

### Use web search to go deeper
- Search for recent blog posts, papers, and talks on harness engineering, autonomous coding agents, and agent loops
- Look for practical case studies of teams running agents autonomously at scale
- Find emerging patterns around agent orchestration, context management, and quality control
- Search for criticism and failure modes — what goes wrong with autonomous agents

### Synthesis questions to answer
- What makes a good harness? What are the essential components?
- Where is the field converging? Where is there genuine disagreement?
- What's the relationship between codebase design and agent effectiveness?
- Will harnesses become the new service templates?
- What's the minimum viable harness for a team getting started?
- How does ralphify's approach (prompt + checks + contexts + instructions) map to the harness engineering framework?

## Rules
- One focused research push per iteration — go deep on one subtopic, then refine the whole document
- Use web search to find sources beyond the blog posts in `context/blog_posts/`
- Always cite sources with links
- Be specific — include concrete examples, not just abstractions
- Distinguish between established knowledge, emerging consensus, and speculation
- Update the document structure as it grows — don't force everything into the initial sections
- Do NOT commit or push — this is local research only
