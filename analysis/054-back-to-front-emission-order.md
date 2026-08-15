# 054 — Back to front is an emission order, not a second decomposition

2026-08-15, branch `liveTooling`, from `86eb6b5`. Closes the open point
`analysis/052` scoped and did not start.

## What was asked

greatEndian: *"I select Roughing direction front to back - ok, back to front -
is mess, it creates messy preview and mess Gcode ... path have to be same Gcode
as Front to back but movement is from last polyline reference to front, means
rough all long passes from last reference to first, then last recognized
section rough, last recognized section - 1, repeating to first/front
section"*.

Three rules, and the third is the one that decides the design: **the cut set is
the front-to-back set, unchanged.** So `param_dir` = 1 is an ORDER, not a
geometry.

## The probe, validated first

`analysis/052` published 45 level cuts front to back, 40 back to front, one
shared, on testing_15_6 with sectioning on. A probe that cannot reproduce those
is not a probe, so it was checked before anything was touched:

```
front -> back    45 level cuts     44 distinct Z spans
back  -> front   40 level cuts     40 distinct Z spans
shared 0   only f2b 44   only b2f 40
```

Same numbers, and the apparent disagreement is arithmetic, not measurement:
front to back emits r34.0636 Z0 -> -31.2092 **twice**, so 45 cuts are 44
distinct spans and `052`'s "44 not in back to front" leaves nothing shared
rather than one. Recorded because the "one shared" figure will otherwise be
carried forward as if it were a real cut.

## Root cause

Two halves of one mistake, and either alone would have been enough.

1. **`poly_lathe_mill.ngc` swept the reversed record array.** `r_pds` was
   `#<_mill_data_rev>` at `dir == 1`, so `e_z`/`l_z`, `z_dirw`, the crossing
   mesh, the windows, the ladder and every stop were computed in a reversed
   frame.
2. **`lathe_sections.py` rebuilt its tables on a reversed profile.** Both
   `build_sections_gcode` and `build_floor_ladder_gcode` did
   `points = list(reversed(points))`, and `build_flank_gcode`,
   `build_entry_contour_gcode`, `build_floor_contour_gcode` and
   `build_stop_contour_gcode` all passed `rough_dir` straight into geometry
   that branches on it - which side of a peak the trailing flank shadows, which
   way `resume_envelope` runs.

So back to front asked a different question and got a different answer. Nothing
in either half was reversing an *emission*; both were reversing the *input*.

`analysis/052` had already ruled out fixing half of it: disabling only the two
Python reversals makes it worse, 34 cuts, still disjoint. That is consistent
with this root cause and is why the cheap fix does not exist - the two halves
have to move together.

## The fix

**One decomposition frame, reversed emission.** The split is deliberate about
which side of the line each piece falls:

- **Python decides the ORDER**, at generation time. `rough_frame_dir()` maps
  direction 1 to frame 0 for every table that feeds the roughing scans, so the
  windows, bands, floor stages, reachable envelope, entry/stop/floor contours
  and the resume envelope are the front-to-back ones. `_sections_back_to_front()`
  then re-orders the finished window list - **within each radius band**, since
  bands must stay highest-first or the tool would drop to the deepest levels
  before the stock above them is gone - so the last recognised section is
  visited first. The `.ngc` walks the table it is given and decides nothing.
- **The `.ngc` reverses only the MOVEMENT.** `poly_lathe_mill` sets the new
  global `#<_pl_cut_rev>`; `lathe_level_pass` computes its whole interval - the
  crossing scan, the multi-crossing replay, the entry contour, the stop table -
  in the front-to-back frame exactly as before, and then swaps which end the
  tool arrives at (`em_z0`/`em_z1`) and which way it travels (`e_dir`).

What moved out of O-code: nothing new was added to it. The section visit order,
which is the part of greatEndian's spec that is a decision, is answered in
Python and arrives as table order; the `.ngc` gained one flag and a sign, not a
rule. `poly_lathe_mill` lost its `o<rpick>` branch and no longer needs the
reversed record array for roughing at all.

Three places where a reversed pass cannot simply mirror, all in
`lathe_level_pass` and all gated so front to back is untouched:

- **the profile-angle ramp is dropped** (`pa_on = 0`). It is armed from the
  entry-contour crossing at `z_start`, and `z_start` is where a reversed pass
  now *finishes*.
- **the straight lead-in is dropped**, and the approach descends at the
  interval end with no Z stand-off. The lead runs backward from the pass start
  along `+e_dir`; a reversed pass starts where the profile rises above the
  level - that is what stopped the cut - so backward from there is inside that
  material. The floor allowance still leaves the surface `lvl_d` below the
  level at the descent point.
- **the lead-out radius is clipped rather than the cut end pulled back.** The
  pull-back exists to land the arc tangent to the pre-finish wall; a reversed
  pass ends in air, and pulling back would shorten the cut and break the very
  set equality being asked for.

## Measured

Gate 1 and 2, four projects, both sectioning modes. `spans` are Z spans taken
unordered, so a reversed cut still matches its forward twin:

```
                     f2b cuts/spans   b2f cuts/spans   shared  onlyF onlyB   b2f reversed
testing_15_6 sect=0      42 / 42          42 / 42         42     0     0        42/42
testing_15_6 sect=1      45 / 44          45 / 44         44     0     0        45/45
testing_15_5 sect=0      45 / 45          45 / 45         45     0     0        45/45
testing_15_5 sect=1      47 / 46          47 / 46         46     0     0        47/47
testing_15_2 sect=0      27 / 27          27 / 27         27     0     0        27/27
testing_15_2 sect=1      30 / 29          30 / 29         29     0     0        30/30
testing_15_4 sect=0      29 / 29          29 / 29         29     0     0        29/29
testing_15_4 sect=1      29 / 29          29 / 29         29     0     0        29/29
```

