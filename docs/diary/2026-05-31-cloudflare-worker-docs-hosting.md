# Diary: Host ralphify.co docs on a Cloudflare Worker

Goal: serve the docs at `ralphify.co/docs/` via Cloudflare instead of GitHub Pages. The site is a combined static artifact — landing page (`/website/`) at the root plus mkdocs Material output under `/docs/` — assembled by `just website-build` into `/_site/` (gitignored). What started as "how do I do this?" turned into untangling a two-Worker clash and landing on a single self-contained Worker deploy.

## Step 1: Recommend an approach and scaffold the Worker config

**Author:** main

### Prompt Context

**Verbatim prompt:** I'm hosting the docs for ralphify on ralphify.co/docs/ as cloudflare worker. how can i do that?
**Interpretation:** The user wants to move docs hosting to a Cloudflare Worker and asked for the how-to.
**Inferred intent:** Get docs live at `ralphify.co/docs/` on Cloudflare, replacing the existing GitHub Pages deploy.

### What I did
Inspected the repo to understand the existing setup: `/justfile` (`website-build` copies `website/*` into `_site/` then runs `mkdocs build --site-dir _site/docs`), `/.github/workflows/docs.yml` (deploys the same `_site/` to GitHub Pages), and `/mkdocs.yml` (`site_url: https://ralphify.co/docs/`). Confirmed `_site/` is a build artifact, not committed. Recommended Cloudflare **Workers Static Assets** (point a Worker at `_site/`; `/docs/...` routing is just physical files) and scaffolded `/wrangler.jsonc` with `assets.directory = "./_site"`.

### Why
The site is 100% static, so a Worker with the static-assets binding is the simplest, lowest-maintenance option, and it's Cloudflare's go-forward path over Pages. Pointing at the combined `_site/` makes `/docs/` work for free.

### What worked
The repo's existing build pipeline (`just website-build` / the Actions workflow) already produced exactly the artifact a static-assets Worker needs, so no build changes were needed at this stage.

### What didn't work
Nothing failed here — this was investigation and scaffolding.

### What I learned
The deploy artifact is a *merge* of two sources: landing page from `/website/` and mkdocs output into `_site/docs`. That layering detail drives everything downstream (the assets directory must be the parent `_site`, never `_site/docs`).

### What was tricky
Distinguishing the three lookalike directories: `/website/` (landing source), `/site/` and `/_site/` (build outputs). `_site/` is the real combined artifact.

### What warrants review
`/wrangler.jsonc` `compatibility_date` and the `html_handling`/`not_found_handling` defaults for mkdocs directory-style URLs.

### Future work
Decide custom-domain vs route, and retire the GitHub Pages workflow once Cloudflare is live.

## Step 2: Untangle the wizard, the domain clash, and the two-Worker collision

**Author:** main

### Prompt Context

**Verbatim prompt:** (across several turns) "what should i do" → screenshot of `Hostname 'ralphify.co' already in use by other custom domain` → "okay. so what do i have to do. i have two workers now, one for landing page one for docs"
**Interpretation:** The user was clicking through the Workers Builds wizard, hit a custom-domain conflict, and ended up with two Workers (`ralphify-co` for the landing page, `ralphify-co-docs` for docs) both connected to the same GitHub repo.
**Inferred intent:** Resolve the clash and get a working, non-conflicting deploy.

### What I did
Diagnosed two stacked problems. (1) **Custom-domain conflict:** a Custom Domain maps an entire hostname to one Worker, and the landing Worker already owned `ralphify.co`, so the docs Worker couldn't also claim it — the fix is a Route pattern (`ralphify.co/docs*`), not a second custom domain. (2) **Two Workers, one repo, one config:** a `wrangler.jsonc` describes exactly one Worker, so when the landing Worker `ralphify-co` ran `wrangler deploy` it read my config (`name: ralphify-co-docs`) and failed ("Latest build failed"). Used `AskUserQuestion` to choose between consolidating to one Worker vs. maintaining two configs; the user chose **one Worker for everything**. Rewrote `/wrangler.jsonc` to `name: ralphify-co`, `assets.directory = "./_site"`, no `routes` (the existing custom domain already routes the whole hostname). User deleted the `ralphify-co-docs` Worker.

### Why
One Worker serving the combined `_site` is strictly simpler than two: the landing Worker already holds the `ralphify.co` custom domain, so reusing it means no route juggling and no per-Worker config files. The two-Workers-one-repo arrangement was itself the cause of the build failure.

### What worked
Reframing the failure as "one config can't describe two Workers" made the consolidation decision obvious. The existing custom domain on `ralphify-co` meant zero domain reconfiguration was needed.

### What didn't work
The custom-domain dialog returned: `Hostname 'ralphify.co' already in use by other custom domain. Either delete it, try a different hostname, or use the option 'override_existing_origin' to override.` That was the trigger to abandon the second-custom-domain idea entirely.

