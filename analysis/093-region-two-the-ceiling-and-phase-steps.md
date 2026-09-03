# 093 — region 2: the ceiling and the two phase steps

**Asked**: greatEndian, 2026-09-03 — *"go on with region 2"*, the block
`analysis/092` named at `poly_lathe_mill:486-620`.

## What moved

`sect_top_r`'s initial value with both its clamps, and `p1_step` / `p1_first` /
`p2_step` / `p2_first`. `roughing_ladder` already computed all five.

`sect_top_r` is only **initialised** from Python. The phase-1 handover still
moves it at runtime and the level table still stands down when it does
(`analysis/091`), so the one genuine runtime feedback is untouched.

## The find, and the gate would not have caught it

**The O-code uses two different gates that read as one.**

```
o<sec_on> if [[_pl_sectioning GT 0] AND [_pl_sect_count GT 0]]   <- the ceiling
o<lad2>   if [ _pl_sectioning GT 0]                              <- the steps
```

A profile with Sectioning ON that `build_sections_gcode` declined to describe
therefore falls to `sect_top_r = step_target` **and still takes phase-1 steps
off that span**.

`roughing_ladder` takes ONE conflated flag - its callers pass
`sectioning and cnt > 0` - so reusing it for the emitter would have quietly
given such a profile `cut_step` instead. `ladder_phases()` now takes the two
flags separately and BOTH callers share it, so the predictor and the code that
will drive the machine cannot drift.

**No project in the sweep is that shape, so the motion gate could not have
caught it.** It came from reading the two conditions side by side.

## The gate

Both regions share `_pl_lad_ok`, so one flag disarms the head and the phase
steps together:

```
36 configurations, emitted in 36, absent in 0
MOTION IDENTICAL - on equals off, everywhere
```

Suite green: twelve gates, `cam_map`, `test_lathe_validation`, flake8. The
ladder gates were re-run immediately after the `ladder_phases` share, before
any `.ngc` edit, because that refactor touches the proved predictor.

## Still runtime, and still not shrunk

The `.ngc` has not lost a line - the computation stays as the fallback, for the
reason `analysis/092` gives. What remains of greatEndian's list:

- `lvl_floor` / `fl_prot` - per window AND per floor stage, so not constants.
- The decisions: thin, blocked, out of band, split into intervals.
- The ramp and stop machinery - `s_reach`, the clamp, the profile-angle
  approach.
- **The deletion pass**, once this has cut on the machine.

`w_total` was deliberately left alone: it is a direct read of
`_pl_sect_count`, not arithmetic, so moving it would add a global and remove no
decision.
