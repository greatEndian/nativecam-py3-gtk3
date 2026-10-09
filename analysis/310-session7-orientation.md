# 310 — Session 7 orientation: crash-capture gap, branch merge check

2026-10-05, branch `liveTooling` at `5bddd32`. Read-only: nothing in `cfg/`,
`lib/` or any `.py` was touched.

## What was asked

greatEndian: *"findout where we finished and what we have opened... create
planning how to continue"*, the first request after a week's break.

## What was measured

- **Static checks:** `python3 cam_map.py` passes 9/9. `python3 openpoints_check.py`
  reports 0 high-confidence stale entries, 1 closure claim with no evidence
  (L3365, "So the remaining reading is COMPENSATION", which is a finding and
  is correctly still open), and 2 word-overlap hints (L2298, L3847).
- **The worker branches merge cleanly.** `git merge-tree --write-tree --name-only`
  printed only a tree OID, with no conflicted paths, for:
  - `liveTooling` + `worker/restart-rebuild` (`099be90`, 12 commits behind)
  - `liveTooling` + `worker/crash-hunt` (`f7e6dc6`, 11 commits behind)
  - `worker/restart-rebuild` + `worker/crash-hunt`

  All three branches edit `openPoints.md`, and git merges those edits
  automatically. (The `rc=0` printed alongside came from `head` in the pipe,
  not from `merge-tree`. Clean is read from the missing path list.)
- **`crash-hunt-relay`** (`01029f3`) is fully contained in `worker/crash-hunt`.
  **`worktree-agent-a4a1768ec665006c8`** is 465 commits behind and carries
  only two `.gitignore` commits. Both can be removed, but only once
  greatEndian says so.
- **No crash capture exists in the app.** Grepping `*.py`, `*.sh` and `*.ini`
  for `faulthandler`, `GDK_SYNCHRONIZE`, `set_error_handler` and `ulimit -c`
  finds one hit: a comment in `test_end_z.py`. NativeCAM never turns on
  `faulthandler` and never logs GLib/GDK warnings to a file.
- **Roughing compensation (polyline):** `lathe_level_pass.ngc` and
  `poly_lathe_mill.ngc` contain 0 `tip_comp` references. openPoints L2086
  records the polyline all-or-nothing rule as satisfied through Python tables
  instead. The CLAUDE.md line "lathe_level_pass.ngc — NOT compensated" is
  dated 2026-08-03 and is out of date on that point.
- `openPoints.md` header said `Last pushed: d6aae05`; actual was `5bddd32`.

## Root cause / reading

The crash greatEndian reports (the panel disappears, with no Python
traceback) has been chased by two harnesses that only watch Python-level
signals (session 6, `analysis/291`/`292`). A fault in GTK, GDK or Xlib would
kill the process before Python prints anything, and nothing writes it to
disk. So the evidence is lost unless someone is watching the launching
terminal at that moment.

## Why it was not caught earlier

Both harnesses were checked for whether they reproduce the crash. Neither was
checked for whether it could see this class of crash at all. Session 6 says
as much ("both harnesses built so far watch Python-level signals only") but
did not check what the app itself records.

## Proposed (not built, waiting on greatEndian's go)

Turn on `faulthandler` at NCam startup, writing to a log file, plus a
GLib/GDK log handler to the same file. Gate: a deliberately segfaulting child
process leaves a C-level traceback in the log, and the 46-project motion
fingerprint stays 46/46 identical.

## Still unknown

- Whether the vanishing panel is a process death at all, or the AXIS
  `container=1` frame dropping a live plug. If it is the second,
  `faulthandler` will log nothing and the X-level evidence is needed instead.
- Whether greatEndian's AXIS tests after session 6 (the torn-read fix, Z
  limits) passed. No report so far.
