# Task: the Z limits are only half validated

You are working in `/home/user/nativeCamDev`, branch `liveTooling`.
Read `CLAUDE.md` first. Analysis range: **`analysis/250`–`259`**.

## Run alone

This touches generation. Do not start while another geometry session is
active, and do not run `rs274` concurrently with one.

**Lane: GEOMETRY, main tree — queued AFTER `SONNET-PROMPT-NEG-STOCK.md`.**
Read `/home/user/nativeCamDev/SONNET-LANES.md` first. Start only once
`git log` shows the negative-stock guard committed. Every
`rs274`/generation/sweep/fingerprint command runs as
`flock /tmp/ncam-rs274.lock <command>`.

## The gap, as recorded in `openPoints.md`

> The crossed case is refused. NOT checked: **a limit that falls outside the
> profile entirely** (it silently does nothing), and **limits that leave too
> little to machine**. Both need the resolved profile, which the block cannot
> have — they belong in the `[AFTER]` block or in Python at generation time.

Read the entry in full before starting.

## Why this is a Python-first task

`CLAUDE.md`'s standing rule: **solve it in Python at generation time.** The
entry already says where this belongs — a `[VALIDATION]` block cannot see
resolved geometry, so the check has to run where the profile exists. The
pattern to copy is `lathe_sections.py` itself: GTK-free, imports nothing from
`ncam`, called from a `.cfg` `[AFTER]` block via
`<exec>print(...)</exec>`, unit-testable with plain `python3`.

Prefer putting new validation in a **new module** over growing
`lathe_sections.py` — it keeps you off the single-writer file and makes the
check testable on its own.

## What to deliver

1. **A limit outside the profile entirely** — today it silently does nothing.
   Detect it and say so, naming the limit and the profile's actual Z range.
2. **Limits that leave too little to machine** — define "too little" from the
   geometry (depth of cut, nose radius) rather than a magic number, and
   justify the threshold you choose in the analysis file.

Both messages must be legible to an operator: the value they typed, what the
profile actually is, and what to do.

## The cfg trap, which has silently eaten a change before

`CLAUDE.md`: **a `cfg/` edit does nothing until `version` is bumped.** A saved
project embeds the whole `after=` template including `<exec>` lines, so
NativeCAM reads the STORED copy until migration runs. If you add an `[AFTER]`
call and do not bump `version`, it will appear to work on a new project and do
nothing on every existing one. Bump it, and verify migration actually picked
the new template up rather than assuming it did.

Other O-code rules that bite here: comments must close on the same line, no
nested parens inside a comment, LF line endings only.

## Verify it yourself

- A project whose limits are fine: **no new message, and motion unchanged.**
- A limit outside the profile: the new message fires, with the right numbers.
- Limits leaving too little: fires, with the right numbers.
- **Fingerprint: capture a baseline before editing, and the 46 projects must be
  identical afterwards** — this is validation, not geometry. Any motion change
  means the check is doing more than reporting; stop and report.
- Prove the migration point: an existing saved project must get the new
  validation after the version bump.

## Gates

```bash
flake8 ncam_*.py lathe_sections.py <your new module> --builtins="_" --select=E9,F63,F7,F82
python3 run_tests.py test_lathe_validation.py test_cam_map.py test_vkb.py <your new test>
python3 cam_map.py
python3 test_surface_equality.py
python3 test_project_sweep.py
python3 test_motion_fingerprint.py
```

## Deliverable

The validation, its tests, and the `version` bump committed;
`analysis/25N-...md` with the threshold chosen and why, the three cases proved
with numbers, the migration evidence, and the fingerprint result; then a
report with every gate's exit code.

## Non-interference rules

1. **Never `git add -A`, `git add .`, or `git commit -a`.** Stage by explicit
   path only. On 2026-09-13 a worker's bulk `git add` swept three of another
   session's in-flight files into its commit (`8c38722`, undone by `1e08a93`).
2. **You are the single writer of `lathe_sections.py`.** Nearly every geometry
   task edits that file, so only one such session may run at a time. Confirm
   with greatEndian that no other geometry worker is active before you start.
3. **If a gate fails in a file you did not touch, re-run it once**, then report
   it. `analysis/134`: this suite returns **false FAILs under load**. Prefer
   `python3 run_tests.py <drivers>` — it re-runs a failing driver once and
   reports "passed on retry" separately from "failed twice".
4. **Do not push.** Local commits only — greatEndian's call.
5. Do not touch the live `configs/sim/axis/ncam_demo/ncam/scripts/ncam.ngc` or
   any `.var` file. ID work is **paused** by instruction.
6. `test_rough_ends.py` is a known failure awaiting greatEndian's tip-vs-cut
   ruling — not yours, not a blocker.
