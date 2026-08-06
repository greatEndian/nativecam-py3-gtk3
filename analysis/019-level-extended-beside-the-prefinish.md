# 019 — The stop extension carried a level 19.4 mm beside the pre-finish

2026-08-06, branch `liveTooling`. greatEndian, `testing_15_4` (front chamfer):
*"last roughing pass is at all long length same as prefinishing passing ..
passing must not be repeated in the same spot"*.

## Measured

```
deepest level     r20.5240
pre-finish contour r20.5080 on the cylinder      -> 0.0160 apart
the level ran Z-0.0882 .. -19.5318, 18.5 mm of it within 0.10 mm of the contour
```

## Why it happened

The ladder's floor is anchored on the polyline's **Final Diameter, 38 (r19)** -
the chamfer's small end - so the grid is `19.508 + k*0.508` = …20.016,
**20.524**, 21.032… The cylinder's own roughing floor is `20 + 0.762 = 20.762`,
so level 20.524 sits **below** it and the floor scan correctly stops that level
at Z-0.0882, on the chamfer.

The **stop table then extended it**. That extension exists to carry a level
from the floor allowance it stops on to the pre-finish allowance the table
holds, and it was unbounded:

```
legitimate extensions, both projects, every level:  0.90 .. 1.0034 mm
this one:                                          19.4436 mm
```

It jumped the entire cylinder - a region where the level is below the local
roughing floor and has no business cutting - and left it running the length of
the part 0.0160 mm from the pre-finish contour.

## The fix

Bound the extension by the band it crosses: at most one depth of cut of
RADIUS, which costs `doc/|slope|` of Z on the crossing segment, with a floor of
`3 x doc`.

The floor is not decoration. A slope-only bound collapses to nearly zero on a
near-vertical segment and rejects a good extension: the end wall of
`testing_15_2` needs 0.5080 and was cut off, which left **every** level 0.508
short of the pre-finish wall and made one pass behind the boss plunge. That was
measured, not predicted - the first version of this bound shipped it and five
assertions failed.

```
after   testing_15_4  deepest level 19.132 mm -> 0.088 mm, 28 cuts, longest 22.898
        testing_15_2  29 cuts, 0 under 2 mm, longest 23.139
        test_rough_comp Off 0.1116 | compensated 0.0503, unchanged
```

## The wrong fix, and why it was wrong

`224c0b9` truncated the level instead, and was reverted. It measured "what a
level removes" as `level - stop_contour`, which is what is left **below** the
level rather than what it takes - a level removes down to itself from the
PREVIOUS level above it. On the far taper those cuts were taking a full 0.508
step and were truncated anyway: **10 honest passes cut to 1.299 mm**, which is
`photo/spaceBehindIssue_9.png`.

Treating it at the level's length was the wrong end. The level should never
have been carried across the cylinder in the first place.

## Two process notes

- **The first bisect was invalid.** `lib/*.ngc` are read at rs274 RUNTIME, so
  checking out an old lib and parsing a file generated separately measures
  nothing: six commits gave byte-identical output, and the md5s matching is
  what gave it away. The parse has to run with that lib on disk.
- A script named `bisect.py` shadows the stdlib module and breaks
  `import random` -> `tempfile` -> `ncam_preview`.

## Coverage

`test_ladder.py`: no level may run more than 2 mm within 0.10 mm of the
pre-finish contour. Negative control, bound removed:
`r20.5240 runs 18.5 mm of its 19.5 within 0.10 mm of it`.
