# 072 — gaps 10 and 14: the radial limits get a datum and a reference point

**Asked**: greatEndian, 2026-09-02 — *"fix 10 and 14"*, the two entries the
reference-CAM re-read had named as worth doing.

## What they were

**14 — radial limits as references.** A diameter limit was a number and nothing
else. The Z half had already been done: each Z limit carries a datum, Absolute
or From workpiece face. The diameter half had not.

**10 — Tool Limit, cutting edge vs contact point.** Every limit we have is on
the CONTROL POINT, so a diameter limit could not say whether it meant where the
cutting edge stops or where the nose touches. The two differ by exactly the
nose radius.

## What was built

`x_limit_abs(feature, which, nose_r=None)` resolves both **in one place**,
because they are two adjustments to the same number and applying them
separately would let them disagree.

- **Datum**: `Value` (0) is the diameter itself and stays the default; `Stock
  OD` (1) and `Stock ID` (2) make it an offset from the Workpiece's own
  diameter, so 0 from the OD is the bar and a negative offset comes in from it.
  This is the vocabulary `cfg/lathe/facing.cfg` already uses - borrowed, so the
  two operations read the same, rather than reinvented.
- **Reference point**: `Cutting edge` (0) is the control point and what the
  value has always meant; `Contact point` (1) shifts by one nose radius so the
  stated diameter is where the nose TOUCHES - outward on OD, inward in a bore,
  because the material is on the other side.

Three new parameters in `polyline.cfg` (1.68 -> 1.69): `PARAM_B_X_DAT`,
`PARAM_E_X_DAT`, `PARAM_X_LIMIT`. `WORKPIECE_OD` / `WORKPIECE_ID` and
`TOOL_NOSE_R` are published by `to_gcode`'s walk exactly as `WORKPIECE_FACE_Z`
and `TOOL_FRONT_ANGLE` already were - `lathe_sections` imports nothing from
`ncam` and a Feature has no back-reference to its tree.

`param_b_x` is not only a limit: it is also the profile's ORIGIN and the stock
reference for sectioning and the X-wall detour.

**So the two settings reach different things, and that is greatEndian's ruling**
— 2026-09-02: *"origin should stay put, only the ladder bound moves"*.

- **The DATUM applies to both.** "Start at the stock OD" has to carry the origin
  with it, or the profile begins where the limit no longer is.
- **CONTACT POINT applies to the cut alone** — not the origin, not the
  sectioning stock envelope, not the X-wall stand-off. Those three ask where the
  MATERIAL is; the tool reference point is about where the CUT must stop.

Two named functions carry the distinction so it cannot blur: `x_stock_ref`
(datum only) for the three material references and the two emitted globals, and
`x_limit_abs` (datum + contact) for the ladder bound and the OD/ID check. The
reference package has one limit where ours doubles as a datum, so it could not
settle this; the split is ours.

## THE FAULT THIS NEARLY SHIPPED WITH

The first working version resolved the limit correctly and **changed nothing**.
`_pl_b_x` went 70.0 -> 70.8 in the emitted program, and the toolpath was
**byte-identical**.

The five internal consumers call `x_limit_abs(feature, 'begin')` and the
signature defaulted `nose_r=0.0`, so none of them ever saw the shift. It was
visible only because the check measured the MOTION and not just the emitted
number - had it asserted the global alone it would have passed, and gap 10
would have shipped as a parameter that does nothing. That is the
`Retract = Minimal` failure exactly (`analysis/065`).

Fixed by publishing `TOOL_NOSE_R` and defaulting `nose_r=None` to mean "the
tool that is loaded". `test_x_limits` asserts the motion moves, not the global.

## Measured

`_pl_b_x` is the ORIGIN, so the two settings show up in it differently - which
is what makes the ruling checkable rather than a matter of belief:

| | `_pl_b_x` (origin) | motion |
|---|---|---|
| testing_15_9, defaults | 70.0000 | `6cf361a8b8f5`, 1575 moves - **unchanged** |
| datum Stock OD | **140.0000** - moves | moved, 1580 moves |
| contact point | **70.0000** - stays | **moved**, 1578 moves |
| both | 140.0000 | moved, 1587 moves |
| testing_15_2, defaults | 60.0000 | `e2744cbb6ff0`, 327 moves - **unchanged** |
| datum Stock OD | 120.0000 - moves | moved, 341 moves |
| contact point | 60.0000 - stays | **moved**, 333 moves |

The contact-point shift is one nose radius expressed as a diameter - R0.400 x
`DIAMETER_MODE` 2 = 0.8 - applied to the ladder bound, where it no longer
appears in the origin at all. The default hashes match the pre-change baselines
measured in `analysis/071`, so every saved project keeps the toolpath it has.

## Also worth recording

A literal `#<name>` inside an inline cfg `<exec>` is **not** decoded - the cfg
is INI-style, not XML, so `&lt;` stays as written and the interpreter is handed
`#&lt;_pl_b_x&gt;`, which fails with "bad number format". Every other emitter
returns its G-code from a Python helper; `build_x_limit_gcode` now does too.

## Gates

`cam_map`, `test_cam_map`, `test_leftover` (24/24 control, which also proves
the 1.69 migration), `test_ramps` (68), `test_sections`, `test_ladder`,
`test_x_continuity`, `test_air_leads`, `test_ramp_orient`, `test_bidir_warn`,
`test_flank_envelope`, `test_front_flank`, `test_leads`, `test_skip_short`,
`test_lathe_validation`, `test_coord_mapping`, and the new **`test_x_limits`**
(24 assertions: the arithmetic as units, defaults unchanged, and each setting
moving the toolpath).

## Still unknown

- ID work is paused, so the inward shift for `param_side` = 1 is implemented
  and unit-tested but never exercised end to end.
- The datum offsets from the stock diameter; it does not CLAMP to it. Setting
  Stock OD with a positive offset puts the limit outside the bar, which is
  legitimate (clearing an oversize blank) and also an easy way to ask for
  something meaningless. Nothing refuses it.
