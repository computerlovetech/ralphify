---
description: The ralphify web dashboard is a planned feature for managing runs, editing primitives, and watching agent activity from your browser.
---

# Web Dashboard

!!! warning "Coming Soon"
    The web dashboard is **not yet available**. The features described below represent what's planned for a future release. The `ralph ui` command does not exist yet.

A browser-based UI for managing ralphify loops is planned. The dashboard will let you:

- **Launch and monitor runs** — start loops, watch iterations complete in real time, and stop or pause runs from your browser
- **Edit primitives** — browse, create, edit, and delete checks, contexts, instructions, and named ralphs without touching the filesystem
- **Review history** — see past runs with pass rates, iteration details, and check results
- **Watch agent activity** — when using Claude Code, see tool calls and text output stream in real time during each iteration

The dashboard will be a single-page app backed by a FastAPI server, using the same `run_loop()` engine that powers the CLI. It will be available as an optional install extra (`ralphify[ui]`).

## Stay updated

Follow the [changelog](changelog.md) for release announcements, or watch the [GitHub repository](https://github.com/computerlovetech/ralphify) for updates.
