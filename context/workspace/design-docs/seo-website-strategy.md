# SEO & Website Strategy

**Date:** 2026-03-12

## Domain

Use `ralphify.co`. The `.co` TLD is well-established for tech/dev tools and has no SEO disadvantage vs `.dev` — Google treats all TLDs equally for ranking.

## Docs: Host on `ralphify.co/docs/`, not GitHub Pages

Don't keep docs on `computerlovetech.github.io/ralphify/`. Reasons:

- **Split domain = split authority.** Every backlink to GitHub Pages docs builds `github.io`'s domain authority, not yours. All link equity should flow to `ralphify.co`.
- **Internal linking is weaker across domains.** Pillar page at `ralphify.co/blog/harness-engineering` linking to `ralphify.co/docs/checks` passes full authority. Cross-domain links don't.
- **One domain = one sitemap** — simpler for Google, better crawl budget.

Once migrated, redirect `computerlovetech.github.io/ralphify/` to `ralphify.co/docs/` to preserve existing links and funnel their authority to the new domain.

## Site Structure

```
ralphify.co/                    ← Landing page
ralphify.co/docs/               ← MkDocs documentation
ralphify.co/blog/               ← Blog / pillar pages / cluster content
ralphify.co/blog/harness-engineering-guide
ralphify.co/blog/what-is-ralph-loop
ralphify.co/docs/checks
ralphify.co/docs/contexts
...
```

Deploy as one MkDocs Material site (it has a blog plugin built in), or use a separate static site generator for the blog and proxy both under `ralphify.co` via Cloudflare.

## Channel Strategy

| Channel | Role | Priority |
|---------|------|----------|
| `ralphify.co` (website + blog) | Primary hub. All link equity, schema markup, and sitemap live here. | Highest |
| GitHub repo | Supporting signal. Good for branded searches (`ralphify`), but weak for concept searches (`harness engineering`). One of ~10 SERP slots. | Medium |
| dev.to / Medium / LinkedIn | Amplification. Cross-post with canonical URLs pointing back to `ralphify.co`. | Supplement |
| HN / Reddit | Seeding. Post only after pillar pages are live so there's something to link to. | After launch |

## Execution Order

1. Set up `ralphify.co` — static site, deploy to Cloudflare Pages or Vercel for speed.
2. Publish the first pillar page: "The Complete Guide to Harness Engineering" — coined term with zero competition. Own the definition before anyone else writes about it.
3. Add schema markup — FAQ, Article, SoftwareApplication. FAQ schema = 60% more likely to appear in AI Overviews.
4. Submit to Google Search Console immediately after launch.
5. Publish cluster blog posts (tutorials, comparisons, case studies), all linking back to the pillar page.
6. Cross-post to dev.to, Medium, LinkedIn with canonical URLs pointing to `ralphify.co`.
7. Seed on HN / Reddit once pillar content is live.

## Related Research

- [seo-domination-emerging-terms.md](../research/seo-domination-emerging-terms.md) — Full SEO research with tactics, examples, and action plan.
