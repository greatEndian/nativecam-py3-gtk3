# 004 — The pre-finish pass collapses onto the finish contour when compensation is on

2026-08-03. greatEndian: *"if I switch from compensation Off to native/CAM the
prefinish contour is at same place as the finishing contour, there is no offset
present"*. **In CAM fixed. Native reproduced and NOT fixed** — it needs a
design change, recorded below.

## Measured

Radial separation between the pre-finish and finish passes on testing_15_2,
130 samples along the profile. Positive means the pre-finish stands outside the
finish, which is what leaves stock for it to take:

| mode | min | max | mean |
|---|---|---|---|
| Off | +0.5072 | +3.6892 | +0.5742 |
| Native | **−0.4389** | +0.4467 | **+0.0890** |
| In CAM, before | **−0.4318** | +0.1307 | **+0.0223** |
| In CAM, after the fix | **+0.5080** | +3.4115 | **+0.5711** |

The Offset per side is 0.508 mm. **Negative means the pre-finish pass cuts
inside the finished surface** — this is not cosmetic.

## In CAM — cause and fix

`offset_contour` folded the allowance into the nose radius and so scaled BOTH
the normal term and the orientation term by `nose_r + extra`. On a surface
parallel to an axis those two cancel exactly, so the allowance vanished:

    offset_contour(wall_at_r20, nose_r=0.4+0.508, orient=2)  ->  r 20.0000
    lathe_comp.offset_vector(..., nose_r=0.4, extra=0.508)   ->  dx +0.5080

`offset_contour` now takes `extra` separately and scales only the normal by it,
which is the rule `lathe_comp.offset_vector` already implemented and
`test_lathe_comp` already pinned.

**This is the asymmetry recorded in `lathe_comp` on 2026-08-02 with the note
that it was "masked because every caller passes extra_r = 0". That note was
wrong.** `build_cam_comp_gcode` passes a non-zero `extra` for every pass but the
last, so it was never masked — it was the live bug, sitting behind a comment
saying it could not bite. A latent-bug note is only worth what its survey of
callers is worth.

## Native — reproduced, not fixed

Same symptom, different mechanism, and the fix is architectural.

`tip_comp_dia` builds the D word as `2*extra_r + nose_dia` and hands the
interpreter `G41.1 D<that> L<orientation>`. But **with a non-zero L the
interpreter takes D/2 to BE the nose radius**: the control point is the
imaginary tip of a nose of exactly that size, and the orientation term is scaled
by the same D/2. So the allowance folded into D gets cancelled by the
orientation term for precisely the reason it did in Python — an allowance
cannot be carried in the D word while L is set.

**To finish**: the allowance has to move the programmed contour instead of the
D word. `poly_lathe_mill` already loads the pre-finish pass's points from
`_pl_fc_base` through `cam_load`, so Python can emit that table already offset
by the allowance and pass `shift_r = 0`, leaving D as the bare nose diameter.
That is generation-side work in `lathe_sections` plus the call sites in
`poly_lathe_mill.ngc`, and it wants its own measurement run.

Note the same reasoning applies to any op that folds an allowance into D while
setting L — worth checking `taper`, `taper_id` and `boring` when this is picked
up.

## Verified

- In CAM separation +0.5080 min / +0.5711 mean, matching Off's +0.5072 / +0.5742
- the finish surface is unchanged: testing_15_2 Off 0.1094 / Native 0.0080 /
  In CAM 0.0080, so the last finish pass, which carries no allowance, is
  untouched
- `test_offset_contour`, `test_sections`, `test_lathe_comp`, `test_comp_overlay`,
  `test_arc_endpoint`, `test_flank_envelope` green
