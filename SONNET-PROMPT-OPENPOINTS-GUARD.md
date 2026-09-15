# Task: a guard that stops `openPoints.md` going stale

You are working in `/home/user/nativeCamDev`, branch `liveTooling`.
Read `CLAUDE.md` first. Analysis range: **`analysis/240`–`249`**.

**You create new files only** — a checker script plus its test. Do not edit
`lathe_sections.py`, `ncam*.py`, `lib/`, `cfg/`, or any existing `test_*.py`.
You may edit `openPoints.md` only to correct entries your own checker flags.

## Why this exists

`openPoints.md` is the project's account of what is LEFT. It cannot currently
be trusted, and the decay is fast:

- **2026-09-13**: a full reconciliation (`ce28d71`, `analysis/190`) found
  **six** entries already done but still unticked. One of them —
  *"RESPECT TOOL FRONT ANGLE MEASURES THE ANGLE FROM THE WRONG AXIS"* — had
  been fixed on 2026-08-24 with the measurement sitting in its own body, and
  was within one step of being handed to a worker as new work.
- **2026-09-14, one day later**: the same list was stale again. Six preview
  entries were still `- [ ]` although `24c0b80` had implemented all of them in
  `ncam_preview_ui.py` with `test_preview_wiring.py` passing.

A reconciliation done by hand decays within a single round of work. This
project's answer to that shape of problem is a checker — `cam_map.py` exists
for exactly this reason, with a test per check. Follow that idiom.

## What to build

A script (suggested: `openpoints_check.py`) that reports entries whose closing
work already exists, and a `test_openpoints_check.py` that fails on each bug
the checker exists for — `test_cam_map.py`'s convention.

Signals worth checking, strongest first. **Decide which are reliable enough to
report as findings and which are only hints, and say why in your analysis:**

- an unticked entry whose own body contains a closure claim (`FIXED`, a date,
  an `analysis/NNN` reference with a measurement);
- an unticked entry naming a symbol (function, file, parameter) whose
  implementing code now exists — the preview case: `Programmed Point` →
  `programmed_point`, `Accuracy slider` → `accuracy_divisor`;
- an entry referencing an `analysis/NNN` that does not exist;
- a claim of "fixed" with **no** analysis number and no measurement behind it —
  per `analysis/190` that is a *finding*, not a closure, and must be reported
  separately rather than ticked.

**False positives are the failure mode here.** A checker that cries wolf gets
ignored, and then the list rots anyway. Prefer a small set of high-confidence
checks over broad guessing, and make the output name the evidence for each hit
so a human can confirm it in seconds.

## Verify it yourself

Your checker must find the two historical cases above when pointed at the
relevant commits, and must **not** flag entries that are genuinely open. Build
the test from real entries in the file, not invented ones. `analysis/190` has
the entry-by-entry evidence from the manual pass — use it as your answer key.

Then run the checker on `openPoints.md` as it stands and report what it finds.

## Gates

```bash
flake8 openpoints_check.py test_openpoints_check.py --builtins="_" --select=E9,F63,F7,F82
python3 cam_map.py && python3 test_cam_map.py
python3 test_openpoints_check.py
python3 openpoints_check.py
```

## Deliverable

Checker and test committed; `analysis/24N-...md` with the signals chosen, the
ones rejected and why, the false-positive rate against `analysis/190`'s answer
key, and what it flags today; then a report with every gate's exit code.

## Non-interference rules

Other Claude sessions may work in this same git tree.

1. **Never `git add -A`, `git add .`, or `git commit -a`.** Stage by explicit
   path only. This is not hypothetical — on 2026-09-13 a worker's bulk `git
   add` swept three of another session's in-flight files into its commit
   (`8c38722`), and needed `1e08a93` to undo it.
2. **If a gate fails in a file you did not touch, re-run it once**, then report
   it. `analysis/134` records that this suite returns **false FAILs under
   load**. Use `python3 run_tests.py <drivers>` — it re-runs a failing driver
   once and reports "passed on retry" separately.
3. **Do not push.** Local commits only — greatEndian's call.
4. Do not touch the live `configs/sim/axis/ncam_demo/ncam/scripts/ncam.ngc` or
   any `.var` file. ID (inside-diameter) work is **paused** by instruction.
5. `test_rough_ends.py` is a known failure awaiting greatEndian's tip-vs-cut
   ruling — not yours, not a blocker.