### What I learned
Custom Domains and Routes are different mechanisms in Cloudflare: a Custom Domain grabs a whole hostname for one Worker; more-specific Routes can carve out subpaths to other Workers. And critically, multiple Workers Builds projects pointed at the same repo all execute their own build+deploy on every push, all reading the same `wrangler.jsonc` — they collide unless each has its own config.

### What was tricky
The `name` field had to match the *existing* Worker (`ralphify-co`) exactly, or CI would deploy into a brand-new stray Worker instead of the one holding the domain. Easy to miss; it was wrong in my first two drafts (`ralphify-site`, then `ralphify-co-docs`).

### What warrants review
Confirm no leftover route or binding from the deleted `ralphify-co-docs` Worker lingers in the Cloudflare account.

### Future work
Make the deploy self-contained so it doesn't depend on a dashboard-only build-command field (Step 3).

## Step 3: Make the build self-contained, verify, deploy, and monitor to success

**Author:** main

### Prompt Context

**Verbatim prompt:** Great, i've deleteed ralphify-co-docs.. Please fix this and monitor the build until to make sure it builds successfully
**Interpretation:** Finish wiring the single Worker, push it, and watch until the Cloudflare build actually succeeds.
**Inferred intent:** A verified, live deploy — not just instructions.

### What I did
Checked auth and state: `npx wrangler whoami` reported **not authenticated** (login is an interactive browser flow), so a local deploy was off the table. To remove the dependency on the dashboard "Build command" field (which I can't set), I moved the build *into* `/wrangler.jsonc` under `build.command`, so `npx wrangler deploy` builds then uploads. Verified the real build locally with `just website-build` (produced `_site/index.html`, `_site/docs/index.html`, `_site/docs/404.html`). A `wrangler deploy --dry-run` confirmed wrangler runs the custom build for assets-only Workers, but the first `build.command` used `pip install uv` and failed with `/bin/sh: pip: command not found`. Switched to the portable uv standalone installer (`curl -LsSf https://astral.sh/uv/install.sh | sh && export PATH="$HOME/.local/bin:$PATH" && uv sync ...`); the next dry-run ran end-to-end and reported `Read 101 files from the assets directory`. Removed `/.github/workflows/docs.yml` (`git rm`), committed both changes as `20c3901`, and pushed to `main` to trigger the Workers Build. Polled `https://ralphify.co/docs/` and watched it flip 404 → 200 within ~30s. Final checks: `/` 200 (landing intact), `/docs/` 200 (Material markup, title "a runtime for the ralph format"), `/docs/cli/` 200 (deep directory route resolves).

### Why
Putting the build in `wrangler.jsonc` makes the repo the single source of truth and removes a dashboard field I have no API access to set. The portable installer avoids assuming `pip`/system Python exist in Cloudflare's Node-first build container — uv even fetches its own Python per `requires-python`.

### What didn't work
First `build.command` attempt failed in dry-run: `× ERROR Running custom build 'pip install uv && ...' failed` / `/bin/sh: pip: command not found` (exit code 127). `pip` is not on PATH on the dev machine and isn't guaranteed in CI either. Replacing it with the curl-based uv installer fixed it.

### What I learned
Three concrete facts: (1) `wrangler` runs `build.command` even for assets-only Workers (no `main` script) — confirmed via the dry-run output `runCustomBuild`. (2) `wrangler deploy --dry-run` executes the custom build and validates assets without auth, which makes it a genuine pre-flight check. (3) The assets directory must be `./_site`, not `./_site/docs`, because requests arrive with the `/docs/` prefix and are resolved against the assets root — so the file at `_site/docs/cli/index.html` is what serves `/docs/cli/`.

### What was tricky
Monitoring without Cloudflare API access. I couldn't read build logs, so I established a baseline first (`/` = 200, `/docs/` = 404) and used the 404→200 transition on `/docs/` as the success signal. The mkdocs-material build also prints alarming red "mkdocs 2.0" advisory lines that look like errors but aren't — the build succeeds ("Documentation built in 1.71 seconds").

### What warrants review
- `/wrangler.jsonc` `build.command` — it shells out to `curl | sh`; confirm that's acceptable supply-chain-wise for this project, or pin uv to a version.
- The `ralphify-co` Worker may still have a stale dashboard **Build command**; it didn't interfere (deploy succeeded), but clearing it removes ambiguity since `build.command` now does the work.
- `/docs/assets/` returns 404 (directory with no index) — expected, but worth a glance to confirm no real asset paths are affected.

### Future work
Optionally pin the uv version in `build.command`; optionally add a redirect for `/docs` (no trailing slash) if anyone links it that way; consider whether the landing page wants its own `404.html`.
