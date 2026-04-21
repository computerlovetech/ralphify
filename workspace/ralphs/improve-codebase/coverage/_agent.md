# `_agent.py` coverage

Valid at: 66d6c60

## Recent changes

- 66d6c60 — inlined the `remaining = deadline - time.monotonic()` local
  in `_read_agent_stream`'s per-iteration timeout calc.  The alias was
  read exactly once on the next line as `max(remaining, 0)`; collapsing
  to `max(deadline - time.monotonic(), 0)` matches the inline-alias
  style from e1ad87a / 497c028 / 52e0272 / ce487d3.  The adjacent
  comment was updated ("max(remaining, 0)" → "clamp to 0") since the
  name no longer exists.  Behavior preserved — the clamped timeout
  still reaches `line_q.get(timeout=...)`, so the non-blocking drain
  on an already-expired deadline still fires and deadline enforcement
  is unchanged.  Pinned by the streaming-path agent tests.  No other
  `remaining` locals remain in the module (grep confirmed).
- b24accf — inlined the `reader` thread handle in `_read_agent_stream`.
  The local served only to call `.start()`; the thread is never joined
  explicitly (termination is signalled through the queue's `None`
  sentinel produced by `_readline_pump`'s `finally` and through the
  daemon flag).  Collapsing into the fluent
  `threading.Thread(target=_readline_pump, args=(stdout, line_q),
  daemon=True).start()` drops an unused binding and matches the
  fire-and-forget intent.  Python keeps live threads reachable via
  `threading._active`, so no GC risk.  Side effects preserved: the
  reader still closes cleanly on `_close_pipes` (OSError in
  `readline`), and the main loop still relies on `line_q.get` for
  deadline enforcement.  Pinned by the full `tests/test_agent.py`
  suite (streaming-path coverage).  This is the same alias/handle-drop
  shape as e1ad87a / 497c028 / b19625e, specialised to a Thread —
  thread-return values aren't special, they're just another handle
  whose only use was `.start()`.
- e1ad87a — inlined the `binary = Path(cmd[0]).stem` local in
  `_supports_stream_json`.  The alias was read exactly once on the
  following line as `binary == CLAUDE_BINARY`.  Collapsing to
  `return Path(cmd[0]).stem == CLAUDE_BINARY` matches the already-inline
  sibling check in `_console_emitter.py:_is_claude_command`
  (`return Path(parts[0]).stem == CLAUDE_BINARY`).  Same Phase 4
  inline-alias shape as ce487d3 / 52e0272 / 497c028 / fc5e1cb.  Empty-cmd
  short-circuit (`if not cmd: return False`) preserved so
  `Path(cmd[0])` never gets indexed into an empty list.  Backlog note
  about consolidating `_is_claude_command` and `_supports_stream_json`
  across modules is unchanged — still deferred until a third caller
  appears.
- cf72fd9 — replaced the `parsed = None` sentinel in `_read_agent_stream`
  with a `try/except/else` block.  The old code set `parsed = None` in
  the JSON-decode-except branch solely so the next line's
  `if isinstance(parsed, dict):` would fall through; restructuring with
  `try: ... except: pass; else: if isinstance(...):` makes the "only
  forward when parsing succeeded" intent structural instead of encoded
  through a sentinel value.  The error path now skips the isinstance
  check entirely (dead work before), and the success path is unchanged.
  `parsed` is no longer bound when the except clause runs, which matches
  Python convention — the value was always meant to be ignored there.
  Pinned by `tests/test_agent.py::test_ignores_non_json_lines` and the
  broader stream-JSON coverage in that file.
- d8d5592 — gated the `"".join(...)` of `stream.stdout_lines` and
  `stderr_lines` at the tail of `_run_agent_streaming` on
  `log_dir is not None`.  The joined strings were only consumed by
  `_write_log` (which short-circuits when log_dir is None) and by the
  `captured_stdout` / `captured_stderr` AgentResult fields, both of
  which previously discarded the joined string with
  `... if log_dir is not None else None`.  Now matches the
  already-lazy `"".join(x) if x is not None else None` idiom in
  `_run_agent_blocking`'s tail, and the duplicated ternary on each
  AgentResult field collapses to a bare `stdout` / `stderr`.  Same
  observable behavior — pinned by `test_captured_output_set_when_logging`
  and `test_no_log_when_dir_not_set` in tests/test_agent.py.
- cb61477 — added `_call_safely(callback, *args)` helper next to the
  callback type aliases.  Replaces three copies of the
  `if cb is not None: try: cb(...); except Exception: pass` pattern
  (two in `_read_agent_stream`, one in `_pump_stream`) with single-line
  calls.  Behavior preserved — identical None guard, identical broad
  `Exception` suppression, identical argument-once semantics.

## Shape of the module

- Two execution paths: `_run_agent_streaming` (JSON line stream, used for
  `claude`) and `_run_agent_blocking` (subprocess.Popen with optional
  capture, used for all other agents).
- `execute_agent` is the single public entry point; selects mode via
  `_supports_stream_json(cmd)` (checks `Path(cmd[0]).stem == CLAUDE_BINARY`).
- Shared shutdown sequence is centralized in `_cleanup_agent`:
  1. `_ensure_process_dead` (SIGTERM → SIGKILL via `_try_graceful_group_kill`,
     then `proc.kill()`).
  2. `_close_pipes` (raw `os.close` on stdout/stderr fds to unblock readers).
  3. `_drain_readers` (bounded join on reader/writer threads).
  4. `_finalize_pipes` (Python-level `pipe.close()` for GC hygiene).
- Thread spawning uses `_start_writer_thread` / `_start_pump_thread` to
  centralize the `Thread(..., daemon=True); .start()` boilerplate.

## Verified live (grepped, confirmed used)

- `CLAUDE_BINARY` — public; imported by `_console_emitter.py` for display
  logic (see backlog note about consolidating `_is_claude_command` /
  `_supports_stream_json`; deferred until a third caller appears).
- `_STDOUT`, `_STDERR` — used in `_run_agent_streaming` /
  `_run_agent_blocking` stderr pump calls and inside `_read_agent_stream`.
- `_SIGTERM_GRACE_PERIOD`, `_THREAD_JOIN_TIMEOUT`, `_PROCESS_WAIT_TIMEOUT`
  — each referenced exactly once; constants kept near usage as the
  project convention prefers.
- `AgentResult`, `_StreamResult` — returned from streaming/blocking paths
  and consumed by `engine.py`.

## Potential future wins (not yet taken)

- `_run_agent_streaming` and `_run_agent_blocking` both finish with the
  same "`stdout = "".join(...) if … else None; stderr = "".join(...)
  if … else None; log_file = _write_log(...); return AgentResult(...)`"
  tail.  After d8d5592 the conditional-join idiom is now identical
  across both paths (gated on `log_dir is not None` for streaming,
  on `stdout_lines is not None` for blocking — but `stdout_lines` is
  itself `[] if log_dir is not None else None`, so the conditions are
  equivalent).  The intermediate state still differs (`stream.stdout_lines`
  tuple vs `stdout_lines` list|None), so extracting a shared helper
  would mostly move arguments around.  Revisit only if a third
  execution path appears.
- The two `if proc.stdin/stdout/stderr is None: raise RuntimeError(...)`
  guards just after `Popen` could use a single helper, but `subprocess`
  guarantees these are non-None when `PIPE` is passed — the guards exist
  mainly to narrow for the type checker, and a helper would make the
  narrow less explicit.  Leave as-is.
