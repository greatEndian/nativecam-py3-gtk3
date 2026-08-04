# 008 — The bump at Z−20 is a swallowed segment, and it was In CAM only

2026-08-04, branch `liveTooling`. Resolves `analysis/007`, and overturns its
hypothesis.

## What was asked

greatEndian: *"no bump at radius start in the prefinish contour is still
present... fix it first"*, then *"bump is at Z−20 where the wall meets the
arc"*, then *"fix it, print the cross sign at Z−20 first"*.

## What 007 concluded, and why it was wrong

007 measured the pre-finish contour leaving the r20 wall at **Z −19.5138**
instead of −20.0000 and called that the bug — 0.4862 mm early. It derived the
corner's cross sign as −0.9990, which takes the `_isect` trim branch, and then
declined to flip the sign because the reasoning was ambiguous. That restraint
was right, but for the wrong reason: **the sign was never wrong.**

The empirical check 007 itself prescribed settles it in five lines. A nose of
radius `roll` rolling along an r20 cylinder into a wall that rises at Z−20
touches that wall when its centre is at Z −20 + roll. It stops short. It has
to. A trim at a concave corner is the correct parallel offset, and leaving the
flat early is what a finite nose does — it is not a defect and it cannot be
removed by any choice of side convention.

Confirmed by construction:

| profile | offset | wall leaves at |
|---|---|---|
| r20 wall → arc, pure geometric offset 0.508 | trimmed | Z −19.5138 |
| hand-computed rolling-circle contact | — | Z −19.5138 |

So `offset_contour`'s sign, `entry_contour`'s `z_dir`, and their agreement —
the three things 007 sent the next session to check — were all fine.

## What the bug actually was

Measured on the three generated modes of `testing_15_2`, counting reversals
in +Z along the pre-finish pass:

| mode | leaves the wall at | +Z reversals | verdict |
|---|---|---|---|
| Off | Z −19.5143 | 0 | clean |
| Native | Z −19.5310 | 0 | clean |
| **In CAM** | **Z −19.5061** | **1** | **the bump** |

The In CAM pre-finish point table, read straight out of the generated `.ngc`:

```
   Z -19.5061  r  20.5080
   Z -19.5032  r  20.3210      <-- +0.0029 in Z, 0.1870 mm INTO the part
   Z -19.5054  r  20.3723
   Z -19.5564  r  21.0773
```

Out and back. Exactly greatEndian's *"first inside the part and then outside"*.

**Root cause.** An inside corner trims both offsets to where they cross. When
the segment *after* the corner is shorter than the offset, that crossing lands
beyond the whole of it — the segment is swallowed by the corner and the nose
never touches it. `_join_offsets` (then two copies of the same loop) appended
the crossing and carried straight on to that swallowed segment's own corner
join, which sits **behind** the crossing. The connector between them is the
bump.

Here the swallowed segment is the arc's first chord: **0.0049 mm of Z against
a 0.508 offset**, a hundredfold mismatch.

## Why the other two modes escaped

- **Native** never runs this code for the contour — the interpreter does its
  own corner logic inside `G41.1`/`G42.1`.
- **Off** offsets by the allowance alone through `G41.1 L0`, also in the
  interpreter.
- **In CAM** is the only mode where Python emits the offset path as a point
  table, so it is the only mode that can carry a Python offsetting fault.

## Why it was not caught earlier

`test_comp_overlay` compares Python's offset against the interpreter's on the
contour read back from an **Off-mode run**, and that contour is coarse — its
chords near the corner are 1.41 mm of radius, twenty times too long to be
swallowed. `build_cam_comp_gcode` does not use that contour: it takes
`finish_profile`, whose arc subdivision is much finer. **The test and the
shipped path were offsetting two different point lists**, and only the finer
one contains a segment short enough to trigger the fault.

That is the same shape as the `_min_segment` arc truncation of 2026-08-02: a
check that never sees the input the product actually uses.

## The fix

`lathe_sections.py` — the corner-joining loop, which `offset_contour` and
`entry_contour` had a near-identical copy of each, is now one function
`_join_offsets(segs, sign, roll, vkey)`. Inside the trim branch, `_consumed()`
asks whether the crossing lies past the far end of the segment being trimmed
to; when it does, that segment is **deleted and the trim recomputed** against
the one after it. The loop terminates because every retry removes an element.

The two existing trim guards are unchanged and now apply to both callers,
where before only `entry_contour` had the distance bound: `TRIM_REACH * roll`
(near-parallel segments cross arbitrarily far away — unguarded this once put a
point 17.83 mm off a contour offset by 0.5), and the new end-of-segment test.

## Measured after

```
mode 0 prefinish  +Z reversals: 0   wall leaves at Z-19.5143
mode 1 prefinish  +Z reversals: 0   wall leaves at Z-19.5310
mode 2 prefinish  +Z reversals: 0   wall leaves at Z-19.5152   <- was -19.5061 + a bump
mode 0/1/2 finish +Z reversals: 0
```

Nothing else moved. `test_rough_comp` still measures Off 0.1116 / Native
0.0503 / In CAM 0.0503 mm of overcut past the pre-finish contour, digit for
digit, and `test_comp_overlay` still agrees with the interpreter over all 34
contour points.

## The regression test

`test_swallowed_corner` in `test_sections.py`, on both `entry_contour` and
`offset_contour`, using the real chord lengths from the In CAM table. It
asserts no +Z reversal, no point below the offset wall, and exactly two points
at the wall radius — a single straight run, then the rise.

**Verified to fail without the fix**: with `_consumed` forced to `False`, the
same profile yields 1 reversal and 4 points inside the part, dipping to
r 20.3210 against a wall at r 20.5080.

It also carries a control — a coarse corner whose next segment *survives* must
still be trimmed and not dropped — so "drop the swallowed one" cannot decay
into "drop every short one".

## Still unknown

- **In CAM trims 0.0158 mm earlier than Native** (−19.5152 against −19.5310).
  Both are clean and both stand off the profile correctly; the difference is
  the arc subdivision each starts from, not the corner rule. Small enough to
  leave, worth knowing before anyone reads the two tables side by side.
- The symmetric case is **not** handled: a crossing that lands *before* the
  start of the current segment means the current segment is swallowed, which
  would need the already-emitted point popped. It does not occur on any
  profile in this repo, and no synthetic case has been built to force it.
