# Diary: Migrate Ralphify skills to skills.sh

Replace Ralphify's agr-managed skills with skills.sh for Claude Code and Codex.

## Step 1: Convert active skills

**Author:** main

### Prompt Context
**Verbatim prompt:** you should also do it for the other projects and repos.
**Interpretation:** Include Ralphify in the cross-repo skill migration.
**Inferred intent:** Eliminate agr configuration while retaining usable project skills.

### What I did
Installed `brand-guidelines`, `ralph-cli`, `release`, `playwright-cli`, and `code-review`; created `/skills-lock.json`; and removed `/agr.toml` and `/agr.lock`.

### Why
The repository should use skills.sh and target only Claude Code and Codex.

### What worked
All five existing skills validated and installed.

### What didn't work
The old `docs-audit` and `setup-agent-workspace` skills were absent from `computerlovetech/skills`. The local release directory exposes the skill name `release`, not `ralphify-release`. Ralph resources are not supported by skills.sh.

### What I learned
The old manifest mixed active skills, stale remote skills, and ralph resources.

### What was tricky
The migration needed to preserve actual frontmatter names rather than stale manifest labels.

### What warrants review
Review the lockfile and omitted stale/ralph dependencies.

### Future work
Choose another mechanism for ralph dependencies if they remain necessary.
