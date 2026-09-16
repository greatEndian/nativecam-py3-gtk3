# 292 — "Both directions" + Regenerate crash hunt, re-run with a preview that actually parses motion

2026-09-16, worktree `worker/crash-hunt` (commits made from this agent's own
assigned worktree, `crash-hunt-relay` branch off `c3c678d` — see "Where this
ran" below). Continues `analysis/291`/`c3c678d` after `analysis/211` proved
that run's negative result untrustworthy.

## What was asked

`SONNET-PROMPT-CRASH-RERUN.md`: `c3c678d` reported "did not reproduce in 250
iterations", but every one of its 197 `rs274` preview runs exited `rc=1` with
**zero** parsed motion (`analysis/211`) — the harness never exported
`INI_FILE_NAME`, so `PreviewPane`'s ini stayed `None` and every parse died at
the first o-word. Task: (1) fix the harness (not `ncam_preview_ui.py`) so the
preview resolves a real ini, (2) prove it with a hard assertion — rc=0,
non-zero moves — on `testing_15_7`/`testing_15_8` BEFORE the long run, (3)
re-run the full 250-iteration hunt with the same randomised delay set, (4)
record before/after numbers and findings, (5) update `openPoints.md`.

## The fix

`tools/crash_hunt_both_dir.py`, `build_app()`: export
`INI_FILE_NAME=<scratch ini>` before `ncam.NCam()` is constructed —
`create_preview_pane()` (`ncam.py:3286`) runs synchronously inside
`NCam.__init__()` and reads `os.getenv('INI_FILE_NAME')` once, at
`ncam_preview_ui.py:1206`, into `PreviewPane.ini_path`, which is fixed for
the pane's lifetime. `self.ini_file` is confirmed dead code (never assigned
anywhere in this project, per `analysis/211`) — left alone per the task's
own instruction not to touch `ncam_preview_ui.py`'s resolution rule.

Added `prove_preview_parses()` — the acceptance gate — and `--gate-only` to
run it standalone: for each project, load it, call the real
`action_regen()`, wait for the preview's worker thread to land
(`wait_for_preview`, polling `PreviewPane._busy`), then assert every
`rs274` invocation exited `rc=0` and the parsed `Toolpath` has non-zero
moves and no `.error`. Wired into `run_hunt()` so the long loop is never
started if the gate fails. Added `install_preview_logging()` — a
non-blocking wrap of `PreviewPane._done` that logs every completion's move
count/error without changing the loop's timing (a *blocking* wait after
every iteration would remove the exact overlap — short delay interrupting a
still-running parse — the hunt exists to exercise).

## Two bugs in the new gate code itself, caught by running it, not by reading it

Per the "validate the instrument before trusting it" rule — both were
inside the gate's own new code, neither is a finding about the app:

1. **`run_gate_only()` never armed `auto_dismiss_dialogs`.** `NCam.__init__()`
   opens its own synchronous `gtk.MessageDialog.run()` — `create_M_file()`
   (`ncam.py:656`), "LinuxCNC needs to be restarted now", fired on every
   fresh `NCAM_DIR` — and with nothing answering it the gate hung forever.
   Caught by the 25 s watchdog dumping the same stack
   (`mess_dlg`→`NCam.__init__`) repeatedly. Fixed: arm the timer before
   `build_app()`, same as `run_hunt()` already did.
2. **`prove_preview_parses()` reset `preview_pane.toolpath = None` before
   regenerating.** `PreviewPane.__init__` seeds `self.toolpath` with a real
   `ncam_preview.Toolpath()` sentinel, never `None`
   (`ncam_preview_ui.py:113`). With it forced to `None`, `refresh()` itself
   threw `AttributeError: 'NoneType' object has no attribute 'moves'` before
   the worker thread ever started, so `rs274` never ran at all
   (`rs274_rcs=[]`) and the gate correctly reported FAIL — for a reason that
   had nothing to do with `INI_FILE_NAME`. Fixed by removing the reset;
   `PreviewPane._busy` alone is the correct, already-used completion signal.
3. **60 s wasn't enough headroom under real machine contention.** The first
   live gate run inside `run_hunt()` timed out on `testing_15_7` at 60 s
   while its `rs274` call was still running — `fuser
   /tmp/ncam-rs274.lock` showed a concurrent session's
   `test_motion_fingerprint.py --write ...` (GEOMETRY lane) holding the
   shared lock, exactly the false-FAIL shape `SONNET-LANES.md` documents
   (`analysis/134`, `analysis/230`). That run finished clean at 112.7 s
   (rc=0, 472 moves) — real work, just queued. Widened the wait to 600 s so
   the gate outwaits contention instead of misreading it.

