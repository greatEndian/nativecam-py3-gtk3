# 064 — Respect tool front angle took the complement twice

2026-08-24. `liveTooling`.

## What was asked

greatEndian: *"respect tool front angle counts angle from opposite side .. T2
has 15deg and code generates restriced area as like there is -15"*,
`photo/frontAngleRespectIssue_0.png` — testing_15_6 with *Respect tool front
angle* ticked, running T2.

## The tool

`configs/sim/axis/ncam_demo/lathe_mm.tbl`:

```
T2  P2  D0.8  I15.000000  J75.000000  Q2  ;orient2 D2.54 CL45
```

Centre line `(I+J)/2 = 45`, included angle `|J-I| = 60`. **The two edges are
mirror images 30 degrees either side of the bisector.**

## What was measured

`flank_slope(deg, clr)` is `tan(90 - deg - clr)` — written for the BACK column,
where `J75` correctly becomes a 13 degree ramp at the 2 degree default
clearance. `front_flank_envelope` at `lathe_sections.py:2253` handed it the raw
`I`.

| flank | call | ramp |
|---|---|---|
| trailing, `J75` | `flank_slope(75, 2)` | **13.00°** |
| leading, `I15` — before | `flank_slope(15, 2)` | **73.00°** |
| leading, `I15` — after | `flank_slope(90-15, 2)` | **13.00°** |

`I` is already the other edge of the same wedge, so complementing it
complements an angle that was never measured from the axis `flank_slope`
assumes. The result is the leading flank ramping **five and a half times
steeper** than the trailing one.

**The symmetry is the proof, and it does not depend on which axis the table
measures from.** A symmetric insert cannot have one flank shadow at 13 degrees
and the other at 73 — whatever the convention, the two edges are mirror images
and the two shadows must be the same size. greatEndian's phrasing, "counts
angle from opposite side", is exactly a complement.

## The fix

`90 - front_deg` in, so `tan(I - clearance)` out. `None` still passes straight
through, so an absent column is still "unknown" rather than 0.

## What moves and what does not

Nothing in `test_front_flank`'s fixtures moves — the change is in the middle of
the range, which is where a shadow is a shadow rather than a wall:

| profile | before | after |
|---|---|---|
| steep front wall, 89.7° | 1 span, worst 19.160 | 1 span, worst 19.940 |
| plain rising taper, 26.6° | silent | silent |
| plain cylinder | silent | silent |
| **moderate 45° front face** | **silent** | **1 span, worst 2.314** |
| unusable 105° | None, silent | None, silent — `90-105` is negative and
  `flank_slope` refuses it just the same |

The 45° face is the case that was being missed: a face the leading flank
genuinely cannot make, reported as reachable.

## Gates

- `test_front_flank` — all pass, including the four checks that the front spans
  are asked for in `[VALIDATION]` and nowhere else.
- `test_front_flank_path` — all pass. **Off by default is intact**: testing_15_2
  at 341 moves `3f98389e76f7` and testing_15_5 at 484 moves `f1e3e5026d7a` are
  unchanged, and each still changes when the switch is asked for, 341 → 320 and
  484 → 461.
- `flake8` clean.

## Why it was not caught earlier

The function was written as a deliberate mirror of `flank_envelope` — "there is
almost no new maths here" — and the mirroring was done on the SIDE, through
`mirror_dir`, which is right. The angle was passed through unchanged because
both columns look like angles of the same kind. They are, but `flank_slope`
does not take an edge direction; it takes the number the BACK column happens to
be, and complements it. The docstring even stated the rule it was breaking:
*"`flank_slope(75)` is tan(15 degrees), which is what a J75 insert ramps at"* —
and then said the front is "read the same way", which is what made 15 come out
as 73.

`test_front_flank`'s fixtures could not catch it because both fixtures sit at
the ends of the range: an 89.7° wall is unreachable at either ramp, and a 26.6°
taper is on the unshadowed side either way. Nothing exercised a face BETWEEN 13
and 73 degrees, which is the only band where the two conventions disagree.

## What is still unknown

- greatEndian's phrase "as like there is -15" may also mean the region appears
  on the wrong SIDE. The side comes from `mirror_dir`, which `test_front_flank`
  checks directly and which is unchanged here. If the region is still wrong
  after this, the side is the next thing to measure.
- The 2 degree default `back_clear` is applied to the leading flank as well.
  It is named for the trailing one and no one has said the leading flank wants
  the same number.
