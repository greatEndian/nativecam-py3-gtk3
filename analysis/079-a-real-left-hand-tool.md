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

## Still unknown

- Why T13 arms no ramps in its own direction. The flank envelope flips with the
  insert (`analysis/071`), the entry contour halves, and no level ends up
  arming one. Whether that is correct for a left-hand tool on this part, or a
  fault in the mirrored envelope, is the question above and is not answered
  here.
- T13 is a left-hand OD turning tool only. Nothing in the demo tables is a real
  left-hand BORING bar, so ID work still has no mirrored case at all.