## Gate result — the required BEFORE/AFTER

**BEFORE** (`analysis/211`, measured on a freshly generated `testing_15_7`):

```
rs274 -b -g <ngc> <canon>                    (cwd = repo root, no -i/-t)
    rc=1,   0 motion lines
    stderr: EOF in file:… seeking o-word: o<facing> from line: 392
```

**AFTER** (`--gate-only`, uncontended, `/tmp/crash_hunt_gate_relay3.log`):

```
testing_15_7.xml: rs274 -b -g -i <ini> -v <var> -t <tbl> <ngc> <canon>
    rc=0, 456 moves   -> PASS
testing_15_8.xml: rs274 -b -g -i <ini> -v <var> -t <tbl> <ngc> <canon>
    rc=0, 472 moves   -> PASS
```

Same gate, run live inside `run_hunt()` immediately before the 250-iteration
loop (`/tmp/crash_hunt_main_relay2.log`, after the 600 s widen):

```
testing_15_7.xml: rc=0, 456 moves -> PASS
testing_15_8.xml: rc=0, 472 moves -> PASS
```

Identical move counts both times (same seed, same projects) — deterministic,
as expected. **This is the acceptance gate the task asked for, and it PASSED
before the long run started.**

## Main run — 250 iterations, same delay set, seed 42

`python3 tools/crash_hunt_both_dir.py --iterations 250 --seed 42
--max-seconds 5400 --log /tmp/crash_hunt_main_relay2.log`, under `xvfb-run
-a`. Same `DELAYS_MS = [0, 5, 15, 40, 100, 250, 600, 1200, 3000]` ms and
`random.Random(seed=42)` as `c3c678d`/`analysis/291`, so the exact same
sequence of delays and `#param_dir`/`#param_f_dir` 0→2→1→2 choices was
replayed — the only thing that changed is the preview now actually parses.

```
GATE RESULT: PASS (both projects, see above)
HUNT DONE: iterations=250 regen_ok=250 regen_fail=0 elapsed=1594.9s
           preview_parsed_ok=163 preview_parsed_fail=2
```

- **250/250 iterations completed, `regen_fail=0`** — same as `c3c678d`, but
  this time meaningful: `action_regen()` really did drive the preview through
  a real interpreter parse on almost every call.
- **165/250 regenerate calls produced a landed preview result** (163 ok + 2
  failed, see below). The other 85 were coalesced by `PreviewPane.refresh()`'s
  own "a second Regenerate while one is still parsing: keep the newest
  request and drop the rest" rule (`ncam_preview_ui.py:505-511`) — expected
  under short delays, not a bug, and exactly the overlap the task asked the
  delay set to produce.
- **Zero `MAIN-THREAD EXCEPTION` / `THREAD EXCEPTION` lines** (`grep -c
  EXCEPTION` = 0) across the whole 2789-line log.
- **Zero `GLIB-LOG` lines** — no GTK/GLib critical, error or warning on any
  of the 9 watched domains, across the whole run.
- **674 dialogs auto-dismissed** (673× the "Lathe Polyline … cuts the other
  way / directional insert" warning — msg_inv msgid 3, the named suspect —
  plus 1× "LinuxCNC needs to be restarted now" at startup), every one
  answered cleanly including while overlapping an in-flight worker thread.
- **68 `Timeout (0:00:25)!` watchdog dumps** — confirmed benign, same
  mechanism as `c3c678d`: `faulthandler.dump_traceback_later(25,
  repeat=True)` armed once, 1710 s (gate + hunt) ÷ 25 ≈ 68.4. 48 of the 68
  happened to land inside `PreviewPane._on_draw` mid-frame (normal — GTK
  redraws constantly during animation/playback), not a hang.
- Process exited **0**.

### A real finding: 2 preview parses failed on a torn read of `ncam.ngc` — not a crash

Both failures, identical error:

```
PREVIEW DONE: moves=486 error='File ended with no percent sign (%) or
  program end (M2) | o<poly_lathe_mill> endsub' ok=False
```

