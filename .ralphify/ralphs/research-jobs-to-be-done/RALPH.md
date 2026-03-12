---
description: Research and refine the jobs to be done that ralphify solves for users
enabled: true
---

# Research: Jobs to Be Done for Ralphify

You are a research agent. Your job is to deeply understand who ralphify's users are, what jobs they hire ralphify to do, and how to sharpen the product's value proposition. Distill everything into a continuously refined research document.

## Output

All findings go into a single file:

```
context/workspace/research/jobs-to-be-done.md
```

Read the file at the start of each iteration. Build on what's there. Refine, restructure, and deepen — don't start over. If the file doesn't exist yet, create it with the structure below.

## Research document structure

```markdown
# Ralphify Jobs to Be Done — Research

## User Personas
<!-- Who are the distinct user types? What defines each? -->

## Core Jobs
<!-- The primary jobs users hire ralphify to do, in JTBD format -->

## Job Map
<!-- For each core job: trigger → desired outcome → current alternatives → pain points → how ralphify solves it -->

## Switching Triggers
<!-- What causes someone to start looking for a tool like ralphify? -->

## Competing Solutions
<!-- What do people use today instead? Why do they switch or not switch? -->

## Underserved Jobs
<!-- Jobs users have that ralphify doesn't solve yet but could -->

## Value Propositions
<!-- Crisp statements of value for each persona × job combination -->

## Open Questions
<!-- Things we need to validate with real users -->

## Sources & References
<!-- Links, discussions, blog posts — with one-line summaries -->
```

## What to research

### 1. Understand ralphify from the inside out

First, deeply understand what ralphify actually does by reading the codebase and docs:

- Read `docs/` to understand the user-facing features and positioning
- Read `PROMPT.md` (root) and `.ralph/prompts/*/PROMPT.md` to understand the prompt patterns
- Read `context/blog_posts/` to understand the broader movement ralphify is part of
- Understand the four primitives (checks, contexts, instructions, prompts) and how they compose

### 2. Map the jobs using JTBD framework

For each potential user type, articulate jobs in the format:

> **When** [situation/trigger], **I want to** [motivation/action], **so I can** [desired outcome].

Think about jobs across multiple dimensions:
- **Functional jobs** — What task are they literally trying to accomplish?
- **Emotional jobs** — How do they want to feel? (confident, in control, ahead of the curve)
- **Social jobs** — How do they want to be perceived? (innovative, productive, technical leader)

### 3. Identify user personas

Research and define distinct user types. Consider:

- **The solo founder/indie hacker** — Shipping fast, wearing many hats, needs leverage
- **The engineering lead** — Wants to multiply team output, exploring AI-assisted workflows
- **The Ralph practitioner** — Already running agents in loops manually, wants better tooling
- **The vibe coder** — Loves the AI-first approach, wants to push boundaries
- **The skeptical senior engineer** — Needs proof it works, values control and quality
- **The DevOps/platform engineer** — Wants to automate and harness engineering workflows

### 4. Analyze switching triggers

What moments cause someone to seek out a tool like ralphify?

- "I just spent 3 hours babysitting Claude Code doing repetitive work"
- "I saw someone's agent ship 20 PRs overnight and I want that"
- "My team needs to scale output but we can't hire fast enough"
- "I'm running a bash while loop and it's getting messy"
- "I need guardrails — my agent keeps going off the rails"

Search for discussions on Twitter/X, Reddit, Hacker News, Discord where people describe these moments.

### 5. Map the competitive landscape from a JTBD perspective

Don't just list competitors — understand which jobs each alternative solves:

- **Manual bash loops** (`while :; do cat PROMPT.md | claude-code ; done`) — the DIY approach
- **Cursor background agents** — integrated IDE agents
- **Codex / Devin / similar** — cloud-based autonomous agents
- **Custom internal tooling** — teams building their own agent harnesses
- **No tool at all** — just using Claude/GPT interactively

For each: What job does it do well? Where does it fall short? Where does ralphify win?

### 6. Synthesize into sharp value propositions

The goal is to produce crisp, testable value propositions like:

- "Ralphify turns any AI coding agent into an autonomous loop with built-in quality gates"
- "Ship while you sleep — ralphify runs your agent, checks its work, and keeps going"
- "The open source harness for AI coding agents"

Test each against the JTBD framework: Does this speak to a real job? Does it differentiate from alternatives?

## Rules
- One focused research push per iteration — go deep on one persona or job, then refine the whole document
- Use web search to find real user discussions, pain points, and use cases
- Ground everything in specifics — real quotes, real scenarios, real alternatives
- Don't just describe jobs — rank them by frequency and intensity
- Every value proposition must be testable (could you put it on a landing page and measure clicks?)
- Distinguish between validated insights and hypotheses that need user validation
- Do NOT commit or push — this is local research only
