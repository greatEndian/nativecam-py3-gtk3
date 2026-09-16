# Task: re-run the "Both directions" crash hunt with a preview that actually parses motion

You are working in `/home/user/nativeCamDev`, branch `liveTooling`.
Read `CLAUDE.md` first, then `/home/user/nativeCamDev/SONNET-LANES.md`.
**Lane: GUI, in the existing `crash-hunt` worktree.** Analysis range:
**`analysis/292`–`299`** (291 is taken).

```bash
cd ~/nativecam-worktrees/crash-hunt     # already exists, branch worker/crash-hunt
git log --oneline -1                    # expect c3c678d
```

If that worktree is gone: `cd /home/user/nativeCamDev && python3
worker_worktree.py create crash-hunt2` and cherry-pick `c3c678d`.

## Why you are here

`c3c678d` hunted the intermittent crash greatEndian reports — selecting
**Both directions** and regenerating — and reported *"did not reproduce in 250
iterations"*. **That negative result is not trustworthy, and the reason is
measured, not suspected** (`analysis/211`):

Every one of its **197** `rs274` runs exited `rc=1` having produced **zero**
motion. The preview parsed nothing, all 250 times.

The chain, each link confirmed:

- `ncam_preview_ui.py:1206` — `ini = getattr(self, 'ini_file', None) or
  os.getenv('INI_FILE_NAME')`. **Nothing in this project ever assigns
  `ini_file`**, so the ini comes only from the environment.
- `/usr/bin/linuxcnc:802` exports `INI_FILE_NAME`, so a panel embedded in AXIS
  is fine. A harness that passes `-i` on `sys.argv` instead is **not**.
- With no ini, `ncam_preview.py:215` sets `cwd = dirname(ini_path or path)` —
  the `.ngc`'s own directory — and omits `-t`, which its own comment at `:201`
  calls "NOT optional". The ini's relative `SUBROUTINE_PATH` cannot resolve
  from there.
- Measured on a freshly generated `testing_15_7` (generation itself is healthy,
  `rc=0`, 2270 lines):

```
rs274 -b -g <ngc> <canon>                   (cwd = repo root, no -i/-t)
    rc=1,   0 motion lines
    stderr: EOF in file:… seeking o-word: o<facing> from line: 392

rs274 -b -g -i lathe-mm.ini <ngc> <canon>   (cwd = the ini's directory)
    rc=0, 457 motion lines
```

So the hunt genuinely exercised edit → `action_regen()` → the `msg_inv`
"directional insert" dialog (which fires and is auto-dismissed), but **never a
preview that parsed a toolpath** — and the suspected crash is in the preview
worker thread interleaving with the next edit. The most likely window was never
covered.

## What to do

1. **Make the preview resolve a real ini in the harness.** Simplest is to
   export `INI_FILE_NAME` (pointing at the harness's own scratch ini) before
   the pane is built. Do NOT change `ncam_preview_ui.py`'s resolution rule as
   part of this task — whether the app should set `ini_file` from `-i` is a
   separate open point and greatEndian's call.
2. **Prove the preview now parses motion BEFORE the long run.** This is the
   acceptance gate for the fix, and the whole point of the task:
   - every `rs274` invocation the harness logs exits **rc=0**, and
   - a parsed `Toolpath` has **non-zero moves** (the old harness asserted
     nothing about moves — `regen_ok=250` only counted Python exceptions
     escaping `action_regen()`). Add that assertion permanently.
   State the move count you observe for `testing_15_7` and `testing_15_8`.
3. **Then re-run the hunt**, at least the same 250 iterations and the same
   randomised delays (0/5/15/40/100/250/600/1200/3000 ms), so short delays
   interrupt a still-running preview parse and long ones let it finish.
4. **Report what you find.** A reproduction with a captured traceback is the
   goal; a *clean* run is now a meaningful negative and worth recording as one.
   Do not fix anything on a guess — `openPoints.md` records that two GUI
   guesses were already wrong on this bug.
5. If it still does not reproduce, deliver the AXIS-repro handoff: a
   ready-to-paste command block for greatEndian with the instrumentation on,
   teeing stderr and the fault log, plus the exact click sequence. **Do not
   start LinuxCNC yourself.**

## Traps, each of which has already cost this project a session

- **The 44 `Timeout (0:00:25)!` entries in the old log are NOT hangs.**
  `faulthandler.dump_traceback_later(25, repeat=True)` is armed once and never
  cancelled; 1112 s ÷ 25 ≈ 44.5. Do not chase them.
- **A harness's "scratch" copy of `cfg/` is not scratch.** `analysis/212`:
  `update_user_tree` (`ncam_app_actions.py:115-143`) DELETES a real
  `NCAM_DIR/{cfg,lib,graphics}` and replaces it with a symlink to
  `SYS_DIR/<dir>` — the tracked tree — during `NCam()` startup. Any copy made
  before startup is destroyed and re-pointed at the repo. Check your harness
  for this shape.
- **`run_tests.py` now fails any driver that modifies a tracked file**
  (`332ffd1`). Your run must leave `git status` clean.
- **Machine contention produces false FAILs** (`analysis/134`, `230`). Every
  `rs274` run goes under `flock /tmp/ncam-rs274.lock`. The existing harness
  already wraps only the `subprocess.run()` call, which is the right shape —
  keep it, so a long loop does not starve the geometry lane.
- Validate any new instrument against a number you already know before
  trusting it. The old harness's self-test (forced main-thread exception,
  thread exception, GLib critical) is sound — keep it and extend it.

## Deliverable

Commits on `worker/crash-hunt`; `analysis/29N-...md` with the before/after
`rs274` exit codes and move counts, iterations run, delays tried, and what was
captured or ruled out; `openPoints.md` updated — the "BOTH DIRECTIONS" entry
and the `analysis/211` qualification both need to reflect the new result.
Report every gate's exit code. **Do not push and do not merge** — greatEndian
merges.