Traced with the log's own timestamps (first occurrence): an `rs274` run
started at `t=243.443s` against `.../ncam/scripts/ncam.ngc`, and **while it
was still running**, four more `set_value` + `action_regen()` cycles fired
(steps 19–22, `t=250.1` to `t=261.6s`) — each calling `write_ngc()`
(`ncam_app_actions.py:924-926`):

```python
fname = os.path.join(ncam.NGC_DIR, GENERATED_FILE)
with open(fname, "w") as f:
    f.write(self.to_gcode())
```

`open(fname, "w")` truncates the file **in place** at open time, non-atomic
(no temp-file-plus-rename). With a background `rs274` thread reading that
exact path directly while a later iteration's `write_ngc()` truncates and
rewrites it underneath, `rs274` can read a torn file — old tail gone, new
content only partially written — and lands exactly on the observed failure:
EOF reached mid `o<poly_lathe_mill>` subroutine, no closing `M2`/`%`. The
`rs274` process itself exited `rc=1` at `t=261.944s`; `_done()` landed the
result ~7 s later via `idle_add` (main-thread backlog under this run's own
load, not a bug).

**This is not the reported crash** — no traceback, no GLib critical, the app
handled it exactly as `ncam_preview.py:261`'s docstring says it should
(`tp.error` set, `tp.moves` kept as whatever parsed before the truncation,
status line shows `Preview: <error>`). It is a genuine, previously-invisible
race between `write_ngc()`'s non-atomic write and the preview's own direct
read of the live path, surfaced *only* now that the preview actually parses
— `c3c678d` could never have seen this, because every one of its parses was
already failing identically before any race could matter. Recorded as its
own new open point below; **not fixed here** — out of this task's scope
(the task's own instruction is "do not fix on a guess", and this task's
target is the reported GUI crash, not this race).

## Result: still does NOT reproduce — now a meaningful negative

Zero Python exceptions, zero GLib criticals/warnings, `regen_fail=0`, exit
code 0, across 250 real edit→regenerate cycles where the preview genuinely
parsed motion on 163/165 landed results (and degraded gracefully, not
crashed, on the 2 that hit the torn-read race). Unlike `c3c678d`, this run
actually exercised the suspected window — the preview worker thread
interleaving with the next edit — for the great majority of its iterations,
including the exact overlap that produced the torn-read race above. It still
did not produce anything resembling the reported crash.

The three gaps `analysis/291` already listed (Auto-refresh's
`linuxcnc.command()` path, AXIS's real Tk/GTK socket embedding, the
debounced autorefresh cancel/rearm timer) are unchanged by this run — none of
them were exercised here either, same as before.

## Where this ran

This agent was assigned its own fresh worktree
(`.claude/worktrees/agent-a4a1768ec665006c8`) rather than
`~/nativecam-worktrees/crash-hunt`, and the sandbox refuses any git operation
(`cd`, `-C`, `--git-dir`) that targets a different worktree's path — even a
read-only `git -C ... status`. Since all worktrees of this repo share one
`.git` object database, `worker/crash-hunt` and `c3c678d` were still visible
from here (`git cat-file -t c3c678d`, `git log --all`), so the work was done
on a local branch `crash-hunt-relay` created with `git checkout -b
crash-hunt-relay c3c678d` inside this agent's own worktree — same starting
point, same file content, just a different branch name because
`worker/crash-hunt` itself cannot be checked out twice at once. These
commits need to be fast-forwarded or cherry-picked onto `worker/crash-hunt`
by whoever can reach both worktrees; the report to the coordinator states
this plainly. All file paths logged above (`/tmp/crash_hunt_g_g10tgw/...`,
tracebacks under `.../agent-a4a1768ec665006c8/...`) are artifacts of running
from this worktree and are not meaningful beyond this run.

## What is still unknown

Unchanged from `analysis/291`: whether the crash needs a live
`linuxcnc.command()` state transition (Auto-refresh on), AXIS's real Tk/GTK
socket embedding, or the debounced autorefresh timer's cancel/rearm race —
none of which a standalone harness without LinuxCNC running can reach. See
the AXIS-repro handoff in `openPoints.md`.

## Deliverable given this result

Same outcome class as `c3c678d`: did not reproduce, now backed by a preview
that actually parsed real motion. The AXIS-repro handoff already in
`openPoints.md` is kept (the click sequence and instrumented launch command
are unchanged — LinuxCNC was never started by this agent, per the task's
explicit boundary), with this run's numbers added as a second, stronger
data point, and a new open point added for the torn-`ncam.ngc`-read race.
