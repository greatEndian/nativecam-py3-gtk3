# 082 — the blocked decision, replicated in Python and proved call for call

**Asked**: greatEndian, 2026-09-03 — *"go on with the blocked decision"*, the
item `analysis/081` named as the thing standing between the ladder and the
migration.

## What blocked actually is

`lathe_level_pass` sets `#<_level_blocked>` in exactly two places, and it is
**not** a geometry solve. When the floor contour Python emits is present -
`_pl_flc_n GT 1` - both of the subroutine's scans walk **only that table** and
skip the record-array offset scan outright (`scan_i = rec_count`,
`mc_i = rec_count`). The contour is already blended by each surface's own
normal with its corners joined, so there is no perpendicular offset arithmetic
and no corner connector left to redo.

So the decision to reproduce is a walk of a table Python itself built.

- **single crossing**: the first place the contour rises to
  `level + 0.001 x _mm`. Blocked when that crossing is at or before the window
  start - the profile is already above the level before the window begins, so
  nothing inside it is reachable.
- **multi crossing**: replays every crossing in order, tracking above/below,
  and **freezes that state at the window start**. Blocked when the state there
  is "above". A level behind a boss crosses several times and only the state at
  `w_from` decides.

## The gate

`test_level_blocked`. Same five projects x 2 sectioning states x 3 directions.
An instrumented **scratch** copy of `lathe_level_pass` - the repo's `lib/` is
never touched - emits one `BLKREC` at each of the subroutine's two blocked
returns and at the point it commits to cutting. Python must return the same
answer for every call.

```
30 configurations, 3373 calls, 3373 agree, 1519 blocked, 0 uncovered
3373 calls on the multi-crossing branch, control disagrees on 2038
```

**Nothing in the toolpath reads `level_blocked`.** Same order as the ladder:
replica, parallel run, migration last.

## Three faults the gate caught before it could report anything

1. **The `blk=0` record was inside the branch that returns.** Placed before
   `o<blk> endif` rather than after it, so it could never fire and every
   not-blocked call would have counted as uncovered.

2. **`floor_contour` read nothing, and the test passed anyway.** The defaults
   block assigns `_pl_flc_base = 0` like every other global, so a plain count of
   assignments is always at least two and my "more than one polyline" guard
   rejected every file. Result: `0 agree, 3373 uncovered` - and the thirty
   per-configuration checks all reported **PASS**, because a config with no
   answers has no disagreements. Only the coverage check failed.

   This is the same defaults-block trap that made the gap-10 fix nearly ship
   inert. It is now a rule with two scars: **read the LAST assignment, and
   count only the non-placeholder ones.**

3. **A clean sweep with no control.** The per-config check now also requires
   the config to be **fully covered**, and a reversed-window control asserts the
   answers change when the arguments do - 2038 of 3373 - so a function ignoring
   its inputs cannot pass.

## Coverage, stated rather than implied

**Every one of the 3373 calls took the multi-crossing branch.** `polyline.cfg`
hard-wires `#<_pl_multi_cross> = 1` - *"disjoint-interval roughing is always
active ... there is no safe off case"* - and `lathe_level_pass` has exactly one
caller, `poly_lathe_mill.ngc:984`. So the single-crossing branch is
**unreachable from a polyline**, in the O-code as much as in the replica. It is
replicated for fidelity, not because anything exercises it.

The record-array scan is **not** dead and is **not** replicated. It runs when
`build_floor_contour_gcode` returns nothing: total allowance zero, fewer than
two contour points, or the table overflowing `FLOORC_TOP`. `level_blocked`
returns None there and the test counts those calls rather than passing over
them.

## What the next layer needs

`level_blocked` is handed `w_from` and `w_to` out of the record. Supplying them
from Python means also knowing the interval walk: the 3373 calls are not one
per level - a level behind a boss is re-called for each disjoint interval, and
where the next one starts comes from `lathe_level_next_start` and the resume
envelope, which read the previous blocked answer. **The first call of each
level in a window is the one Python could already predict**; the continuations
are the layer after.

That, and not the geometry, is what still stands between here and the
migration - together with the ordering `analysis/081` recorded: `skip_thin`
cannot move ahead of this, because `_pl_prev_thin` advances only where a level
actually cuts.

## Gates

`test_level_blocked` (new), `test_ladder_account`, `test_ladder_python`,
`test_ladder`, `test_leftover`, `test_x_continuity`, `test_ramps`,
`test_sections`, `test_bidir_warn`, `cam_map`, flake8. Motion untouched: no
`.ngc` or `cfg` edited, and the instrument is proved inert.
