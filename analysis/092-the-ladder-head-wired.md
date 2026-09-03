# 092 — the ladder head in Python, and why the .ngc did not shrink

**Asked**: greatEndian, 2026-09-03 — *"go with - Still runtime O-code:
dirsign, step_target, both step sizes, lvl_floor/fl_prot, and every decision
about what a level does — plus the whole ramp/stop machinery"*.

## What that list actually contains

Two different problems, and only one of them is a migration:

- **scalars computed once above the window loop** - `dirsign`,
  `rough_target`, `step_target`, `lad_tgt`, `cut_step`, `first_step`,
  `rough_passes`. Pure generation-time arithmetic.
- **per-window state and decisions** - `lvl_floor` and `fl_prot` mutate
  through the floor stages; thin/blocked/band/intervals and the ramp-stop
  machinery are decisions, not constants.

This closes the first group. The second is untouched and needs its own
proof-then-wire pass each.

## Blast radius, measured

All eleven candidate names are confined to `poly_lathe_mill.ngc` - nothing in
`lib/` reads them. `cut_step` and `first_step` have **12 writes** between them,
mutated per window and per level, so they are not constants and only their
INITIAL values move.

## What shipped

`ladder_consts()` returns the head as a dict and `roughing_ladder` now calls
it, so the two cannot drift. `build_ladder_consts_gcode()` emits it, and
`poly_lathe_mill` replaces its own answers immediately after `o1001 endif`.

`pass_from` is the piece worth moving: anchored on the finished contour the
ladder walks in WHOLE depths of cut from a floor rounded outward, and it
reassigns `step_target` to that rounded floor - which decides where the levels
land without changing how much stock is left. Conflating those two once left
roughing holding 1.016 off a profile configured for 0.762.

## The gate

Same shape as `analysis/091`, one number flipped:

```
36 configurations, head emitted in 36, absent in 0
MOTION IDENTICAL - on equals off, everywhere
```

Stronger than the level table's gate, because `step_target` is read by the
stop scan and the floor logic too - a mismatch would move motion well beyond
the ladder. Suite green: twelve gates, `cam_map`, `test_lathe_validation`,
flake8.

## THE .ngc DID NOT SHRINK, and it cannot yet

The standing rule wants the `.ngc` smaller. **A migration that keeps a fallback
never shrinks it** - the `if` block costs more lines than it saves, and the
override form used here leaves the original computation running and then
discards its answers.

That is deliberate, not an oversight. Deleting the runtime computation is the
actual shrink and it should not happen until the Python path has cut on the
machine. Recorded as the follow-up rather than dressed up as a reduction.

Region 1 could not be wrapped in an `if/else` either: it is INTERLEAVED with
unrelated setup - the `fin_off` clamp, `fin_passes`, `op_chk`, `_lo_rad_cap`
and the feed-rate call all sit between the ladder statements.

## Left for next time

- **Region 2**, lines ~470-596: the section ceiling with its two clamps and
  `p1_step`/`p1_first`/`p2_step`/`p2_first`. Same treatment, and `roughing_ladder`
  already computes all four.
- `lvl_floor` / `fl_prot` - per window and per floor stage.
- The decisions: thin, blocked, out of band, split into intervals.
- The ramp and stop machinery - `s_reach`, the clamp, the profile-angle
  approach.
- **The deletion pass**, once this has run on metal.

## Compatibility

`_pl_lad_ok = 0` in `create_defaults` means an older saved project takes
exactly the ladder it had. `polyline.cfg` 1.73 -> 1.74 so saved projects
migrate.
