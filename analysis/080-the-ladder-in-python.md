# 080 — the roughing ladder, in Python and proved against the O-code

**Asked**: greatEndian, 2026-09-03 — *"do the ladder into python"*.

## Stage one only, deliberately

`roughing_ladder()` computes the level radii at generation time. **Nothing in
the toolpath reads it.** `poly_lathe_mill` still walks its own ladder and the
motion is untouched.

That is the order I set out and it is not caution for its own sake: replacing a
working ladder with a plausible one is precisely how the anisotropic stock to
leave cost four rounds. The replica is written first and proved against the
running O-code; only then is it worth wiring in.

## What it replicates

All of it is arithmetic on values known before the program runs:

```
dirsign      from start vs final radius
rough_target final + dirsign * fin_off
step_target  rough_target + dirsign * prefin_off
lad_tgt      step_target, or floors[0] when there are floor stages
             passes = FUP(|lad_tgt - start| / doc), step = span / passes
pass_from    whole depths of cut from a floor rounded outward instead
sect_top_r   the ceiling, clamped into the band the ladder spans
p1 / p2      phase 1 in whole steps, phase 2 SPREAD evenly
per window   sect_mode 1 starts at the stock, Natural at the ceiling
floor stages re-anchor on each in turn
```

**The runtime still decides what each level DOES** — skipped as thin, refused
as blocked, outside a window's radius band, split into disjoint intervals — and
none of those change the level SET. That is why this can be a pure function,
and it is also why the ladder is a SUPERSET of what gets cut.

## The parallel run, and what it caught

5 projects × 2 sectioning states × 3 directions = 30 configurations. Every
level the program actually cuts must lie on the predicted ladder.

**First run: 15 of 30 failed, each with exactly one level off — always
r20.516.** That is the first level of the SECOND floor stage on testing_15_4,
_15_5 and _15_6. My replica walked to the first floor stage and stopped, where
`poly_lathe_mill` re-anchors on each stage in turn:

```
fl_n     = FUP(|next stage - current| / doc)
cut_step = (next stage - current) / fl_n
```

Reading the O-code had not shown me that. Running the two side by side did, and
the identical radius across three different projects is what made it obvious it
was structural rather than a rounding drift.

**Second run: 0 of 30.** Every cut level, every project, every direction, every
sectioning state, within 0.002 mm.

`test_ladder_python` is that sweep, with a guard that the sweep actually ran -
a comparison over zero configurations would pass silently.

## What is NOT proved

The ladder is a superset. This shows every cut level is on it; it does not show
the extra levels are exactly the ones the runtime skips. **That is the next
gate and it has to come before the `.ngc` reads anything**: predicted-minus-cut
must equal skipped-plus-blocked-plus-out-of-band, per configuration.

Until then this is a verified prediction, not a replacement.

## Gates

`test_ladder_python` (61 assertions), `test_ladder`, `test_leftover`,
`test_x_continuity`, `test_ramps`, `test_sections`, `test_bidir_warn`,
`cam_map`. Motion is untouched by construction - no `.ngc` or `cfg` was edited.

## Still unknown

- Whether the extras match the runtime's skips exactly, as above.
- `roughing_ladder` takes its inputs as scalars read back out of the generated
  program. Wiring it for real means taking them from the Feature instead, and
  the two paths must agree - `_pl_rgh_hi_r` and `_pl_rgh_lo_r` already come
  from `rough_radius_bounds`, but `fin_off` and `prefin_off` are read here from
  the emitted `#3144` / `#3156` rather than from the parameters.
