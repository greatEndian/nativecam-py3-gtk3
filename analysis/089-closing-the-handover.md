# 089 — closing the handover: the last runtime feedback, predicted

**Asked**: greatEndian, 2026-09-03 — *"close it"*, on the gap `analysis/088`
opened: the two predictions that read `sect_top_r` were wrong on
`testing_15_blocked`.

## Closed

```
test_ladder_account   36 configurations   pred=888 cut=792 unvis=0   no phantom
test_level_intervals  36 configurations   2731 walks, 765 multi-interval, 3496 calls
```

Both now include `testing_15_blocked` and **the SKIP is gone** - the part is
checked, not excused. Nothing in the toolpath reads any of it; no `.ngc` or
`cfg` was edited.

## What had to be understood first

Reading the branch gave me the rule but not the arithmetic, and two things only
came out of dumping the actual level sequence.

**The two ceilings are used in different places, deliberately.** `p1_step` and
`p2_step` are worked out ONCE above the window loop from the ceiling Python
emitted, while `lvl_start` reads `sect_top_r` at the moment each window runs -
which the handover may have moved. On this part the steps stay +/-0.500, from
`(36.016 - 31.016)/10` against the ORIGINAL 31.016, while every phase-2 window
starts at the MOVED 34.572. Feeding the moved value into both gives 0.4813 and
a ladder matching nothing. `roughing_ladder` therefore takes `top_override`
that moves only the phase-2 START.

**A floor stage can sit above the stock.** This part has two, the first at
36.016 - the front region's floor is the stock face plus allowance - so phase 2
walks UPWARD to it and then re-anchors down. Levels 35.072, 35.572 and 36.016
are above the stock radius and can never cut, which is exactly why gate one
passed while gate two failed.

**Phase 1's window starts at Z-20, not Z0.** The record array's first entry is
the first ITEM's endpoint, not the polyline origin - the `.cfg` says so about
`_pl_begin_z` and I had still assumed the origin. That is why the failing call
carried `w_from = -20`, which made no sense against my reading of the branch
and was the thing that forced a measurement instead of another guess.

## The two pieces

- **`phase1_stop(levels, floor_contour, stock_r, doc, e_z, l_z, skip_thin, ...)`**
  - walks the phase-1 ladder and returns the radius where `o<p1_none>` fires:
  the first level that gets a pass and comes back blocked. A level only gets a
  pass if it enters `o<lvl_ok>`, so at-or-past-stock and thin levels are
  skipped - and the thin test is predictable here precisely because
  `_pl_prev_thin` stays at the stock radius while nothing has cut.
- **the interval walk learns which phase it is in.** Phase 1 blocked from its
  sub-span's own start with nothing cut yet abandons the level outright; a
  phase-2 window blocked the same way goes looking for a resume. That is not
  visible from `lathe_level_pass` - phase 1 ends by a branch in its CALLER - so
  `poly_lathe_mill` now emits one header per sub-span carrying `w_idx`.

## The whole stack, and what is left of the boundary

```
window (085) -> sub-span (084) -> interval (083, 089) -> level set (080..082, 089)
```

Every layer is predicted at generation time, on 36 configurations including the
part built to break it. **The phase-1 handover is no longer an exception** -
`level_blocked` answers, per level, whether phase 1 can cut anywhere, and
agrees with the O-code on all 3496 calls.

What that does NOT mean: nothing is wired. The `.ngc` still decides everything
at runtime and the motion is untouched. What has changed is that there is no
longer a known reason it could not read tables instead - which was the open
question since `analysis/080`.

## Still not proved

- The three `sect_top_r` sites: **site 1 now fires** (3 configurations). Sites
  2 and 3 - the resume-disagreement and split-table handovers - remain at 0
  fires and are still unexercised by any project.
- `band=0` across the whole sweep: no project has split windows.
- The stop-contour and reach clamp still move `z_end` on 0 of 1902 cutting
  calls, so that refinement remains carried but untested.

## Gates

Every test above, plus `test_ladder`, `test_leftover`, `test_x_continuity`,
`test_ramps`, `test_sections`, `test_bidir_warn`, `cam_map`, flake8.
