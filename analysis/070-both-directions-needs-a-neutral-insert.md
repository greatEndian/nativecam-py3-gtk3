# 070 — Both directions needs a neutral insert, and now says so

**Asked**: greatEndian, 2026-09-01 — *"whole time is open both direction
roughing.. go online and study what that means"*, then *"warn and proceed ..
build it"*.

## What the trade says

Standard canned cycles (G71/G72) are **unidirectional**: cut one way, rapid
back, repeat. CAM packages add bidirectional roughing as a zigzag - cut, step
over, cut back - and the saving is the return rapid.

The caveat is stated plainly by machinists and is not optional:
**bi-directional turning wants a NEUTRAL insert, because an LH or RH tool will
rub in the opposite direction.** Sandvik's PrimeTurning exists precisely because
ordinary inserts cannot do this - it needed purpose-built "all-directional"
geometries (Type A light, Type B rough) to cut both toward and away from the
chuck - and in CAM terms, "tool holder settings and insert settings determine
the directions and geometries that your tool can cut."

Sources: MHCC's G71 chapter, gcodetutor's G72 page, the Practical Machinist
thread "Bidirectional cutting on lathe", Modern Machine Shop's "A New Turning
Process Enables Cutting In Reverse", and Esprit's tool-setup documentation.

## What NativeCAM was doing

`rough_dir` 2 sets `_pl_cut_alt`, rides frame 0 - identical windows, levels and
intervals to front-to-back - and `lathe_level_pass` flips `_pl_cut_rev` after
each pass that emitted motion. A true zigzag, and it **assumed a neutral tool
without ever checking**. With the demo T2 (Q2, an ordinary right-hand OD
insert) half the passes ran with the trailing flank leading.

That is the same blind spot `analysis/069` closed for the profile-angle ramp,
one level up: there it was the approach move, here it is the whole pass.

## What was built

A `[VALIDATION]` warning in `cfg/lathe/polyline.cfg` (version 1.66 -> 1.67):
`param_dir` = 2 together with `lathe_sections.ramp_facing(orient) != 0` - a
directional insert - names the orientation, says the trailing flank will lead on
alternate passes, and points at the neutral orientations 6, 8 and 9.

**Warn and proceed, by greatEndian's choice.** Nothing is refused: a saved
project must keep generating, and the tool table cannot express every real
holder - the insert in the machine may be neutral even when Q says otherwise.

## THE PREREQUISITE: msg_inv blocked every headless run

This warning could not have been added at all before fixing that. `msg_inv`
prints, then builds a modal dialog and calls `dlg.run()`, which waits for a
button. From `gen_project.py` or any test there is nobody to press it, so the
generator hangs with nothing to show but the print. It is the reason
`openPoints.md` carried "msg_inv at severity 1 blocks any headless run".

`ncam.py` now returns after the print when there is no visible toplevel window.
In the GUI there always is one; in a batch run there never is, and the message
is already on stdout, which is all a batch caller can use.

`test_bidir_warn` asserts this directly - all six combinations must still
produce a program - so a future validation cannot quietly reintroduce the hang.

## Measured

| insert | direction | warns | generates |
|---|---|---|---|
| T2 as shipped, Q2 (directional) | both directions | **yes** | yes |
| T2 as shipped, Q2 | front to back | no | yes |
| T2 as shipped, Q2 | back to front | no | yes |
| T2 as Q9 (neutral) | both directions | **no** | yes |
| T2 as Q9 | front to back | no | yes |
| T2 as Q9 | back to front | no | yes |

The neutral half is the non-vacuous control: without it a warning that always
fires would pass the reported case. It runs from a scratch config copy with one
character changed, Q2 -> Q9, so orientation is the only variable.

## Gates

`cam_map`, `test_cam_map`, `test_leftover` (24/24 control - and the cfg version
bump migrates every saved project, so this also proves the migration),
`test_ramp_orient`, `test_ramps` (68), `test_x_continuity`, `test_ladder`,
`test_leads`, `test_sections`, `test_skip_short`, `test_air_leads`,
`test_lathe_validation`, `test_coord_mapping`, and the new `test_bidir_warn`
(13 assertions).

## What this does NOT do, and it matters

The warning tells the truth; it does not make Both directions correct.

- **`flank_sides` still picks the shadowed side from the roughing direction
  alone.** For `rough_dir` 2 it was collapsed to frame 0, so the reachable
  envelope is computed for ONE direction while the passes run BOTH ways. That is
  the real blocker to Both directions being right rather than merely fast, and
  it is unmeasured.
- **The entry and exit leads are not yet gated per pass direction.** The ramp is
  (`analysis/069`); the leads are not.
- **The intermittent Both directions + Regenerate crash is untouched.** It is
  not a generation fault - all three directions generate clean here - so it
  needs a traceback from a live AXIS session.
