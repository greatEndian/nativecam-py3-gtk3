# 039 — Z limits measured from the workpiece face

2026-08-13, branch `liveTooling`, from `7ebe403`. The useful half of gaps **8**
and **14**.

## What was asked

The reference package gives each Z limit a **mode, a datum and an offset**. Its
datums — Model front, Model back, Chuck front, Selection — point at solid
geometry we do not have, and `POLYLINE-GAPS.md` already records why copying that
vocabulary would leave parameters that can never resolve. It also records the
version that *can* work here:

> *"What survives the translation is pointing at **our own** objects: the
> Workpiece's stock diameter and face Z. That single idea would close the useful
> half of gaps 8 and 14 at once."*

Until now `param_fr_z` and `param_e_z` were absolute Z and nothing else.

## The blocking question, settled before anything was designed

The trim happens in **Python at generation time**, inside `resolve_points`. Two
facts make the workpiece hard to reach from there, and both had to be checked
rather than assumed:

- **a `Feature` has no back-reference to its tree.** It holds `attr` and
  `param`, nothing else. There is no walking to a sibling from inside
  `resolve_points(polyline_feature)`.
- **`lathe_sections` imports nothing from `ncam`** by design — that is what
  keeps it GTK-free and unit-testable — so it cannot look the workpiece up
  either.

`ncam.py:2461` states the general constraint outright: *"a cfg `<exec>` can only
reach ncam's module namespace"*, and solves it for the tip-comp values by
promoting them to module globals.

**The mechanism already existed, one layer up.** `to_gcode`'s tree walk already
publishes the tool change's values as it passes them, with the reasoning in the
code:

> *"Features are processed in order, so by the time a later feature asks, the
> nearest preceding tool change has spoken."*

The Workpiece is the **first** feature in the tree, so the same argument covers
it exactly. The walk now sets `lathe_sections.WORKPIECE_FACE_Z` when it passes a
`workpiece` feature, and clears it at the start of every build so a face left
over from a previous generation cannot silently datum this one.

Direction of the dependency: **`ncam` → `lathe_sections`**, which already exists
(`ncam.py:2806` imports it). `lathe_sections` still imports nothing from `ncam`.

## What was built

- `PARAM_FR_Z_DAT` / `PARAM_E_Z_DAT`, combos: **Absolute Z** (0, the default and
  what the value has always meant) or **From workpiece face** (1).
- `z_limit_abs(feature, which)` resolves a limit through its datum to the
  absolute Z the trims already take. `trim_to_front_z` / `trim_to_end_z` are
  **unchanged**, so every contour, section window, ladder and table inherits the
  datum without knowing it exists.
- `_pl_begin_z` calls the same resolver. A front limit that moves without
  `begin_z` moving leaves the levels sweeping from the old place — the trap
  `analysis/025` recorded and the tangential extension hit again.
- **The sign**: datum 1 measures *into* the stock, so absolute = `face - value`.
  That makes the number read the way a machinist says it, "40 from the face",
  rather than as a coordinate that happens to be negative.
- **No Workpiece in the tree** → the value is taken as absolute, which is what
  every existing project already does. Not silent: `build_z_limit_note` emits a
  WARNING comment into the program.

`polyline.cfg` → **1.55**.

## Measured

**The default changes nothing.** Move list hashed with the feature present and
with it reverted (`git stash`), on three projects:

```
testing_15_5   328 moves   935de6981007   identical
testing_15_6   322 moves   2b98722a3e21   identical
testing_15_2   256 moves   c908bba0b1f1   identical
```

**The datum does what it says**, on testing_15_2 — the project whose limit
numbers `test_end_z` established, so the probe is anchored to a figure already
known to be right rather than one invented here:

```
absolute -40                 back-most cutting Z -40.6043   (the known number)
datum, 40 past the face      back-most cutting Z -40.6043   identical
   same, workpiece at -10    back-most cutting Z -50.6043   follows the face
absolute -40, workpiece -10  back-most cutting Z -40.6043   does not follow
```

The last two are the pair that matters: a datum follows the workpiece and an
absolute value does not, which is the whole difference between the two modes and
something no single measurement could show on its own.

## Noticed, not fixed, and not caused here

On **testing_15_5** an End Z limit does not bite at all — an absolute `-40`
still reaches Z-70.4. Verified pre-existing by running the same case with this
change stashed: identical. Out of scope, but worth an open point.

## Verified

`test_z_datum` (new), `test_end_z`, `test_all_projects`, `test_extension`,
`test_below_inner_radius`, `test_peck`, `test_leftover`, `test_x_continuity`,
`test_behind_boss_ladder`, `test_rough_comp`, `test_stock_to_leave`,
`test_rough_ends`, `test_rough_overlay`, `test_ladder`, `test_floor_ladder`,
`test_ramps`, `test_section_length`, `test_resume_envelope`, `test_pane_layout`,
`test_lathe_validation`, `cam_map`, flake8 both lists.
