# `_resolver.py` coverage

Valid at: 6227863

## Recent changes

- 6227863 — dropped `if not user_args: return _ARGS_RE.sub("", prompt)`
  early return in `resolve_args`.  `_ARGS_RE.sub` with the callable
  `lambda m: user_args.get(m.group(1), "")` already resolves every match
  to `""` when the dict is empty, so the fast path produced byte-for-byte
  identical output to the general path.  Test
  `test_empty_args_clears_placeholders` still covers the empty-dict
  behavior.

## Potential future wins (not yet taken)

- None obvious; the module is 80 lines and both `resolve_args` /
  `resolve_all` share the substitution shape but operate on different
  regexes (single-kind vs multi-kind), so extracting a helper would add
  indirection for two very short call sites.
