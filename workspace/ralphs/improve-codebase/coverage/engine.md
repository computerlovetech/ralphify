# `engine.py` coverage

Valid at: c5ce11d

## Recent changes

- c5ce11d — inlined the `reason = state.status.reason` local in
  `run_loop`.  The alias was read exactly once on the next line as the
  `reason=` kwarg to `RunStoppedData(...)`.  Inlined to
  `reason=state.status.reason` to match the chained-read style elsewhere
  (e.g. `_IterationPanel._apply_assistant`'s `raw.get("message", {}).get("usage")`
  after 52e0272).  Same Phase 4 inline-alias shape as ce487d3 (`text`),
  52e0272 (`msg`), 497c028 (`agent`), fc5e1cb (`total_in`).
  Safe: the immediately-preceding `if state.status == RunStatus.RUNNING:
  state.status = RunStatus.COMPLETED` normalizes the status to a terminal
  value, so `RunStatus.reason`'s ValueError guard (non-terminal) cannot
  fire here.

## Structure notes

`run_loop` is the main loop orchestrator.  Its control-flow helpers
(`_handle_control_signals`, `_wait_for_resume`, `_run_iteration`,
`_delay_if_needed`) are each short and single-purpose.  `_run_iteration`
splits into `_run_commands` → `_assemble_prompt` → `_run_agent_phase`.
`_run_agent_phase` is the longest at ~80 lines but its branches map 1:1
to the agent outcome tri-state (timed_out / success / failure) — no
obvious extraction candidate without inventing synthetic abstractions.

## Potential future wins (not yet taken)

- None spotted.  The locals that survive in `_run_agent_phase`
  (`duration`, `event_type`, `state_detail`, `ended_data`) all have
  multiple uses and good names.  `_run_commands`'s `output` is mutated
  before use.  `_run_iteration`'s `iteration` alias is used 4 times.
