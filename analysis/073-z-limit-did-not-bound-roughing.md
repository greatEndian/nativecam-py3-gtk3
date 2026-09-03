# 073 — a Z limit trimmed the profile but not the roughing

**Asked**: greatEndian, 2026-09-03 — *"go, fix the End Z limit"*, the first of
the three I recommended and the one I put ahead of the rest because of what it
is rather than how big it is.

## The fault

`testing_15_5` with **End Z = −40** cut to **Z−70.8000**. The same limit on
`testing_15_2` correctly stopped at −40.6043.

Six roughing FEED moves ran past it, one of them **Z−0.4000 → Z−70.8000 at a
constant X34.4371** — a full-length level cut taking 30 mm of stock the limit
was set to protect. Every one had `subs=()`: roughing only. The pre-finish and
finish passes stopped correctly.

**This is a safety bug, not a cosmetic one.** A back limit is what you set to
keep the tool out of a chuck, a steady, or a second setup — and it was obeyed by
the passes visible in the plot and ignored by the roughing underneath them.

## Root cause

The Z limits trim the PROFILE, and every table built from it — finish,
pre-finish, entry, stop — inherits the trim. The roughing window does not:
`poly_lathe_mill` takes `e_z` and `l_z` from the **record array**, which is
built from the raw polyline items and has never seen the trim.

The code says so itself, three lines above the fault, about the back extension:
*"The record array is built from the raw polyline items and never sees an
extension"* — and carries a displacement to correct exactly that. This is the
same correction for the same reason, on the same two variables.

A roughing level that never crosses the trimmed profile then has nothing to stop
it and runs to the untrimmed end.

## Why it survived

`testing_15_2` obeys the same limit, because there every level crosses the
profile before reaching it and the window end never bites. One project honoured
the limit and one did not, which reads like a project quirk until the two are
measured side by side. `test_z_limits` measures both.

## The fix

`build_z_limit_bounds_gcode` emits the Z **band** the operation may work in —
`_pl_lim_on`, `_pl_lim_lo`, `_pl_lim_hi` — and `poly_lathe_mill` clamps both
window extents into it.

A band rather than two clamps, worked out in Python, because which limit is the
near one depends on the direction the profile was drawn in and on which switches
are on. Python knows all of that; the subroutine keeps two numbers in range.
999999 stands for "unbounded on that side", so one limit works without the
other, and `_pl_lim_on` is 0 when neither is set — which skips the clamp
entirely for every project that sets no limit.

Clamped AFTER the back extension on purpose: **a limit is a hard bound and an
extension is a request**, so the limit wins when both are set.

## Measured

| | before | after |
|---|---|---|
| testing_15_5, End Z −40 | cuts to **Z−70.8000** | **Z−40.6043** |
| testing_15_2, End Z −40 | Z−40.6043 | Z−40.6043 |
| testing_15_5, Front Z −20 | — | feeds begin at **Z−20.4**, none in front |

The corroboration that the number is right and not merely smaller: **15_5 now
stops at exactly the same Z as 15_2** under the same limit.

No limit set, motion hashed against the `analysis/071`/`072` baselines:
`6cf361a8b8f5`/1575, `e2744cbb6ff0`/327, `128ebb273ba5`/458 — all three
unchanged, in all three directions.

## An assertion of mine that was wrong

The front-limit check first read `zmax` over every move and failed on a **rapid
at Z0.0000**, while every feed correctly began at Z−20.4. A limit bounds the
CUTTING, not the travel: the tool still has to reach its start point through
air. The test measures feeds for that reason, and says so.

## Gates

`cam_map`, `test_cam_map`, `test_leftover` (24/24 control, which also proves the
1.71 migration), `test_ramps`, `test_sections`, `test_ladder`,
`test_x_continuity`, `test_air_leads`, `test_x_limits`, `test_ramp_orient`,
`test_bidir_warn`, `test_flank_envelope`, `test_front_flank`, `test_leads`,
`test_skip_short`, `test_lathe_validation`, and the new **`test_z_limits`**
(15 assertions).

## Still unknown

- The clamp bounds the roughing WINDOW. Whether anything else reads the record
  array's raw extents and would want the same bound has not been swept for -
  `test_z_limits` would catch it in the roughing, but not in a table nobody
  measures.
- A limit outside the profile entirely still silently does nothing, which is a
  separate recorded open point about the validations.
