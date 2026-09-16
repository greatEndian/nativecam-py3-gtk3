# 291 - "Both directions" + Regenerate crash hunt

## What was asked

`openPoints.md`, "BOTH DIRECTIONS" + REGENERATE CRASHES, AND IT IS RANDOM:
greatEndian, 2026-08-26, confirmed intermittent. Not a generation fault -
testing_15_7 and testing_15_8 both generate and run clean headless at
`param_dir` 0/1/2 (444 and 458 moves, no interpreter error). So it is
GUI-side, in NativeCAM or AXIS, and no Python traceback has ever been
captured. Task: instrument, validate the instrument, reproduce standalone
under Xvfb in a loop, and either fix a captured cause or hand back a ready
AXIS-repro command block. Do NOT start LinuxCNC.

## Method

Built the harness at `tools/crash_hunt_both_dir.py` (worktree
`worker/crash-hunt`). It builds a real `ncam.NCam()` panel - the same object
AXIS embeds - inside a plain `Gtk.Window`, shown (not just constructed) under
Xvfb, because `msg_inv`/`mess_dlg` both skip their dialog entirely with no
visible toplevel (`gtk.Window.list_toplevels()` empty), and "a message dialog
opened from inside a generation callback" is the prime suspect named in the
task prompt - a headless run with no window would silently walk past it.

Drives the real edited-cell tail: `Parameter.set_value(new_val, feature)`
then `NCam.refresh_views()`/`.action()` - exactly what
`ncam_treeview.py:edited()` does after a combo edit - for `#param_dir` and
`#param_f_dir` on the polyline feature in `testing_15_7.xml` and
`testing_15_8.xml`, cycling 0 -> 2 -> 1 -> 2 per the task prompt, each change
followed by a real `action_regen()` (never touches `linuxcnc.command()`).
Runs inside one real `Gtk.main()` so the preview's worker thread +
`GLib.idle_add(self._done, ...)` genuinely interleaves with the next edit;
timing is varied by chaining `GLib.timeout_add` with a randomised delay
(0/5/15/40/100/250/600/1200/3000 ms) after each regenerate - short delays
interrupt a still-running preview parse, long ones let it finish, both asked
for by the task prompt. A persistent `GLib.timeout_add(25, ...)` auto-answers
OK to any `Gtk.Dialog` that appears (msg_inv's and mess_dlg's dialogs are
both `Gtk.MessageDialog`), including while a NESTED `dlg.run()` main loop from
an earlier `msg_inv` is still on the stack - this is what lets the loop run
unattended for hundreds of iterations instead of hanging on the first
warning.

**Isolation.** Runs against a `tempfile.mkdtemp()` scratch copy of this
worktree's own `configs/sim/axis/ncam_demo` (`-i <scratch>/lathe-mm.ini`),
which resolves `NCAM_DIR` from the ini path - the main tree's `~/nativecam`
is never touched (verified: no writes outside `/tmp` in the run). This is
`test_all_projects.py`'s own proven isolation pattern, used instead of the
task prompt's literal `HOME=$(mktemp -d)` + `~/nativecam` recipe, because
that recipe is for the true standalone `./ncam.py` entry point (no `-i`),
which needs a fully bootstrapped `~/nativecam` symlink farm the `-i` path
does not; the `-i` route gives the same isolation guarantee with less setup.
`testing_15_7.xml`/`testing_15_8.xml` and the (gitignored) `lathe_mm.tbl` /
`lathe.tbl` tool tables are read-only-copied in from the main tree per
iteration's `build_app()` - reads only, no writes back.

**rs274 lock.** `ncam_preview.subprocess.run` is monkeypatched so only calls
whose `cmd[0] == 'rs274'` are wrapped in
`flock('/tmp/ncam-rs274.lock')` - around the single `subprocess.run()` call,
not the whole harness, so a hundreds-of-iterations loop does not starve the
GEOMETRY lane for the run's whole duration.

