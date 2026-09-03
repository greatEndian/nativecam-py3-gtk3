# 079 — T13, a real left-hand tool, and what it exposed

**Asked**: greatEndian, 2026-09-03 — *"add left hand tool to demo tool table"*,
after `analysis/078` recorded that no demo project carried one and the mirrored
path had only ever been exercised by editing `Q` in a scratch copy.

## What was added

`T13`, the **left-hand twin of T2**: same 0.8 mm nose, orientation mirrored to
`Q1`, and — this is the part that matters — **its I/J mirrored with it**.

```
T13 P13 D0.8 I105.000000 J165.000000 Q1   ;left-hand twin of T2
```

Added to the TRACKED `configs/common/lathe.tbl` and `lathe_mm.tbl` as well as
the local `ncam_demo` copies, because `configs/sim/*/ncam_demo/*.tbl` is
gitignored and a row added only there would not survive a fresh clone.

## THE SCRATCH CONTROL WAS A TOOL THAT CANNOT EXIST

`test_ramp_orient` mirrors T2 by changing one character, `Q2` → `Q1`, and
leaving `I15 J75`. Those angles bisect to **CL45**, which contradicts `Q1` =
CL135. The tool describes an orientation its own cutting edges deny.

That is why it behaved differently from a real left-hand tool: the inconsistent
one gives **18 ramps** back to front, T13 gives **0**. The angles are not
decoration — they drive the flank envelope, and mirroring the orientation
without them mirrors half the tool.

The control still demonstrates what it was written for, that `ramp_facing`
flips with `Q`, and it is left alone. But it is now known to be a synthetic
tool, and `test_bidir_warn` carries a real one beside it.

## Measured, on testing_15_9

| tool | direction | face | ramps | warns |
|---|---|---|---|---|
| T2, right hand | front to back | −1 | **15** | no |
| T2 | back to front | −1 | 0 | **yes** |
| **T13, left hand** | **back to front** | **+1** | **0** | **no** |
| T13 | front to back | +1 | 0 | **yes** |
| T13 | both directions | +1 | 0 | **yes** |

The warning is exactly right in all five: each tool is quiet in its own
direction and warns in the others, and `wrong_way_dirs` needs no special case
for the mirrored tool.

## AND IT REPRODUCES THE OPEN QUESTION WITH A REAL TOOL

T13 in **its own direction** gets **0 ramps**, where T2 in its own direction
gets 15. That is `openPoints`' *"Does a mirrored insert really lose EVERY ramp
on testing_15_9?"*, which `analysis/071` recorded as consistent but **not
independently proven**.

It is now reproducible with a tool a user could load, rather than with a
scratch `Q` edit — which is worth more than the answer would have been, because
the previous evidence came from a tool that could not exist. The question is
still open; what changed is that it can now be investigated honestly.

## Gates

`test_bidir_warn` (19 assertions, T13 included), `test_ramp_orient`,
`test_leads`, `test_leftover`, `test_ramps`, `test_ladder`,
`test_x_continuity`, `test_air_leads`, `test_z_limits`, `cam_map`.

## THE ID PAIR, T14 / T15 — and a correction

greatEndian, same day: *"add left hand boring bar too"*. Adding it corrected
something I had written the hour before.

**`T4` already WAS a left-hand-orientation boring bar.** `Q4` is
`NOSE_OFFSET (-1, -1)`, an ID orientation with facing +1, and its `I195 J255`
bisect to CL225 consistently. The open point I had just added — *"nothing in
the demo tables is a real left-hand boring bar"* — was wrong on its face.

What was genuinely missing is a **matched pair at a realistic bar nose**. `T3`
and `T4` carry the two ID orientations but both at `D2.54`, an R1.27 nose that
is large for a bar, and there was nothing comparable to the `T2`/`T13` pair OD
now has. So:

```
T14 P14 D0.8 I285.000000 J345.000000 Q3   ;boring bar, right hand - bores toward -Z
T15 P15 D0.8 I195.000000 J255.000000 Q4   ;boring bar, LEFT hand  - bores toward +Z
```

`Q3` is `(-1, +1)`, facing −1, so front to back is its own direction; `Q4` is
`(-1, -1)`, facing +1, so back to front is. They are each other's hand exactly
as T2 and T13 are, and `wrong_way_dirs` needs no ID branch:

| tool | quiet in | warns in |
|---|---|---|
| T14, bore right hand | dir 0 | dir 1, 2 |
| T15, bore LEFT hand | dir 1 | dir 0, 2 |

**Only the warning is asserted for these.** They are exercised against
testing_15_9, which is an OD part, so nothing about the ID TOOLPATH is tested —
ID work is paused. The warning depends on orientation and direction alone, so
it is meaningful there; ramp counts for a boring bar on an OD part would not
be, and are not claimed.

## Still unknown

- Why T13 arms no ramps in its own direction. The flank envelope flips with the
  insert (`analysis/071`), the entry contour halves, and no level ends up
  arming one. Whether that is correct for a left-hand tool on this part, or a
  fault in the mirrored envelope, is the question above and is not answered
  here.
- T13 is a left-hand OD turning tool only. Nothing in the demo tables is a real
  left-hand BORING bar, so ID work still has no mirrored case at all.