45, not 40, and the SET matches - not merely the count. Every back-to-front
pass travels from its back end toward the front, 45 of 45.

**Order**, testing_15_6 sectioning on, the `#3401+` window table:

```
band                     front to back                      back to front
65.318 .. 1e6    [0,-70.4]                          [0,-70.4]
40 .. 65.318     [0,-32.5]  [-32.5,-70.4]           [-32.5,-70.4]  [0,-32.5]
0 .. 40          [0,-1] [-1,-20] [-32.5,-45]        [-45,-70.4] [-32.5,-45]
                 [-45,-70.4] [-20,-32.5]            [-20,-32.5] [-1,-20] [0,-1]
```

The long full-length window stays first and is now cut from Z-68.892 to Z0;
below it every band runs last-section-first. Artificial sectioning
(`param_sec_len` 20) is the clean case - one band, six slices:

```
front to back   [0,-1] [-1,-20] [-20,-32.5] [-32.5,-45] [-45,-57.7] [-57.7,-70.4]
back to front   [-57.7,-70.4] [-45,-57.7] [-32.5,-45] [-20,-32.5] [-1,-20] [0,-1]
```

**Gate 3, front to back unchanged.** Every one of the 39 demo projects
regenerated before and after; the ONLY textual difference in any of them is the
one line the new global adds to the defaults block:

```
64a65
> #<_pl_cut_rev>              = 0.0
```

**Gate 4**, `test_x_continuity` and `test_leftover` extended to run both
directions - they had only ever been asked about one - and green in all four
combinations on both projects, with their negative controls still firing (the
leftover control fires on 21 of the 21 projects that carry it).

Plus, because a reversed approach descending in the wrong place would gouge
rather than leave metal, the deepest cut past the pre-finish target, same
construction `test_rough_comp` uses:

```
                        f2b        b2f
testing_15_6 sect=0   9.7335     9.7334
testing_15_6 sect=1   9.8530     9.8529
testing_15_5 sect=0   0.2208     0.2184
testing_15_5 sect=1   0.2202     0.2199
```

Identical to within 0.0024 mm. (The 9.8 figures are the end-wall artefact this
probe does not guard against - `test_rough_comp`'s `radius_span` exists for
exactly that, and records 4.7405 mm at Z-69.4 on testing_15_2 in every mode.
What matters here is that the two directions agree, not the absolute value.)

`check_tangent` PASS on both programs, min |dot| 1.00000. `cam_map` six checks
clean, `test_all_projects` all 39 green, flake8 clean.

## Why it was not caught earlier

Because nothing ever ran the gate in the other direction. `test_x_continuity`,
`test_leftover`, `test_rough_comp`, `test_ladder` and the rest all generate at
`param_dir` = 0 - the project default - so a decomposition that lost five of
its 45 cuts, and shared one with the correct one, passed every check in the
repo. Both tests now take a direction; that is the durable half of this fix.

## Attempts and dead ends recorded

- **Reversing only the two Python profile reversals** - tried in
  `analysis/052`, measured at 34 cuts and still disjoint, reverted. It is
  consistent with the root cause above: the `.ngc` was still sweeping the
  reversed array, so removing half the reversal left the two halves
  disagreeing rather than agreeing.
- **Mirroring the lead-in instead of dropping it** was considered and rejected
  before it was written: the lead offsets along `+e_dir` from the pass start,
  which on a reversed pass is inside the material that stopped the cut. The
  forward direction has a Python answer for the same problem - `resume_envelope`
  pushes a resume point back by the lead length so the lead fits in air - and
  the reversed direction has no such table yet. See below.

## Still open

- **The lead-in and the profile-angle ramp are absent on a reversed pass.** The
  mirror of `resume_envelope`/`entry_contour` - a table saying, per level,
  where a pass approaching from the back may descend and at what angle - is the
  next step, and it belongs in Python beside the ones that already exist.
  Measurable consequence today: the reversed roughing leaves slightly more
  metal at the pass ends, 1.1827 mm against 0.7219 worst standing on
  testing_15_5 sectioning off, both well inside the one-depth-of-cut bound and
  neither forming a wide region.
- **Interval order inside one level is still front-first.** Where a boss splits
  a level into two disjoint intervals - three levels of 45 on testing_15_6 -
  the front interval is emitted before the one behind the boss, so the tool
  works front, then jumps back. Strictly, *"movement from last reference to
  front"* wants the rear interval first. The intervals are discovered at
  runtime by the crossing scan, so emitting them in reverse needs either a
  scratch array or a dry-run pass in the `.ngc`; neither was worth attaching to
  this change. Front to back has the same alternation, so it is not a
  regression.
- **Natural sectioning's weakest-first ranking is replaced by section order in
  direction 1.** `rank_weakest_first` is a rigidity strategy - keep the rest of
  the bar at full diameter while the weakest section is roughed - and
  greatEndian's spec asks for geometric order instead. Both were implementable;
  his words were followed. If he wants weakest-first preserved in both
  directions, `_sections_back_to_front` is the single place to change.
- **`param_dir` = 2, "both directions", is untouched** and remains its own open
  point. `rough_frame_dir` passes 2 through unchanged on purpose.
