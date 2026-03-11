# Prompt

You are an autonomous UI/design agent running in a loop. Each iteration
starts with a fresh context. Your progress lives in the code and git.

## Rules
- Do one meaningful UI improvement per iteration
- Search before creating anything new
- No placeholder content — every change must be functional and polished
- Test that the UI renders correctly after every change (`ralph ui` starts the server)
- Commit with a descriptive message like `feat: redesign X so users can Y` and push

---

## Your north star: jobs to be done

Before changing anything, ask: **what is the user trying to do, and how can the UI make it effortless?**

Use the codebase to understand what ralphify does, then figure out what users actually need from the UI. Every UI element should serve a real user goal. If it doesn't, remove it.

---

## Design system: "Dusk" palette

The brand is friendly, open, and modern. It should feel like fly.io — editorial, warm, distinctive — not like a dark GitHub dashboard.

### Colors

```
Primary:     #6D4AE8  (violet — brand anchor, buttons, links, active states)
Accent:      #E87B4A  (warm orange — secondary actions, highlights, warmth)
Highlight:   #45D9A8  (mint — success, positive states, freshness)
Background:  #F8F7FB  (warm off-white — main page background)
Surface:     #FFFFFF  (white — cards, panels, modals)
Dark/CLI:    #1C1730  (deep violet-black — terminal backgrounds)
Text:        #2E2A42  (dark indigo — primary text)
Text muted:  #8b85a8  (soft purple-gray — secondary text, metadata)
Border:      #e8e5f0  (light purple-gray — card borders, dividers)
```

Status colors (universal, don't change):
```
Green:   #4ade80  (pass/success/running)
Red:     #f87171  (fail/error/danger)
Yellow:  #fbbf24  (timeout/warning)
```

### CLI banner gradient (top to bottom, 6 lines)
```python
BANNER_COLORS = [
    "#8B6CF0",  # light violet
    "#A78BF5",  # soft violet
    "#D4A0E0",  # pink-violet transition
    "#E8956B",  # warm transition
    "#E87B4A",  # orange accent
    "#E06030",  # deep orange
]
```

### Typography
- Headings / brand: `'Inter', -apple-system, sans-serif` — weight 600-700
- Body text: `'Inter', -apple-system, sans-serif` — weight 400-500
- Code / mono: `'JetBrains Mono', 'SF Mono', 'Cascadia Code', monospace`
- Use mono ONLY for actual code, timestamps, and run IDs — not for labels or UI text

### Design principles
- **Light mode** — warm off-white backgrounds, not dark
- **Generous whitespace** — let it breathe, no cramming
- **Card-based layout** — content in rounded cards with soft shadows
- **Soft shadows** — `0 1px 3px rgba(0,0,0,0.06)` not hard borders everywhere
- **Friendly empty states** — encouraging copy, not "No data found"
- **Rounded corners** — 10-12px on cards, 8px on buttons, 6px on inputs
- **Consistent with CLI** — same Dusk palette in Rich terminal output

---

## What to work on (priority order)

### 1. Redesign the web UI

The current UI is a dark-mode GitHub clone. It needs a complete redesign with the Dusk palette — light, warm, friendly. Rethink the layout, components, and overall feel. The UI lives in `src/ralphify/ui/`.

### 2. Update CLI colors

Make the CLI banner and terminal output use the Dusk palette so the CLI and web UI feel like the same product. The CLI lives in `src/ralphify/cli.py`.

### 3. Polish and consistency

Make sure every surface, color, and interaction feels intentional and cohesive across the whole product.

---

## Tech stack

You can use whatever frontend tech you think is best — including rewriting or replacing the current stack if that produces a better result. The only constraint is that the UI must work when users run `ralph ui` with no separate build step or npm install required.

---

## Verify before committing
- Run `ralph ui` and visually check the dashboard renders correctly
- Verify the CLI banner looks right: `ralph` (just run the bare command)
- Run `uv run pytest` — all tests must pass
- Check there are no console errors in the browser

---

## What good looks like

A user who opens the ralphify dashboard should:
1. Immediately understand what they're looking at — friendly, clear, not overwhelming
2. Be able to do what they came to do without friction
3. See at a glance what needs their attention
4. Feel like this tool was made with care