## Instrument validation (BEFORE the hunt - CLAUDE.md: "validate the
instrument before trusting it")

`tools/crash_hunt_both_dir.py --selftest`, log `/tmp/crash_selftest.log`:

- `sys.excepthook` witness: forced `RuntimeError('SELFTEST-MAIN-EXC')` inside
  a `GLib.idle_add` callback. **PASS** - full traceback landed in the log.
- `threading.excepthook` witness: forced `RuntimeError('SELFTEST-THREAD-EXC')`
  inside a plain `threading.Thread`. **PASS** - full traceback landed in the
  log.
- `GLib.log_set_handler` witness: a destroyed-`Gtk.Button().set_label()` call
  did NOT emit a GLib critical on this pygobject/GTK build (it silently
  no-ops rather than asserting `GTK_IS_BUTTON`) - that path proved nothing
  either way, so it was replaced with a direct `ctypes` call into
  `libglib-2.0.so`'s `g_log(domain, G_LOG_LEVEL_CRITICAL, "SELFTEST-GLIB-CRITICAL")`.
  **PASS** - the handler fired, with a Python stack attached showing the call
  site.

All three: `INSTRUMENT VALIDATION: PASS`
(`/tmp/crash_selftest.log`, `/home/user/nativecam-worktrees/crash-hunt/tools/crash_hunt_both_dir.py:selftest`).

## Smoke tests (mechanics, before committing to a long run)

1. First smoke run had NO tool table in the scratch copy (`lathe_mm.tbl` is
   gitignored, absent from a fresh worktree) - `Tools.get_tool_nose_radius()`
   resolved to 0 and every step only hit the "needs a tool nose radius"
   dialog (msgid 1), never the direction-specific one. Fixed by copying
   `lathe_mm.tbl`/`lathe.tbl` read-only from the main tree in `build_app()`.
