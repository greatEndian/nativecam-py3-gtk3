# Task: a suite runner that does not lie under load

You are working in `/home/user/nativeCamDev`, branch `liveTooling`.
Read `CLAUDE.md` first and follow its standing rules.

Analysis range: **`analysis/230`–`239`**.

**You create ONE new file** — a suite runner, `run_tests.py` at the repo root —
plus its own test. Do not edit any existing `test_*.py`, `ncam*.py`,
`lathe_sections.py`, `lib/`, or `cfg/`.

## Why this exists

`analysis/134` — read it first. A full 74-driver sweep reported three failures:

```
test_rough_ends.py     rc=1     genuine, awaiting greatEndian's ruling
test_sub_spans.py      rc=124   TIMEOUT
test_x_continuity.py   rc=1
```

Re-run individually with nothing else running, **both of the latter exit 0**.
They were load artifacts. Concurrency has corrupted measurements in this
project **four** times now, each time treated as a one-off scheduling mistake.
It is not one: the sweep is an instrument that returns false FAILs under load,
and that is a property of the instrument.

The cost is real — a false FAIL sends someone to "fix" a test that was never
broken, and this project has a standing rule that agents must verify results
rather than relay them, precisely because of this.

## What to build

A runner that makes a reported FAIL trustworthy:

- **Re-run a failing driver once** before reporting it, and report a driver
  that passed on retry distinctly from one that failed twice — the retry
  outcome is itself the signal that the machine was loaded.
- **A per-driver timeout** that is generous enough for the slow drivers
  (`test_sub_spans.py` timed out at whatever the old limit was) and reports a
  timeout as a *timeout*, not as a failure.
- **Serial by default.** Never run two drivers that drive `rs274` at once.
- A summary that states, separately: passed, failed twice, passed on retry,
  timed out, and skipped.
- **`test_rough_ends.py` must be reportable as a known-expected failure**
  without turning the whole run red — it is blocked on a decision from
  greatEndian, not broken.

Keep it a plain script, this repo's style: no pytest, runs under `python3`,
exit non-zero only on a genuine failure.

## Verify it yourself — this is the interesting part

**Do not validate the runner by running the real suite.** Another session may
own `rs274`, and a runner tested only on a quiet machine proves nothing about
the behaviour it exists for.

Validate it against **deliberately-built fake drivers** in a temp directory:
one that always passes, one that always fails, one that **fails the first time
and passes the second** (the retry case — the whole point), one that sleeps past
the timeout, and one that is the known-expected failure. Assert the runner
classifies all five correctly.

`CLAUDE.md`'s rule applies squarely here: **validate the instrument before
trusting it** — a broken probe costs more than no probe. Your runner is a probe
for every other probe in this repo.

## Gates

```bash
flake8 run_tests.py <your test> --builtins="_" --select=E9,F63,F7,F82
python3 cam_map.py && python3 test_cam_map.py
python3 <your test>
python3 run_tests.py --help      # or equivalent; it must be self-describing
```

You MAY run the runner over the **cheap** drivers only — `test_vkb.py`,
`test_coord_mapping.py`, `test_lathe_validation.py`, `test_cam_map.py`,
`test_geometry_primitives.py` — to show it works end to end. Do not point it at
the full suite.

## Deliverable

`run_tests.py` and its test committed; `analysis/23N-...md` recording the five
fake-driver cases and what each proved, the timeout chosen and why that number,
and anything about the suite you learned while building it; then a report with
every gate's exit code.

## Non-interference rules

Other Claude sessions work in this same git tree right now.

1. **Never `git add -A`, `git add .`, or `git commit -a`.** Stage by explicit
   path only.
2. **Do not run** `test_project_sweep.py`, `test_motion_fingerprint.py`,
   `test_surface_equality.py`, `test_all_projects.py`, or anything under
   `.claude/skills/lathe-gcode-verify/scripts/` — they drive `rs274`, and
   another session may own that. `analysis/134` records that this suite returns
   **false FAILs under load**.
3. **If a gate fails in a file you did not touch, re-run it once**, then report
   it. Never "fix" a failure outside your own files.
4. **Do not push.** Local commits only — greatEndian's call.
5. Do not touch the live `configs/sim/axis/ncam_demo/ncam/scripts/ncam.ngc` or
   any `.var` file. ID work is **paused** by instruction.
6. `test_rough_ends.py` is a known failure awaiting greatEndian's tip-vs-cut
   ruling — not yours, not a blocker.
