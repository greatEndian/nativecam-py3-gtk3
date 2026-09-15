# Task: catch the random "Both directions + Regenerate" crash in the act

Read `/home/user/nativeCamDev/CLAUDE.md`, then
`/home/user/nativeCamDev/SONNET-LANES.md`. **Lane: GUI, in a worktree.**
Analysis range: **`analysis/290`–`299`**.

```bash
cd /home/user/nativeCamDev && python3 worker_worktree.py create crash-hunt
cd ~/nativecam-worktrees/crash-hunt
```

## What is known — `openPoints.md`, search *"BOTH DIRECTIONS" + REGENERATE*

- greatEndian, 2026-08-26: selecting **Both directions** and regenerating
  crashes, **intermittently**.
- **It is not generation.** testing_15_7 and testing_15_8 generate and run
  clean at direction 0, 1 and 2 — 444 and 458 moves, no interpreter error.
- So it is GUI-side, in NativeCAM or AXIS. **No traceback was ever captured**,
  and two GUI guesses were already wrong that week. A fix without a captured
  cause is not acceptable here.

The relevant code: the direction combos at `cfg/lathe/polyline.cfg:159`
(roughing) and `:354` (finishing), option 2 = Both directions;
`action_regen` (`ncam_app_actions.py:146`); `autorefresh_call` (`:980`); the
preview pane re-running the interpreter after a regenerate
(`ncam_preview_ui.py`); and the 3-level message raised at `polyline.cfg:601`
for a directional insert under Both directions — a message dialog opened from
inside a generation callback is a prime suspect, but it is a suspect, not a
finding.

## Method

1. **Instrument before hunting.** `PYTHONFAULTHANDLER=1`,
   `faulthandler.dump_traceback_later` for hangs, `sys.excepthook` and
   `GLib.log_set_handler` to a file, `G_DEBUG=fatal-criticals` for GTK
   criticals. `openPoints.md` records a 45-second hang found this way.
   Validate the instrument: force a known exception in a callback and prove it
   lands in your log.
2. **Reproduce in a loop, standalone, under Xvfb**, isolated from the main
   tree's `~/nativecam`:
   ```bash
   export HOME=$(mktemp -d)
   mkdir -p $HOME/nativecam/catalogs/lathe/projects
   cp /home/user/nativeCamDev/configs/sim/axis/ncam_demo/ncam/catalogs/lathe/projects/testing_15_{7,8}.xml \
      $HOME/nativecam/catalogs/lathe/projects/
   ```
   Drive it programmatically: load the project, set direction 0 → 2 → 1 → 2,
   regenerate, let the preview finish or interrupt it mid-run — hundreds of
   iterations, varying the timing, because it is random. Each interpreter run
   goes under `flock /tmp/ncam-rs274.lock`.
   `test_pane_layout.py` is an existing Xvfb harness to copy.
3. **If it reproduces:** the traceback or fault location is the finding. Fix
   the cause, then prove it: the same loop runs N iterations clean where it
   previously failed within M — state N and M.
4. **If it does not reproduce standalone** after a real effort (say how many
   iterations, which timings), the crash may need AXIS itself. Do **not**
   start LinuxCNC. Deliver instead a ready-to-paste command block for
   greatEndian that launches the sim with the instrumentation on and tees
   stderr and the fault log to `photo/crash-<date>.log`, plus the exact
   click sequence to try. That is a valid outcome.

## Deliverable

Commits on `worker/crash-hunt` (the instrumentation harness as a
`test_*.py` or `tools/` script, and the fix if found);
`analysis/29N-...md` with iterations run, timings tried, what was captured,
and what is still unknown; `openPoints.md` updated. Report every gate's exit
code.
