# 001 — The pre-finish pass started on the finish contour

2026-08-03. Reported by greatEndian from AXIS, `photo/prefinishLeadInIssue_0.png`,
project testing_15_2. Fixed the same day.

## What was asked

*"its starting point is same as finishing and it have to be offsetted by
finising offset like other points/contour of prefinish are"*

The pre-finish contour (blue) is correctly offset from the finish contour (pink)
along the whole profile. At its start point the two coincide.

## What was measured

First cutting point of each pass, testing_15_2, generated headlessly:

| | pre-finish | finish | difference |
|---|---|---|---|
| before Step 4 (`c16df1f`) | Z 1.7071, r **21.2151** | Z 1.7071, r 20.7071 | 0.5080 |
| after Step 4 | Z 1.7071, r **20.7071** | Z 1.7071, r 20.7071 | **0.0000** |
| after this fix | Z 1.7071, r **21.2151** | Z 1.7071, r 20.7071 | 0.5080 |

0.5080 mm is the project's Offset (per side), 0.02 in. So Step 4 removed it, and
this restores it.

With `Passes = 2` the first finish pass now starts at r 20.9611 — 0.2540 from
the finish contour, half the offset, which is what an intermediate pass should
carry. No test covered that case before.

## Root cause

`lathe_poly_pass` places its entry at `entry + r * normal - R * orientation`.
Step 4 changed the scale `r` from `comp_r` to `#<_tip_cam_r>` and gated the
whole block on the same value. That conflated two separate questions:

- **How far** the entry moves is `comp_r = #<_tip_comp_d> / 2 = shift_r +
  nose_r` — the same `D` the interpreter is about to be given.
- **Whether** the offset is orientation aware is the **L word**. `L0` is a pure
  geometric offset and takes no orientation term; `L1`–`L9` does.

`tip_comp_dia` sets `_tip_cam_r = 0` whenever nose comp is **off**. And
testing_15_2 has `Tool nose comp = 0` — but an Off-mode pass still runs
`G41.1 D[2 * shift_r] L0` to hold its allowance. So the gate was false, the
entry never moved, and the pre-finish pass started on the finish contour.

The fix gates the distance on `comp_r` and the orientation term separately on
`#<_tip_comp_l> GT 0`. In CAM still gets no shift at all: its `comp_r` is 0
because the path is already offset.

## Why it was not caught

Step 4's acceptance measurement sampled the **finish phase only**, and the last
finish pass carries `shift_r = 0`, where the fault is invisible. The pre-finish
pass was never measured, and no project in the suite ran `Passes > 1`.

Worth keeping: **the first fix attempt was wrong and the measurement said so.**
The diagnosis was "the allowance dropped out of the scale", and the fix
`pe_r = _tip_cam_r + shift_r` was applied — and changed nothing, because the
*gate* was false before the scale was ever reached. That attempt was reverted
rather than committed. A plausible mechanism that does not move the number is
not the mechanism.

## Still unknown

Nothing outstanding on this fault. The related open question — whether the
preview should draw a compensated-path overlay — is untouched and recorded in
`openPoints.md`; what was established while looking is that the preview already
draws the tool at the interpreter's compensated positions, and it is the contour
overlays that are the uncompensated programmed profile.

## Verified

- entry offsets above, generated and parsed in one run
- surface unchanged where it must be: testing_15_2 Off 0.1094 / Native 0.0080 /
  In CAM 0.0080, testing_13_arcs 0.0013 / 0.0014 / 0.0014
- `check_tangent` `[VERDICT: PASS]`, min |dot| 1.00000
- flake8 both lists; twelve `test_*.py` green
