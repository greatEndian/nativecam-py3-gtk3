# 003 — AXIS froze on the preview's Stop button

2026-08-03. Reported by greatEndian. **Not solved** — this file records what was
ruled out and what was put in place to catch it next time.

## What was reported

*"I hit stop button in native CAM visu and axis freeze"* — AXIS had to be
killed. The log carried only the GladeVCP XID line and three copies of the
back-angle reachability warning; **no traceback**, which is what a hang looks
like: the process is alive and stuck, so there is nothing to raise.

Asked afterwards: the simulation's state at the moment of pressing Stop is not
remembered, and AXIS **had to be killed** rather than recovering.

## What was ruled out, by reading and by measuring

| suspect | finding |
|---|---|
| `_on_stop` doing work | cheap — `sim_t = 0` makes `_stock_field` return `None` at once, so no material rebuild |
| `_render_info` | with `sim_t = 0` it short-circuits to `info_at(None)`; no path walk |
| `set_value(0.0)` recursing | `_on_scrub` sets `sim_t` and redraws; no recursion |
| `rs274` hanging | runs on a **worker thread**, with `-b` (required, or the safety block waits on stdin) and a 120 s timeout |
| memory pressure from the canon | **measured**: `parse_program` on the live `ncam.ngc` is **1.76 s, 17 MB peak RSS**, 341 moves, 6.9 kB flat listing. Not it. |

So the stop path audits as cheap and nothing in it can block the main loop.
Reading found nothing, and the fault is not reproducible here — AXIS cannot run
in this environment, the same limitation that made `be094c2` a reasoned fix.

## What was found and fixed anyway

`_sim_tick` called `_stop_sim()` — which does `GLib.source_remove` — and *then*
returned `False`. Returning `False` is itself what removes the source, so the
source was taken away twice from inside its own dispatch. It normally only
logs, and it fires at the END of playback rather than on the Stop button, so it
is **not** presented as the cause. It is a real double-removal of a dispatching
source with no reason to keep it, so it is gone.

## What was put in place

`_trace()` in `ncam_preview_ui.py` — one flushed line to stderr naming each
coarse UI callback as it runs: `play`, `stop`, `stop done`, `refresh start`,
`done`. Deliberately **not** the per-frame tick, so it is a handful of lines a
session rather than a flood.

A hang gives up exactly one piece of evidence: whatever was already flushed.
The last `[ncam-preview]` line before the freeze names the callback that did not
return. `stop` with no `stop done` after it localises the fault to a few
statements; `refresh start` with no `done` points at the worker instead.

Silenced with `NCAM_NO_TRACE=1`. Verified both ways.

## Still unknown — this is the open part

The cause. The next occurrence should be reported with the last few
`[ncam-preview]` lines from the log, which is what turns this from a hunt into a
location.

Two hypotheses worth holding, neither tested:

- **The refresh flag wedges.** `refresh()` returns early when `self._busy` is
  set, and `_busy` is only cleared inside `_done`. If `_done` ever fails to
  run, the preview stops updating for good. That is a stuck preview rather than
  a frozen AXIS, so it does not explain a kill, but it is the same area.
- **`_done` touching a dead panel.** Its guard is
  `if self.area.get_window() is None and self._acc is not None` — the
  `and self._acc is not None` half means a panel that has gone away *before*
  the first successful parse falls through and touches widgets anyway.

## Verified

- trace fires on stop / play / refresh / done, and `NCAM_NO_TRACE=1` silences it
- `parse_program` timing and peak RSS, above
- flake8 clean; `test_preview_ui` and seven others green
