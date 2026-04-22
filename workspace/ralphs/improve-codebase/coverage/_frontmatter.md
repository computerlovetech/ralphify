# `_frontmatter.py` coverage

Valid at: a6f4c47

## Recent changes

- a6f4c47 — dropped the `if text.startswith(_UTF8_BOM):` guard in
  `parse_frontmatter` before the `text = text.removeprefix(_UTF8_BOM)`
  call.  Python's `str.removeprefix` is already a no-op (returns the
  same string object) when the prefix is absent, so the guard was
  purely decorative dead code.  Behavior preserved:
  - BOM-prefixed input still gets stripped (pinned by
    `test_utf8_bom_does_not_break_frontmatter` in
    `tests/test_frontmatter.py`).
  - Non-BOM input is passed through unchanged (exercised by every
    other parse test in the file).
  - The CPython implementation returns the same object identity when
    no prefix match occurs, so there's no allocation overhead either.

## Shape of the module

- `parse_frontmatter(text)` — public entry point.  Strips optional
  UTF-8 BOM, splits on `---` delimiters via `_extract_frontmatter_block`,
  runs `yaml.safe_load`, strips HTML comments from the body with
  `_strip_html_comments`, returns `(dict, body)`.
- `serialize_frontmatter(frontmatter, body)` — inverse; emits
  `---`-delimited blocks only when the frontmatter is non-empty *or*
  the body would otherwise be mis-parsed as frontmatter.
- Constants: `RALPH_MARKER`, `FIELD_*`, `CMD_FIELD_*`, `NAME_RE`,
  `VALID_NAME_CHARS_MSG`.  All imported by `cli.py` and
  `_resolver.py`; each one is reused across modules so centralisation
  is justified.

## Verified live (grepped, confirmed used)

- `_FRONTMATTER_DELIMITER` — used 4× in `serialize_frontmatter` (plus
  2× in `_extract_frontmatter_block`).
- `_FENCE_OR_COMMENT_RE` — used in `_strip_html_comments`.
- `_UTF8_BOM` — used in `parse_frontmatter` (BOM strip).

## Potential future wins (not yet taken)

- `_extract_frontmatter_block` splits `text` on `"\n"` up front, then
  re-joins slices for the body — the body slice is re-joined even when
  the input is tiny.  Could stream with `str.find` + `str.index` to
  avoid the list allocation, but this function runs once per
  iteration and the input is ~1 KB in practice; not worth the churn.
- The `serialize_frontmatter` `needs_delimiters` expression uses
  `body.lstrip().startswith(...)` which allocates a new stripped
  string just to check a prefix.  Could collapse via
  `re.match(r"\s*---", body)` but the current form reads cleanly;
  revisit only if this becomes hot.