2. Second smoke run (10 iterations, `/tmp/crash_smoke2.log`) confirmed T2
   (`dnum=2` in both projects' `tool-change` feature) resolves to its real
   table entry - `D0.8 Q2`, a **directional** insert - and on step 7, where
   both `#param_dir` and `#param_f_dir` were set to 2 (Both directions), the
   exact suspect dialog fired:
   > "Both directions alternates the cutting direction every pass, and this
   > tool can only cut one way. Orientation 2 is a directional insert..."
   Auto-dismissed cleanly, no crash, rs274 continued. This confirms the
   harness genuinely reaches the named suspect path (msg_inv msgid 3,
   `polyline.cfg` ~line 601, opened synchronously from inside
   `write_ngc()`/`validate()`), not just a generic regenerate loop.
3. ~4.2 s/iteration observed (rs274 run + dialog handling on this demo
   project size), which sets the iteration budget for the main run.

## Main run - RESULT: did not reproduce

`tools/crash_hunt_both_dir.py --iterations 250 --seed 42 --max-seconds 1500
--log /tmp/crash_hunt_main.log`, under `xvfb-run -a`, in the background.

```
HUNT DONE: iterations=250 regen_ok=250 regen_fail=0 elapsed=1112.3s
EXITCODE=0
```

- **250/250 iterations completed clean.** Every `action_regen()` call
  returned normally (`regen_fail=0` - no Python exception ever escaped it).
- **Zero `MAIN-THREAD EXCEPTION` / `THREAD EXCEPTION` lines** in the 2006-line
  log (`grep -c EXCEPTION` = 0) - no uncaught exception on the GTK thread, in
  `_worker`'s background thread, or anywhere `GLib.idle_add`/`timeout_add`
  landed a callback.
- **Zero `GLIB-LOG` lines** (`grep -c GLIB-LOG` = 0) - no GTK/GLib
  critical, error or warning fired on any of the 9 watched domains
  (`Gtk`, `Gdk`, `GLib`, `GLib-GObject`, `Pango`, `GdkPixbuf`, `cairo`,
  `PyGObject`, and the unnamed default domain) across the whole run.
- The suspect dialog (`msg_inv` msgid 3, "Both directions... directional
  insert") fired repeatedly across the run (alongside the front/back-angle
  warnings that fire on every generation of these two profiles - 402
  `AUTO-DISMISS` lines total) and was auto-dismissed every time with no ill
  effect, including while overlapping with a still-in-flight worker thread
  from the previous iteration (confirmed by timestamps: `rs274 run start`
  for iteration N logged a few ms before the next `step N+1` line, at the
  0/5/15 ms delay settings).
- Coverage: both `testing_15_7.xml` and `testing_15_8.xml` (switched every 25
  steps, 5 switches each project over the run), both `#param_dir`
  (roughing) and `#param_f_dir` (finishing) driven through the prompt's
  0 -> 2 -> 1 -> 2 sequence individually and together, 9 delay values from
  0 ms (interrupt while the previous preview's rs274/worker thread is still
  running) to 3000 ms (let it fully settle) chosen per step by
  `random.Random(seed=42)`.
- ~4.4-5 s/iteration (rs274 run + dialog round-trip on this demo project
  size), 1112 s total - a real, quantified effort, not a token pass.

## What is still unknown / not covered by this standalone attempt

Three real gaps between this harness and the reported environment, listed so
the next pass (or greatEndian's own AXIS run) starts from them rather than
re-discovering them:

1. **`action_regen()` never calls `linuxcnc.command()`, by design** (see its
   own docstring) - this harness deliberately used it because starting
   LinuxCNC was out of scope. `autorefresh_call()` - what every tree edit
   arms via a debounced `GLib.timeout_add(self.pref.timeout_value, ...)` in
   `update_do_btns` - DOES call `send_to_linuxcnc()` ->
   `linuxcnc.command()`/`linuxcnc.stat()` when Auto-refresh is on. If the
   real crash needs that path (a live task/interpreter state transition, not
   just NativeCAM's own preview), no standalone attempt without a running
   LinuxCNC can reach it. This harness left Auto-refresh OFF throughout.
2. **The panel is shown in a bare `Gtk.Window`, not AXIS's actual embedding.**
   AXIS reparents the NativeCAM panel through a Tk/GTK socket bridge; a bare
   toplevel is not that, and a reparenting-specific race (focus/grab
   handoff between two different toolkits' event loops) cannot show up here
   by construction.
3. **The debounced autorefresh timer's cancel/rearm dance was not
   exercised.** `action()` -> `update_do_btns()` calls
   `self._cancel_autorefresh_timer()` then rearms a fresh
   `GLib.timeout_add` on every single param edit *when Auto-refresh is on*.
   Two rapid combo edits (e.g. dragging/scrolling through Front-to-back ->
   Both directions in the real widget, which may emit several intermediate
   `edited` signals where this harness makes one `set_value` call) could
   race the cancel against an already-fired timer id in a way a single
   explicit `set_value` + `action_regen()` never will.

None of these are "the answer" - they are the honest list of what a clean
250-iteration standalone result does and does not rule out.

## Deliverable given this result

Per the task's own stated acceptance criteria ("If it does NOT reproduce
standalone after a real, quantified effort... deliver instead a ready-to-paste
command block"): this is the AXIS-repro handoff outcome. LinuxCNC was NOT
started by this agent, at any point. The command block and click sequence are
appended to `openPoints.md` under the existing "BOTH DIRECTIONS" open point,
and repeated in the handback report to the coordinator.

## Artifacts

- Harness: `tools/crash_hunt_both_dir.py` (this worktree, branch
  `worker/crash-hunt`) - reusable for a follow-up run (e.g. with Auto-refresh
  on, once that gap above is wired in).
- Self-test log: `/tmp/crash_selftest.log` (not committed - `/tmp`,
  ephemeral, reproducible by rerunning `--selftest`).
- Main run log: `/tmp/crash_hunt_main.log`, 2006 lines (not committed -
  `/tmp`, ephemeral; the counts and greps above are the durable record).
