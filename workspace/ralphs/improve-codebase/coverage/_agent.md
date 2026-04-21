# `_agent.py` coverage

Valid at: cb61477

## Recent changes

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
  same "`stdout = "".join(...); stderr = "".join(...); log_file =
  _write_log(...); return AgentResult(...)`" tail, but the shape of the
  intermediate state differs (tuple vs list|None), so extracting would
  mostly move arguments around.  Revisit only if a third execution path
  appears.
- The two `if proc.stdin/stdout/stderr is None: raise RuntimeError(...)`
  guards just after `Popen` could use a single helper, but `subprocess`
  guarantees these are non-None when `PIPE` is passed — the guards exist
  mainly to narrow for the type checker, and a helper would make the
  narrow less explicit.  Leave as-is.
