# 112 — the native gouge was the LEAD-OUT, and it is fixed

**Asked**: greatEndian, 2026-09-06 — *"find out why it didn't fire"*.

## It did fire. I was fixing the wrong end.

Printing the gate values at the point `analysis/110`'s second attempt sat:

```
LEADGATE side=1  lilen=1.0  lirad=1.0  d=0.8  lw=1.6  flt=1  done=0
```

Every gate passed, so the insert executed and compensation WAS established
before the lead-in. The gouge did not move because it was never the lead-in.

**This tool traverses the profile REVERSED** - `analysis/107`, the same fact
that caused the In-CAM defect - so the pass runs Z-40 to Z0 and the bore MOUTH
is where it ENDS. The single gouging point at the mouth is the LEAD-OUT.

And `tip_comp_off` sat immediately after the contour trace, before
`o<lead_out>`: **compensation was cancelled while the tool was still on the
wall**, so the retreat ran uncompensated from the profile's own last point and
the nose sat R inside it.

## The fix

Cancel compensation AFTER the lead-out, not before - the mirror of what the
arc-entry branch already does at the start. `analysis/111` established that
G41.1 carries through a straight-then-arc perfectly well, so keeping it on
through the retreat is sound.

Gated three ways: ID only, compensation actually active (`_tip_comp_d`), and a
lead-out actually present. OD, uncompensated passes and lead-less passes keep
exactly the motion they had.

## Gates

```
native (mode 1)   whole path 0.8000 -> 0.0000    contour 0.0000, 413 tangent
                                                 points, 0 uncovered -> PASS
In-CAM (mode 2)   whole path 0.0000              unchanged           -> PASS
wrong-side ctrl   FAILS at 0.8000 in both        as it must
36 OD configs     byte-IDENTICAL
testing_15_0 OD   PASS, control FAILS
suite             twelve gates, cam_map, lathe_validation, flake8
```

## Both ID compensation defects are now closed

```
In-CAM contour   0.8000 -> 0.0000   analysis/107   the profile reached
                                    offset_contour reversed
Native lead      0.8000 -> 0.0000   here           comp cancelled on the part
```

One root cause underneath both: **the finishing direction for a right-hand
boring bar runs the opposite way round the profile**, which flipped the offset
in one place and put the mouth at the wrong end of the pass in the other.

## Why it took three attempts

1. Widen the ID approach - the approach is before the lead; wrong move.
2. Establish comp before the lead-in - right idea, wrong END.
3. Cancel comp after the lead-out - correct.

Attempts 1 and 2 were reverted. What broke the deadlock was not a better
hypothesis but printing the gate values: discovering the code HAD fired proved
the premise wrong rather than the mechanism, and the reversed traversal
followed immediately.
