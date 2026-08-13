# 038 — Cutting past the End diameter, and the pip that needs it

2026-08-13, branch `liveTooling`, from `bd50c55`. Gap **13** of
`POLYLINE-GAPS.md`, first in the build order set by `analysis/037`.

## What was asked

The reference package: *"an adjustment to a Face or Part cut to position the
tool nose past the Inner Radius position. Use this to cut past the Centreline of
the part."* Pictured as *Cut up to the CentreLine* against *Cut past the
CentreLine*.

## Why it is needed

Facing to centre with a round nose leaves a **pip**. The nose is a circle, so
when its centre reaches the axis the cutting edge has not yet swept the last of
the material and a small cone stands on the axis. Running on past by about the
nose radius removes it.

## Where it went, and why not the polyline

**`cfg/lathe/facing.cfg` + `lib/lathe/facing.ngc`.** The dependency map picked
this gap first precisely because it is a **leaf**: `o<facing>` has exactly one
caller, `facing.cfg:280`; nothing else reads its `end_x`; it needs no parameter
window; and it never touches `resolve_points` or `finish_profile`, the choke
points every contour and table derives from.

**Not the polyline.** Its End diameter is the final diameter of a *turning*
region and reaches `poly_lathe_mill` as `final_radius`. Running a turning pass
past the spindle axis is not a thing — the pip is left by a *face*. A parameter
there could never sensibly be used.

**The spec's open question — "facing, parting, or both?" — answered itself.**
There is no parting operation in this codebase, so "both" was not available.
Parting inherits the parameter when it is built. No guess was required, which is
why this one could proceed while gap 1 could not.

## The implementation

One adjustment, at the single point where `end_x` is read:

```
o<bir> if [#<_fc_below_ir> GT 0.000001]
    ... direction from the ORIGINAL #1 and #2 ...
    #<end_x> = [#<end_x> + #<bir_dir> * #<_fc_below_ir> * #<_diameter_mode>]
o<bir> endif
```

Three things in that are deliberate:

- **Applied where `end_x` is read**, so everything downstream inherits it at
  once. `end_x` feeds the roughing passes, the finish pass, the lead-out fillet
  and the tip-comp vector; adjusting any one of them alone would leave the
  others disagreeing.
- **Direction from the original `#1`/`#2`**, not from the extended value. A
  distance large enough to carry `end_x` past `begin_x` would otherwise flip the
  test at `o<f_dx>` and invert the whole operation.
- **Scaled by `_diameter_mode`.** `_fc_below_ir` is a radial length while
  `end_x` is in machine X units — the same conversion `#2` already gets. This is
  the exact class of error that made the tangential extension move a surface
  1.5 mm for a 3.0 mm request (`bd50c55`), so it was checked against the
  produced surface rather than the arithmetic.

**A global, not a 16th CALL argument.** `facing.ngc` is re-read at runtime while
a saved project keeps its stored template until it is loaded, so a new argument
lands on one side only — the fault that crashed LinuxCNC in `ba3fb0c`.
`cfg/lathe/facing.cfg` → **1.25**; `#<_fc_below_ir>` defaulted in
`create_defaults`.

## Measured

`testing_15_5`, how far the facing feeds actually reach in X:

```
default / 0.0     6 facing feeds, reaching X 0.0000     (the centreline)
below_ir 1.0      6 facing feeds, reaching X-1.0000
below_ir 2.0      6 facing feeds, reaching X-2.0000
```

Exactly the distance asked for, in the direction the cut was already going, and
**the pass count does not change** — it lengthens the cut, it does not add a
pass.

**And the untouched case is provably untouched.** The whole move list of
`testing_15_5` was hashed with the feature present and with it stashed away:

```
with the change (default 0)   484 moves   51ab329033b339b3861258ecffa4be26
baseline (change stashed)     484 moves   51ab329033b339b3861258ecffa4be26
```

Identical, move for move.

## Verified

`test_below_inner_radius` (new), `test_all_projects`, `test_extension`,
`test_peck`, `test_leftover`, `test_x_continuity`, `test_behind_boss_ladder`,
`test_rough_comp`, `test_stock_to_leave`, `test_rough_ends`,
`test_rough_overlay`, `test_ladder`, `test_floor_ladder`, `test_ramps`,
`test_section_length`, `test_resume_envelope`, `test_end_z`, `test_pane_layout`,
`test_lathe_validation`, `cam_map`, flake8 on both lists.

## Still open

The reference names *Face or Part*. Parting has no operation here; when one is
built it should read the same `#<_fc_below_ir>` rather than inventing a second
parameter for the same idea.
