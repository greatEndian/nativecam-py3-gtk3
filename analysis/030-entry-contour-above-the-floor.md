# 030 — The entry contour stood above the wrong surface

2026-08-11, branch `liveTooling`, merged from `entry-contour-fix` (`349d2ad`).

## What was reported

Two of the six roughing bugs greatEndian raised on 2026-08-11, on
`testing_15_5`:

- with **pre-finish offset = 0.0**, roughing still left something standing off
  the final contour — the yellow dashed line did not move;
- with the **regular offset at 1.0**, roughing behind the boss started from the
  older offset value, and the 2D view showed *"roughing entry is nearer to Z
  axis as the prefinish surface is"* — the entry sitting **inside** the surface
  it is meant to stand off.

They are one fault.

## The motion was right; the entry contour was not

First the report had to be split from the code, because the obvious reading was
wrong. Changing only `param_pf_off` on testing_15_5:

```
pf_off=0.01   50 level cuts, deepest level X=20.0000
pf_off=0.0    49 level cuts, deepest level X=19.5080     0.492 deeper
```

Roughing cuts closer when the pre-finish offset is zeroed, so **the levels do
honour it**. `#3156 = [#param_pf_off * #param_pf_on]` arrives as
`#<prefin_off> = #25` and `poly_lathe_mill:665` sets
`#<lvl_d> = fin_off + prefin_off`. All correct.

What ignored it was the **entry contour** — the surface a level may *begin*
cutting on. `build_entry_contour_gcode` offset the profile by `entry_off`
alone, which is **one roughing depth of cut**, and `ncam_preview_ui:1195` drew
the yellow twin from `TOOL_TABLE.get_rough_cut()` the same way. Neither added
the finish or pre-finish allowance, so the entry sat one depth of cut from the
**finished shape** whatever had been asked for.

That explains both reports exactly:

- zeroing the pre-finish offset cannot move a line that never depended on it;
- once the allowance exceeds one depth of cut — 1.0 against 0.508 — the entry
  necessarily falls **inside** the pre-finish surface.

## The rule

The floor already stands `fin + prefin` off the profile, so the entry belongs
at **`fin + prefin + one depth of cut`** — one cut's worth of clearance above
the floor, not above the part. Anisotropic on the two allowances the same way
the floor is; the depth of cut is added to both, because it is one cut's
clearance in whatever direction the surface faces rather than a radial-only
quantity.

The `.cfg` signature is unchanged, so **no version bump**.

## Blast radius, walked before editing

| consumer | reached via | verdict |
|---|---|---|
| ENTRY table 4200–4400 | `#<_pl_entry_base>/_n` → `lathe_level_pass.ngc:407` | moves outward — the point of the change |
| ramp directions, ERAMP 3200 | `build_entry_ramp_gcode(env, entry_off)` | built from the same `env`; its directions are surface tangents, unchanged by a parallel move |
| yellow overlay | `ncam_preview_ui.py:1195` | must move identically or the drawing lies — updated |
| cfg exec line 600 | passes `get_rough_cut()` as `entry_off` | signature unchanged |

## Measured

testing_15_5, entry and stop tables sampled at Z−50:

```
pf 0.254    entry X30.3540   stop X29.5720   entry outside stop
pf 0.0      entry X30.0933   stop X29.5720   moved in by 0.2607
offset 1.0  entry X30.8590   stop X30.0769   entry outside stop
```

The entry now responds to the pre-finish offset, and stays outside the
pre-finish surface at a large offset. Both symptoms gone.

## The test it invalidated, and greatEndian's call

`test_rough_comp` failed:

```
before   Off 0.1115   Native 0.0503   In CAM 0.0503
after    Off 0.0503   Native 0.0503   In CAM 0.0503
```

Nothing got worse — **uncompensated roughing improved to match compensated**.
The old assertions were keyed on the *gap* between the modes: Off had to
overcut at least 0.03 more, and each compensated mode at most three quarters of
Off. That gap existed only because the broken entry let an uncompensated level
begin too far in. With the entry fixed the gap is gone, and an assertion keyed
on it would now demand that roughing be **bad** in the uncompensated case.

greatEndian, 2026-08-11: *"the fault was real, merge it and rewrite the test"*.

The test now asserts the **absolute** overcut, which is what matters: the
pre-finish surface is the one the operator measures to dial in the finish
compensation, so cutting past it is what ruins the measurement.

**The bound sits between the two measured states**, which is what keeps it an
assertion: `0.08` clears the good case (0.0503) by 0.0297 and rejects the bad
one (0.1115) by 0.0315. A first attempt used 0.0508 — one tenth of the finish
offset, which *sounds* principled — and left **0.0005** of margin, an assertion
that would flip on rounding.

## Verified

`test_rough_comp`, `test_ramps`, `test_rough_overlay`, `test_ladder`,
`test_rough_ends`, `test_all_projects`, `test_stock_to_leave`, `cam_map`,
flake8 both lists.

## Still open

The other four of greatEndian's 2026-08-11 reports are untouched: sectioning
with a non-zero Z section length ignoring the back tool angle, sectioned passes
crossing each other in front of the boss, roughing using the per-side offset
instead of the separate Z one, and the missing first pass behind the boss.
