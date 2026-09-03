# Open points

The running list of what is not finished. Every new open point gets written
here as soon as it appears, and gets ticked off here as soon as it is done —
not left to be remembered.

> **Python first, O-code last.** Standing rule, all of it: solve the problem in
> Python at generation time and leave the `.ngc` walking a table. See CLAUDE.md.

**Conventions**

- `- [ ]` open, `- [x]` done. A finished item moves to **Done**, newest first,
  with the commit that closed it.
- A point that needs a decision from greatEndian is marked **NEEDS A CALL** and
  says what the choice is between. Nothing gets guessed twice.
- Numbers, not adjectives: if something is wrong by 9.73 mm, say 9.73 mm.

Branch: `liveTooling`. Last pushed: `d6aae05`.

---

## Building 2026-08-26 — the perpendicular X wall detour

greatEndian specified the shape and confirmed every assumption: degrees for the
tolerance, 2 degrees and 0.5 mm as defaults, moved to Python, rapid on the way
out, the existing lead settings, mode 2 only. And one correction that changed
the geometry: **the clean-up move is TWICE the stand-off**, *"because the will
stay some non removed material"* - at one it ends exactly on the stop point and
the two cuts only touch.

- [x] **STAGE 1 - the geometry and its validator, in Python.** `x_wall_indices`
  detects walls by ANGLE off the X axis, replacing a hard-coded `ABS[to_z -
  from_z] LT 0.0005` that does not scale: **2 degrees over a 5 mm rise is
  0.1746 in Z, 349 times that limit**, so a wall any machinist would call
  perpendicular read as a taper. `x_wall_moves` returns the five-move detour
  as (kind, z, x) with kind feed or rapid - which maps straight onto the record
  `dir` field `g123_lathe` already branches on, 1 feeds and 0 rapids, so no new
  runtime concept is needed.
  **Why Python at all**: the stop-short has to happen on the move BEFORE the
  wall, and `g123_lathe` sees one segment at a time - by the time the wall
  record arrives, that move is already cut. Only generation time can see a wall
  coming.
  `check_x_wall_moves` is the validator greatEndian asked for, stating the
  rules rather than the coordinates. `test_x_wall.py` runs both approach
  directions through it and **also feeds it four deliberately broken shapes** -
  a one-stand-off clean-up, a rapid where the face is cut, a feed for the lift,
  a stop that is not short - and requires each to be REJECTED. A validator that
  cannot fail proves nothing, which is what `test_ladder`'s skip-thin control
  had been doing. All 23 checks pass.

- [x] **STAGE 2 - the parameters.** `PARAM_XW_FRONT` 0.5 mm and `PARAM_XW_TOL`
  2.0 degrees, both `minimum_value = 0.0`, travelling as the globals
  `_pl_xw_front` / `_pl_xw_tol` because the `poly_lathe_mill` CALL is already
  at the 30 argument limit, with defaults in `create_defaults` or the file will
  not load. `polyline.cfg` 1.63 -> 1.64. `cam_map` 6/6; testing_15_7 and 15_8
  still generate and run at `param_dir` 0, 1 and 2.

- [x] **THE RESOURCE PROBLEM IS SOLVED BY NOT HAVING A FLAG AT ALL - option
  (d), and greatEndian's objection is what produced it.** They rejected the
  per-point flag outright, 2026-08-27: *"there could come any files with any
  number of points .. therefore the should not be limit that low"*. That is
  right, and it rules out (b) as well - ANY fixed table caps the profile.

  **Their own description contains the answer.** The sequence ends *"lead out
  and retract to property selected retraction behaviour"*: that IS a pass
  ending and another starting. So `split_contour_at_walls` splits the contour
  into sub-paths at each wall -
  **A** the contour up to the stop, **B** wall top -> corner -> clean-up,
  **C** the remainder - and each runs through the EXISTING lead-in, lead-out
  and retract machinery. No new motion concept, and the rapids between
  sub-paths are the existing inter-pass retract, already outside the material.
  Cost is **2 slots per sub-path in a directory** against walls that are few,
  the point tables keep stride 2, and **no profile gets a smaller ceiling than
  it has today**. `build_cam_comp_gcode` already emits a directory of
  `(base, count)` pairs that `cam_load` walks one at a time, so this extends a
  proven concept.
  Guarded by assertion: a profile with no wall, and the feature switched off,
  both come back **untouched** - which is what makes it safe to enable.
  32 checks pass in `test_x_wall.py`.

  - [x] **One of my own checks was wrong and the code was right**, recorded
    because it is the instrument trap CLAUDE.md names. "The clean-up passes
    the stop" was tested as `abs(-9.0) > abs(-9.5)`, which is false: Z is
    negative here, so bare magnitudes said the clean-up ended NEARER the wall
    when it ends a full stand-off further from it. Measured from the wall it
    is 1.0000 against 0.5000. The assertion now measures from the wall.

- [x] **STAGE 3 - DONE for In-CAM, and verified on testing_15_8.** The CAM
  directory is a flat list of sub-paths; both pass loops walk it and run the
  entries they own, backwards when the pass is reversed - cam_load reverses
  points INSIDE a path, so the order the pieces are cut in has to turn round
  with them.
  **Measured on testing_15_8**, all three detours: face at one Z, descending
  from outside, clean-up **1.0000 = 2 x 0.5000**, the previous sub-path ending
  **exactly 0.5000** short and the clean-up passing it by **0.5000**.
  Directory: 6 sub-paths - pre-finish 2 parts, finish 4.

  - [x] **A REGRESSION I CAUSED AND CAUGHT, and it is the slot budget again.**
    The first cut put the owner in the directory itself, three slots per entry.
    That cost one slot on EVERY project, and **testing_13_arcs was already at
    384 of 384**: it needed **386** and In CAM refused to compensate at all -
    *"the offset path needs 386 parameter slots and only 384 are safe"*.
    `test_leads` caught it. The owners now live in a separate table that only
    exists when something actually split, so the directory stays two slots per
    entry and **a project without walls pays nothing**. `_pl_cam_own` is 0
    there and entry k IS pass k, exactly as before.
    This is the fourth time the parameter-slot budget has bitten in this
    codebase. It is not a place to spend a slot casually.

  - [x] **The untouched case is PROVEN, not assumed**: testing_15_2 341 moves
    `3f98389e76f7` and testing_15_5 478 moves `2e60740fdab8`, hash-identical
    across the change, both with `#3157 = 0`. testing_15_7 has `#3157 = 2` and
    moves 472 -> 495, which is the feature working. Only projects with X wall
    cut on change at all.
    Gates: `cam_map` 6/6, `test_x_wall` 32 checks, `test_leads` **fully green**
    - including the testing_13_arcs case that was red before this work, which
    I have no proven explanation for and am not claiming credit for -
    `test_x_continuity` and `test_sections` pass, `check_tangent` **[VERDICT:
    PASS]** on testing_15_8, min |dot| 1.00000 over 136562 canon events.

- [x] **A DETOUR LANDED IN THE MIDDLE OF THE BOSS ARC — FIXED**, 2026-08-27.
  greatEndian: *"at boss segment start point of arc it generates infinite long
  orange stand still line in the tangential diraction to boss arc"*,
  `photo/infrontOfInfiniteLongLine_0.png`.

  **The culprit was already in my own validation output and I read past it**:
  `detour sub 3: top Z-20.0062 X40.6260, corner X40.0000` - a **0.626 mm**
  "wall" against real ones of 19.24 and 20.52. It is where the offset path runs
  the cylinder into the boss arc, and it is **exactly** perpendicular, dz
  0.0000, so no angle tolerance could ever separate it. My first theory - a
  near-perpendicular arc CHORD - was wrong, and measuring the chords is what
  showed it: they run 26.57, 33.09, 50.36, 75.25 degrees off X, none of them
  near the tolerance.

  **The discriminator is size, and a physical one was available**: a step
  shorter than the tool's nose DIAMETER is not a wall the tool could cut from
  outside - the nose rolls through it as a corner blend. `x_wall_indices` takes
  a `min_rise` and the caller passes `2 * nose_r`. No new user parameter.

  **The runaway, measured**: the longest feed in the program was **455.9729 mm,
  reaching X-435.1979**, ending at Z-20.0121 - the spurious wall. After the fix
  the longest feed is **69.5920** at X34.4831, an ordinary full-length pass.
  testing_15_8 goes from 6 sub-paths to 4, testing_15_7 from 495 moves to 480.
  Gates: `check_tangent` PASS min |dot| 1.00000, `test_leads` green,
  testing_15_2 `3f98389e76f7` and 15_5 `2e60740fdab8` still hash-identical.

  - [ ] **A LEAD THAT RUNS 455 mm IS ITSELF A FAULT**, and it is only masked
    now. An invalid detour triggered it, but nothing in the lead code refuses
    to emit a lead longer than the part. A guard there would have turned this
    into an error instead of a picture. Not built - there is no reproducing
    case any more, and a speculative clamp could hide a real geometry problem.

- [x] **THE DETOUR HELD X CONSTANT AND GOUGED THE BACK-ANGLE RAMP — FIXED**,
  2026-08-27. greatEndian: *"behind boss artificial angled tool back respected
  area where we need respect not just Z axis but X axis also in the final move
  back movement ... if there is arc or taper present movement have to be in all
  axis together"*.

  Both ends of the detour - the stop-short and the 2x clean-up - held X at the
  corner radius and moved in pure Z. That is right only where the surface into
  the wall is parallel to Z. Behind a boss it is the **artificial back-angle
  ramp**, and elsewhere an arc or a taper.

  **Measured on testing_15_8, and it was a gouge, not a cosmetic error.** The
  ramp rises **0.4617 mm of diameter over the 1.0 mm clean-up**:

  | detour | corner X | clean-up ends X | before |
  |---|---|---|---|
  | pre-finish | 49.9592 | **50.4209** | 49.9592 |
  | finish | 48.6819 | **49.1436** | 48.6819 |

  Holding X at the corner put the tool BELOW that rising surface for the whole
  move - up to **0.2308 mm of radius into the finished ramp**, on both passes.

  `_back_along` walks the path backwards by a Z distance and interpolates onto
  the segment the end falls in, so the stop carries whatever X the surface has
  there and the clean-up retraces the real vertices. Segments with no Z extent
  are stepped over rather than measured.
  Tested on a taper - stop at X21.9 and clean-up at X21.8 where the corner is
  22.0 - and on a multi-segment ramp, where the clean-up keeps every vertex it
  crosses instead of cutting the chord across them. The flat case is unchanged.
  Gates: `check_tangent` PASS min |dot| 1.00000, `test_leads` green,
  testing_15_2 `3f98389e76f7` and 15_5 `2e60740fdab8` hash-identical;
  testing_15_7 keeps 480 moves with new coordinates, which is the clean-ups
  following the surface.

- [x] **THE WALL FACE STARTED A NOSE RADIUS INSIDE THE BAR — FIXED**,
  2026-08-28. greatEndian, after confirming the detour shape itself is right:
  *"we have inlead X coordination again shifted toward the center by tool tip
  compensation and its not starting from the stock envelope"*, on both the
  pre-finish and the finish contour,
  `photo/leadInIssueAtFinishPrefinishPass_0.png`.

  The stored path is CONTROL points, shifted in by the tip compensation, so a
  wall running out to the bar had its top at **34.6000 radius against a 35.0000
  envelope** - the nose contacting the envelope at exactly one point. *"From
  mathematical point of view we reach this point 100%, but in reality
  everything have some stiffness and rigidity and everything will somehow
  bend"*, and what survives is a small sharp tip at the outside.

  **The asymmetry is the tell**: the pass END already adds the nose term -
  `_ex_tgt = _cut_phys_x + _pl_rgh_ox` in `lathe_poly_pass.ngc` - to run out to
  the envelope, and greatEndian had already approved that behaviour. Only the
  START was missing it.

  | | before | after |
  |---|---|---|
  | face top, control point | 34.6000 | **35.0000** - the envelope |
  | nose contact there | 35.0000, touching | **35.4000**, 0.4 past the bar |

  Guarded so it cannot drag an INTERNAL step out to the bar: the contact has to
  be reaching the envelope already before the control point is moved onto it,
  and a wall stopping inside the part is asserted to stay put.
  Gates: `check_tangent` PASS min |dot| 1.00000, `test_leads` green,
  testing_15_2 `3f98389e76f7` and 15_5 `2e60740fdab8` hash-identical,
  testing_15_7 keeps 480 moves.

- [x] **THE 2x IS TWO NUMBERS NOW, BOTH SETTABLE FROM CAM**, 2026-08-28.
  greatEndian: *"create from them Back lenght overlap UU(mm/inch) propert which
  will able us to control this movememnt from CAM ... also create parameter
  property in UU of before vertical segment lenght back offset"*.

  The second of those **already existed** - `X wall stand-off`, `param_xw_front`
  - and is exactly the distance before the vertical segment, so no duplicate
  was made. The new one is `X wall back overlap`, `param_xw_back`, how far the
  clean-up runs PAST the stop. The clean-up is **stand-off + overlap** instead
  of 2 x stand-off; the two were locked together only because the overlap was
  born as a correction to a 1x move.
  `polyline.cfg` 1.64 -> 1.65, `_pl_xw_back` a global with a default in
  `create_defaults`.

  **The defaults reproduce the old behaviour to the digit**, which is what
  makes it safe: with both at 0.5 the clean-up is still 1.0000, and
  testing_15_2 `3f98389e76f7`, 15_5 `2e60740fdab8` and 15_7 `7601dadb411c` are
  all hash-identical to the run before the split. Measured across the range:
  overlap 0.0 -> 0.5000, 0.2 -> 0.7000, 0.5 -> 1.0000, 1.5 -> 2.0000, and at
  zero the clean-up is asserted to end exactly ON the stop - the sliver case
  the 2x existed to prevent, stated as a measurement rather than a belief.

  - [x] **A signature trap caught by the tests, worth remembering.** Adding
    `back` as the fourth positional argument silently shifted every existing
    call: `split_contour_at_walls(pts, TOL, FRONT, 0.0)` had meant
    `min_rise=0.0` and became `back=0.0`. All callers are keyword now past the
    third argument.

- [ ] **STILL OPEN on the X wall.** Native compensation and the no-comp path
  do NOT get the detour - only In CAM does, because only the CAM branch has a
  path directory. `_pl_pf_*` and `_pl_fc_*` are single tables. The old
  `o<xw_00>` branch in `g123_lathe.ngc:38` is therefore LEFT IN PLACE: it is
  still the only X-wall handling those modes have. It cannot fire on a split
  sub-path - the wall segment there descends, and that branch requires
  `to_x GT from_x` - so the two do not collide.
  - [ ] A second measured probe worth keeping: my own directory reader went on
    using stride 3 after the layout changed and printed nonsense - owners of
    4776, counts of 4758. The generated file was right and the instrument was
    stale. Re-read the layout before trusting a probe across a format change.
  ~~STAGE 3 - the .ngc has to walk it, and there is a RESOURCE PROBLEM.~~ `cam_load` hard-codes `dir = 1` for every point, so nothing
  can currently emit the two rapids. The point tables are (z, x) PAIRS.
  **The numbered-parameter space is full**: windows run to `CAM_TOP = 4984` and
  `poly_add_item` owns #4984-#4999, so a new parallel flag table has nowhere to
  live. Three options, none of them free:
  - **(a) stride 2 -> 3 on the PATH tables only** - FC, PF and the CAM paths
    carry `dir` per point. No new window, but capacity halves: the FC window is
    200 slots, so 100 points becomes 66. **Measured on the real projects:
    `_pl_fc_n` is 21 on testing_15_7 and 15_8**, so there is room today - but
    66 is a real ceiling on a denser profile.
  - **(b) shrink another window** to make space for a parallel flag table.
  - **(c) keep pairs and send a tiny wall-INDEX table**, a slot per wall, with
    the O-code deriving which two records are rapids. Cheapest in slots but it
    puts the detour's shape back into O-code, against "moved to python".
  Not chosen unilaterally: the parameter-slot budget is exactly what cost four
  rounds on the anisotropic stock-to-leave, one of them an overflow that
  emitted a WARNING and silently fell back.

- [x] **A FALSE ALARM, recorded so it is not re-investigated.** testing_15_8
  dropped from 444 to 436 moves across the cfg edit and I suspected the
  migration had reset a parameter. It had not: `#3157`, `param_xw_dir`, went
  from 2 to 0 because **greatEndian re-saved the project at 09:44:07**, between
  the two runs. Check the file's mtime before blaming a migration.

## Reported 2026-08-26 — Save, the Both-directions crash, and the X wall

- [x] **A PLAIN SAVE, ABOVE SAVE AS, ON Ctrl+S — DONE.** greatEndian: *"add to
  Bar menu above Save Project As.. just Save to save only right open project
  with not pop up window"*, and *"Crtl+S is Save and Save as.. is selected from
  drop down menu"*. `actionSave` now writes back to `ncam.CURRENT_PROJECT`
  with no dialog and keeps Ctrl+S; `actionSaveAs` carries the chooser and sits
  below it in the menu with no accelerator.
  A project that has never been saved has no file to write back to -
  `new_project` sets `CURRENT_PROJECT` to the bare name `Untitle.xml`, not a
  path - so Save hands over to the dialog rather than inventing a location.
  The Ctrl+S key handler at `ncam_treeview.py:260` activates `actionSave` and
  needed no change; `set_actions_sensitives` now enables both.
  Gates: `test_menu_layout` walked 41 items with **0 dead actions**,
  `test_ui_panel` all pass.

- [ ] **"BOTH DIRECTIONS" + REGENERATE CRASHES, AND IT IS RANDOM.** greatEndian
  confirmed 2026-08-26 that it is intermittent, so it will not fall out of a
  single run. **It is NOT a generation fault**: testing_15_8 and testing_15_7
  both generate AND run clean at `param_dir` 0, 1 and 2 - 444 and 458 moves,
  no interpreter error, all three the same count. So it is GUI-side, in
  NativeCAM or AXIS. **Needs the Python traceback from the terminal that
  launched linuxcnc, captured when it actually happens** - without it any fix
  is a guess, and two GUI guesses have already been wrong this week.

## Changed 2026-08-26 — Skip short roughing passes is a typed length

- [x] **IT WAS A BOOL RESOLVING TO ONE FIXED LIMIT; IT IS A THRESHOLD NOW.**
  greatEndian: *"We have there property skip short roughing passes .. its radio
  buttion with fixed values .. change it to same like behaviour as is skip thin
  roughing passes"*. The switch evaluated to `5.0 * tip_comp_inputs()[0]` -
  5 x the nose RADIUS, 2.0 mm on the demo tool - so the only way to ask for a
  different limit was to change the tool. Now `type = float`,
  `minimum_value = 0.0`, 0 = off, and the `.cfg` reads
  `#<_pl_min_pass> = #param_min_pass` with no `<eval>` at all. `version`
  1.62 -> 1.63 so saved projects migrate.

  - [x] **THE RENAME IS THE LOAD-BEARING PART, and it was found by measuring
    rather than by reasoning.** A float parameter's stored `value` is in
    **INCHES** - `skip_thin` carries `value 0.0118110236` against
    `metric_value 0.3`. The old bool stored `1`, so keeping the id
    `param_skip_short` made that **1 inch = 25.400000 mm**. Measured on
    testing_15_6, the one project that had the switch ON: it generated with
    `_pl_min_pass 25.400000` against a longest pass of 69.59 mm, which would
    have skipped most of its ladder **in silence**. A bool and a float cannot
    share an id across this change, so it became `param_min_pass`.
    After the rename, testing_15_6 / 15_7 / 11 all come back at
    **`_pl_min_pass 0.000000`** - off, the cfg default, to be retyped
    deliberately. The DISPLAYED name is unchanged, so the panel looks the same.

  - [x] `test_skip_short.py` asks for the old bool's 2.0 explicitly so it goes
    on measuring what it always measured, and gained a check that the limit is
    **the number the operator typed** - it sets 3.7 and asserts 3.7 arrives.
    Without that, a switch resolving to 2.0 would still have passed "the gate
    has a real limit". All checks pass on both projects.

  - [ ] **testing_15_6 loses its setting.** It was the only saved project with
    the switch on and it now comes back off. greatEndian retypes a length
    there if it is still wanted - about 2.5 x the nose diameter is what the
    switch used to mean.

## Decided 2026-08-26 — phase 1 cuts at full depth, and nothing is spread

- [x] **PHASE 1 NO LONGER THINS EVERY PASS TO SUIT THE ROUNDING — DONE.**
  greatEndian asked why the first three full-length passes were thinner than
  the ones below. **Measured**: the section ceiling is radius **33.4671**,
  which is exactly where the change happens.

  | | span | ÷ doc | passes | step |
  |---|---|---|---|---|
  | phase 1, stock 35.0000 -> ceiling 33.4671 | 1.5329 | **3.017** | ceil -> 4 | 0.3832, 0.75 doc |
  | phase 2, ceiling -> floor 20.3139 | 13.1532 | 25.892 | ceil -> 26 | 0.5059, 1.00 doc |

  Phase 1 divided its own span evenly so it would land exactly on the ceiling.
  **1.5329 / 0.508 = 3.017** - it cleared three passes by 0.017 mm, rounded up
  to four, and every pass lost a quarter of its depth for that.

  greatEndian, 2026-08-26: *"we need to let full depth of cut"* and *"do not
  apply spreading leftover depth into other passes"*.

  **Built as: whole depths of cut, leftover on the FIRST pass at the stock,
  nothing redistributed.** Every phase-1 level now sits exactly one doc from
  its neighbour and the ladder still ends precisely on the ceiling.

  | | levels | phase-1 levels | stock -> first | phase-1 gaps |
  |---|---|---|---|---|
  | before | 30 | 34.6168 / 34.2336 / 33.8503 / 33.4671 | 0.3832 | 0.3832 x4 |
  | after, skip thin OFF | 30 | 34.9911 / 34.4831 / 33.9751 / 33.4671 | **0.0089** | **0.5080 x3** |
  | after, skip thin doc/2 | 29 | 34.4831 / 33.9751 / 33.4671 | 0.5169 | **0.5080 x2** |

  **No new control was added** - the thin first pass is removed by the shipped
  *Skip thin roughing passes*, measured doing exactly this in `analysis/062`.
  `_pl_prev_lvl` is `stock_r` at a window head, so the first pass is judged
  against the bar and the guard sees it. greatEndian was offered an automatic
  bounded absorb instead and chose the setting.

  **Why the leftover may sit at the stock when the identical leftover was
  ruled unacceptable at the ceiling two days before** - what lies under the
  pass differs. At the ceiling it is the part, so a dropped level leaves the
  next cutting over the doc into a measured surface, and phase 2 spreads. Here
  it is oversize bar: skipping leaves 0.5169, 1.02 of a doc, through raw
  stock, which the unsectioned ladder has always done at this same envelope.
  **Phase 2 keeps its spread** - that ruling is untouched.

  Gates: `cam_map` 6/6, `test_ladder` all pass, `test_x_continuity` all pass
  with its delete-a-pass control still firing.

  - [ ] **With Skip thin at 0 the rubbing pass IS emitted** - 0.0089 mm on
    testing_15_7. That is the operator's call by greatEndian's decision, taken
    after being shown the consequence. The cfg default is still 0.0 while the
    parameter's own tooltip recommends half the depth of cut; whether that
    default should change is not mine to decide and has not been changed.

## Reported 2026-08-28 — sections not touching, on testing_15_9

- [x] **A 0.4 mm RING OF METAL AT EVERY SECTION BOUNDARY — FIXED.**
  greatEndian: *"sectionning segments are not touching each other endings .. as
  ends of first ones are in other position as fronts of second ones, which have
  to be exactly same, i think the is comming same thing of tool tip radius
  compensation"*, `photo/passesBeforeBossSectionninOnIsseu_2.png`. **They named
  the cause correctly.**

  `z_start` is `w_from - _pl_rgh_oz`, so the cutting EDGE begins where the
  window does. A window-clamped `z_end` was raw `w_to` and carried nothing, so
  one window ended at the boundary while the next began a nose radius past it
  and the strip between was never cut.
  **Measured by instrumenting the interpreter**: `wf=0.0 wt=-1.0 ze=-1.000000`
  with the next window's cut starting at `-1.4000`, `oz=0.400000`. At radius
  34.4941, 15 of 16 joins were exactly **+0.4000**. Fixed: `ze=-1.400000`, and
  every join is now **0.0000**.
  Only the WINDOW clamp changed; a cut stopped by the profile crossing keeps
  its value, since the stop table has carried the nose since it was built.
  Gates: `check_tangent` PASS min |dot| 1.00000 over 811503 canon events,
  `test_x_continuity`, `test_leftover` control 24/24, `test_ladder`,
  `test_leads`, `test_skip_short` all pass.

  - [x] **THE TRAP THAT COST FOUR CONTRADICTORY MEASUREMENTS, and it is worth
    more than the fix.** `lib/*.ngc` is a SUBROUTINE, re-read by rs274 on every
    parse - the generated `.ngc` does not contain this behaviour at all,
    because `z_end` is computed at runtime. So re-parsing an OLD generated file
    measures the CURRENT lib, not the lib that produced it. Two "before/after"
    comparisons therefore came back byte-identical and made a real fault look
    absent; a third made a working fix look inert. **Keeping a generated file
    as a "before" is meaningless for any lib change.** The before state has to
    be re-measured with the lib actually reverted - `git stash`, measure,
    restore - or read out of the interpreter with a DEBUG line, which is what
    finally settled it.

- [x] **THE BACK-ANGLE SEGMENTS BEHIND THE BOSS NOW MEET — FIXED 2026-08-29.**
  The front cut is lengthened to the point the next window will start at, which
  greatEndian chose over relaxing the entry test. **The six ramp gaps are
  closed**: 0.7653, 0.6162, 0.4670, 0.3178, 0.1686 and 0.0194 are all gone, and
  the project's positive-gap count falls from 24 to 18 - the 18 being the
  legitimate disjoint intervals either side of the boss.

  **What made it work where the first attempt failed**: `e_xz` is purely
  geometric - where the entry contour's own LINE reaches this level's radius -
  so it does not depend on the window, and the front window can compute the
  very number the next one will start at. Mirroring `e_best` could not, because
  `e_have` is 0 for exactly these levels; that is WHY they take the fallback.
  Four guards keep an ordinary boundary still: the cut must have ended ON the
  window bound, the entry line must be known, it only ever lengthens, and it
  never passes the level's own crossing nor three depths of cut.
  Gates: `check_tangent` PASS min |dot| 1.00000 over 819758 canon events,
  `test_x_continuity`, `test_leftover` control 24/24, `test_ladder`,
  `test_leads`, `test_skip_short`, `test_sections` all pass.

  ~~THE BACK-ANGLE SEGMENTS BEHIND THE BOSS STILL DO NOT MEET, AND THE
  METAL IS REAL.~~ greatEndian, 2026-08-28: *"segments behind the boss which
  are artificial created from the tool back angle compensation respection are
  still not in contact"*, and 2026-08-29 on which repair to make: *"front
  before is shorter in the behind boss area then are next segments behind
  them"* - so the FRONT cut is the short one and is the one to lengthen.

  **Measured, and it is not cosmetic.** testing_15_9, radius 26.3998 =
  52.7996 diameter. The cut ends Z-66.5667 and the next begins Z-67.3320,
  leaving 0.7653. Across that strip the STOP contour - the roughing floor -
  runs 52.1103 down to 51.7569, i.e. **below the level the whole way**, so
  there is material at that radius and no pass takes it. Six such gaps, one
  per level, shrinking linearly with radius: 0.7653, 0.6162, 0.4670, 0.3178,
  0.1686, 0.0194. `test_leftover` misses them because what stands is roughly
  0.17-0.26 mm of radius, under its one-depth-of-cut threshold.

  **The mechanism, read out of the interpreter:**
  ```
  cut A  window -65.0738..-66.1667  starts -65.4738  ends -66.5667
  cut B  window -66.1667..-70.4000  starts -67.3320  ends -69.5918
  ```
  B's start is not `w_from - oz`, which would be -66.5667. It is pushed to
  -67.3320 by the entry-contour machinery, and A stops at its own window bound.

  - [ ] **AN ATTEMPT THAT FAILED, recorded so it is not repeated.** I added an
    accumulator mirroring `e_best` - the nearest entry crossing - measured
    from `w_to` instead of `w_from`, to let A reach where B starts. It never
    fired, and instrumenting showed why: **`e_have` is 0 for window B**, so
    B's start does NOT come from `e_best` at all. It comes from the FALLBACK
    at `o<e_ext>`, the branch for *"a level that never crosses the entry
    contour"*, which reaches -67.332047 by a different route. Any fix has to
    mirror THAT computation, not `e_best`. The attempt was reverted rather
    than left in as dead machinery.

- [x] **A COVERAGE SWEEP THAT CLAIMED NINE MORE GAPS WAS AN INSTRUMENT ERROR,
  2026-08-30.** Sampling Z and asking "does any cut cover this level here"
  reported nine levels each missing exactly **0.40 mm** on the ramp - and 0.40
  is `_pl_rgh_oz`, which should have been the tell.
  **The cut positions are CONTROL points; the floor table is where the NOSE
  must contact.** The nose contacts at control + oz, so a cut whose control
  span is -43.5611..-45.4194 contacts -43.1611..-45.0194, and the floor crosses
  that radius at **-43.1613** - a match to 0.0002. The metal is cut; the
  sampler was comparing the two frames directly.
  **Rule for the next sweep**: before comparing a cut against any contour
  table, decide which frame the table is in and add the nose term if it is a
  contact surface. A discrepancy that equals `_pl_rgh_oz` on every sample is an
  instrument error until proven otherwise.
  The two gaps below are NOT affected: they are measured cut-to-cut, control
  against control, so both sides shift equally and the gap is real either way.

- [x] **THE BOSS-FRONT GAPS ARE CLOSED — FIXED 2026-08-30.** Same repair as
  behind the boss, but it needed the latch taken at the right end. `e_w*` - the
  entry surface the fallback extrapolates - is latched at the segment spanning
  **`w_from`**, deliberately, since that is the surface this window's own start
  needs. The lengthening needs the surface at **`w_to`**, because that is the
  NEXT window's start and therefore what ITS fallback will use.
  Reusing `e_w*` failed silently: at level 28.9293 the segment spanning
  `w_from` -15.2500 is VERTICAL, `e_wdx` 0.0000, so the lengthening was skipped
  by its own divide-by-zero guard - while the segment spanning `w_to` -20.0000
  has `e_wdx` 0.8235 and yields the **-21.3269** the next window actually
  starts at. A second latch `e_t*` at `w_to` fixes it.
  **Positive-gap count on testing_15_9: 18 -> 16**, and the 16 are the
  legitimate disjoint intervals either side of the boss. Gates:
  `check_tangent` PASS min |dot| 1.00000 over 931423 canon events,
  `test_x_continuity`, `test_leftover` control 24/24, `test_ladder`,
  `test_leads`, `test_skip_short`, `test_sections` all pass.

  ~~TWO GAPS REMAIN, AND THEY ARE ON THE BOSS FRONT - which is
  greatEndian's other observation**: *"segments which are touching the arc
  surface from the front side"*. Measured on testing_15_9 after the ramp fix:
  **0.9269 at radius 28.9293, Z-21.3269 to -20.4000**, and **0.2214 at radius
  28.4234, Z-20.6214 to -20.4000**. Both are metal - the floor runs 3.67 to
  7.13 mm below the level across them - and both sit where the boss arc starts
  at Z-20. A different mechanism from the ramp behind the boss: these end at a
  window bound of -20.4000 that the next cut starts exactly on, so the
  lengthening rule does not apply.~~

- [x] **SECTIONING ON NOW MATCHES SECTIONING OFF — FIXED 2026-08-30, and the
  cause was a test that did not compare against what it assigned.**
  The window clamp read `if zc GT w_to` while assigning `w_to - _pl_rgh_oz`.
  Those disagree over a band one nose term wide: a crossing falling just past
  `w_to` is judged *"not before the window end"* and the cut is then sent to
  `w_to - oz`, PAST the reach the crossing named.
  **Measured at level 24.3762**: `zc -20.002614` against `w_to -20.000000` -
  short by 0.0026, so the test said no - and the cut ended -20.400000, running
  **0.3974 beyond where that level can cut**. Invisible until the nose term was
  subtracted there, because the else used to give `w_to` itself, 0.0026 from
  `zc`. `z_wend` names the bound once so the two cannot drift apart again.

  | # | radius | before | after |
  |---|---|---|---|
  | 8 | 30.4470 | -0.2521 | **-0.0057** |
  | 19 | 24.8821 | -0.1975 | **-0.0041** |
  | 20 | 24.3762 | -0.4017 | **-0.0043** |
  | 17 | 25.8939 | +0.2510 | +0.2510, and it is NOT a fault - see below |

  **Level 17 is `Skip short roughing passes` doing its job.** Its reach is
  -20.6510 and the window bound is -20.4000, so the remainder is a **0.251 mm**
  pass against a **0.500** setting, and it is dropped. With Skip short at 0 that
  level ends -20.6559 against -20.6510 off, a difference of 0.0049 like every
  other. **With Skip short off the largest difference across all 29 levels is
  0.0147**, which is the ladder difference on a sloped surface and not a
  defect.
  Gates: `check_tangent` PASS min |dot| 1.00000 over 934723 canon events,
  `test_x_continuity`, `test_leftover` control 24/24, `test_ladder`,
  `test_skip_short`, `test_leads`, `test_sections` all pass.

  ~~FOUR LEVELS END IN A DIFFERENT PLACE WITH SECTIONING ON.~~ greatEndian, 2026-08-30: *"passes are not
  missing now but they are more mixed between pass section before and after"*,
  asking for testing_15_9 with sectioning off against on.
  Matched by LEVEL INDEX, since the ladders differ slightly - the radii are
  34.4936 off against 34.4941 on - **24 of 28 levels agree to about 0.005**,
  which is just that ladder difference on a sloped surface. Four do not:

  | # | radius on | OFF ends | ON ends | difference |
  |---|---|---|---|---|
  | 8 | 30.4470 | -24.3146 | -24.5667 | -0.2521 past |
  | 17 | 25.8939 | -20.6510 | **-20.4000** | +0.2510 short |
  | 19 | 24.8821 | -20.2025 | **-20.4000** | -0.1975 past |
  | 20 | 24.3762 | -19.9983 | **-20.4000** | -0.4017 past |

  **-20.4000 is a window bound minus `_pl_rgh_oz`.** Instrumented at level
  24.3762: the level's own reach is `zc = -20.002614` while the cut ends
  -20.400000, so it runs **0.3974 past where the level can actually cut**.

  - [x] **THE ORDERING, MAPPED - which is what finally located it.**
    `zc` is settled at line 394, BEFORE the window clamp at 424, so the clamp
    always had the right value and my two earlier clamps were solving a problem
    that did not exist. The end is then rewritten twice more: by the entry
    lengthening, and at **817 by the stop-contour extension**, which is where
    the end is finally settled. The fault was never about ordering at all - it
    was the clamp comparing `zc` against `w_to` while assigning `w_to - oz`.
    ~~TWO CLAMP ATTEMPTS FAILED AND WERE REVERTED, both for the same
    reason.~~ A clamp placed with the window clamp, and a second placed after
    the entry scan, neither fired: **`zc` is not final at either point** - it
    is refined further down, past `o<stp>` and the multi-crossing `z_end_try`.
    The value my debug printed at the foot of the subroutine, -20.0026, is not
    the value those clamps saw. A fix has to sit where the cut end is actually
    settled, and that needs the ordering of this subroutine mapped rather than
    assumed - five attempts in it have now failed on exactly that.
  - [ ] **The before/after comparison does NOT say whether these four are new.**
    Running the pre-boundary-fix lib gives front intervals ending at -1.0000
    for every level, because without that fix the cuts do not join and the
    merge fragments them. The metric only means anything once they join, so it
    cannot be used to date these four.

- [x] **EVERY PASS NOW RUNS ITS OWN SECTION'S LENGTH — FIXED 2026-08-31, and
  it replaced the lengthening rather than adding to it.** greatEndian:
  *"16 and 17 are longer than 18 19 20 pass and they should be the same ones"*.
  On testing_15_9 the 5th section from the front is 4.7500 wide, and 26 of its
  28 passes ran exactly that - while two ran **5.6769** and **4.9714**, past
  the section into the next.

  Those two were my own lengthening, pushing a window-clamped end on to where
  the next window's entry rule would start. **The guard on the START does the
  same job from the other side**: the entry contour may only pull a start
  EARLIER, never later. A level that survived the blocked test is cuttable from
  `w_from`, so there is nothing for the entry rule to protect against there -
  it is a continuation, and the boundary is where the previous section's cut
  ended. `w_from - _pl_rgh_oz` is that boundary in control terms, the same
  expression the window END uses, so the two sides meet by construction.

  **Measured**: passes 12 and 13 are now **4.7500** like the rest, every pass
  1-19 ends exactly on -20.4000, and 20 onward taper only because their own
  reach ends earlier. Positive-gap count **16 -> 15, with no small gaps left at
  all** - every remaining one is a large legitimate disjoint interval across
  the boss. So this is strictly better than the lengthening it removed: same
  strips closed, no pass overrunning its section.
  Gates: `check_tangent` PASS min |dot| 1.00000 over 938973 canon events,
  `test_x_continuity`, `test_leftover` control 24/24, `test_ladder`,
  `test_skip_short`, `test_leads`, `test_sections` all pass.

  - [x] **A NEAR MISS WORTH RECORDING: a scripted edit deleted 594 lines.**
    Removing the lengthening by locating its start and walking a line range
    took out the entire entry scan - `o<ent> endif` ended up at line 85 and the
    file went 1406 -> 812. `cam_map` still PASSED, because it checks tables and
    windows, not that the geometry survived. Caught by `git diff --stat` and
    reverted. **Edit O-code by exact string replacement only; never by line
    arithmetic, and always read the diffstat before believing an edit.**

- [x] **A PASS IS NOW CONTAINED BY ITS OWN SECTION AT BOTH ENDS — 2026-08-31.**
  greatEndian, on the 6th section from the front: *"13.14.15th pass too long ..
  they stops well at tangential surface back at boss segment but they starts
  wrong in the 5th section segment looks like offsetted wrong"*,
  `photo/sectionning_1.png`.

  The far end was already bounded and the near end was not. The entry rule may
  pull a start BACK so the pass arrives parallel rather than diving in at 45
  degrees - the testing_15_5 ramp - but a continuation has no room for it: the
  previous section has already cut that ground at that radius, so the reach-back
  only re-traverses air and hangs into the section before.
  **Measured**, section 6 begins -20.4000 and three passes started **-19.9158,
  -19.2103 and -18.5048** - reaching back 0.4842, 1.1897 and 1.8952 into a
  section that had already cut to -20.4000 at those very radii.
  Clamped with the same bound the far end uses, `w_from - _pl_rgh_oz`.

  **After**: every pass in the section starts on -20.4000 and the lengths taper
  cleanly 4.1667 -> 0.5299 as the boss arc rises. 18 passes become 17 - the last
  had 0.0105 of reach left once clamped, under the operator's 0.500 Skip short.
  Positive-gap count stays **15, with no small gaps**.

  **The regression this risked was checked, not assumed**: `test_ramps` passes,
  **68 ramps, every one arriving at the same angle and none starting inside the
  level it enters**, so the parallel arrival the clamp touches still holds.
  Gates: `check_tangent` PASS min |dot| 1.00000 over 941985 canon events,
  `test_x_continuity`, `test_leftover` control 24/24, `test_ladder`,
  `test_skip_short`, `test_leads`, `test_sections` all pass.

- [x] **EVERY PARALLEL RAMP IS FULL LENGTH — 2026-08-31.** greatEndian:
  *"parallel artificial lead ins are every second time halfsized ... artificial
  lead in should start at endings of lead in from segment before"*.

  It was literally half: `#<pa_room> = [0.5 * ABS[#<z_end> - #<z_start>]]`
  capped the ramp at **half the cut it enters**, and the comment beside it said
  so - *"Half the cut, so the ramp never eats the whole pass"*.
  **Measured on testing_15_9**: against a standard 2.1724, the last ramp of
  each section came out **1.0544, 0.9436, 0.8671, 0.7905, 0.7139** - each
  exactly half its own cut.

  **The length is not a free choice, and that is why the cap was wrong.** A
  ramp runs `doc / sin` of the contour angle and the levels sit one doc apart,
  so consecutive ramps are parallel lines whose END is the next one's START -
  which is exactly the rule greatEndian stated. Capping one breaks the chain
  and it reads as a lead-in hanging in space beside its neighbours.
  The cap was guarding against a ramp eating its whole pass; it does not need
  to, because a ramp runs through metal that is ALREADY GONE. Longer than the
  cut costs air time, not a gouge. The real guards - it must come from the
  stock side and must not start inside the level it enters - are elsewhere and
  are asserted by `test_ramps`.

  **After**: every ramp is **2.2583**, uniform across all passes and sections,
  and they chain - in the 12th section pass 7's ramp ends -45.7524 where pass
  8's starts -45.7433.
  Gates: `test_ramps` **68 ramps, all at one angle, none longer than the
  standard, none starting inside the level it enters**; `check_tangent` PASS
  min |dot| 1.00000 over 943861 canon events; `test_leftover` control 24/24,
  `test_x_continuity`, `test_ladder`, `test_skip_short`, `test_leads`,
  `test_sections` all pass.

## Reported 2026-08-31 — the roughing air, and a setting that cannot fire

- [x] **MEASURED: cutting is 16% of the roughing motion.** greatEndian, asking
  whether the parallel ramp could be armed only on the pass that touches the
  part: *"there is a lot of the cutting air passings"*. On testing_15_9:

  | roughing motion | moves | distance |
  |---|---|---|
  | level cuts | 266 | 1010.0 mm |
  | entries + lead-outs | 594 | 602.0 mm |
  | **rapids** | **799** | **4688.3 mm** |

- [x] **THE RAMP GATE WAS BUILT, MEASURED AND REVERTED - it is the wrong
  lever.** Arming the ramp only where the pass begins ON the entry surface
  keeps 31 ramps and drops 235 - but the ramp does not vanish, it falls back to
  the configured 1.0 mm lead-in **at 45 degrees, X step 0.7072**, deeper than
  one depth of cut. Entry feed 389.3 -> 305.0 mm, a **22% saving, not the 79%
  I projected**, in exchange for 235 plunging entries - the very shape the ramp
  machinery exists to prevent. Reverted. The projection was wrong because it
  assumed the ramp would simply disappear.

- [x] **`Retract = Minimal` CANNOT FIRE ON ANY PROJECT, AND IT IS WORTH 48% OF
  THE ROUGHING MOTION.** DONE 2026-08-31, see `analysis/065`. The safe
  reference below was built: the retract radius is now the roughing floor's
  **peak between where the tool is and where it is going**, taken together with
  the previous level, so an interval-splitting boss raises the retract by
  construction and the force in `poly_lathe_mill.ngc` is gone. Shipped numbers
  on testing_15_9, same 799 rapids either way: **4688.3 -> 1898.3 mm of rapid
  distance, 6451.6 -> 3661.6 mm total** (60% / 43%). Slightly more than the
  1589.1 mm the unsafe prototype measured - that difference is the price of the
  peak lookup, and it is the right price. **The number that proves it is not
  the distance but the clearance**: every Z traverse sampled along its length
  against the roughing floor, tightest **+1.0693 mm**, never negative. Falls
  back to full retract with no floor table and on ID work, both unmeasured
  rather than assumed. The setting reaches the runtime - the generated file
  carries `#<_pl_ret_mode> = 1` - but `poly_lathe_mill.ngc:336` forces it back:
  ```
  o<mx_ret> if [#<_pl_multi_cross> GT 0]
          #<_pl_ret_mode> = 0
  ```
  and `_pl_multi_cross` is set to **1 unconditionally** in the cfg, which says
  so itself: *"disjoint-interval roughing is always active .. it no longer
  gates anything"*. So the combo is dead for every project, always. Instrumented
  to be certain: the level pass reads `mode=0.000000` when the file says 1.

  **What it would be worth, measured by neutralising the guard for one run:**

  | | rapids | total roughing motion |
  |---|---|---|
  | Full - above stock | 4688.3 mm | 6451.6 mm |
  | Minimal | **1589.1 mm** | **3352.4 mm** |

  **3099 mm of rapids removed, 66% of them; total motion nearly halved.** The
  guard was restored immediately - this was a measurement, not a change.

  - [x] **The guard's reason is real and must not simply be deleted.**
    `_pl_prev_lvl` is a single reference radius meaning "the previous level",
    and it goes stale the moment a boss splits a level into disjoint intervals:
    retracting there can put the tool into the boss. Full retract is an
    absolute upper bound and unconditionally safe.
  - [x] **The fix is a safe reference, not a removed guard.** BUILT. The retract
    radius should be the highest material between where the tool IS and where
    it is GOING - `max(profile) over the traverse span + ret_dist` - rather
    than the previous level. That is a table lookup of the kind the stop and
    entry scans already do, and Python already emits the contours to read.
    That measurement was made and is the acceptance number above: +1.0693 mm
    tightest clearance, positive everywhere.

- [x] **Air entry leads under Natural sectioning and Both directions** — DONE
  2026-08-31, `analysis/067`. The single carried value was replaced by a
  **per-window record at #2800, looked up by which windows the lead's Z span
  actually crosses**, so the visiting order stops mattering: a window that has
  not run yet still reads 999999 and keeps the lead by itself. One mechanism now
  covers all four mode combinations and both earlier bounds are gone.
  - Both directions: entry-air down to 10 moves / 5.0 mm, roughing feed
    1951.1 -> **1744.2 mm**, all 811 rapids through cleared metal.
  - Artificial unchanged at 1540.6 / 1547.4 mm; back-to-front now has **zero**
    air entry leads.
  - **Natural had nothing to take** — 10.0 mm and 7.9 mm of air entry lead,
    against 419.4 mm on Artificial. Its windows carry a RADIUS BAND and so
    partition the ladder between them, where Artificial's every window re-walks
    the whole shared ladder. That is the result, not a shortfall, and
    `test_air_leads.py` asserts the figures so it stays a recorded fact.
  - The table took room from nothing: 1000-2999 measured completely
    unreferenced across cfg/, lib/, the Python and the generated program.

- [x] **Lead-OUTs — DONE 2026-08-31 as a PARAMETER, `analysis/068`.**
  `PARAM_LO_AIR` "Skip lead-out in cleared metal", Off/On, **default Off** =
  the original motion byte for byte. On, roughing feed: front-to-back
  1352.9 -> **1103.9 mm**, Both directions 1556.5 -> **1435.5**, Natural 15_5
  1144.4 -> **1103.4**, 15_2 530.0 -> **505.0**. The leads that cut are
  identical On and Off in every case, and no rapid enters standing metal.
  Bounded to FORWARD passes, measured: applied to reversed ones it put 2 of 799
  rapids **7.5622 mm into standing metal**. The climbing ramp is a separate
  move and is never touched, so back-to-front keeps the 304.6 mm it really cuts.

  Artificial front to back, roughing only: **266 lead-outs, every one exactly
  1.0000 mm, purely outward, removing nothing — 19.7% of the roughing feed.**
  Turning them off saves 266.0 mm of feed, leaves the cutting leads identical
  (54 / 67.9 mm either way), and keeps every one of the 799 rapids out of
  standing metal. Rapid distance rises 353.3 mm, so the gain is feed rate ->
  rapid rate, not less travel.
  **Back to front must not be touched**: its retreats ARE the climbing ramp and
  cut 304.6 mm; dropping that once left a 0.4255 mm tooth per level on a taper.
  What measurement cannot settle: the lead-out backs the tool off the end wall
  at feed before the rapid, which is what avoids a witness mark at the stop
  point. That is a machining-practice decision, not a geometric one.

- [x] **Both directions WARNS but is not yet CORRECT** — both halves now
  closed. `flank_sides` was done in `analysis/071`; the leads are done in
  `analysis/078`, and NOT by gating them.
  - **The leads are sound in every direction** - measured with `test_leads`'
    own criterion on 15_5 and 15_2, dir 0, 1 and 2: no lead cuts into the
    material. The real gap was COVERAGE: that file sets `param_n_comp` and had
    never set `param_dir` at all. It now covers all three.
  - **Gating them would have been wrong.** The ramp is gated because its
    purpose - arrive PARALLEL to a surface - is void when the insert cannot cut
    that way. A plain lead eases into the cut, which survives the direction.
    Gating by facing would drop every lead on back-to-front, a legitimate mode
    with a left-hand tool.
  - **What the investigation found instead**: the warning fired only for
    `param_dir` 2, narrower than the toolpath's own belief - `_pl_ramp_face`
    drops all 15 ramps for a right-hand insert roughed back to front and said
    nothing to the operator. `wrong_way_dirs` now asks "can this insert cut the
    direction asked for", so Q2 warns on 1 and 2 and stays quiet on 0, and a
    mirrored insert warns on 0. cfg 1.72.

- [x] **No demo project carries a genuinely LEFT-HAND tool.** DONE 2026-09-03,
  `analysis/079`. `T13` is the left-hand twin of T2 - same 0.8 nose, `Q1`, and
  its I/J mirrored with the orientation - added to the TRACKED
  `configs/common/lathe*.tbl` as well as the local demo copies, since those are
  gitignored. `test_bidir_warn` now exercises it: quiet in its own direction,
  warns in the other two, no special case needed.
  - **It also showed the scratch control is a tool that cannot exist**:
    `test_ramp_orient` mirrors `Q2`→`Q1` and leaves `I15 J75`, which bisect to
    CL45 and contradict Q1 = CL135. That is why it gives 18 ramps where a real
    left-hand tool gives 0 - the angles drive the flank envelope, and mirroring
    the orientation without them mirrors half the tool.

- [x] **Nothing in the demo tables is a real left-hand BORING bar** — WRONG
  when written, corrected 2026-09-03 the same hour. **`T4` already was one**:
  `Q4` is `NOSE_OFFSET (-1, -1)`, an ID orientation with facing +1, and its
  `I195 J255` bisect to CL225 consistently. What was actually missing was a
  matched pair at a realistic bar nose - T3 and T4 carry both ID orientations
  but only at D2.54. Added `T14` (Q3, D0.8, bores toward −Z) and `T15` (Q4,
  D0.8, bores toward +Z), each other's hand exactly as T2 and T13 are, and
  `wrong_way_dirs` needs no ID branch. `test_bidir_warn` pins both.
  - **Only the WARNING is covered.** They run against testing_15_9, an OD part,
    so nothing about the ID toolpath is exercised - ID work is paused. Ramp
    counts for a boring bar on an OD part would be meaningless and are not
    claimed.

- [x] **`flank_sides` decides the shadowed side from the ROUGHING DIRECTION
  alone** — DONE 2026-09-01, `analysis/071`. `insert_flank_side` now answers it
  from the loaded insert inside `flank_envelope`, and for orientation 2 it
  returns exactly what the direction-derived answer gave, so motion and tables
  are byte-identical on 3 projects x 3 directions. A mirrored insert moves the
  flank table 42 slots -> 24. Also found: every caller reaches `flank_sides`
  through `rough_frame_dir`, which collapses 0/1/2 to 0, so its direction
  argument was already dead and the shadow was hard-wired to +Z.

- [ ] **Does a mirrored insert really lose EVERY ramp on testing_15_9?**
  **NOW REPRODUCIBLE WITH A REAL TOOL, 2026-09-03**: T13 in its OWN direction
  (back to front) arms 0 ramps, where T2 in its own direction arms 15. The
  earlier evidence came from a scratch `Q` edit that describes an impossible
  tool, so this is the first honest reproduction. Still unanswered - see
  `analysis/079`. With
  the insert mirrored the entry contour halves, 40 segments to 20, and no level
  arms a ramp in either direction - so `test_ramp_orient`'s mirror control went
  from 18 ramps to 0 and no longer discriminates. The tables are consistent and
  a large swing is expected when a right-hand tool is mirrored on a taper, but
  this is NOT proven. The test says so in its docstring; the shipped pair
  (0 against 15) and the flank wiring check carry the discrimination now.

- [ ] **A neutral insert still defers to the roughing direction for its flank
  shadow** rather than declaring no shadow at all. Orientations 6, 8 and 9 have
  no axial component; a genuinely neutral insert has clearance both ways and
  arguably shadows neither side. That is a reachability claim that wants a gouge
  check behind it, so it was left alone.

- [ ] **Should a ramp also be refused when the tool faces the right way but the
  surface is steeper than its FRONT angle?** The front-flank question, left
  alone here because `Respect tool front angle` is off by default.

- [ ] **A 0.0042 mm rapid overlap survives on roughing direction 1.** Assumed to
  be grid discretisation on a sloped floor in the material probe: it matches the
  baseline 0.0041 exactly and is four hits fewer after the change. Far below any
  machining significance, but not chased to ground.

- [ ] **Minimal retract still falls back to Full on ID work and with no floor
  table.** Both are deliberate abstentions from `analysis/065`, not oversights:
  `_pl_side != 0` is a different retract geometry that the +1.0693 mm clearance
  measurement did not cover, and `_pl_stop_n = 0` leaves nothing to verify a
  shorter retract against. ID roughing therefore still pays the full-retract
  rapids. Closing it needs the same clearance measurement run on an ID project
  before the gate is widened - not a widened gate followed by a check.

- [ ] **THE COVERAGE SWEEP IS STILL AN UNTRUSTWORTHY INSTRUMENT, and that is
  the honest state.** Sampling Z and asking whether any cut covers each level
  gives a different answer depending on which frame the floor table is assumed
  to be in, and I can only verify the assumption at ONE end. Contact = control
  + oz was confirmed at a cut's START, where it matched a floor crossing to
  0.0002; applied to the far end as well it reports 0.40 uncut at the back face
  on every level, which no one has seen on the machine. **Settle which frame
  `build_stop_contour_gcode` emits before trusting either answer.** Until then
  use cut-to-cut measurements, which are frame-independent because both sides
  shift equally.

## Reported 2026-08-26 — the tiny backwards pass behind the boss

- [x] **A LEVEL PASS THAT RUNS BACKWARDS ALONG ITS OWN WINDOW — FIXED**,
  `lathe_level_pass.ngc`. greatEndian, on testing_15_7,
  `photo/extraSmallSegmentBehindBossIssue_0.png`: *"really shot pass roughing
  under the roughing and prefinish passing behind the boss segment ... it
  basically connects very bottom tip of orange dot dashed contour in
  horizontal direction with finish contour ... this tiny pass is senseless it
  should not be there even with property off skipp short passes .. it has
  wrong location"*.

  **Measured before touching anything.** Roughing on this project is
  `param_dir` 1, back to front, so every real cut runs toward increasing Z.
  One did not:

  | X | length | Z from -> to | |
  |---|---|---|---|
  | **25.3728** | **0.3304** | **-69.5918 -> -69.9222** | **backwards** |
  | 25.8787 | 1.8609 | -69.5918 -> -67.7309 | |
  | 26.3846 | 4.0522 | -69.5918 -> -65.5396 | |
  | 26.8905 | 6.2435 | -69.5919 -> -63.3484 | |

  The ladder steps 0.5059 in X and each level gains **2.1913** mm of length, so
  the next level down is **-0.33 mm**: it has no material at all. The scan
  handed back a start from the ENTRY contour and an end from the STOP contour
  that had **crossed**, and the crossed interval was emitted instead of
  nothing - which is exactly greatEndian's "connects the bottom tip of the
  orange dot-dashed contour to the finish contour".

  **Why skip-short could never catch it**: that guard measures
  `ABS[z_end_cut - z_start]`, and an absolute value cannot see a sign. It is
  also opt-in, and this is a geometric impossibility rather than a saving - so
  the new guard is **unconditional**: a cut with
  `z_dir * [z_start - z_end_cut] LE 0` emits nothing. Returning there was
  already a supported path, since `_pl_level_z_end` is set above it and the
  disjoint-interval scan still knows where the level reached.

  **Measured after**: 46 -> **45** constant-X level cuts on testing_15_7, and
  exactly the one removed - 1.8609 / 4.0522 / 6.2435 / 8.4348 / 10.6261 /
  12.8173 and the 69.5920 longest are all identical to the digit. The 0.4065 mm
  pass at X20.3139 SURVIVES, because it runs the right way at the front face:
  the guard discriminates on direction, not on length, which is the whole point.

  **Gates**: `cam_map` 6/6; `test_x_continuity` worst gap **0.0000** with its
  delete-a-pass control still firing, so nothing was left uncovered;
  **`test_leftover` reports no metal standing proud, its control firing on 22
  of 22 projects** - which is the measurement that proves the removed pass was
  not cutting metal.

  - [ ] **Python-first debt, noted not paid.** The decision is still made at
    runtime because the crossed interval comes out of the runtime scan. The
    real repair is that the scan should not PRODUCE a crossed interval, and
    that scan is the "ramp and stop machinery is still runtime O-code" item
    further down this file.

## Reported 2026-08-25 — the plot's scroll wheel

- [x] **SCROLL-TO-ZOOM ONLY WORKED WITH THE WHEEL HELD DOWN — FIXED**,
  `ncam_preview_ui.py`. greatEndian: *"scrolling function is now not just midle
  wheel scroll but I need to hold down whell and then scroll .. zooming then
  working well"*.

  **That symptom names the fault on its own.** A button press takes an implicit
  pointer grab, and a grab routes scroll to the grab window whatever its mask
  says - which is why the zoom behaved perfectly once held. So the handler and
  `zoom_at` were never in question; the events were not reaching the drawing
  area at all.

  `add_events` sets the WIDGET mask, and GTK copies that onto the GdkWindow
  when the window is created - **and only then**. A widget already realized
  when the mask is added keeps its old window mask. This pane is reparented
  into a `Paned` after the panel exists, which is exactly that case.

  Fixed by re-applying the mask at realize, on the window that actually reads
  it. One `_EVENT_MASK` constant now feeds both `add_events` and the realize
  handler so the two cannot drift.

  **Measured, with a control**: a built pane's plot window carries mask
  **10486562**; stripping the scroll bits leaves **802**; the realize handler
  returns it to **10486562**. The strip is the point - asserting the bits are
  present on a fresh pane proves nothing, since `add_events` alone would pass
  that. Guarded permanently in `test_preview_ui.py`, which now also had to
  build its own pane because the panel the earlier checks use is destroyed by
  the timer test.

  - [ ] **STILL NOT CONFIRMED, AND THE FIRST FIX DID NOT CURE IT.**
    greatEndian, 2026-08-26: *"scrolling in the preview and also scrolling in
    properties does not work"* - so it is BOTH panes, which the plot-only
    repair could never have covered.
    The two treeviews carry the same `add_events` pattern
    (`ncam_treeview.py:19-21` and `71-73`), and `create_treeview` packs itself
    into the builder's `feat_scrolledwindow` **before** calling `add_events`,
    while the parameters view is later repacked into `feature_Hpane` by
    `set_layout`'s deferred pass. `8a0bf34 fix(ui): mouse wheel scrolling` had
    already had to chase this once. Both now re-arm at realize through a
    shared `TV_EVENT_MASK` / `arm_scroll_events` in `ncam_treeview.py`.
    **Measured**: stripping the bits off a live treeview window gives
    4326160, and the realize handler returns 10617088 with SCROLL and SMOOTH
    both back. The plot's own check still passes, 802 -> 10486562.

  - [ ] **WHAT IS STILL NOT PROVEN, SAID PLAINLY.** The FAULT has never been
    reproduced outside the running panel. Packing a treeview into an already
    realized ScrolledWindow and only then calling `add_events` still left the
    bits present - **14811920, SCROLL True** - so the "too late" ordering does
    NOT lose the mask in isolation, and the bits had to be stripped by hand to
    exercise the repair. Three widgets are now robust against a mask that goes
    missing; whether that is what greatEndian's GTK is actually doing is
    unknown.
    The panel defers `show_all()` to AXIS for XEMBED, so realize happens under
    the host - which is when these handlers fire - and the whole panel is a
    reparented X client, where an ancestor eating the wheel is the other live
    candidate.
    **A diagnostic ships with the fix rather than another guess**:
    `NCAM_SCROLL_DEBUG=1` prints each widget's real mask before and after the
    re-arm, at realize, in the running panel. If the wheel is still dead, that
    output says whether the bits are missing or whether something above the
    widget is consuming the event - and the next step follows from it instead
    of from a fourth reading.

## Reported 2026-08-24 — greatEndian's three, on testing_15_6 / 15_7

- [ ] **1. RESPECT TOOL FRONT ANGLE MEASURES THE ANGLE FROM THE WRONG AXIS.**
  greatEndian: *"respect tool front angle counts angle from opposite side ..
  T2 has 15deg and code generates restriced area as like there is -15"*,
  `photo/frontAngleRespectIssue_0.png`, testing_15_6 with Respect tool front
  angle ticked.
  `flank_slope(deg, clearance)` is `tan(90 - deg - clearance)`, written for the
  BACK angle where `J75` correctly becomes a 15 degree ramp.
  `front_flank_envelope` at `lathe_sections.py:2253` hands it the raw `I`, so
  T2's `I15` becomes a ramp of **90 - 15 - 2 = 73 degrees** where its
  symmetric back edge gets **15 - 2 = 13**. The insert is symmetric about its
  CL45 centre line - `J` is 30 above it, `I` is 30 below - so both flanks must
  ramp the same, and the leading one is coming out five times steeper.
  **FIXED 2026-08-24, `analysis/064`** - `90 - front_deg` in, so `tan(I -
  clearance)` out; both flanks now ramp at 13.00 degrees. Nothing in
  `test_front_flank`'s fixtures moves, because both sit at the ENDS of the
  range - an 89.7 degree wall is unreachable at either ramp and a 26.6 degree
  taper is on the unshadowed side either way. The band where the two
  conventions disagree was untested: a 45 degree front face went from silent
  to 2.314 mm of unreachable radius. Gates: `test_front_flank` all pass,
  `test_front_flank_path` all pass with off-by-default intact - testing_15_2
  341 moves `3f98389e76f7` and testing_15_5 484 moves `f1e3e5026d7a`
  unchanged, each still moving when asked, 341 -> 320 and 484 -> 461.
  - [ ] **Still open**: if the region is now the right SIZE but the wrong
    SIDE, the side comes from `mirror_dir` and is next. And the 2 degree
    `back_clear` default is applied to the leading flank too, under a name
    that means the trailing one - nobody has said they want the same number.

- [ ] **2. BACK TO FRONT: THE PRE-FINISH PASS AT THE PART BACK HAS A MIRRORED
  LEAD-IN AND A WRONG X, CUTTING AN UNDERCUT.** greatEndian: *"again I
  reporting issue with Direction Back to front, where prefinish pass at real
  part back has mirrored lead in direction and it also has wrong X
  position(undercut present)"*, `photo/backToFrontPathDirection.png`,
  testing_15_6, Direction = Back to front, pre-finish offset 0.300.
  "Again" - this is the same area as `photo/prefinishLeadOutBackToFrontError_0.png`
  of 2026-08-18 and the lead-out fix in the uncommitted `lathe_poly_pass.ngc`
  hunk, which pinned the RETREAT to +Z. The LEAD-IN was not touched, and the X
  fault is new: an undercut means the pass is at a radius inside the finished
  surface, which is a gouge, not a cosmetic direction problem.

  **MEASURED 2026-08-24, and the fault is entirely in the LEAD-IN.** The
  pre-finish CONTOUR is innocent: its closest approach to the finish contour is
  **0.5079 at Z-24.4632 X30.1798 in BOTH directions**, the same point and the
  same number, so the offset geometry does not care about the emission
  direction. The lead-in does: front to back its endpoints stay **0.5080**
  clear, back to front they come within **0.3660** - 0.142 mm closer to the
  finished surface than the pass they lead into.
  The lead-in also swaps ends with `param_dir` while the FINISH pass does not:
  pre-finish leads in at Z+0.7071 -> Z0.0000 front to back and at Z-70.5991 ->
  Z-69.8920 back to front, whereas finish leads in at Z+0.7071 -> Z0.0000 in
  both. `lathe_poly_pass.ngc:222` still has `#<li_bz> = [#<z_dir> * COS...]`,
  the exact form the lead-OUT was moved off in the uncommitted hunk.
  - [ ] **NEEDS A CALL before the fix.** "Mirrored" admits two readings and
    they want opposite changes:
    - **Pin the lead-in to +Z**, exactly as the lead-out was pinned. The
      approach then always comes from the free end. At a back entry that means
      rapiding to Z-69.1849 and feeding back down over the part.
    - **Leave the end-following as is and fix only the magnitude.** The
      approach at the back already comes from Z-70.5991, which is PAST the
      part's back end at Z-70.4 and so in free air; on that reading the
      direction is right and only the 0.3660 encroachment is wrong.
    A first instrument here reported a 10.5286 mm undercut in BOTH directions -
    a ray cast taking the outermost X across the vertical back face. It was
    wrong and was replaced by a true point-to-polyline distance. Recorded
    because it is exactly the trap CLAUDE.md names. A SECOND correction
    followed: measuring the lead-in's ENDPOINTS gave 0.3660, but sampling
    ALONG the move gives **0.0768** - the ends are clear and the middle grazes
    the back-face corner. Always sample the move, not its ends.

  **BOTH VARIANTS BUILT AND MEASURED 2026-08-24**, testing_15_6 `param_dir=1`,
  at greatEndian's request to see them before anything is committed:

  | | lead-in | min clearance to the finished surface | inside profile |
  |---|---|---|---|
  | B, current | Z-70.5991 X35.3071 -> Z-69.8920 X34.6000 | **0.0768** at Z-70.3516 X35.0596 | 0 of 41 |
  | A, pinned +Z | Z-69.1849 X35.3071 -> Z-69.8920 X34.6000 | **0.5080** at the entry | 0 of 41 |

  468 moves either way. B starts past the back end at Z-70.5991 - the part
  spans -70.4000 .. 0.0000 - so it enters in free air and then sweeps ACROSS
  the back-face corner at 0.0768. A starts within the part's Z span but a full
  pre-finish offset clear of the surface the whole way, and never enters the
  profile.
  **Front to back does not move under A**: testing_15_6 472 moves
  `f27eaf129627` and testing_15_2 341 moves `3f98389e76f7`, identical hashes
  before and after, because front to back already has `z_dir` 1. A is
  therefore the same shape of change the lead-out fix already was.
  Recommendation is A; awaiting greatEndian's pick.

  **RE-MEASURED ON testing_15_7 2026-08-25 at greatEndian's instruction** -
  *"measure them with the testing_15_7.xml there is actual"*. The project is
  saved with **`param_dir` = 0, FRONT TO BACK**, `param_sectioning` 1,
  `param_skip_short` 0, `_pl_skip_thin` 0.300, `_pl_pass_from` 0. Part Z span
  -70.4000 .. 0.0000.

  | lead | end | move | clearance |
  |---|---|---|---|
  | pre-finish IN | **BACK** | Z-70.5991 X35.3071 -> Z-69.8920 X34.6000 | **0.0768** |
  | pre-finish OUT | FRONT | Z+0.2421 X19.6421 -> Z+0.9492 X20.3492 | 0.7909 |
  | finish IN | FRONT | Z+0.7071 X19.4728 -> Z0.0000 X18.7657 | 0.0000 - on the contour, correct |
  | finish OUT | BACK | Z-70.4000 X35.0000 -> Z-69.6929 X35.7071 | 0.0000 - on the contour, correct |

  **THIS IS TWO FAULTS, NOT ONE, AND THEY NEED DIFFERENT FIXES.**

  - [x] **2a. THE UNDERCUT - APPLIED AND VERIFIED 2026-08-25.** On
    testing_15_7 the pre-finish lead-in at the back now runs Z-69.1849 ->
    Z-69.8920 and clears the finished surface by **0.5080**, up from 0.0768.
    Every other lead is unchanged to the digit. `#<li_zs> = 1` at
    `lathe_poly_pass.ngc:225`, taken by BOTH entry branches - the straight
    lead-in and the arc-entry approach in the elseif, which carried the same
    `z_dir`. The no-lead PLUNGE approach at `:316` still uses `z_dir`; it is
    the same class but a different path with no coverage in any project I can
    measure, so it was deliberately left and is recorded here instead.
    ~~**2a. THE UNDERCUT - variant A fixes it.**~~ On testing_15_7 the
    pre-finish lead-in at the back grazes the finished surface at **0.0768**
    where the pass it leads into keeps 0.5080. Variant A - pinning `li_bz` to
    +Z at `lathe_poly_pass.ngc:222`, the same change the lead-OUT already had -
    takes it to **0.5080** exactly. 480 moves either way, every other lead
    unchanged to the digit, and front to back on testing_15_6/15_2 is
    hash-identical. Ready to apply.
  - [ ] **PRE-EXISTING, FOUND BY THE 2a GATE - `testing_13_arcs.xml` does not
  generate in nose-comp mode OFF.** `test_leads` reports
  `{'Off': False, 'Native': True, 'In CAM': True}`. **Not caused by 2a**:
  measured by reverting `lathe_poly_pass.ngc` to the pre-2a state and
  re-running, which gives the identical failure. It is the only red in that
  suite; testing_15_2 passes all twelve checks in all three modes. Recorded
  2026-08-25, not chased.

- [x] **2b. THE MIRRORING — CLOSED 2026-09-01 by measurement.** The `pf_rev`
  fix resolved it. On `param_dir=0` both contour phases now lead in at the
  FRONT and run to the back: pre-finish starts Z0.7071 X20.1912, finish starts
  Z0.7071 X19.4728, on testing_15_7 and testing_15_9 alike — and the X
  separation is the pre-finish offset, correctly OUTSIDE the finish. Everything
  below describes the state before that commit and is kept for the reasoning,
  not as a live fault.

- [x] **2b. THE MIRRORING - variant A does NOT fix it, and this is the
    bigger one.** `param_dir` is **0, front to back**, yet the PRE-FINISH pass
    leads in at the **BACK** while the FINISH pass leads in at the FRONT. The
    two contour passes run the part in opposite directions on the same job.
    And **setting `param_dir=1` produces byte-identical leads** - the
    pre-finish pass is not following Direction at all on this project.
    That is about which END the pass starts at, not about the lead vector, so
    it is a different fix in a different place.

    **MEASURED 2026-08-25, on the traversal rather than on the leads.** The
    two contour passes run the part in opposite directions on the same job:

    | pass | feeds | Z travelled | net | runs |
    |---|---|---|---|---|
    | pre-finish | 74 | -69.8920 .. +0.9492 | **+70.1341** | **BACK to FRONT** |
    | finish | 75 | -70.4000 .. +0.7071 | **-70.4000** | FRONT to BACK |

    testing_15_7 is saved `param_dir` 0 and `param_f_dir` 0 - front to back
    BOTH - so the pre-finish is the one going the wrong way.

    **The structural asymmetry, found and worth fixing on its own merits:**
    the pre-finish pass takes its direction from **`rough_dir`**, the ROUGHING
    parameter - all three of its `cam_load` calls at
    `poly_lathe_mill.ngc:1209/1218/1224` pass `[#<rough_dir> EQ 1]` - while the
    finish pass takes it from **`fin_dir`**, the FINISHING parameter, through
    `#<f_rev>` at `:1254`. `rough_dir` is `#12` = `param_dir` and `fin_dir` is
    `#15` = `param_f_dir`. Two passes that trace the same contour should not
    read two different parameters to decide which way round.

    **But that asymmetry does not explain THIS flip, and saying so matters.**
    Both parameters are 0 here, so both flags resolve to 0, and
    `param_n_comp` is 0 with `_pl_pf_n` 0 and `_pl_fc_n` 21, which should put
    both passes in the same `_pl_fc_n` branch with the same flag. They still
    traverse oppositely. The feed counts - 74 and 75 against a 21-point table -
    say neither pass is tracing the table I think it is.
  - [x] **2c. "LEAD-OUT ENDING SUNK UNDER THE STOCK ENVELOPE" IS THE SAME BUG
    AS 2b - MEASURED 2026-08-25, NOT A SEPARATE FIX.** greatEndian:
    *"lead out prefinish direction is right now, but its ending sinked under
    stock envelope not as should at X"*. testing_15_7 stock is
    `_wp_dia_od = 70/2`, so the envelope is **X35.0**.

    | pass | lead-out ends | vs envelope |
    |---|---|---|
    | pre-finish | Z+0.9492 **X20.3492** | **14.65 under** |
    | finish | Z-69.6929 X35.7071 | 0.71 above |

    The pre-finish ends at X20.35 because it ENDS AT THE FRONT, where the
    profile is X~19.6, and it ends at the front because it runs back to front -
    2b. The finish pass ends at the BACK where the profile is X35, so its
    lead-out clears the envelope on its own.
    **Confirmed against a case where the pre-finish runs the right way**: on
    testing_15_6 the pre-finish lead-out ends at **X35.7071**, above the
    envelope, exactly like the finish pass. So the lead-out length and angle
    are innocent and must NOT be given a separate "extend to the envelope"
    fix - that would paper over 2b and break the case that is already correct.
    The rapid after the pre-finish already retracts to X36.8160, clear of
    stock, so nothing is being cut; the complaint is about where the FEED
    stops, and 2b is why.

  - [x] **2b FIXED 2026-08-25 — THE PRE-FINISH NOW TAKES THE FINISHING
    DIRECTION.** `#<pf_rev>` from `fin_dir` replaces `[#<rough_dir> EQ 1]` in
    all three pre-finish `cam_load` calls. `rough_dir` keeps its OTHER use at
    the roughing level-array pick - roughing's emission is still roughing's to
    choose - which is why the replacement was scoped to the `cam_load` lines
    and not done by name.

    **FOUND BY INSTRUMENTING, and two of the facts I had asserted from reading
    were wrong.** The run reported `PFBRANCH 1 rev=1.000000 fcn=21 pfn=0`
    against `FNBRANCH 1 frev=0.000000 fcn=21`. So both passes take branch ONE,
    the `nose_comp EQ 2` In-CAM branch - not the `_pl_fc_n` branch I had
    claimed twice - and `rough_dir` is **1**, not the 0 I read out of the XML.
    Confirmed against the generated program, which is authoritative:
    `#3143` = **1** back to front for ROUGHING, `#3146` = **0** front to back
    for FINISHING, `#3159` = **2** In CAM. Both settings legitimate; the
    pre-finish was simply obeying the wrong one of them.
    My XML greps were unreliable throughout - those lines carry several
    `value=` attributes and the pattern kept matching the wrong one. **Read
    the generated program, not the project file.**

    **Measured after, testing_15_7:**

    | | before | after |
    |---|---|---|
    | pre-finish lead-IN | BACK, Z-70.5991, clear 0.0768 | **FRONT, Z+0.7071, clear 0.5080** |
    | pre-finish lead-OUT | FRONT, X20.3492 | **BACK, X35.0000 -> X35.7071** |
    | pre-finish traversal | net +70.1341, back to front | **net -69.8920, FRONT to BACK** |
    | finish traversal | net -70.4000, front to back | unchanged |

    The lead-out now leaves from **X35.0000, the stock envelope**, and then
    angles to X35.7071 - identical in form to the finish pass's X35.0000 ->
    X35.7071. That is exactly what greatEndian asked for against
    `photo/prefinishLeadOutBackToFrontError_2.png`: *"it have to be at outside
    same ending as light blue one and then it continue in the lead out angled
    and beside finish pass orange one"*.
    **2c closed with it** - the 14.65 mm under-envelope ending is gone, with no
    separate lead-out change, exactly as predicted.
    Gates: `cam_map` 6/6, `test_x_continuity` all pass with its delete-a-pass
    control still firing, `test_leads` unchanged apart from the pre-existing
    testing_13_arcs Off failure.
    ~~**NEXT STEP for 2b, and it is instrumentation, not reading.**~~ Emit the
    branch taken and the resolved rev flag for each of the two passes at
    runtime and read them back from the generated program. Three readings of
    this code have now each looked conclusive and each been wrong about which
    branch runs; the next claim about it should come from the interpreter.

- [ ] **3. FRONT TO BACK + SECTIONING 5 mm PRODUCES BAD SECTIONS**, on the new
  `testing_15_7.xml`. greatEndian lists four:
  - wrong shape of sectioning;
  - the lead-in collides with the part face, sunk inside the raw stock, and
    they suspect **Skip short roughing passes** is involved;
  - the sectioning's tangential contact with the boss front face is messed up,
    passes skipped, again possibly Skip short roughing passes;
  - the whole thing appears only with Sectioning on at a 5 mm Z section length,
    i.e. ARTIFICIAL sectioning, `_pl_sect_mode` 1.
  Note the live session in `frontAngleRespectIssue_0.png` also has **Skip thin
  roughing passes at 0.300** and Skip short ticked - the saved testing_15_6 has
  both off, so the reports are from a session with them ON.

  **FIRST MEASUREMENT 2026-08-24 - it generates and runs clean, so the faults
  are geometric, not a crash.** testing_15_7 as saved: 2012 moves, 1172 feeds,
  840 rapids, **no WARNING comments and no interpreter error**. Its globals:
  `_pl_sectioning` 1, **`_pl_sect_mode` 1 - ARTIFICIAL**, **`_pl_sect_count`
  17**, `_pl_sect_top_dia` 66.93423409, `_pl_pass_from` **0 - Stock**, and
  `_pl_skip_thin` **0.300**.
  Two of these bear on greatEndian's own suspicion:
  - **`_pl_min_pass` is 0.0** - Skip short roughing passes is OFF in the saved
    project, whatever the screenshot's tick showed. So it cannot be the cause
    of the skipped passes unless the report came from a different session
    state. Worth confirming with greatEndian before hunting it.
  - `_pl_skip_thin` 0.300 is below the Stock ladder's own step, so it should
    not be alternating the way the 2026-08-24 hazard entry describes - but that
    hazard is measured on the FINAL CONTOUR anchoring and this project is on
    Stock. Check the step before ruling it out.
  - [ ] Still to measure: the section shape itself, the lead-in that sinks into
    raw stock at the face, and the tangential contact at the boss front face.
    840 rapids against 1172 feeds on 17 windows is a lot of repositioning and
    is the first thing to look at.

## Reported 2026-08-21 — the thin pass at the boss top

- [x] **A ROUGHING PASS TANGENT TO THE BOSS TOP, PRESENT AT EVERY OFFSET —
  FIXED**, 2026-08-21, `analysis/061`. greatEndian: *"there is tangential top
  boss point pass which is present across any offset values.. which is wrong it
  should be present only if it depth is equal or higher then 1/2 of depth of
  cut"*, and *"now position is at roughing 4th from the outside envelope, but it
  is floating with increasting or decreasing the prefinish offset"*.

  It is phase 2's **first** pass. With *Space passes from = Final contour* that
  ladder takes whole depths of cut from the floor and puts the leftover on its
  own first pass — which, with Sectioning on, sits ON the section ceiling, i.e.
  against the boss top. The ceiling floats continuously with the pre-finish
  offset while the ladder is anchored on the floor, so the remainder is
  `span mod doc`: on testing_15_6, 0.89 / 0.21 / 0.51 / **0.10** / 0.89 × doc
  at offsets 0.00 / 0.15 / 0.30 / 0.60 / 1.00, and the pass wanders 5th → 4th →
  3rd from the envelope.

  **Fixed by spreading, not dropping** — deleting the level would leave the one
  below it taking `remainder + doc`, over the depth of cut and against the
  finished surface. When the remainder is under half a depth of cut the span is
  divided evenly into the same `p2_n` steps, so every step stays under the doc,
  the last still lands exactly on the floor, and no even step can be under
  doc/2. **Measured**: 0.1091 → 0.4920 and 0.0511 → 0.4897; level counts
  unchanged in every column (44/44/44/43/41); testing_15_6 at default settings
  byte-identical.

  - [x] **FIXED 2026-08-24, `analysis/063` — the threshold is gone entirely.**
    greatEndian checked `testing_15_6.xml` and reported the pass still there;
    the project's saved `param_pf_off` is 0.30, so this was the 0.2591 case
    that survived by 0.0051. ~~At the default offset 0.30 the pass survives at
    0.51 × doc — NEEDS A CALL, the threshold is the dial.~~ **The threshold was
    never the question.** The remainder-on-the-first-pass rule belongs to the
    ladder that starts AT THE STOCK, where the leftover lands in oversize
    material; phase 2 starts at the section ceiling, against the part, so a
    partial pass is misplaced there at ANY size. Phase 2 is spaced evenly
    unconditionally now and `Space passes from` no longer reaches it — the
    setting keeps its meaning through `lad_tgt`, which anchoring still
    reassigns to `anch_floor` at `poly_lathe_mill.ngc:231`.
    **Measured on testing_15_6, thinnest gap in the whole ladder**: 0.4582 /
    0.4207 / **0.3832** / 0.4109 / 0.4165 at offsets 0.00 / 0.15 / 0.30 / 0.60
    / 1.00 — from 0.10-0.51 × doc up to **0.75-0.90 × doc**, with **no level
    dropped at any offset** (29/29/29/28/27 unchanged). The pass also stops
    wandering 5th → 4th → 3rd from the envelope.
    Gates: `cam_map` 6/6, `test_x_continuity` worst over-step 0.0000 with its
    delete-a-pass control still firing, `test_sections` all pass, `test_ladder`
    all pass. The `o<p2_an>` if/else, the `o<p2_thin>` conditional and the dead
    `#<p2_sgn>` initialiser are all gone.

- [x] **`#<p1_cut>` READ BEFORE IT IS ASSIGNED — FIXED**, 2026-08-21. The
  uncommitted `o<p1_end>` block reads `#<p1_cut>` at `poly_lathe_mill.ngc:1118`,
  outside `o<lvl_ok>`, while the assignment at `:723` is inside it — so a level
  that is out of band, thin, or past stock and sitting on `lvl_floor` aborted
  the program at run time with *Named parameter #<p1_cut> not defined*. **16 of
  55 tests were red on this alone.** Now initialised at the level-loop head,
  which is also what the flag means. Generation was never affected, only the
  run.

- [x] **CORRECTED 2026-08-24, `analysis/062` — `_pl_skip_thin` IS NOT INERT.**
  ~~`_pl_skip_thin` IS INERT — the shipped setting drops nothing.~~ It works:
  on testing_15_2 a 0.400 threshold drops the 29.6520 envelope level, 18 → 17,
  every surviving gap still a whole 0.5080. It dropped nothing at `doc/2`
  because **nothing was eligible** — every in-ladder gap is 0.5080 and the only
  smaller one is the stock handover at **0.3480, above the 0.2540 threshold**.
  The wrong finding came from an uncalibrated control; `test_ladder` asserted a
  drop the geometry never warranted. Control replaced, all 26 checks pass.

- [x] **BUT IT IS BLIND AT WINDOW BOUNDARIES** — the reference is FIXED
  2026-09-03, `analysis/077`, and the effect is masked. `_pl_prev_thin` is new
  and carries "the surface immediately above this level" - the section ceiling
  at a phase-2 window start - while `_pl_prev_lvl` keeps meaning "a radius
  already cut, safe to move at" for the retract. Exactly the separation this
  entry called for. Byte-identical motion on all three projects.
  - The reported 0.2591 gap **no longer exists**: 15_6 as saved has every step
    at 0.5080. The spread removed those ceiling passes structurally.
  - A case that still exercises it: **Artificial sectioning**, `sec_len` 3/5/8/12
    gives a 0.0387 mm step on 15_6 and 0.0903 on 15_5.
  - **And the pass is still not skipped** - the check now SEES it, and the gap
    rule from `analysis/076` refuses, correctly by its own terms: skipping a
    level 0.0387 below the ceiling leaves the next cutting 0.5467 against a
    0.5080 doc.

- [x] **NEEDS A CALL — should a thin skip be allowed to overshoot the depth of
  cut slightly?** WITHDRAWN 2026-09-03, same day, `analysis/077`: the premise
  was wrong. The 0.0387 step is not a stray remainder near the ceiling - it is
  at index 27 of 29 and lands EXACTLY on the floor stage 21.0160. **It is the
  region's roughing floor**, and `fl_prot` already protects it: with the gap
  rule fully neutralised the level is still there. Skipping it would leave a
  region's floor uncut, not trade chatter against tool load. The Artificial
  ladder is landing on a floor it is required to land on, and the short step
  before it is the cost of `floor_ladder` re-anchoring per region - which is
  what greatEndian asked for. Nothing to fix and nothing to decide.

- [x] **A `skip_thin` threshold above the LADDER STEP halves the ladder** —
  DONE 2026-09-03, `analysis/076`. The skip now refuses when the level that
  would FOLLOW would sit more than one depth of cut from the last one cut.
  testing_15_2: 13 levels / 0.9983 gap at 0.5070, 0.6000 and 0.9000 becomes
  **18 levels / 0.4992 at every threshold**. Not inert - testing_15_5 carries
  0.3 mm saved and the refusal gives back a level it was wrongly dropping,
  458 -> 464 moves. `test_ladder`'s control was ASSERTING the bug ("a threshold
  above the thinnest gap DOES drop a level", impossible on a uniform ladder
  without opening the gap) and is inverted; it still fails on the old build.
  `test_skip_thin_gap` is new.

- [x] **RULED 2026-08-24 — SPREAD, not drop.** greatEndian chose the spread on
  being shown both with their numbers: nothing is removed, no step exceeds the
  depth of cut, and no step falls under `doc/2`. The uncommitted change of
  2026-08-21 IS the answer; `_pl_skip_thin` is not the mechanism for this.
  ~~**NEEDS A CALL — drop the thin pass, or spread it?** greatEndian's rule
  ("present only if its depth is at least half the depth of cut") admits two
  readings and the codebase already contains the first:
  - **Drop** — repair `skip_thin` and default it to `doc/2`, which is what its
    own tooltip already recommends. The pass disappears; the level below it
    then takes `remainder + doc` — 0.5591 against a 0.5080 doc at pf 0.60, 10%
    over, against the finished surface.
  - **Spread** — the change made 2026-08-21: divide the span evenly so every
    step is 0.4897 and none is under `doc/2`. Nothing is removed and no step
    exceeds the doc, but every level in that ladder moves.~~

- [x] **THE LADDER BEHIND THE BOSS IS TRUNCATED AGAIN** on testing_15_6 with
  `param_sectioning=0`: last pass cuts 2.8021 mm against a 2.3247 step. Same
  class as the 2026-08-12 fix. Hidden until 2026-08-21 by the `#<p1_cut>`
  abort, which truncated the program the test was measuring.
  **CLOSED 2026-09-03 — no longer reproduces, and this time the pass means
  something.** Measured on the same case: 16 passes, deepest r25.5880, **last
  cut 0.6017 mm against the SAME 2.3247 step**. The step matching to four
  decimals is what says it is the same geometry and the same measurement, with
  only the last cut changed — 2.8021 to 0.6017, comfortably inside the step, so
  the ladder tapers out rather than stopping short.
  **Why it can be believed now**: the program reaches `PROGRAM_END` with 482
  moves and no error. That is exactly the check this entry said was missing —
  the fault was hidden once by an abort truncating the program the test
  measured, and since `8d15e86` an incomplete run is refused rather than
  measured, so a green tick here can no longer come from a fragment.
  Which commit fixed it is not determinable: projects are gitignored and always
  current, so bisecting past their stored version is impossible (`analysis/075`).

- [x] **`test_extension` FAILS, found 2026-09-03** — CLOSED the same day,
  `analysis/075`. It was the TEST, not the toolpath: 0.4000 is exactly
  `_pl_rgh_oz` and 2.4284 + 0.4000 = 2.8284, the contour front, to four
  decimals. A level starts at `w_from - _pl_rgh_oz` so its NOSE begins where
  the surface does; the assertion compared that control point against the
  contour's contact point. Same phantom-0.4 this project has recorded before.
  - Ruled out by worktree at `9ca60c1` with its symlinks repointed: identical
    numbers, so none of this week's contour work caused it.
  - **Bisecting past a project's stored version is not possible** — projects
    are gitignored and always current, and a worktree at `f7356af` dies on
    `#<_pl_hf_x> not defined`. Worth knowing before the next attempt.

- [x] **A test that passes on an aborted program is not passing.** DONE
  2026-09-03. `parse_program` records whether `PROGRAM_END` was reached and
  sets `error` when it was not, so all 29 test files that already refuse an
  errored run are protected without each needing a second check, and a test
  written tomorrow inherits it. Measured: truncating a real program two-thirds
  through still yields 14 moves against 341, so every geometric assertion here
  would have run happily on the fragment. The END MARKER is what is tested, not
  the absence of an error, because some aborts are silent - a truncated var
  file stops the interpreter at `T<n> M6` with no message.
  `test_program_completes.py` proves both directions.

- [ ] **`cam_map` does not catch a scan reading the wrong profile.** It checks
  windows, globals, `order` names and subroutine definitions — not *which scan
  walks which table*. It passed clean through the whole of `analysis/029`.
  A check that every `_pl_*_base` table has all of its walkers, or none, would
  have named this in a second.

## Next — before anything else

- [x] **THE "KLINGY" ARC — FIXED**, 2026-08-10, `ac61573`, `analysis/024`
  addendum 4. With *Separate Z offset* on, the dashed contours were jagged on
  the boss's rising arc. `curve_offsets` now offsets along the **curve's own
  normal** (the bisector of the two chords) at any vertex interior to a curve,
  while corners keep each surface's own normal and allowance. On testing_15_2:
  **66 direction reversals → 8**, against 6 for the isotropic case it has to
  match. `test_arc_smoothness.py`, two-sided negative control.
  - Two things worth carrying forward. The **metric is sign alternation**, not
    turn size — counting large turns measures curvature and made a failed
    attempt look 50% better while the error was untouched. And `entry_contour`
    takes **radius**: a harness that passed diameters made a 0.9 allowance
    measure 0.45, and inflated the figures first reported for this bug
    (0.35660 → **0.02580** at true scale). Corrected in `analysis/024`.
  - Still open, unaffected either way: `lathe_level_pass`'s runtime scan
    still offsets each record by a scalar — the same gap addendum 2 records.
  - `CURVE_TURN_DEG = 20` is derived from the arc mesh step (3.2° at R12.66,
    16.2° at R0.5). A profile with arcs **below R0.5** would approach the cut;
    re-run the derivation rather than nudging the number.


- [x] **ROUGHING IGNORES THE AXIAL STOCK TO LEAVE — FIXED**, 2026-08-09,
  `analysis/026`. Roughing now stops **2.0000** from the wall where it stopped
  0.7620; the isotropic case is unchanged at 0.5080 with the same 341 moves and
  29 levels. The level scan walks a floor contour Python builds instead of
  offsetting the record array by one scalar at runtime. Original report below.

- [x] ~~ROUGHING IGNORES THE AXIAL STOCK TO LEAVE~~ — greatEndian 2026-08-09,
  `photo/separateOffsetZ_0.png`, `analysis/024`. With *Separate Z offset* on,
  X 0.508 and Z 2.000, measured against testing_15_2's Z−70.4 end wall:

  ```
  stop contour (Python)   stands off 2.0000   correct
  pre-finish reaches      2.0000              honours Z
  finish reaches          0.0000              correct - it is the final pass
  roughing reaches        0.7620              WRONG - fin_off + prefin_off
  ```

  **Cause.** `lathe_level_pass` scans the profile and offsets each segment
  perpendicular by the single scalar `cross_t` at runtime, so it cannot express
  two allowances. The stop table only ever EXTENDS a stop, never pulls it back,
  so it cannot rescue the case where the axial value is larger than the floor
  allowance. Roughing then cuts 1.238 mm past where it was told to stop.

  The part still comes out right - the finish pass reaches the profile - but
  the whole point of the setting, controlling what roughing leaves, is lost.

  **Fix, and it is the standing rule again**: the level scan should walk a
  FLOOR CONTOUR that Python builds - the profile offset by
  `fin_off + prefin_off` anisotropically - instead of offsetting by a scalar at
  runtime. Same shape as the stop and entry tables. The subroutine's own
  comment warns that halving that scan once turned 487 mm of cut into 875.6, so
  it wants its own measurement and a negative control.

  The tooltip has been corrected to say so rather than promise it.


- [ ] **NEEDS A CALL — may a roughing level pass an obstruction it clears at
  the PRE-FINISH allowance but not at the floor allowance?** `testing_15_5`,
  2026-08-08, `analysis/023`. Level 3 sits at r33.2080; the pre-finish contour
  peaks at r33.1657 in front of the boss, so the level clears it by **0.0423**
  — but the floor allowance (fin + prefin = 0.762) still blocks it, so the pass
  splits into two intervals with a retract between where one sweep would do.
  Letting it through leaves **0.5503** at the boss peak instead of 0.762: more
  than the pre-finish pass needs, less than the roughing allowance promises.
  The code carries a warning against relaxing that scan — halving it once turned
  487 mm of cut into 875.6 and finished ten ends inside the contour — so this is
  greatEndian's call, not a guess.


- [ ] **RESTART NATIVECAM LANDS OUTSIDE THE AXIS TAB** — greatEndian
  2026-08-13: *"restart is working but it starts in separated window outside axis
  ui"*. `96e91ec` fixed the HAL half; this is the X half. `analysis/048`.
  - **Measured, not reasoned**: AXIS embeds the panel in
    `Tkinter.Frame(root_window, container=1, ...)`, and **Tk destroys a
    `container=1` frame when the window embedded in it goes away**. By the time
    the replacement runs, the XID on its command line is dead — `Gtk.Plug.new()`
    raises `BadWindow`, gladevcp swallows it under `Gdk.error_trap_push()`, and
    the plug stays a toplevel. Reproduced under Xvfb: a plain `tk.Frame` survives
    its child and a second process reparents in fine; a `container=1` frame is
    `XERROR BadWindow` immediately after.
  - **So no re-exec can ever reach the tab**, and AXIS exposes no way to rebuild
    it: `load_gladevcp_panel()` runs once at startup with no re-entry point, and
    AXIS tracks only the `halcmd loadusr` wrapper, which exits 0 at once.
  - **The answer is an IN-PROCESS rebuild** — the point of the menu item is to
    pick up changed `cfg/` and `catalogs/`, not to get a new pid. Scoped in
    `analysis/048`: save the project, rebuild menus/toolbars from
    `catalogs/<machine>/menu.xml`, reload the project through
    `update_features` (the migration path that already exists), and leave the
    plug, the HAL component and the preview pane alone. NOT built — it changes
    the startup sequence and wants its own plan.
  - The confirmation dialog now states what actually happens rather than only
    that LinuxCNC is untouched.

- [x] **LEAD-OUT MISPLACED UNDER COMPENSATION — FIXED**, 2026-08-04,
  `analysis/009`. greatEndian's criterion: *"lead in and lead out can not end
  in the part or stock... we need them to be like when comp off, there is no
  play"*.

  **The lead-IN was already correct** and was left alone — the nose centre sits
  at control + R·orient, so the cutting edge starts exactly where Off's tip
  does. `c16df1f`'s pre-shift working.

  **The lead-OUT was wrong in Native only.** `lathe_poly_pass.ngc` cancels comp
  (G40) after the contour and then names where the tool physically is — but
  computed that point with a **plain normal offset and no orientation term**,
  the very term the entry gained in `c16df1f`. After G40 the control point IS
  the tip, so naming the wrong point makes cancelling comp a real move:
  **0.5657 mm = |(0.4, 0.4)| = R√2**, jerking out of the finished corner, and
  the retreat then ran **1.5657 mm where 1.000 was asked for**. In CAM has
  `comp_r` 0 and never entered that arithmetic, so **In CAM was right**; the
  fix makes Native agree with it.

  Exit line now 0.0000 in all three modes; Native and In CAM place every lead
  identically on testing_15_2 and testing_13_arcs. `check_tangent` PASS,
  min |dot| 1.00000.

  **`test_leads.py` is the test that did not exist** — no lead removes
  material, every lead is the length Off makes it, cancelling comp moves
  nothing, and the two compensated modes agree. Fails without the fix.

  **Left knowingly**: roughing's leads are not covered (it never runs
  interpreter comp, so it has no exit shift to get wrong), and the same exit
  arithmetic in `taper.ngc` / `taper_id.ngc` / `boring.ngc` / `facing.ngc`
  has not been checked for the same fault.

- [x] **The radius start point on the PRE-FINISH contour — FIXED**, 2026-08-04,
  `584a7db`, `analysis/008`. greatEndian's criterion: *"radius start can not go
  first inside the part and then outside... it has to be exact line with no
  bump till radius start rising"*.

  It was **In CAM mode only**, 0.1870 mm deep at Z−20. An inside corner trims
  both offsets to where they cross; when the segment after the corner is
  shorter than the offset — the arc's first chord, **0.0049 mm of Z against a
  0.508 offset** — the crossing lands beyond the whole of it and the path
  stepped back to reach that swallowed segment's own join. `_join_offsets` now
  drops a swallowed segment and retries the trim against the next one. Both
  `offset_contour` and `entry_contour` call it, so the two can no longer drift
  apart.

  `analysis/007`'s hypothesis is **overturned there**: the trim leaving the
  wall 0.486 early is the correct parallel offset of a concave corner, not a
  fault, and the cross sign was never wrong.

  Pre-finish +Z reversals now 0 in all three modes;
  `test_swallowed_corner` covers it and fails without the fix.
  **Left knowingly**: In CAM trims 0.0158 mm earlier than Native (−19.5152 vs
  −19.5310) — different arc subdivision, both clean.


- [x] **ROUGHING'S LEVEL START Z — FIXED**, 2026-08-04, `analysis/010`.
  greatEndian: *"roughing has to start from 1 too"*. Green cut from Z+1.4000
  against a segment drawn from Z+1.0000, in every mode, because the level falls
  back to the WINDOW start (a raw profile Z) whenever the entry contour never
  crosses it. Its stop and re-entry already carried the nose — one end
  compensated, the other not, the same asymmetry as `analysis/009`.

  `build_rough_nose_gcode()` emits `#<_pl_rgh_oz>` **already gated** by
  `_comp_nose`, and `lathe_level_pass` subtracts it — no gate in O-code.
  Now Z+0.6000 tip / **Z+1.0000 cut** in both compensated modes, green blue and
  magenta together. Off unchanged.

  Side effect worth knowing: `test_rough_comp` overcut **0.0503 → 0.0394 mm**.

  **Left**: roughing's lead-OUT retreat geometry is still unmeasured, and no
  test asserts the start directly.

- [x] **Last pass behind the boss plunged instead of ramping — FIXED**,
  2026-08-04, `analysis/012`. greatEndian compared it against Sectioning ON,
  where the shape was right. The profile-angle ramp is capped so it is never
  longer than the cut it enters, but the cap sat **before** the stop table
  extends that cut — so it was tested against a stale, shorter length and the
  shortest pass lost its ramp: 2.2004 ramp against a 2.6397 cut, rejected.
  Arming moved after the stop extension. `test_rough_comp` gained *every pass
  behind the boss ramps in, none plunges*; negative control 9 of 9 plunge.

- [x] **Top roughing level missed the back wall — FIXED**, 2026-08-04,
  `analysis/011`. Compensated only: level r29.6520 stopped at Z-69.3840,
  **0.5080 short**, never touched the pre-finish, rapided away. The stop
  contour's orientation shift moved its open END too, so the back wall topped
  out at r29.6000 while the highest level sits at r29.6520. `entry_contour`
  now extends both terminal segments by the shift. `test_rough_comp` gained an
  UNDER-cut assertion - its existing metric is one-sided and a level that stops
  early reads as an improvement.

- [x] **Roughing lead-out "reference" — CLOSED, not a defect**, 2026-08-04.
  greatEndian: *"1 mm is not a stricted value .. leads are dependent only from
  properties"*. So a lead is `lo_len` at `lo_ang` from the point the cut ends,
  and nothing else may move it — not the stock envelope, not the pre-finish
  contour. Two earlier attempts to give it an external reference were wrong in
  principle, not just in implementation: `57eea44` stretched every retreat to
  the stock and was reverted.

  **Verified**: all 54 lead moves on testing_15_2 measure the configured
  length in both Off and Native (52 at 1.0000, 2 at 1.0001 rounding). The
  Z-room cap in `lathe_level_pass` that *could* shorten a retreat never fires
  on this project.

  Consequence accepted: a retreat therefore ends wherever its own length and
  angle put it — measured from 0.96 mm below the blue contour to 5.10 mm above
  it. That is the geometry of a property-driven lead, not a fault.

- [x] **Tool tip compensation on roughing's leads — ALREADY DONE**, verified
  2026-08-04 by measurement, no code change needed. The lead-in inherits from
  the entry contour (`dz -0.4456` Off→Native) and the lead-out from the stop
  table — retreat ends move by *exactly* the amount the stops move
  (-0.2459, -0.2197, -0.2194 …). Behind the boss those deltas read 0.0000
  because the stop there is limited by the **wall**, identical in both modes -
  nothing to shift, not a missing shift.

  Roughing now carries the nose end to end: level start Z (`_pl_rgh_oz`,
  `bfa2fa2`), entry crossing and profile-angle ramp (entry contour), stop
  (stop table), leads (inherited). The all-or-nothing rule is satisfied for
  roughing.

- [x] **Roughing ladder shifts out in X with Sectioning on — BY DESIGN**,
  2026-08-04, `analysis/013`. greatEndian: *"with sectionning its a separated
  sections and it has own rules"*. No change made.

  Instrumented, not reasoned: phase 1 runs stock → the section ceiling
  (29.8894) and its remainder is clamped away, then each section's ladder
  restarts there with full 0.508 steps and cannot land on the floor —
  0.2374 sliver at the bottom, 0.1106 skim at the top, whole ladder 0.2374
  further out. **Do not "fix" this into matching the unsectioned ladder.**

- [x] **"Compensated roughing overcuts the steep wall" — REFUTED**,
  2026-08-05, `analysis/015`. There is no defect. The stop contour matches the
  hand-derived tip stop **exactly** on a synthetic 83 deg wall (error 0.0000 at
  four levels), and measured as perpendicular distance — the only valid
  comparison on a near-vertical surface — compensation **improves** that wall:
  Off -0.2824, Native -0.1320, In CAM -0.1320.

  The 0.1643 mm was radius-at-Z compared column by column across an 83 deg
  wall, where one 0.0667 mm column spans 0.54 mm of radius. `test_rough_comp`'s
  own `radius_span` docstring documents this exact trap; it was written in this
  codebase and then walked into anyway. **Seventh baseline-class metric error
  of the session and the first to be committed as a finding.**

- [x] **Sectioning defeated "Space passes from" — FIXED**, 2026-08-06,
  `analysis/013` addendum. greatEndian: *"there have to be two different
  ladders.. one from stock and second for Final Contour"*.

  Phase 1 (stock → section ceiling) is spaced evenly; phase 2 (ceiling →
  floor) is anchored on the part. One shared ladder left phase 2 unable to
  land on the floor.

  | | before | after |
  |---|---|---|
  | Final contour | 17×0.5080 then **0.2374 at the contour** | **0.2374 at the top**, then 17×0.5080, deepest exactly 21.0160 |
  | Stock | 18×0.4862 then **0.3756** | **0.5071 throughout** |

  A ladder PER WINDOW was tried first and is wrong — the seven section windows
  start at different radii and their levels miss each other by 0.006 mm.
  `test_ladder.py` covers both anchorings; fails without the fix on both.

- [x] **Pre-finish OFF: a level swept 45.7 mm THROUGH the boss — FIXED**,
  2026-08-06, `analysis/016`. 2.7697 mm into a boss peaking at r32.66, 11 of 31
  cuts. The entry-contour crossing may sit behind the interval start - that is
  the ramp's room, +1.8127 mm on every level - but had no upper bound, so with
  the pre-finish off it reached 24-28 mm back, past the boss.

  Bounded to one depth of cut of PROJECTED length along the candidate's own
  segment (x1.5). A steep face then allows almost nothing; the 13 deg taper
  allows 2.2004 so pf ON is byte-identical. Clamping to `w_from` was tried
  first and is too blunt - it costs the ramp its room, 6 failures.

  `test_through_cut.py` toggles the pre-finish pass, because every saved
  project has it on and a check that did not toggle it would have passed
  throughout. Negative control: 11 of 31 through, worst 2.7697 mm.

- [x] **Bump at the part start: every pass now begins at Begin Z** —
  2026-08-06, `analysis/017`. Not a compensation fault: testing_15_2's first
  item runs to Z+1.0000, forward of the origin, so every pass followed it
  there. Now Z+0.0000 for roughing, pre-finish and finish in all three modes,
  with the reference from a new `#<_pl_begin_z> = #param_b_z` - record 1 of the
  lathe array is the first ITEM's endpoint, not the origin, and using it did
  nothing for 29 calls. **Known**: compensated overcut 0.0394 -> 0.0503 at
  Z+0.3, which is air (stock only at Z <= 0). Front-to-back only.

- [x] **The last roughing pass ran beside the pre-finish — FIXED**,
  2026-08-06, `analysis/019`. Not the level's length: the stop table's
  EXTENSION, unbounded, carried it **19.4436 mm** across a cylinder where it
  sits below the local roughing floor, leaving it 0.0160 mm from the pre-finish
  contour for 18.5 mm. Every legitimate extension on two projects is
  0.90-1.0034 mm.

  Bounded by the band it crosses - one depth of cut of radius, `doc/|slope|` of
  Z - with a floor of `3 x doc`, because a slope-only bound collapses on a
  near-vertical segment and cut the end wall's own 0.5080 extension, leaving
  every level short of the pre-finish wall.

  testing_15_4's deepest level 19.132 -> 0.088 mm; testing_15_2 unchanged.
  `test_ladder` asserts no level runs more than 2 mm within 0.10 mm of the
  contour; negative control 18.5 mm of 19.5.

- [x] **Every pass starts at Begin Z — roughing, pre-finish and finish** —
  2026-08-06. greatEndian: *"we are reaching roughing diameter in the stock"*,
  then *"implement this artificial extension to the prefinish and finish passes
  to have same starting behaviour as roughing has"*.

  **Roughing**: an EQUALITY on the first interval - the tip sits on Begin Z, so
  the lead-in has reached the cutting diameter by the reference. Two wrong
  versions shipped before it: a one-sided bound (the nose shift then pushed the
  start to Z-0.4, inside the stock - the reported fault) and bounding the CUT
  (arrives at diameter at -0.4 as well).

  **Contour passes**: the first segment is EXTENDED to Begin Z along its own
  direction. A bound on Z alone is wrong here - a level is a straight line at
  one radius so moving its start in Z keeps it on the level, but a contour
  entry moved in Z alone comes off the contour and the first cut becomes a
  diagonal onto it. On testing_15_4's chamfer the entry moves -0.1172 -> 0.0000
  with the radius carried back along the chamfer to r18.7657.

  Both projects, all three modes, all three pass types: **Z+0.0000**. Negative
  controls: roughing +1.0000/+0.6000/+0.6000, contour the same.
  `test_leads` still passes - the lead-in stays out of the material.

- [x] **One ladder floor for the whole part — FIXED**, 2026-08-08,
  `analysis/022`, `test_floor_ladder.py`. greatEndian: *"floor has to follow
  the profile per region"*.

  The whole bug in one line: on testing_15_4 the chamfer is entitled to a floor
  of 20.016 and the cylinder to 21.016 — **1.000 apart against a 0.508 depth of
  cut**, and 0.508 does not divide 1.000, so no single grid lands on both.

  **The ladder now re-anchors on each floor as it descends.** It does not need
  to know where each applies: a level that drops past a region's floor cannot
  reach it any more, so the Z span narrows by itself — **no windowing change and
  no traversal change.** Python emits the floors (`floor_ladder`, `#3300+i`);
  the `.ngc` walks them.

  Measured against the same program with the gate forced off: floors landed on
  go 0 → 2 (testing_15_4), 1 → 2 (15_2), **1 → 7** (13_arcs), 0 → 1 (11). The
  cylinder stops at 21.016 where it stopped at 21.032.

  Tried and rejected on the way: per-region **windows** — testing_15_4 has
  Sectioning on and the window that cuts spans both regions, so it cannot
  separate them, and splitting it would double the sweeps.

  **Caused one regression, fixed**: the moved ladder left a 1.3003 mm cut behind
  the boss where the profile-angle ramp no longer fitted, so it was dropped and
  the pass plunged. The cap now shortens the ramp to fit — half the cut — rather
  than dropping it, which also removes the coupling that let any ladder change
  cause a plunge.

- [ ] **Not every floor is reachable, and one of them is a point.**
  testing_15_4's chamfer bottoms at r19 at a SINGLE POINT, so no level can cut
  at its 20.016 floor and the pass is correctly blocked — 2 of 3 floors is the
  right answer there. testing_11 lands on 1 of 2 and has **not** been checked
  for the same cause. Worth confirming before anyone reads the number as a
  fault.

- [ ] **ID work has no floor ladder at all.** `build_floor_ladder_gcode`
  declines when the pass starts inside the part: on a bore the floors run the
  other way and every comparison inverts, and a wrong guess would rough INTO the
  wall rather than leave a sliver. Blocked on ID work resuming.

- [ ] **Two "halves" are choices, not measurements.** The ramp cap keeps the
  approach to half the cut it enters, and `floor_ladder` merges floors closer
  together than half a depth of cut. Both are the point below which a pass is
  not worth its approach; nothing says half is the best fraction for either.

- [ ] **The first stage still ends on a light cut.** On testing_15_4 the main
  ladder lands on the first floor with 0.3252 where 0.508 is configured, because
  it aims at the deepest floor and is clamped onto the first. Retargeting it to
  the first floor was tried 2026-08-08 and **reverted**: it gave a uniform
  descent but left the main ladder tiny and pushed the whole depth into the
  per-window stage walk, and `rs274` then failed to finish testing_13_arcs in
  ten minutes against 41.7 s without it. A light cut landing on a floor is not
  the fault that was reported; the 0.7068 overload was, and that is fixed.

- [x] **CLOSED, NOT FIXED — greatEndian 2026-08-13: never repeated.**
  ~~CRASH: toggling the Sectioning property kills the panel~~.
  **The cause was never found.** Closed on the report that it has not recurred
  across a fortnight of heavy use of that very property - the sectioning work of
  12-13 Aug toggled it on and off on every project. Something in that work may
  have carried it away, or it may be latent. If it returns, nothing here was
  fixed: start from a fresh crash, because there is no diagnosis to build on.


- [x] **Nothing asserts the roughing start or the retreat height directly —
  DONE**, 2026-08-08, `analysis/020`, `test_rough_ends.py`. Both ends of a
  level now have a test of their own instead of being read off
  `test_rough_comp`'s overcut number.

  **The start**: no level begins in front of Begin Z, at least one begins
  exactly ON it (the equality, not the one-sided bound the O-code warns about),
  all three modes agree, and it **tracks** — the project is generated again with
  Begin Z at −5.0 and the start has to move exactly with it, which is what stops
  the whole file passing on a program that always starts at Z0.0.

  **The retreat**: no roughing rapid removes material, measured by sweeping the
  real nose against the material as it stands at that point in the program; and
  the return traverse runs r31.8160, **1.8160 mm clear of the r30.0000 bar**.

  Negative controls both fire: with the Begin Z clamp deleted the start goes
  Off Z1.0000 / Native Z0.6000 — `analysis/010`'s bug reproduced exactly — and
  with the retract lowered 2 mm into the bar the rapid cut goes 0.0000 → 1.0000.

  Two things it does not cover, both recorded in `analysis/020`: the stock
  clearance check applies to **OD work only**, and a Begin Z set in FRONT of the
  profile start is deliberately not clamped and has no test either way.

  Noticed doing it: `test_rough_comp` reports Native **0.0503** today where the
  line above recorded 0.0394 on 2026-08-04. The subroutine is byte-identical to
  HEAD, so the number moved with the later commits and nobody saw it — which is
  the argument for the file.

- [~] **DEFERRED TO FINALISATION — greatEndian, 2026-09-03: *"let the roughing
  other operations to finalisation steps .. its not worth time to do now until
  everything in roughing external is done"*.** The gap below is real and the
  standing rule still stands; it is a question of ORDER, not of whether. The
  external (OD polyline) roughing is the thing being finished first, and the
  parametric ops' roughing compensation is picked up after it — not before.
  Nothing here is withdrawn, and nothing about it has been measured away.

- [ ] **Compensation is all-or-nothing — `taper_id`, `boring` and `facing`
  still switch it on inside the finishing loop only.** Standing rule in
  `CLAUDE.md` and memory. Done: the **OD taper** (`analysis/005`) and the
  **polyline's roughing** (`analysis/006`, proved by `test_rough_comp.py` -
  overcut past the pre-finish contour 0.1116 → 0.0503 mm).

  **The pattern to copy, in order:**

  1. Move `o<tip_comp_dia>` and the `#<x_side>` resolution **above** the
     roughing loop — in all three they currently sit inside the finish block,
     below it, which is why roughing structurally cannot use them.
  2. Compute a roughing offset with `o<tip_comp_vec>` whenever `n_comp > 0`
     (not just `EQ 2`), into locals, then clear `#<_tip_off_z>` /
     `#<_tip_off_x>` so the finish block keeps setting them itself.
  3. Apply it to the roughing coordinates. Roughing has **no interpreter
     compensation in any mode**, so there is nothing to double up with — the
     offset goes in the coordinates, as it does in `taper.ngc` now.
  4. Measure with a standalone driver: **no saved project contains a taper,
     boring or facing feature**, so there is nothing to regenerate. Call the
     subroutine directly, the way `test_facing.py` and the OD-taper driver do.

  **Watch for**, all three cost a run today: a comment line with no closing
  paren, or with a nested paren, halts `rs274` silently; a local first assigned
  inside a branch fails load-time pre-parse; and **comparing two move lists of
  different length is not a measurement** — a compensated run emits an extra
  establishing feed, which made an index-matched diff report 16.1588 mm of
  drift that did not exist.

  **`boring` and `taper_id` are ID work**, which greatEndian paused — they are
  listed here for the pattern, but the pause takes precedence. `facing` is OD
  and can be done now.

  Also unchecked and named in `analysis/004`: whether any of the three folds an
  allowance into the **D word** while setting L, which cancels itself the way
  the polyline's pre-finish did.


- [ ] **The artificial back-angle section and compensation do not agree.**
  greatEndian 2026-08-03, reported and NOT investigated - flagged here with
  what was established so it does not start from nothing.

  Two facts checked directly:

  - **Roughing carries no compensation whatsoever.** `lathe_level_pass.ngc`
    has zero references to `tip_comp_*` - no G41/G42, no D word. So what looks
    like compensation in the wrong direction behind the boss is not
    compensation; it is the ENTRY and STOP contour offsets
    (`lathe_sections.entry_contour` and the stop table) together with the
    back-angle ramp from `flank_envelope`, none of which know about the nose.
  - **Pre-finish and finish ARE compensated** - both run through
    `lathe_poly_pass.ngc`, 7 `tip_comp_*` references.

  greatEndian's two observations - roughing offset the wrong way behind the
  boss, and no compensation visible on the pre-finish artificial profile -
  both land on the **artificial section**, which is a surface the TOOL leaves
  rather than one the part has. Its offsets were written before compensation
  existed.

  **To start**: measure the artificial stretch (testing_15_2, Z−70.22 to
  Z−35.77) separately from the drawn profile in all three modes, the way
  `analysis/004` measured the pre-finish separation. Decide first whether that
  section SHOULD be compensated at all - a back-angle shadow is not a
  commanded surface - because that is a design question, not a bug.


- [x] **CLOSED, NOT FIXED — greatEndian 2026-08-13: never repeated.**
  ~~AXIS froze on the preview's Stop button, cause unknown~~.
  **The cause was never found**, and a freeze leaves no traceback - the process
  is alive and stuck, so there is nothing to raise. What it does leave is
  whatever was already flushed, which is why `_trace()` in `ncam_preview_ui`
  prints a line per coarse UI callback: the last line printed names the callback
  that did not return. That instrument is still in place, so a recurrence will
  say where itself. Set NCAM_NO_TRACE=1 to silence it.


- [ ] **Do `taper`, `taper_id` and `boring` fold an allowance into D too?**
  Unchecked. The polyline's pre-finish collapse came from exactly that - with a
  non-zero L the interpreter takes D/2 to BE the nose radius, so an allowance in
  the D word cancels itself on any surface parallel to an axis. Those three ops
  build D the same way through `tip_comp_dia`; whether any of them ever passes a
  non-zero `extra_r` has not been established. `analysis/004` has the mechanism.

- [x] **Two zero-length feeds per contour pass — CLOSED, will not be removed**,
  2026-08-08, `analysis/021`. `(Z−70.4000, r30.0000) → (Z−70.4000, r30.0000)`,
  one at the end of the pre-finish pass and one at the end of the finish pass on
  testing_15_2 — `lathe_poly_pass.ngc:366` naming the point the tool already
  occupies when the pass carries no offset and no nose term.

  **They stay.** `test_leads.py`'s exit-line check is literally *"a zero-length
  move exists in the tail"*, in all three modes, and that formulation is the one
  that survived after three wrong ones (locating the line by position broke when
  the modes stopped having equal move counts; the largest-Z-jerk version caught
  the lead-out blend arc, 0.3902 then 0.2168 mm, and failed on Off itself).
  Skipping the no-op deletes the regression detector for `analysis/009`'s
  0.5657 mm G40 jerk in exchange for 2 moves out of 323. My earlier
  *"skip it when `comp_r` is 0"* was wrong: that is exactly the mode set the
  detector lives in.

## Roughing direction — back to front, 2026-08-15

- [x] **BACK TO FRONT IS A DIFFERENT DECOMPOSITION — FIXED**, 2026-08-15,
  `analysis/054`. It is now one decomposition with two emission orders: every
  Python table that feeds the roughing scans is built in the front-to-back
  frame (`rough_frame_dir`), `poly_lathe_mill` always sweeps the forward record
  array, and direction 1 changes only the window visit order - re-ordered in
  Python, within each radius band, by `_sections_back_to_front` - and the
  movement, via the new global `#<_pl_cut_rev>` that `lathe_level_pass` reads.

  **Gate, all four met.** Cut SET identical on testing_15_6 / 15_5 / 15_2 /
  15_4 in both sectioning modes - 45 cuts not 40 on testing_15_6 sectioning on,
  0 spans unique to either direction - and every back-to-front pass travels
  back to front, 45 of 45. (**Those 45 became 44 on 2026-08-17**, when
  `analysis/058` removed the duplicate pass that was the whole of the "45 cuts,
  44 distinct" gap. The property — same SET, 0 unique — is unchanged.) Order: the long full-length window first, then every
  band last-section-first; Artificial slicing comes out exactly
  `[-57.7,-70.4] ... [0,-1]`. Front to back byte-identical across all 39 demo
  projects, the only difference being the one new default line.
  `test_x_continuity` and `test_leftover` now take a direction and are green in
  all four combinations, controls still firing. Overcut past the pre-finish
  target agrees between the directions to 0.0024 mm; `check_tangent` PASS both.

  **Still short, and recorded rather than hidden:**
  - [x] ~~a reversed pass has **no lead-in and no profile-angle ramp**~~ —
    **FIXED 2026-08-15, `analysis/055`.** Not by the mirror envelope this entry
    predicted: there is no second geometry to compute. Back to front is the
    **same motion played backwards** — each lead belongs to an END of the pass
    and keeps its own geometry either way, and `#<_pl_cut_rev>` only chooses
    which is traversed inward as the approach. `e_dir` is **deleted**; it was a
    second frame, the very thing `054` removed from the decomposition.
    Standing metal now **identical** to front to back, not merely close:
    0.7219 / 0.8579 / 0.6473 / 0.5681 on 15_5 and 15_6 × sectioning, against
    1.1827 / 1.1517 / 0.7324 / 0.8126 before. Lead/ramp moves 45 → **106**,
    equal to f2b. Overcut 0.0503 both directions; front to back still
    byte-identical, 0 lines differing.
  - [x] **INTERVAL ORDER INSIDE ONE LEVEL — FIXED 2026-08-17,
    `analysis/057`.** By the separate-windows route greatEndian ruled for, and
    **entirely in Python**: not one line of O-code changed and the window
    table's format is untouched. `_split_level_intervals` gives each interval
    of a split level its own window, in direction 1 only.

    **The crux dissolved.** The gaps a boss opens are NESTED — lower the level
    and the blocked set only grows — so one split point, the peak's own Z,
    serves every level in the band. The split does not have to move with the
    level. The band's top edge is `peak height + allowance`, below which a
    level is certainly blocked at the peak; above it the window is kept whole,
    or a level that runs straight through would be cut as two spans and the
    cut set would change. The model predicted the bracket the measurement
    shows: X34.5318 unblocked and full-length, X34.0636 the first that splits,
    threshold 34.167.

    **Measured, testing_15_6 sectioning ON: front-first 3 → 0.** Fifteen of
    the sixteen multi-interval levels are now strictly back-first. The
    sixteenth, X34.0636, has its window pair reversed but is still preceded by
    phase 1's own front cut at the same radius — the pre-existing duplicate
    below. So gate A is **15 of 16, not 16**, and the residue is not this
    change's. testing_11 moves 14/2 → 15/1 the same way.

    **And removing that duplicate did NOT close it — the prediction was
    wrong.** After `analysis/058`, X34.0636 reads
    `[-31.21 → 0.00] [-68.89 → -35.00]`: still front-first, now because phase 1
    **finishes the level itself** and cuts both intervals in its own
    front-to-back order. Still 15 back-first / 1 front-first, still not a
    regression, still phase 1. Closing it means teaching phase 1 the emission
    direction — see the paragraph below, which is the same conclusion reached
    from the other end.

    **What is NOT covered, and cannot be by this route: phase 1.** The
    unsectioned full-length pass above the section ceiling is not window-driven
    (`w_idx < 0`) and has its own multi-crossing loop, so no window table can
    re-order it. Every WINDOW-driven multi-interval level in every project
    measured is back-first; both residues seen — 15_6's duplicate, 11's
    three-interval level — are phase 1's own handover level. Giving phase 1 a
    window table is the next step and a bigger one.

  - [x] **PHASE 1 AND SECTIONING OFF NOW KNOW THE EMISSION DIRECTION — DONE
    2026-08-17, `analysis/059`, polyline.cfg 1.62.** The last ordering gap.
    Both sweeps no window table covers — phase 1 (`w_idx < 0`) and Sectioning
    OFF's own full-length window — are ordered by a Python-emitted table of
    PEAKS with their thresholds (`build_level_split_gcode`, `#3160`–`#3200`),
    which the runtime walks back-most sub-span first.
    - **The scan stays the authority.** A split point is only a bound handed to
      it; it still finds where each cut starts and stops. Deliberate, from
      `analysis/058`: the scan's resume answer can land just inside a rise
      (−34.171 where clear ground starts at −35.000), so Python boundaries and
      scan boundaries are NOT interchangeable. A peak sits safely inside the
      blocked gap, where they cannot disagree.
    - **Measured, front-first → 0 everywhere**: sectioning ON 15/1 → **16/0**
      on 15_6, 15_5 and 11; sectioning OFF **0/15 → 15/0** and **0/16 → 16/0**.
      Sectioning OFF was never in the ask — it was front-first on every
      multi-interval level and is fixed by the same change.
    - **Cut SET unchanged**: 8 project × sectioning × direction combinations,
      **lost 0, gained 0**, no duplicates; `cuts == distinct` still holds.
      Standing metal bit-identical. Front to back byte-identical bar the one
      new `#<_pl_p1s_n> = 0.0` default.
    - **A near-miss made permanent**: the table was going into "the free gap at
      3140", which two briefs specified. Only **3160–3200** was ever free —
      `polyline.cfg` stages its own CALL arguments at **#3141–#3159**, a block
      between two declared windows that `cam_map`'s overlap check could not
      see, so a table at 3140 would have silently overwritten them. `cam_map`
      gained a `cfg_scratch()` extractor so it cannot happen twice.
    - **Known limit**: the table holds twenty peaks. Overflow refuses the split
      rather than corrupting anything, so a very complex profile would silently
      keep the old front-first order — it would look like "back to front is
      right on my other parts but not this one".

    Nothing already won moved: cut SET identical between directions on
    15_6 / 15_5 / 15_2 / 15_4 / 9 (45/44, 47/46, 30/29, 29/29, 25/25, 0 unique
    either way), front to back **byte-identical across all 39 projects**,
    standing metal 0.7219 / 0.8579 / 0.6473 / 0.5681 unchanged, overcut 0.0503
    both directions, `check_tangent` PASS, `test_x_continuity` and
    `test_leftover` green in all four combinations with controls firing.
    Rapid travel back to front **1888.7 → 1877.9 mm**.

    **Budget, measured across all 39:** worst case **64 of the 200 slots**
    (testing_13_arcs, unaffected by the split); the split adds at most 8 slots
    to any project. A guard refuses the split rather than overflow.

  - [x] **A DUPLICATE ROUGHING PASS at the phase-1 handover level — FIXED
    2026-08-17, `analysis/058`.** `poly_lathe_mill.ngc` ~715 set
    `_pl_ph1_front_cut = 0` — "nothing was cut at all" — on a LATER iteration,
    where the first interval had already been cut and only the continuation was
    blocked, so phase 2's window redid the whole radius.
    - **The block was a disagreement about WHERE the level resumes, not
      whether there was more to cut.** `lathe_level_next_start`'s scan answers
      -34.171, just inside the rise; clear ground starts at -35.000. The resume
      ENVELOPE lands clear at -34.600 — the pick phase 2's own blocked branch
      already uses. Phase 1 now retries from there, searching from the last CUT
      end, and finishes the level instead of handing half over. A progress test
      refuses a candidate not past where the blocked pass started, so it cannot
      loop. It never consults the window table, which is why it holds in both
      directions.
    - **Measured**: 45 cuts/44 distinct → **44/44** on testing_15_6, 47/46 →
      **46/46** on 15_5, both directions; **SET lost 0, gained 0** in all four
      — a duplicate removed, not a pass. Standing metal bit-identical
      (0.7219 / 0.8579 / 0.6473 / 0.5681), which is what proves the removed
      pass was cutting air.
    - **`cuts == distinct` now holds.** The "45 cuts, 44 distinct" arithmetic
      quoted through `analysis/054`–`057` was this bug all along; those files
      are point-in-time records and keep the old number.
    - **Why it survived**: it removes no metal (`test_leftover` blind to it),
      deletes no pass (`test_x_continuity` blind), stays inside the pre-finish
      envelope (overcut blind) and is tangent-continuous (`check_tangent`
      blind). **A count and a distinct-count are different measurements, and
      where they disagree there is something to explain.**

  - **Sectioning OFF still emits multi-interval levels front-first** in
    direction 1. There is no window table at all in that mode -
    `poly_lathe_mill` builds its own single full-length window - so the
    Python-side fix has nothing to re-order. Closing it means emitting windows
    where today there are none, which needs the runtime's `_pl_sectioning`
    gate to change.

  - **the original front-first finding, for the record** — the measurement
    that led to the ruling:
    Re-measured 2026-08-17 on testing_15_6 sectioning ON, `analysis/056`:
    **16 of 28 levels carry more than one interval**, and 13 of those 16 already
    reverse correctly. Only **3 of 45 passes** come out front-first — the top
    three, X34.0636 / X33.5965 / X33.0885.
    - **Root cause, from the emission slots**: where a level's intervals land in
      DIFFERENT windows (slots 8 and 21) Python's `_sections_back_to_front`
      orders them; where both sit in the SAME window (slots 4 and 5) the runtime
      scan walks them sequentially and Python never sees two things to order.
      So it is the levels above the point where the part splits into bands.
    - **It costs nothing measurable.** The cut SET is identical either way
      (proved), and back to front already uses **less** rapid travel than front
      to back — **1888.7 mm against 1914.8 mm**, 146 rapids against 150.
    - **The fix is not cheap**: either the intervals become their own windows so
      the existing Python reorder catches them, or `poly_lathe_mill` gains a
      dry-run/scratch array. That is surgery on the choke point `analysis/032`'s
      five faults came from, for 3 passes of 45 with no metal and no time won.
      Recommend leaving it unless greatEndian sees it in the preview and wants
      it consistent.
    - **RULED 2026-08-17: greatEndian chose to FIX it, by the separate-windows
      route** — the Python-first one — over the scratch-array route and over
      leaving it. **Done, `analysis/057`** — see the tick above.
    - **The crux the route had to survive — it survived it**: intervals are
      per-LEVEL, not per-BAND. A window is `(z_from, z_to, r_lo, r_hi)` over a
      whole radius band, but the boss is tapered, so the split moves with the
      level — `-28.96..-37.41` at X33.5965 against `-27.48..-39.61` at
      X33.0885. **The gaps are NESTED**, so one split point at the peak's own Z
      is inside all of them; only the band's TOP edge has to be worked out, and
      it is `peak height + allowance`.
    - **Budget**: testing_15_6 used 32 of the 200 slots at 3400–3600 and now
      uses 40. Worst case across all 39 measured: **64 slots**, testing_13_arcs,
      which the split does not touch.
  - [x] **SETTLED 2026-08-17 — geometric section order STAYS.** greatEndian
    chose it over restoring the weakest-first rigidity ranking and over making
    it a parameter: back to front walks last section, section−1, … front, as
    specified. No work; recorded so it is not reopened.
    The mechanism, for the record: `_sections_back_to_front` replaces the
    weakest-first ranking within each band in direction 1. That is the one
    place to change if the ruling is ever revisited.
  - [x] **`param_dir` = 2, both directions — DONE 2026-08-18, `analysis/060`.**
    See the entry below.

- [x] **the original measurement, for the record.**
  greatEndian: *"back to front - is mess, it creates messy preview and mess
  Gcode ... path have to be same Gcode as Front to back but movement is from
  last polyline reference to front"*.

  **The spec is an ORDER, and greatEndian stated it fully** on 2026-08-15:
  *"rough all long passes from last reference to first, then last recognized
  section rough, last recognized section − 1, repeating to first/front
  section"*. So it is three ordering rules, not one:
  1. the **long passes first** — those spanning the whole part — run from the
     last reference toward the first;
  2. then the **sections**, in DESCENDING order: last recognised section, then
     that section − 1, down to the front-most;
  3. and within all of it the **cut set is the front-to-back set**, unchanged.
     Front to back must stay byte-identical.

  Measured on testing_15_6, sectioning on:
  front-to-back 45 level cuts, back-to-front 40, and **one cut shared between
  them** (44 unique to one, 40 to the other). Front to back opens with long
  passes down the whole part; back to front opens by roughing one section at
  radii the other never uses there. `analysis/052`.
  - **Ruled out by experiment**: the two profile reversals in
    `build_sections_gcode` / `build_floor_ladder_gcode`. Disabling them makes it
    worse - 34 cuts, still disjoint - so the Python point order is not the
    cause and the cheap fix does not exist.
  - **It lives in `poly_lathe_mill`**: at `dir == 1` the whole sweep runs on the
    REVERSED record array, so every downstream decision - which windows exist,
    their order, where a level starts and stops - is taken in that frame.
  - **The fix**: compute the decomposition in one frame (front to back) and
    reverse only the EMISSION - window order, section order, and each pass's
    cut direction. A rework of direction handling at the choke point
    `analysis/032`'s five faults came from, so it wants its own pass; not
    started rather than half done.
  - **Gate**: same cut SET as front to back (45, not 40), reversed order, front
    to back byte-identical, and `test_x_continuity` + `test_leftover` green in
    BOTH directions - which they have never been asked to be.
- [x] **Both directions (`rough_dir == 2`) — DONE 2026-08-18, `analysis/060`.**
  greatEndian: *"now do the both directions"*.

  It was unimplemented with **two** faults, both measured on testing_15_6
  sectioning ON: it did not alternate at all (28 cuts, every one of them the
  same way round as direction 0), and it was a strict SUBSET of direction 0's
  cuts, missing the 15 behind-boss intervals and leaving **7.49 mm** of stock
  standing at Z−67.

  **Root cause, one line:** `rough_frame_dir(2)` returned 2, so `flank_sides(2)`
  answered `(1, -1)` — peaks on BOTH sides casting a shadow. That makes the
  reachable envelope the INTERSECTION of the two directions' reachable sets, so
  "both directions" reached strictly LESS than either one. Backwards: a tool
  that can approach from both ends reaches more, and the shadow is per PASS,
  each of which has exactly one direction.

  **The fix, Python-first.** Direction 2 now rides frame 0 — direction 0's
  windows, levels, intervals and window ORDER — and alternates only the
  emission. `flank_sides`' and `mirror_dir`'s 2 branches are deleted; both take
  a FRAME direction now. `param_f_dir` = 2 goes through the same mapping, and
  so do the preview's drawn twins. The only O-code is a flag: `#<_pl_cut_alt>`
  set in `poly_lathe_mill`, and `lathe_level_pass` flipping `#<_pl_cut_rev>` at
  its very end — past every motion, and past the three returns that leave
  without emitting any, so a skipped or blocked pass never consumes a flip.
  The parity has to be runtime because only the runtime knows how many passes
  there will be.

  **Gate, all eight met.** Perfect zigzag, **0 repeats**, in all six
  project × sectioning combinations. Cut set against direction 0: **lost 0,
  gained 0**, six of six. Stock field **identical to 0.0000 mm** at Z −40 /
  −50 / −60 / −67 (was +1.26 to +7.49). `test_leftover` and `test_x_continuity`
  extended to direction 2 — they had never generated it, which is exactly how
  it stayed broken — and green in all six combinations, controls firing 21 of
  21. Directions 0 and 1 differ from `1ea086d` by **exactly one line** across
  12 combinations, the required `#<_pl_cut_alt> = 0.0` default. Direction 1
  still 16/0 back-first sectioning ON, 15/0 and 16/0 OFF; `cuts == distinct`
  in all 18 runs. Standing metal 0.7219 / 0.8579 / 0.6473 / 0.5681, unchanged
  and now equal in all three directions. Overcut 0.0503; `check_tangent` PASS
  for direction 2 six of six.

  **Left open, deliberately:** direction 2 removes the same metal as direction
  0 in a better order — it does not yet reach FURTHER. The union envelope a
  genuinely bidirectional tool could use would change the cut set and
  manufactures sub-nose corners the interpreter refuses; that is a third
  decomposition with its own gate. Parity carries across section boundaries
  (one line to reset if greatEndian wants each section to open the same way).
  `param_f_dir` = 2 still does not alternate the finish passes.

## Tool shape

- [ ] **AN EXPANDED TOOL TABLE IS THE PREREQUISITE, and it now blocks real
  geometry.** greatEndian, 2026-09-03: *"we need to insert expanded tool table
  or tool table wizard tab where we will add more dimensions to be able to see
  to real tool setup"*. LinuxCNC's table carries D, I, J, Q and the offsets and
  nothing else, so everything about the tool's BODY is either a NativeCAM
  parameter on the Tool Change or parsed out of the description comment.
  - What it must carry, from `ref/tool-shank/NOTES.md`: the shank height `h`
    (built already, `param_shank_h`), the insert dimension `h` is derived from,
    and the shank width `b` for turn-mill clearance.
  - **CORRECTION, 2026-09-03.** I said the radial datum was the number blocking
    the geometry. It is not missing: `tool_shank` DERIVES the block's position
    from the insert's far corners, and that derivation has a measured
    validation behind it - anchoring on the tool tip instead once reported 50
    collisions on a program with none, and the same 50 for a 12 mm shank as for
    a 25 mm. What is genuinely not carried is the SEATING, the shim that leaves
    the block set back further than the insert corners, and that is a
    refinement rather than a blocker. **The geometry below is not blocked.**
  - Interim, 2026-09-03: `param_shank_ox` / `param_shank_oz` on the Tool
    Change carry that seating for testing now, both defaulting to 0 = flush =
    what has always been drawn. greatEndian: *"for active testing just add
    property near tool section which will carry this value for us now"*. They
    are superseded cleanly when the real table arrives.
  - The full table is designed **from a future CAM tool-table example**
    greatEndian will supply - `/ref-intake` on it, the way `ref/tool-shank`
    was just done.
  - greatEndian ruled `h = 0` does not occur: *"h every time depends at tool
    tip insert dimension which we have to grab from expanded tool table"*.

- [ ] **NEEDS A CALL — the holder model is BUILT and measured, and it cuts
  LESS, not more.** `analysis/074`. `FLANK_SHANK_BOUNDS`, off by default.
  Three regimes replace two: the wedge to the insert's edge length, then the
  block's flat floor `rp - 12.0946` to the holder length, then nothing.
  **I predicted it would recover the 10.0899 mm and it does the opposite**:
  across testing_15_2, _15_4 and _15_5 the reachable contour is never lower and
  up to **2.2288 mm of radius HIGHER** at Z−69.58. The infinite wedge was
  optimistic at long range — it let the nose sit 13.6 mm below an obstruction
  59 mm away when the block face is a fixed 12.09 mm below the nose. So this is
  a safety correction that costs material, not a productivity one.
  - **ON**: roughing stops where a real 25 mm holder clears. Costs 2.23 mm of
    radius behind the boss.
  - **OFF**: today, byte-identical, and the tool reaches 2.23 mm deeper than
    the holder allows at long range.
  - **greatEndian, 2026-09-03: leave it OFF — *"I will test it at real
    machine"*.** So the acceptance is a real cut, not a harness, and the flag
    stays False until that comes back. Nothing further to decide here; the
    model is built, measured and waiting.
  - To try it on the machine: generate with `NCAM_SHANK_BOUNDS=1` in the
    environment, or flip `FLANK_SHANK_BOUNDS` in `lathe_sections.py`. Both
    switch the whole contour at once — roughing, pre-finish, finish and the
    preview take the same surface.

- [x] **The shank bounds the PICTURE but not the reachable contour.** Verified
  2026-08-08 and re-confirmed today: a 25 mm shank and a 0 shank produce a
  byte-identical program. So the tool the preview draws and the tool
  `flank_envelope` believes in are different tools — the picture shows a holder
  that stops, the geometry dilates by an unbounded wedge.
  - **Not the same question as `FLANK_BOUNDS_CONTOUR`**, which bounded the
    shadow by the INSERT length and was withdrawn deliberately in `310a06b`,
    re-confirmed 2026-09-03. The shank is a larger, differently-shaped
    obstruction: near the nose the insert binds, far behind it a constant-height
    block binds instead of an ever-growing wedge. That is why a proper tool
    model may honestly recover some of the 10.0899 mm behind the boss that the
    infinite wedge refuses.
  - **greatEndian ruled the holder may move through metal that is already
    gone** — *"if material was cutted out, then it does not present there
    anymore and shank of tool can move around without any questions"*. So it is
    judged against the CUT STATE, not raw stock; the conservative reading is
    rejected.
  - Blocked on the radial datum above. Acceptance for boring bars and grooving
    holders is *"left to real world testing"*.


> The tool as it stands is written up in full in **`TOOL-DEFINITION.md`** —
> every line, where each number comes from, and what the collision check counts
> as tool. Read that before changing any of it.

- [ ] **Rework the tool dimensions and the visualisation onto a CAM
  package's own tool template.** greatEndian, 2026-08-02, after seeing the
  shank in AXIS. What we have is built up from what LinuxCNC's tool table
  happens to carry — nose radius, orientation, front and back angle — plus two
  numbers bolted onto the Tool Change (flank length, shank height). A CAM
  package defines a turning tool as one object: insert designation, holder
  designation, hand, and a drawn profile that follows from them. That is the
  shape to move to, and it decides which of our numbers survive.

  **Needs the reference material first** — a screenshot or export of the tool
  definition dialog we are to follow, into `ref/tool-template/`, then
  `/ref-intake`: restate it as a parameter table in our vocabulary and confirm
  before any code. Do not start from a guess at what the template contains.

  Known to be affected: the flank length (whether it stays a separate number
  at all), the shank height field added today, the over-90° angle cases below,
  and whether the drawn tool keeps coming out of the tool table or out of its
  own definition.

- [ ] **A front or back angle over 90° still has no defined contour.** The
  construction puts an edge at 90 − angle from Z, so past 90° it leans the
  other way and the shape stops meaning what it means for a normal insert.
  The shank bounds it now, so nothing runs away, but a bounded wrong shape is
  still a wrong shape. Re-measured on a 0.8 mm nose, orientation 2, 6 mm flank,
  25 mm shank:

  | front | back | insert, no shank | insert, 25 shank | holder face |
  |---|---|---|---|---|
  | 15 | 75 | 6.0 × 23.3 mm | 12.6 × 12.6 mm | yes |
  | 15 | 105 | 6.0 × 24.7 mm | 12.2 × 15.7 mm | yes |
  | 95 | 75 | 5.3 × 1.8 mm | 12.0 × 4.2 mm | **none** |
  | 100 | 110 | 5.5 × 2.0 mm | 12.0 × 4.1 mm | **none** |
  | 0 | 75 | **none** | 12.6 × 12.8 mm | none |

  Two things changed with the shank and neither is a fix. A front angle over
  90° still draws a wrong insert - a 12.0 × 4.2 mm sliver - and still drops the
  holder face without saying so. And the 0° case, which used to draw nothing at
  all, now draws a full-looking insert: the shank construction never refuses on
  angle, so the one case that failed loudly now fails quietly. Needs a defined
  answer for those tools - a different closing line, or a refusal the operator
  can see - rather than a quietly wrong picture.

## Simulation — paused at your word

- [ ] **Collision detection is built and tested but not wired to the pane**
  (`fdfa99d`). Reports rapids into metal and the tool body into metal, 1.5 s
  on testing_15_2. It was held back because its output depended on the tool
  shape - **that blocker is gone**: with the shank it reports **0 hits on the
  demo lathe program at every shank size, 12, 25 and 32 mm**, and still catches
  a holder driven through the bar 40 mm behind the tip, which no insert can
  reach. Only the wiring is left.
- [ ] Timeline marks for collisions, and a Verification line in Stats —
  designed, not built.
- [ ] `Accuracy` slider → `StockField.columns_for`.
- [ ] `Regenerate on rewind` as an option (currently always on).
- [ ] `Programmed Point` toggle (the control-point cross is always drawn).

## ID work — PAUSED at greatEndian's word, 2026-08-02

Nothing here is being worked on. Each item says what finishing it would take,
so picking it up again does not start from a blank page.

- [ ] **The comp entry drives into the wall on ID work, 0.2929 mm.** Found by
  the pre-finish / finish lead-in check below, 2026-08-02. On an OD profile the
  entry is harmless; on a bore it is not.

  With `li_len` and `li_rad` both 0, `lathe_poly_pass` takes its plunge branch -
  rapid clear, rapid to the entry radius, switch comp on, trace from record 2 -
  and LinuxCNC's own compensation entry then moves the control point **1.0000 mm
  diagonally at 45 degrees** to reach the compensated start. Measured on
  testing_14_inside, a 34 mm bore, 0.5 mm nose:

  | pass | rapid lands | entry ends | finished wall | overshoot |
  |---|---|---|---|---|
  | pre-finish | r 16.0778 | Z −0.7071, **r 16.7849** | r 16.492 | **0.2929 mm** |
  | finish | r 16.5858 | Z −0.7071, **r 17.2929** | r 17.000 | **0.2929 mm** |

  The same figure on both, so it is the compensation entry vector and not a
  contour artefact. For a bore the metal is at LARGER radius, so 0.2929 mm past
  the wall is 0.2929 mm into it, and it happens 0.7071 mm inside the mouth.
  Note this is the **control point** crossing the wall as `rs274` reports it;
  what it does to the surface depends on the nose geometry and has not been put
  through `prove_tip_comp.py` yet.

  Almost certainly the same fault as the **1.4929 mm ID lead-in/out gouge**
  already open under Lathe G-code, seen on a different op.

  **The fix has a precedent**: `boring.ngc` and `taper_id.ngc` already widen
  their post-comp radial retract by `#<_tip_lead_w>` for exactly this reason -
  the round nose swinging back into the finished wall. The polyline's plunge
  approach needs the same widening on the ENTRY side, so the diagonal happens
  in the bore's open space instead of in the wall. That is a change to
  `lib/lathe/lathe_poly_pass.ngc` - motion, ID, and comp - so it is not being
  made without a word first.

  **To finish**: widen the polyline's plunge approach by `#<_tip_lead_w>` on the
  ID side in `lib/lathe/lathe_poly_pass.ngc`, the way `boring.ngc` and
  `taper_id.ngc` already widen their post-comp retract; regenerate
  testing_14_inside and confirm the entry ends inside the bore's open space
  rather than 0.2929 mm past the wall; then put it through
  `prove_tip_comp.py --op boring` to show the surface itself is clean, which has
  never been done for this case.

- [ ] **ID lead-in/out gouge, 1.4929 mm native** — open since the tip-comp work.
  Very likely the same fault as the item above, seen on a different op.

  **To finish**: measure it again first - the 1.4929 mm figure predates both the
  entry-contour work and the stop table, and no baseline in this project has
  survived that long. Then it is the same one-line widening, or it disappears
  with the item above and only needs confirming.

## Lathe G-code

> Compensation as it stands — the three modes, the shared subroutines, the
> per-op side table, which op supports what, and the entry rule — is written up
> in **`TOOL-DEFINITION.md` §7**. The open points below are what is left.

- [x] **CNC-SIDE IS THE DEFAULT — RULED AND DONE**, 2026-08-13, `analysis/045`.
  greatEndian: *"CNC side"*. Six of the seven lathe ops already defaulted to
  Native LinuxCNC; only `facing` shipped `value = 0`, disagreeing with its own
  tooltip which already called Native the default. `facing.cfg` → 1.26.
  - **Scope, measured**: a cfg default is read when a feature is ADDED, and a
    saved project keeps its own stored value through migration. All three demo
    projects hash identical before and after (`b849fd15881b` / `7de894acaec9` /
    `d5d3b06f1ee0`), and testing_15_5 still stores Facing=0, Polyline=2. **An
    existing feature must be set by hand.** Same asymmetry `analysis/043` found
    for the back-clearance bounds.
  - Noted in the tooltip: any compensated mode on FACING replaces the lead-in/out
    arcs with a straight run-in beyond the OD, because an arc cannot establish
    compensation — so switching a facing cut off Off changes the motion, by
    design. `test_comp_default.py` locks all seven.

- [ ] **In CAM comp is refused on FACING only** — corrected 2026-08-02 by
  reading the code rather than the note. The `.cfg` validation blocks mode 2
  outright: *"it produces the same cutting coordinates as Native LinuxCNC, but
  its approach moves place the tool past the finished face before the cut and
  the tangency proof reports a gouge there that Native does not"*. Both tapers,
  boring and the polyline accept it. The earlier wording here said "the five
  parametric ops" and was wrong.

- [ ] **`turning` and `radius_od` have no Tool nose comp parameter at all.**
  They carry pre-existing native comp chosen inside the subroutine
  (`#<comp>` = 41 / 42 / 40, `G#<comp>`), proven geometrically rather than
  rewritten, and there is no way to ask them for In CAM or for Off. Deliberate
  so far — worth deciding whether they join the other ops.

- [ ] **Grooving and drilling have no compensation story** because neither
  exists yet; whatever is decided below has to cover them when they are built.
- [ ] **Grooving and drilling stay OPEN until the outside polyline is
  finished** — greatEndian, 2026-08-03. Both are planned in full (see the
  compensation plan's steps 6 and 7: the plunge and peck schedules computed in
  Python and walked as tables, the insert-width refusal when the tool
  description carries no `W` token, and a lathe peck cycle written out because
  `G81`/`G83` drill along the axis normal to the plane, which is Y in G18).
  Neither is started. Grooving is **absent** rather than a placeholder - no
  `.cfg`, no `lib/lathe/` sub, no menu item; drilling has a menu placeholder at
  `catalogs/lathe/menu.xml:17` and nothing behind it.

## Consequences of decisions taken, worth a look in AXIS

All four measured 2026-08-08, `analysis/021`. Three are provably harmless; one
is not, and it is the one to look at.

- [ ] **Back angle clearance defaults to 2° and it CHANGES THE PART.** Measured
  on testing_15_2 Native: **323 → 345 moves, 198 of them different** against
  clearance 0, and it deepens the unreachable shadow behind the boss by
  0.3562 mm of radius. Every migrated project's roughing moved. Whether 2° is
  the right standoff is a judgement in AXIS, not a number measurable here —
  **this is the one worth your eyes.**
- [x] The **unbounded flank leaves up to 10.0899 mm of radius uncut** behind the
  boss on testing_15_2, Z−70.22 to Z−35.77, from `unreachable_spans` with the
  live arguments. *(The 9.73 mm over Z−70.22..−36.31 recorded here before was
  the clearance-0 figure, from before the 2° default.)* testing_15_4 is the
  same to four decimals.
  **CLOSED 2026-09-03 as physical, by greatEndian's ruling** — *"tool has some
  dimensions and some of the material behind the boss segment is not
  reachable"*. It is a limitation of the tool and the setup, not a defect, and
  `FLANK_BOUNDS_CONTOUR` stays False: bounding the shadow by the INSERT length
  was withdrawn deliberately in `310a06b` and is not being reinstated.
  What this does NOT settle is whether the shadow should be bounded by the
  HOLDER rather than by nothing — see the tool-model entry below, which is the
  live question.
- [x] **Skip short passes off by default — verified a true no-op**, 2026-08-08.
  Identical program at the default; 0.3 changes 307 moves.
- [x] **Flank length is picture-only — verified**, 2026-08-08. 16 mm and 25 mm
  produce a **byte-identical** program on testing_15_2. testing_15_2 and
  testing_15_3 can have their 25 mm re-entered for the silhouette; it does not
  touch the metal.
- [x] **The 25 mm / 1 in shank is picture-only — verified**, 2026-08-08.
  Byte-identical program with the shank at 0 and at 25 mm. A 12 mm boring-bar
  tool still looks too big until it is set.

## Z limits, stock to leave, and the validations — 2026-08-09

Everything left open from `analysis/024` and `analysis/025`, including the
validation ones.

- [ ] **Negative stock to leave is not exposed, and fails SILENTLY past its
  bound.** `offset_contour` already cuts past the model correctly down to
  `extra > -nose_r` — measured −0.10 → −0.1000 and −0.39 → −0.3900 with a 0.4
  nose. At −0.40 and −0.50 the guard returns the profile unchanged: **ask for
  0.5 past the model and get 0.0, with no warning.** The cfg minimum is 0.0 so
  it is unreachable today. Exposing it needs the bound enforced loudly and a
  decision about roughing, which cannot hold a negative allowance without a
  nose.

- [ ] **Intermediate finish passes under Native comp use the radial value
  alone.** `G41.1 D` is a single number. Only bites with Passes > 1 AND Native;
  the final pass is offset 0 and the pre-finish traces a Python table, so both
  are fine. In CAM has no limit. In the tooltip.

- [ ] **A front limit's lead-in still encroaches 0.707 mm.** Feeds reach
  Z−19.293 against a Z−20.0 limit — 1.0 mm of lead at 45°. It is the rule the
  Begin Z bound has always followed, the TIP is bounded and the lead descends
  from outside, and changing it would change that settled behaviour. Asserted
  as bounded by the lead-in length so it cannot grow. **NEEDS A CALL:** should
  a front limit approach radially instead?

- [x] **The Z limits have datum modes — DONE**, 2026-08-13, polyline.cfg
  **1.55**, `analysis/039`. *Front Z datum* / *End Z datum*: Absolute Z (the
  default, unchanged) or From workpiece face, the value then being how far past
  the face into the stock. The face reaches generation-time Python the way the
  tool change's values already do — `to_gcode` publishes it as it walks the
  tree, the Workpiece being the first feature — because a Feature has no
  back-reference to its tree and `lathe_sections` imports nothing from `ncam`.
  Default proven byte-identical on three projects; datum 40-from-face equals
  absolute −40 (Z−40.6043), follows the workpiece to Z−50.6043 when it moves,
  and an absolute value correctly does not. `test_z_datum.py`.

- [x] **An End Z limit does not bite on testing_15_5.** DONE 2026-09-03,
  `analysis/073`. It was a SAFETY bug: six roughing feeds ran past the limit,
  one of them Z-0.4000 to Z-70.8000, taking 30 mm of stock the limit was set to
  protect - while the finish passes stopped correctly, so only half the program
  was wrong. The Z limits trim the profile and every contour built from it; the
  roughing window takes its extents from the RAW record array and had never seen
  the trim. `build_z_limit_bounds_gcode` emits the Z band and poly_lathe_mill
  clamps both extents into it. 15_5 now stops at Z-40.6043 - the same Z as 15_2
  under the same limit. No-limit motion byte-identical on all three projects.

- [ ] **VALIDATION — a `[VALIDATION]` block cannot use `resolve_points`.** It
  runs from `Feature.validate()` part-way through `to_gcode`'s walk, before the
  children are resolvable, so it returns an **empty list** there. A check
  written as "if the trim leaves fewer than two points, refuse" fired on a
  perfectly good profile. Only parameter-against-parameter checks are reliable
  in that block. In `LEARNINGS-LOG.md`.

- [x] **VALIDATION — `msg_inv` at severity 1 blocks any headless run.** DONE
  2026-09-01, `analysis/070`. `ncam.py` returns after the print when there is no
  visible toplevel window: in the GUI there always is one, in a batch run there
  never is, and the message is already on stdout. `test_bidir_warn` asserts all
  six tool x direction combinations still produce a program, so a future
  validation cannot quietly bring the hang back. This was the prerequisite for
  the Both-directions warning - no validation could be added at all before it.

- [x] **superseded: VALIDATION — `msg_inv` at severity 1 blocks any headless run.** It ends
  in `Gtk.Dialog.run()`, waiting for a button nobody can press when
  `gen_project.py` or a test drives the generator; the symptom is a silent
  45-second hang, found with `faulthandler.dump_traceback_later`. Severity 2
  does not block. **No test may exercise a severity-1 validation**, which is
  why the crossed-limits check is untested.

- [ ] **VALIDATION — the Z limits are only half validated.** The crossed case
  is refused. NOT checked: a limit that falls outside the profile entirely (it
  silently does nothing), and limits that leave too little to machine. Both
  need the resolved profile, which the block cannot have — they belong in the
  `[AFTER]` block or in Python at generation time.

- [~] **THE BLOCKED DECISION IS IN PYTHON AND PROVED CALL FOR CALL** —
  2026-09-03, `analysis/082`. `lathe_sections.level_blocked()` returns what
  `lathe_level_pass` puts in `#<_level_blocked>` for **3373 of 3373 calls**
  across the same 30 configurations, 1519 of them blocked, 0 uncovered.
  **Nothing in the toolpath reads it** - replica, parallel run, migration last.
  - It is a TABLE WALK, not a geometry solve: when the floor contour Python
    emits is present (`_pl_flc_n GT 1`) both scans walk only that table and
    skip the record-array offset scan outright.
  - **Every one of the 3373 calls took the multi-crossing branch.**
    `polyline.cfg:702` hard-wires `_pl_multi_cross = 1` and `lathe_level_pass`
    has exactly one caller, so the single-crossing branch is unreachable from a
    polyline - replicated for fidelity, exercised by nothing.
  - **The record-array scan is a live fallback and is NOT replicated** - it runs
    when `build_floor_contour_gcode` returns nothing: total allowance zero,
    under two contour points, or the table overflowing `FLOORC_TOP`.
    `level_blocked` returns None there and the test counts those calls.
  - **The gate caught three faults before it could report anything**, one of
    which was a silent green: `floor_contour` read nothing, so 30 per-config
    checks all said PASS over 0 answers. Only the coverage check failed. The
    cause was the defaults block assigning `_pl_flc_base = 0` like every other
    global - the same trap that nearly shipped gap 10 inert. Rule, now twice
    scarred: **read the LAST assignment and count only the non-placeholder
    ones.** A reversed-window negative control was added too.

- [~] **THE INTERVAL WALK IS FULLY PREDICTED IN PYTHON** — 2026-09-03,
  `analysis/083`. For every level the ENTIRE sequence of `lathe_level_pass`
  calls is predicted - each interval's start and where the sequence ends -
  across 30 configurations, **2656 interval walks, 717 of them multi-interval,
  3373 calls**. `test_level_intervals`. Nothing in the toolpath reads it.
  - New pure functions: `resume_z` (the `_pl_env_*` answer, a walk of the
    resume envelope Python emits) and `level_stop_z` (`_pl_level_z_end`: the
    crossing clamped at the window end, where the window end carries the nose
    term and the crossing does not). `_level_scan` is now shared with
    `level_blocked` so the two cannot drift.
  - **THE TEST TAKES NOTHING FROM THE RECORD.** That was not the first plan:
    z_end is refined against the stop contour with a tool-reach clamp
    (`lathe_level_pass.ngc:904`), so the walk was first proved with z_end fed
    back IN from the record and the refinement MEASURED - **it moves z_end on
    0 of 1854 cutting calls**. Exact, so the observation was dropped. Measuring
    first is what made that safe.
  - **The stop-contour refinement never fires on these five projects.** It is
    carried for cases that do - `lathe_level_pass.ngc:895` records
    testing_15_2 with the axial allowance at 2.000, which this sweep does not
    set. The count is printed so such a project shows up as a disagreement
    rather than as silence.

- [~] **THE WHOLE ROUGHING STACK IS PREDICTED IN PYTHON** — 2026-09-03,
  `analysis/084` and `085`. Each layer proved GIVEN the one above it:
  `window (085) -> sub-span (084) -> interval (083) -> level set (080/081/082)`.
  **Nothing in the toolpath reads any of it.**
  - `sub_spans()` - poly_lathe_mill's `o<wh_seg>` loop, the `#3160` split table
    read back to front, each peak breaking the sweep at most once.
    **30 configurations, 2537 levels, 119 split into sub-spans.**
  - `roughing_windows()` - the `o<wh_w>` loop. Sectioning off is ONE window
    (`w_len` is the whole span plus 1 on purpose); Artificial is the table
    alone from index 0; Natural adds the phase-1 window at -1. The Z bounds are
    predicted from the RAW profile pair - back extension applied, THEN the Z
    limits clamped, a limit being a hard bound where an extension is a request.
    **179 windows, 152 with a radius band, 27 ceiling phases.**
  - **The sub-span gate's first run failed 7 of 30, all `dir=1`, AND silenced
    its own control.** I predicted `sg_use` from `#<_pl_cut_rev>` read out of
    the program, but that global is a RUNTIME value - set from `rough_dir` and,
    for Both directions, flipped after every pass that emits motion
    (`lathe_level_pass.ngc:1785`) - so the source only shows the defaults
    block's 0.0. The mismatch `continue`d before the control ran, so 119 split
    levels never reached it and it reported nothing rather than a problem.
    **A silent control reads exactly like a passing one.** Also found:
    `rough_dir != 1` ZEROES `_pl_p1s_n` (`poly_lathe_mill.ngc:1320`), so front
    to back and Both directions have no split table at all whatever Python
    emitted. Both fixes are the same: the direction is a cfg parameter, read it
    at generation time.

- [ ] **THE PHASE-1 HANDOVER — MEASURED, AND MY EARLIER CLAIM RETRACTED** —
  2026-09-03, `analysis/086`. I said the boundary of the migration was the
  handover reassigning `sect_top_r`. **All three of its sites fire 0 times over
  30 configurations** - the ceiling is never moved. That claim was wrong, and
  wrong in the direction that mattered: I reported a hard runtime dependency
  the stack does not have.
  - What DOES fire is narrower: `_pl_ph1_front_cut` / `_pl_ph1_z_end`, **6 of
    30** - 15_5 and 15_6 sectioned, all three directions. It records how far
    phase 1 got so phase-2 windows it already covered start one level deeper.
  - **It may reduce to nothing.** `_pl_ph1_z_end` is `_pl_level_z_end`, which
    `level_stop_z` already predicts exactly (1854 of 1854, `analysis/083`), and
    the firing is gated on `p1_cut`, which the proved layers determine.
    HYPOTHESIS, not a result - it is the next gate.
  - **First understand the gap**: 27 configurations run a ceiling phase and
    only 6 hand over. Whatever separates them is the real condition, and a
    narrow path is where a wrong general rule hides.

  `skip_thin` still comes after the blocked decision, not before -
  `_pl_prev_thin` advances only where a level actually cuts.

- [x] ~~**NEXT LAYER: the interval walk.** `level_blocked` is handed `w_from` and
  `w_to` out of the record. Supplying them from Python means knowing the
  interval walk - the 3373 calls are not one per level, a level behind a boss
  is re-called per disjoint interval and where the next starts comes from
  `lathe_level_next_start` and the resume envelope, which read the previous
  blocked answer. The FIRST call of each level in a window is the one Python
  could already predict; the continuations are the layer after. That, plus
  `skip_thin` needing this first, is what stands between here and the
  migration.~~

- [~] **THE LADDER IS IN PYTHON AND PROVED BOTH WAYS, stages one and two**
  - 2026-09-03, `analysis/081`. **GATE TWO PASSES: 0 of 30 configurations has
    an unexplained level.** Per configuration `predicted = cut + thin +
    out-of-band + past-stock + blocked + unvisited`, and the unvisited part is
    a TAIL rather than a HOLE. `pred=807 cut=744 thin=18 band=0 stock=6
    blocked=24 unvis=0`. `test_ladder_account` is that sweep; it instruments a
    SCRATCH copy of `poly_lathe_mill` - the repo's `lib/` is untouched - and
    proves the instrument inert by flattening the same program through a clean
    lib and the instrumented one.
  - **It caught a phantom gate one could not see.** `roughing_ladder` emitted a
    phase-1 ceiling pass for ARTIFICIAL sectioning, which has none - 
    `poly_lathe_mill.ngc:587` says so in words. Four invented levels on
    testing_15_9 x 3 directions, on a grid the windows do not share. Gate one
    passed all thirty: nothing is cut on an invented level. Fixed;
    `pred` 819 -> 807 with `cut` unchanged at 744.
  - **`band=0` over the whole sweep** - the out-of-band rejection never fires on
    these five projects, so that path is carried but untested. Needs a project
    with split windows.
  - **NEXT, and it is now the only thing between here and the migration**: which
    levels get SKIPPED is still read out of the record, not predicted. And
    `skip_thin` CANNOT move to Python ahead of the stop scan - `_pl_prev_thin`
    advances only where a level actually cuts
    (`poly_lathe_mill.ngc:1089`, `:1178`), so the thin decision reads cut
    history, which reads the blocked decision. That fixes the order the
    migration has to go in.
  - Still open: `roughing_ladder` takes its inputs read back out of the
    generated program. Wiring it for real means taking them from the Feature,
    and the two paths must agree.

- [x] ~~**THE LADDER IS IN PYTHON AND PROVED, stage one of two** — 2026-09-03,
  `analysis/080`. `roughing_ladder()` computes the level radii at generation
  time and **nothing in the toolpath reads it yet**; motion is untouched.
  Proved by parallel run: 5 projects x 2 sectioning states x 3 directions, and
  every level the program cuts lies on the predicted ladder within 0.002 mm.
  `test_ladder_python` is that sweep.
  - **The first run failed 15 of 30**, each with one level off and always
    r20.516 - the first level of the SECOND floor stage. The replica stopped at
    the first stage where the O-code re-anchors on each in turn. Reading had
    not shown me that; running the two side by side did.
  - **NEXT GATE, before the `.ngc` reads anything**: the ladder is a SUPERSET,
    so predicted-minus-cut must be shown to equal skipped-plus-blocked-plus-
    out-of-band, per configuration. Until then it is a verified prediction, not
    a replacement.
  - Also open: `roughing_ladder` currently takes its inputs read back out of
    the generated program. Wiring it for real means taking them from the
    Feature, and the two paths must agree.~~

- [ ] **The ramp and stop machinery is still runtime O-code.** `s_reach`, the
  slope term, the flat-boundary clamp, the clamped-candidate rule, and the
  level scan's own perpendicular offset. Python already answers most of these
  questions better, and the roughing defect at the top of this file is the
  first place it has actually cost something. `analysis/023`.

## Pre-finish pass — where it sits, measured 2026-08-11

greatEndian: with the pre-finish offset at 0.0 the pass *"still has some offset
and does not sit on the XZ offsetted contour"*, and *"use same compensation
method as is setuped in polyline — it has to behave in the taste of polyline
other profiling operation"*.

**Measured first, on testing_15_5 with `param_pf_off=0.0`** — worst distance
from the pre-finish moves to the offset contour (the `#4400` stop table), leads
excluded:

```
comp Off      0.0008 mm  at Z-0.862
comp Native   0.0047 mm
comp In CAM   0.0197 mm  (arc chording at Z-29.184)
```

and on the cylinder at Z−50 the gap is **0.0000**. Changing the pre-finish
offset from 0.254 to 0.0 does not move the path at all — it never carried that
allowance; the allowance only ever set **where roughing stops above it**. The
blue overlay is drawn from `stock_pair` with `nose_r 0`, i.e. the same surface,
so the drawing agrees with the motion.

- [ ] **So the remaining reading is COMPENSATION, and it is a real one.** With
  nose comp **Off** the pre-finish path is the offset contour, but the tool tip
  follows that path and the round nose then leaves the *produced surface*
  displaced by up to the nose radius on every sloped or curved section. The
  path is on the contour; the **cut** is not. That is exactly *"still has some
  offset"*, and it is why greatEndian asks for the polyline's own comp method
  to apply here as it does to the finish pass.
- This is the standing **compensation is all-or-nothing** rule reaching the
  pre-finish pass: `o<prefin>` has three branches — In CAM traces the
  `cam_load` path, Native traces `_pl_pf_n`, and the third traces the contour
  **uncompensated**. `build_prefinish_contour_gcode` itself returns `''` unless
  `param_n_comp == 1`, so the Off path has no compensated contour to trace even
  if it wanted one.
- **CONFIRMED by greatEndian: it is the tool tip nose radius**, and the
  pre-finish pass must be compensated with the polyline's own comp method.
- **THE MEASUREMENT ABOVE CANNOT SEE IT — it is the wrong reference.**
  `build_stop_contour_gcode` is built **with `nose_r`**, so the `#4400` table is
  already the tool-CENTRE reference, not the surface. A compensated path lying
  on it is what correct looks like, so 0.0008 / 0.0047 / 0.0197 answer "is the
  tip where the table says" and not "does the CUT land on the offset contour".
  Recorded so the numbers are not read as evidence of correctness.
- **All four `o<prefin>` branches already pass `#<nose_comp>`** to
  `lathe_poly_pass` (In CAM hardcodes `[2]`, which is right for that path), and
  the sim tools carry real noses (`D2.54` → r1.27, `D0.8` → r0.4). So the comp
  method is wired; what is unproven is whether the resulting **surface** lands
  on the offset contour.
- **RUN 2026-08-11, second attempt — Native PROVEN CORRECT; Off not measurable
  by this instrument.** Free side fixed by running the matrix rather than
  reasoning it out:

  ```
  freeside right   gouge  0.011187      <- correct side
  freeside left    gouge 15.676474      <- absurd, so the check discriminates
  ```

  With the correct free side, the pre-finish pass under **comp Native**:
  **6828 tangent points, uncovered segs [], worst tangent err 0.000998, max
  gouge 0.011187.** That is 1/36 of the r0.4 nose and chording-scale on a
  chorded target — a missing comp would show something approaching R, or the
  15.68 above. **So the nose IS compensated on the Native pre-finish pass.**
- **In CAM is compensated correctly too**, asked for separately and proven the
  same way:

  ```
  In CAM, freeside right   85 tangent points, gouge  0.011187, uncovered [2]
  In CAM, freeside left                       gouge 15.676474
  ```

  The same **0.011187** as Native, tangent err 0.000977, 37 of 38 segments
  covered. Fewer tangent points than Native's 6828 because In CAM carries the
  offset in the PATH rather than in `G41.1`, so there are no compensated arcs to
  sample densely — the coverage, not the point count, is what matters, and it is
  there. Segment [2] is a 0.12 mm sliver at the very front, in the lead-in
  region.
  - **So both compensated modes are proven: Native and In CAM both put the
    pre-finish surface on the offset contour to 0.0112 mm**, which is chording,
    not nose. Only comp **Off** leaves the nose uncompensated, and it does so
    because the whole operation is uncompensated there.
- **The comp-OFF run cannot be read at all**, and this is the trap to remember:
  `prove_tip_comp` measures **compensated** moves, and with comp Off there are
  no `G41.1/G42.1` moves for it to find. Its "20 tangent points, 37 of 38
  segments never cut, gouge 0.101" is the instrument finding nothing, NOT the
  pass tracing a wrong curve. A change to `build_prefinish_contour_gcode` built
  on that reading was reverted unverified.
  - What IS known about the Off path, from the distance measurement: it already
    sits 0.0008 mm from the offset contour. So the path is right and the nose is
    simply not compensated — which is the same thing the FINISH pass does when
    the polyline's comp is Off. Whether that counts as the bug depends on
    whether greatEndian's project had comp Off or Native, and that is the one
    fact still missing.
- **ASK BEFORE THE NEXT ATTEMPT**: which Tool nose comp setting is on the
  polyline where the nose offset is visible? Native is proven correct above, so
  if it is Native the fault is elsewhere; if it is Off, the question becomes
  whether an uncompensated pre-finish is acceptable given the finish pass is
  uncompensated too.
- **RUN 2026-08-11, first attempt — inconclusive, and recorded as such.** `prove_tip_comp.py
  --op raw` against the pre-finish-only program (comp Native, `pf_off=0`,
  `f_pass=0`), with the `_pl_pf_*` table (nose_r 0, i.e. the offset contour) as
  the target:

  ```
  6828 tangent points, uncovered segs []   full coverage
  worst tangent err 0.000998               within tol
  max gouge 0.011187                       VERDICT: FAIL - gouge > tol
  ```

  **Identical for `--side 41` and `--side 42`**, so the run does not
  discriminate and cannot be read as evidence either way — a single profile
  line is tangent from both sides, which is exactly the trap the skill notes
  warn about. 0.0112 mm is also chording-scale on a chorded profile, so it may
  be the target's own faceting rather than the comp.
  - To make it discriminate: get `--freeside` right for this geometry (I passed
    `right` for the whole profile), and drop the tail I fed it —
    `-35.4180,32.8356 -69.8918,24.8767 -69.8920,35.0000` walks backwards down
    the end wall and is not a monotone target.
- **NEXT STEP, and it is the project's own instrument, not a new one**:
  `prove_tip_comp.py` places the nose circle at each compensated control point
  and asserts tangency to a target profile with no gouge. Point it at the
  **pre-finish** pass with the offset contour as the target, in each comp mode.
  Correct side must PASS and `--freeside` must FAIL. That answers it directly
  where a distance-to-table comparison cannot.

## The pre-finish allowance is RADIAL ONLY — greatEndian, 2026-08-12

*"why I have prefinishing offset non 0.0 roughing passes are touching the
prefinishing contour in the Z direction (at the boss segment) and offset is only
applied at X direction? prefinish offset has to be constant in the each axis so
the tool will have some material to cut and not to create chattering"*.

**Right, and confirmed by construction**, not by argument:

| table | governs | allowance it carries |
|---|---|---|
| floor contour, `build_floor_contour_gcode` | the level RADII (X) | `fin + prefin` |
| stop contour, `build_stop_contour_gcode` | where a level ENDS (Z) | **`stock_pair` = `fin` alone** |

So against a boss face, a wall or a shoulder a roughing level is allowed to stop
**on** the pre-finish surface, and the pre-finish pass arrives there with nothing
to cut. That is a rubbing pass, and a rubbing pass chatters — a machining
requirement, not a preference.

- [x] **DONE `3df0a4c`** — the stop contour carries `fin + prefin`, verified: `stop_x, stop_z = fin_off + pf_off, fin_off_z + pf_off` in `lathe_sections`. Levels stop 0.2540 short of the wall, exactly `pf_off`. ~~FIX: the stop contour must carry `fin + prefin` too.** It must NOT go
  back to stopping on the roughing FLOOR, which is what that table was built to
  stop doing — the floor is rounded up to the level grid, so that left a gap of
  up to a whole depth of cut. `fin + prefin` is the allowance actually asked
  for, and sits between the two.
- **Tried 2026-08-12, and it works on the isotropic case**: levels then stop
  **0.2540** short of the wall, exactly `pf_off`, in all three comp modes.
  `test_rough_comp`'s *"every roughing level reaches the pre-finish wall"* has
  to become *"stops the pre-finish allowance short"* — with the bound still
  rejecting a whole depth of cut, which is the 0.5080 fault it was written for.
- **REVERTED, because it regresses the ANISOTROPIC case and I did not find
  why**: `test_stock_to_leave` with the axial value at 2.000 went from stopping
  **2.0000** off the Z−70.4 wall to **0.7300** — and 0.762 is `fin + prefin`
  isotropic, so the axial value stops reaching the stop somewhere. Not a table
  overflow: `_pl_stop_n = 20`, no WARNING emitted. The isotropic expectation in
  that test also needs updating (0.508 → 0.762) once the anisotropic path works.
- **Investigated 2026-08-12, and the obvious cause is REFUTED by its own
  arithmetic.** The suspect was `s_reach`, the clamp on how far the stop table
  may extend a cut past the scan's own end — `#<s_reach> = [3.0 *
  #<_rough_cut>]` in `lathe_level_pass`, which is scaled to the depth of cut and
  knows nothing about the allowance. On testing_15_2:

  ```
  _rough_cut = 0.508                    s_reach = 3 x 0.508 = 1.524
  scan z_end, scalar lvl_d = 0.762      0.762 from the Z-70.4 wall
  stop candidate BEFORE, fin_z = 2.000  |delta| = 1.238  < 1.524   accepted
  stop candidate AFTER,  + pf  = 2.254  |delta| = 1.492  < 1.524   should pass too
  ```

  1.492 clears the bound by 0.032, and the slope term `1.5 * rough_cut *
  dz/dx` only ever RAISES `s_reach`. So the clamp should not fire, and the
  0.7300 measured has another cause. Recorded rather than acted on, because
  four hypotheses about this area have now been wrong and this one is refuted
  on paper before costing a round.
- **The instrument to run first**, before any further edit: emit the candidate
  `#<s_zc>`, the scan's `#<z_end>`, `#<s_reach>` and the resulting `#<s_cl>` as
  comments from `lathe_level_pass` for the level nearest the Z−70.4 wall, then
  generate testing_15_2 with `f_off_sep=1, f_off_z=2.0` and read them. Four
  numbers say immediately whether the clamp fired, whether the candidate was
  where Python put it, and whether `z_end` is where this arithmetic assumes.
  Everything above is inference from the source; none of it is measured.

## The preview overlays are undocumented — greatEndian, 2026-08-12

*"I can not see yellow dashed line description in the help section"*, and he is
right: `grep` for `rough entry` across the whole tree returns **one** file,
`ncam_preview_ui.py`, which is the legend swatch itself. No help text, no
tooltip, no `md_files/` entry for any of the four overlays.

- [x] **DONE `65b6672`** — Help > Preview Lines, a drawn dialog beside the tool-orientation entry, using the real colours and dashes from `ncam_preview` so it cannot drift from the plot. ~~Document the four overlays~~, in the help section and not only as a
  colour swatch. What each one IS, and — the part that actually confuses —
  whether it is a *surface*, a *toolpath*, or a *construction reference*:

  | legend | colour | what it really is |
  |---|---|---|
  | rough entry path | yellow-green dashed | `#<_pl_entry_*>` — where a roughing level may BEGIN cutting. A construction contour at `fin + prefin + one depth of cut`, walked by `lathe_level_pass:407` and the source of the ramp-direction table. **Not a path the tool follows.** |
  | rough stop path | orange dashed | `#<_pl_stop_*>` — where a level must STOP. Also a construction contour, and built WITH the nose, so it is a tool-CENTRE reference |
  | pre-finish surface | solid | the offset contour, `stock_pair`, nose 0 — a real surface |
  | comp path | teal dashed | the compensated finish toolpath |

- [x] **DONE `efcea35`** — renamed to *rough entry limit* / *rough stop limit*, and construction references now draw DASH-DOT against the toolpath's plain dash. Guarded by `test_rough_overlay`. ~~The dashed/solid convention mislabels two of them.** The code's own
  comment says *"SURFACES are solid, TOOL PATHS are dashed"*, but `rgh_entry`
  and `rgh_stop` are neither — they are reference contours, and calling them
  "path" in the legend invites exactly the reading that they are where the tool
  goes. Renaming them "rough entry limit" / "rough stop limit", or giving
  references their own dash pattern, would say what they are.
- [x] **DONE `65b6672`** — stated in that dialog: the entry limit sits at Offset + Pre-finish + one depth of cut and so never meets the offset contour, because a depth of cut is not an allowance. ~~The entry line's constant gap needs stating~~:
  it is `fin + prefin + ONE DEPTH OF CUT`, so it never collapses onto the offset
  contour even at a pre-finish offset of 0.0 — measured 0.5213 on testing_15_5
  at Z−50 against a 0.508 depth of cut. That is a cut depth, not an allowance,
  and greatEndian read it as a leftover offset precisely because nothing says so.

## Behind-boss ladder truncated on testing_15_6 — FIXED 2026-08-12

greatEndian: the first and last roughing passes behind the boss are missing on
`testing_15_6.xml`, while `testing_15_5.xml` is right. `analysis/034`.

- [x] **Only the LAST passes were missing; the first was never absent.** 15_6's
  floor contour peaks at X34.1641, so level 34.2240 clears the boss and runs full
  length while 33.7160 splits — correct. The truncated tail made the whole ladder
  look wrong.
- [x] **The two projects are geometrically IDENTICAL** — raw and reachable
  profiles match point for point. They differ only in the **pre-finish offset**,
  0.254 mm against 1.000 mm, which is all it took to expose the fault.
- [x] **Root cause**: `resume_envelope`'s crossing test is strict at a segment's
  lower end (`px >= lev > cx`), so a descending segment never yields a breakpoint
  at its OWN bottom. Behind a boss the back-angle shadow makes the last descent
  ONE long taper with nothing after it, so the envelope stopped partway down —
  lowest breakpoint 27.2313 against a taper ending at 26.2368. The two levels
  between fell outside the table, took the walker's out-of-range fallback, and
  were judged inside the part. **15_5 escaped only by luck**, its lowest
  breakpoint sitting near its own taper end.
- [x] **Fixed** by extending the envelope to the bottom of the last descent that
  lies behind the current last breakpoint, under the same monotone lead-in clamp.
  Python only — no `.ngc`, `.cfg` or parameter change.

  ```
  testing_15_6   r27.1120 len 3.3911 and r26.6040 len 1.1908 restored
                 44 -> 46 level cuts
  testing_15_5   unchanged, 49 level cuts, topmost 33.2080 / 33.1273
  ```

- [x] `test_behind_boss_ladder.py` asserts the general invariant — **a ladder ends
  by running out of material**, so its last pass must be shorter than one step —
  with a negative control that fires on the bug, and on which 15_5 still passes.

## The leftover check — measure the metal, not the recipe (2026-08-12)

- [x] **THE CONTROL COULD NOT FAIL ON MOST GEOMETRY — FIXED 2026-08-15**,
  `analysis/053`. Reported as "does not fire on testing_15_6"; surveying all 21
  runnable demo projects showed the old control — delete one radius at
  `len(radii)//3` — fired on **7 of 21**.
  - **Deleting one pass is not a valid mutilation.** A shallow pass is usually
    redundant: the final surface is the DEEPEST pass covering each Z, so on
    testing_10 removing each of the seven outermost radii in turn left the worst
    standing figure identical to four decimals, 0.2505 mm at Z−14.47 every time.
    Where it is not redundant it is narrow: on 15_6, removing r29.6520 leaves
    0.9580 mm standing across **0.350 mm of Z**, which `MIN_RUN` (0.600)
    discards.
  - **That falsified the file's own justification for `MIN_RUN`** — "a missing
    pass is wide, at least 2.2 mm". It is not; the band runs 3.75 mm at the top
    of 15_6's ladder to 0.05 mm at the bottom. The comment now says so and the
    bound stays, because the nose-fillet case it excludes is real.
  - **Now it leaves a 6 mm Z window UNROUGHED**, trimmed out of the moves rather
    than deleting passes — the failure actually worth catching, and the shape
    the behind-the-boss bug had. Placed on the longest stretch where roughing
    both machines cleanly AND demonstrably cut; each half was needed (a mid-span
    window missed on current_work, 15_2, 15_3, 15_4; without the "did cut" half,
    15_3 slipped through). **21 of 21**, and it runs on every project that can
    carry it with the other 16 named and reasoned.
  - Two rejected rules recorded with numbers: two deepest radii **20/21** (fails
    on the bored testing_14_inside, where the final surface is the LARGEST
    radius), two radii nearest the target **16/21**.

- [ ] **The gate cannot see a SINGLE missing pass on most geometry, and that
  stands.** Not a threshold to tune: in the redundant case the metal is not
  there to find, and in the narrow case it is indistinguishable by width from a
  nose fillet. `test_x_continuity` is what catches a missing pass — it, and not
  `test_leftover`, is what caught the one behind the boss on testing_15_6. The
  two gates are complementary; treating either as sufficient is what invited
  this.

- [ ] **`leftovers()` models the stock from the moves it is given**, so a
  mutilation removing the outermost pass also lowers the modelled stock. Latent
  wart in a measurement helper, not the cause of the above — fixing it changed
  nothing, 7 of 21 either way, so it was left alone rather than fixed on
  speculation. `analysis/053`.


`test_leftover.py`, greatEndian's idea. Sweeps the real nose along the roughing
moves with `StockField` and asks whether any metal stands **more than one depth
of cut** above the surface roughing is meant to leave. It exists because four
turns were spent pronouncing the ladder correct from its own tables —
breakpoints, crossings, start Zs — while material was visible in AXIS. **This is
now the acceptance gate for any roughing change.**

- Excludes, each for a recorded reason: the back-angle shadow (by taking the
  target from the finish pass's own path, which BRIDGES it — the naive version
  reported 5.0452 mm on the known-good baseline), near-vertical segments, stock
  above the first pass, and spikes narrower than the nose.
- **Negative control fires**: deleting one radius of roughing from the parsed
  program is detected on both projects (0.6683 mm / 0.6630 mm).

- [x] **THE ANSWER — testing_15_6 has NO leftover metal.** Zero wide regions on
  both projects in both sectioning states. Roughing removes everything down to
  its target, so **there is no missing pass behind the boss**.
- **What is visible instead is the pre-finish band.** The projects are
  geometrically identical and differ in one parameter — Pre-finish offset
  **0.254 mm on 15_5 against 1.000 mm on 15_6** — so roughing stops
  `0.508 + 0.254 = 0.762` from the part on one and `0.508 + 1.000 = 1.508` on the
  other. **Nearly double the uncut band**, correct and asked for, but against the
  drawn contours it reads exactly like a missing pass.
- [ ] **NEEDS greatEndian's eye**: is the gap you see about 1.5 mm wide, and does
  it shrink to about 0.76 mm if you set Pre-finish offset to 0.01in? If yes this
  is closed and the setting is the answer. If the gap looks wrong even then, the
  suspect is the DRAWING — the rough entry path (yellow-green dashed) sits at
  `Offset + Pre-finish + one depth of cut`, which is **2.016 mm out on 15_6**
  against 1.270 on 15_5, and that overlay has misled twice already this session.
- The tool now prints the worst standing figure whether or not it qualifies.
  Both projects DO have over-threshold points — 0.7219 mm at Z−19.38 on 15_5 —
  but every one is narrower than the nose: the r0.4 nose cannot reach into the
  shoulder at Z−19.51, which rises 0.93 mm in 0.04 mm of Z. That is a fillet the
  pre-finish takes, not a missing pass. Reporting pass/fail alone had hidden it.

## The first pass after the boss — FIXED, 2026-08-12

greatEndian reported it three times on `testing_15_6.xml`, latterly with
`photo/firstPassMissingBehindBoss.png`. Two agents and the coordinator each
concluded from the tables that nothing was missing. All three were wrong.

- [x] **FIXED**, `analysis/036`. `lathe_level_pass`'s stop table accepted a
  **falling** crossing as a place to extend a cut to. A falling crossing is
  where the level LEAVES blocked territory, so extending to it sweeps straight
  through the blockage. Measured: level 34.063647 was correctly stopped by the
  scan at Z−31.209182 on the dome's rising flank, then extended **3.3816 mm**
  to Z−34.590818, cutting through the dome and losing its whole behind-dome
  interval — the step across the dome was **0.9363 = 2 × the 0.4682 ladder
  step**, and the next level down took double depth.
  - `s_reach` could not stop it: it is `3 × doc` = 1.524 mm, but its slope term
    reaches ~4.5 mm on the dome's shallow flank. **The right bound is direction,
    not distance** — the crossing must now ENTER blocked territory, the same
    convention `o<mcf_w>` already uses for `dirup`. One line in
    `lib/lathe/lathe_level_pass.ngc`; no Python, cfg or parameter change.
  - **Why every test passed**: the level cut *through* the dome, gouging at most
    0.1005 mm into a floor allowance standing 1.508 mm above the part. The part
    was never touched, so `test_rough_comp` saw no overcut and `test_leftover`
    saw no metal standing — the next level down removed it.
  - After: levels behind the dome are 34.5318, **34.0636**, 33.5965 with regular
    0.4682/0.4671 steps. `testing_15_5` unchanged at 33.2080 / 33.1273.

- [x] **`test_x_continuity.py`** — greatEndian's own check: compare each level's
  X with the next and flag any step that is not one depth of cut. Shipped with
  two corrections the measurements forced:
  - **one-sided**, because `Space passes from = Final contour` anchors the
    ladder and makes the top step of a region a legitimate remainder (0.4682,
    0.4671 against a 0.5080 doc). Only a step that EXCEEDS the doc is a fault.
  - **positional**. Matching each pass with the next one down whose Z span
    overlaps it could not see this bug — the full-length pass overlaps 34.0636
    *in front of* the dome, so the gap *behind* it was never examined, and it
    reported 0.0000 on a program with a missing pass. It now walks Z and
    compares the levels cutting at each station.
  - Validated both ways: FAILs with the fix reverted (`X34.5318 -> X33.5955 gap
    0.9363 at Z-37.5000`), passes with it applied, negative control fires.

- [ ] **Noted, not fixed**: the front interval of the first blocked level is
  emitted **twice** — identical moves, `34.0636 0.0000 -> -31.2092` here.
  Pre-existing, follows whichever level is first blocked, costs an air-cutting
  repeat rather than any wrong metal.

- **The lesson.** Three checks in a row looked at the passes that EXIST and
  found them regular. A missing pass is only visible if you ask which levels are
  ABSENT — dumping the whole ladder sorted by X, front and behind intervals side
  by side, showed it in one line. Prefer a measurement that enumerates what
  should be there over one that inspects what is.

## Gap 1, front tool clearance — WARNING WIRED, toolpath still open, 2026-08-13

greatEndian settled the question that blocked it: *"yes the limitation is
real"*, *"angle convention is right .. same path generation I see in the CAM
software"*. So the detection describes the part, and the reference package
leaves the same regions.

**Done** (`analysis/041`): the maths moved into `lathe_sections` beside the
back-angle machinery it mirrors, `spans_between` is now shared by both flanks,
and the existing reachable-contour warning reports FRONT and BACK
distinguishably. `polyline.cfg` 1.56. Motion byte-identical — hashed before and
after on testing_15_2/15_5/15_6 — and `test_front_flank` asserts structurally
that the front functions are reachable from `[VALIDATION]` and nowhere else.

Also killed a false alarm on the way: a tool table with **no** angle column
answers 0.0, and 0 degrees is not a tool. With the default 2° back clearance
that made the ramp `tan(88°)` and invented 1.32 mm and 1.10 mm of unreachable
radius on testing_3 and testing_4. `finish_profile` already refuses the trailing
flank the same way; the two now agree.

- [x] **The TOOLPATH half is DONE, opt-in**, `analysis/042`. `Respect tool
  front angle`, `polyline.cfg` 1.57, default OFF. `finish_profile` was the one
  place; `flank_envelope` gained a second flank with its own reach, because
  merging two finished envelopes manufactures corners tighter than the nose and
  the interpreter refuses them outright. Default byte-identical; switched on,
  testing_15_2 goes 361 to 340 moves and testing_15_5 484 to 463, with the
  contour standing further off the drawn shape inside the front-unreachable
  region - 4.787 to 7.228 mm on 15_5. **Never run on a real part**: whether the
  result is the part greatEndian wants is a question for a machine.

- [x] **DONE `8b2da4e`** — greatEndian ruled on 2026-08-13 that the limitation
  is real and the convention right, so the toolpath half was built: *Respect
  tool front angle*, **off by default**, the same wedge dilation mirrored
  rather than a second copy of that geometry. The caution below stands and is
  why it is opt-in. ~~The TOOLPATH half is still open, and is a decision, not
  a task.~~ The warning now says which regions the leading flank cannot make; keeping the path
  out of them means changing `finish_profile`, the choke point every contour,
  section window, ladder and table derives from. For scale, the back clearance
  moves 198 of 323 moves on testing_15_2, and getting the back-angle version of
  this right cost five stacked faults (`analysis/032`). Worth doing only once
  the warning has been read on real parts and says it is worth it.

## Roughing bugs found in AXIS — greatEndian, 2026-08-11

All on `configs/sim/axis/ncam_demo/ncam/catalogs/lathe/projects/testing_15_5.xml`
unless said otherwise. Reported together; none investigated yet.

**What "Offset" and "Pre-finish offset" are FOR** — greatEndian's own statement,
recorded because it decides what correct means for the four below: *"Offset is
prefinish prepare for final finish pass. Prefinish is offset from finish +
offset to be able to do custom measure to operator to make compensation to
finish cutting next."* So the pre-finish surface is a **measurable** surface: the
operator measures it, dials in a compensation, and only then runs the finish
pass. A roughing or pre-finish pass that lands somewhere other than where the
offsets say destroys that measurement, which is why these are not cosmetic.

- [x] **CLOSED 2026-08-12 — it was the TEST, not the code.** `analysis/033`.
  The removed **volume** is **205550.4 mm3 at every section length**, identical
  to a tenth of a cubic millimetre, while a control at `f_off 3.0` moves it — so
  the measure is live and the equality is a result. The sliced program takes off
  exactly the same metal with **less** cutting travel (−7.0% at sec_len 10,
  −5.7% at 20), because a piece stops at its own boundary instead of sweeping
  ground a neighbouring piece already cleared. That is what slicing is for.
  `test_section_length` had asserted travel, which is a strategy property, and
  so encoded a legitimate improvement as a fault. It now asserts volume to 0.5%,
  travel only loosely, the pass count still rising, and carries a CONTROL run so
  it cannot go vacuous. **No production code changed.**
  - The earlier 23.1%/20.1% *was* real and was fixed by `5790e01` — the floor
    contour built from the raw polyline instead of the reachable profile.
  - Also corrected: the throwaway volume probe sized its stock field from each
    run's own moves, measuring two different programs in two different boxes.
    The field is pinned in the test now.
  - Original report below, kept for the record.

- [x] ~~**Sectioning ON with a non-zero Z section length roughs FOUR TIMES the
  passes.**~~ Measured on testing_15_5, changing only `param_sec_len`:

  ```
  sec_len  0.0    49 level cuts   1052.6 mm cut   14 behind the boss
  sec_len 10.0   202 level cuts   1296.2 mm cut   82 behind the boss
  ```

  **4.1x the passes for 1.23x the metal**, which is the *"roughs all part long"*
  greatEndian reports. Extra passes that remove almost nothing means the
  artificial sections are overlapping and re-cutting ground already covered —
  and that is very likely the same fault as the crossed, randomly-offset passes
  in the item below, seen from the other side.
  - **The back-angle half is NOT confirmed.** *Respect tool back angle* is `1`
    in that project, so it is asked for. A first probe read `flank_n=0` and
    `sect_n=0`, but those used the wrong global names — the sections table emits
    `_pl_sect_count`/`_pl_sect_mode` — so both zeros are meaningless and prove
    nothing either way. Re-probe with the real names before concluding anything
    about the back angle.
  - **DUMPED 2026-08-12 — there is NO overlap. The windows carry no RADIUS
    bound.** `_pl_sect_mode` differs between the two:

    ```
    sec_len 10.0  mode=1, 10 windows, contiguous in Z, no overlap:
        Z  0.0000 ->  -1.0000    r 0.0000 .. 1000000.0000
        Z -1.0000 -> -10.5000    r 0.0000 .. 1000000.0000    <- FULL radius range
        ... every window the same

    sec_len 0.0   mode=0, 8 windows, banded BY RADIUS:
        Z  0.0000 -> -70.4000    r 65.3182 .. 1000000.0000
        Z  0.0000 -> -32.5000    r 40.0000 ..   65.3182
        Z -32.5000 -> -70.4000   r 40.0000 ..   65.3182
    ```

    In mode 0 a window is a Z span **within a radius band**, so two windows may
    share a Z span legitimately — a naive overlap check flags those as false
    positives, and mine did. In **mode 1 every window spans `0 .. 1e6`**, so each
    Z slice is roughed from the stock OD downward whatever is actually there,
    while mode 0's banding confines each window to its own band. That is the
    *"roughs all part long, also behind the boss"*, and it explains 202 cuts
    against 49 **with 23% more metal removed** — it is not cutting air, it is
    cutting where the banding would have stopped it.
  - **THAT FIX WOULD BE WRONG — the full radius range is DELIBERATE.**
    `build_sections_gcode` says so at the line itself: *"Artificial bounds how
    long any single cut may be, at every depth, so its pieces deliberately apply
    over the whole radius range - see this function's own docstring for why it
    must not be merged"*, and the docstring gives the reason: a Z section length
    caps **how long a single continuous cut can ever be, for chatter and
    rigidity**, which only means anything if it applies at every depth. Adding
    banding would merge the two modes against an explicit warning not to.
  - **SO THE REAL FAULT IS THE 23%, NOT THE PASS COUNT.** More passes is what
    slicing is FOR: 202 short passes instead of 49 long ones is the feature
    working. **Removing 1296.2 mm of cut where 1052.6 does the same job is
    not** — the same part with the same allowances must yield the same metal
    however the cut is sliced. That is the number to drive to parity, and the
    pass count should be left alone.
  - **VOLUME MEASURED with `StockField`, 2026-08-12 — the part comes out
    DIFFERENT, and greatEndian's back-angle report is confirmed:**

    ```
    sec_len  0.0   removed 148367.8 mm3             cut length 1052.6
    sec_len 10.0   removed 170017.1 mm3   +14.59%   cut length 1296.2
    sec_len 20.0   removed 166663.9 mm3   +12.33%   cut length 1263.9
    ```

    So it is **not** empty travel. A section length removes **14.6% more metal**
    — an over-cut, not a strategy difference, and the part is not the same part.
    The +23% in cut length overstated it because some of that travel is empty;
    **14.6% is the real number** and it is the one to drive to zero.
  - **LOCALISED, 2026-08-12.** Per-column comparison of the two stock fields:

    ```
    279 of 780 columns differ, ALL behind the boss (Z-45 .. -70)
    Z-52.150   sec_len 0 leaves r28.1439   sec_len 10 leaves r21.0018
                                           7.1421 mm deeper
    ```

    So a slice behind the boss is roughed down to roughly the depth the FRONT of
    the part reaches — into the taper, not into stock.
  - **The data for the fix is computed and thrown away.** In
    `build_sections_gcode`, `split_by_length` returns each piece's own minimum
    radius and the next line discards it:
    `ordered = [(z_from, z_to) for z_from, z_to, _min_x in pieces]`, after which
    `windows = [(z_from, z_to, 0.0, BAND_ALL) ...]` gives every slice `r_lo = 0`.
  - **BUT PASSING IT THROUGH CHANGES NOTHING** — tried, and the volume figures
    came back identical to the digit, so the O-code's mode-1 path does not bound
    its depth by the window's `r_lo`. Reverted rather than left as a comment
    claiming a fix it does not make.
  - **THE WINDOW FLOOR IS NOT THE FIX — that theory is dead.** The profile was
    dumped between Z−45 and −70.4 and it genuinely reaches **d40.000** there:

    ```
    -45.000,40.000      -70.400,40.000
    ```

    So `split_by_length`'s `min_x` of 40.0 was **correct**, and so was the
    per-piece computation that reproduced it. An earlier deduction that the
    minimum "should be about d48.2" came from the floor contour's simplified
    long chord, which hides the intermediate geometry — a reminder that the
    contour tables are simplified and must not be used to infer the profile.
  - **Nor is it `poly_lathe_mill:534`.** Line **623** already bounds
    `current_radius` by `w_rlo`/`w_rhi`, so the O-code enforces the band it is
    given. Nothing in `lib/` needs to change for a bound.
  - **THE REAL FAULT: mode 1 cuts BELOW THE FLOOR CONTOUR.** At Z−52 the floor
    sits near r29.6, so a level at r21.0018 is inside the part — mode 0 stops
    at r28.1439, mode 1 cuts straight through the taper. The band permits it in
    both modes (d40 = r20 is a legitimate floor *somewhere* in that section);
    what should stop it is the floor contour scan, per Z, and in mode 1 it does
    not. Look at what the level pass does in a window whose whole Z span lies
    behind an obstruction and finds no crossing — whether "no crossing" is being
    read as "free to cut the whole window".
  - **CONFIRMED BY READING, not yet by measurement**: when `found` is 0, `zc`
    keeps the value `mc_zc` was initialised to — `[#<w_to> - #<z_dir>]`, just
    past the window end — so `o<zend>` clamps `z_end` to `w_to` and the level
    cuts the **whole window**. That is the "no crossing means free to cut" path.
  - **The probe was placed too late to see it.** A `(debug, ...)` after
    `o<blk> endif` returns only unblocked levels, because a blocked one takes
    `o<lathe_level_pass> return` at `o<mc_decide>` (line ~371) well before that
    point. What it did show is that the levels near r21 in window 0 (Z 0 to −1)
    are legitimate: `found=1`, crossing at Z−19.87, clamped correctly to the
    window end — that region is the front cylinder and the cut is right.
  - **FOUND, 2026-08-12.** Probe above `o<mc_decide>`, sec_len 10:

    ```
    lvl=21.016  wf=-45.000000  wt=-53.466667  wfstate=1     blocked, correct
    lvl=21.016  wf=-53.466667  wt=-61.933333  wfstate=0     NOT blocked
    lvl=21.016  wf=-61.933333  wt=-70.400000  wfstate=0     NOT blocked
    ```

    Windows 8 and 9 lie behind the boss where the profile tapers r28 → r25, so
    a level at r21.016 is well inside the part and `mc_wf_state` must be 1 — as
    it correctly is for the same level in window 7. Being 0, the level passes
    the block test and cuts the whole window, which is the r21 over-cut the
    stock field measured.
  - **The cause is in the `o<mc_flc>` state walk.** `mc_state` starts from the
    contour's FIRST point (`o<mcf_st> if [#<fc_px> GE #<l_eff>]`) and is then
    updated only by crossings at-or-before `w_from`. For a level that lies below
    the whole contour in this region there are no crossings behind the boss at
    all, so the answer rests entirely on the initial value and on crossings near
    the FRONT of the part — which is how a level deep inside the taper comes out
    "not blocked" in a window 50 mm away from them.
  - **Fix**: the block test must be a question about the floor **at `w_from`**,
    not a state accumulated from the front of the contour. Evaluating the floor
    contour's radius at `w_from` directly and comparing it with `l_eff` answers
    it in one step, with no walk and no initial-value dependence — and it is a
    Python-computable table lookup, not a scan.
  - **THE FIX WAS APPLIED AND THE VOLUME DID NOT MOVE — and the probe is now
    the suspect, not the fix.** The point-wise block test was written into
    `o<mc_flc>`: interpolate the floor contour's radius at `w_from`, take the
    max where a re-entrant contour crosses it twice, set `mc_wf_state` from
    that. By arithmetic it must block the offending level — the floor at
    Z−53.47 interpolates to about **r28.6** against `l_eff` 21.016 — and
    `_pl_multi_cross` is 1, so the branch is entered.
  - **Volume came back identical to the digit, as it did for the two previous
    changes.** Three distinct behavioural edits producing byte-identical volume
    is far more likely one broken measurement than three genuine no-ops.
  - **PROBE VALIDATED 2026-08-12 — it responds, so the "no effect" results were
    REAL.** Control on testing_15_5, sec_len 0:

    ```
    f_off 0.508 (baseline)    volume 205537.8   moves 312
    f_off 3.000               volume 206601.6   moves 266   both move
    sectioning OFF            volume 205537.8   moves 306   volume held, moves changed
    ```

    Changing the finish offset moves volume and move count together, so the
    measurement is live. The third line is the invariant holding on its own:
    sectioning on and off at `sec_len 0` remove **identical** metal with
    different move counts, which is exactly what a strategy change should do.
  - **So the three edits genuinely did nothing, and two of them are explained.**
    Wiring `min_x` and computing the per-piece floor both yield **40.0** for the
    windows behind the boss — the same value the code already had — so neither
    could change anything. That is consistent, not mysterious.
  - **THE THIRD IS NOW EXPLAINED TOO, AND IT INVERTS THE DIAGNOSIS.** The debug
    was run with the fix in place:

    ```
    lvl=21.016000  wf=-53.466667  wfstate=0  wffl=20.762000  leff=21.017000
    lvl=20.516000  wf=-53.466667  wfstate=1  wffl=20.762000  leff=20.517000
    ```

    **The floor at Z−53.47 is r20.762**, not the r28.6 predicted. So level
    21.016 sits ABOVE the floor and is legitimately unblocked, and the next
    level down is correctly blocked. **The block test was right all along** and
    the fix changed nothing because there was nothing to change.
  - **Where the r28.6 came from — a caution worth keeping.** An earlier dump of
    the floor contour printed only points with `X > 32.0`, and consecutive
    printed points were then read as if adjacent. They were not. The profile
    genuinely reaches **d40 (r20)** behind the boss, exactly as the raw point
    dump said. Never interpolate across a FILTERED point list.
  - **SO THE FAULT IS PROBABLY ON THE OTHER SIDE.** If the part is at r20 behind
    the boss, then roughing down to r21 there is correct, and it is **mode 0
    leaving r28.14** that is wrong — material standing where it should have been
    cut. That is very likely the SAME defect as *"the missing first pass behind
    the boss segment"* already at the top of this file, which is unfixed and has
    its resume-envelope work sitting inert.
  - **Consequence for the gate**: 148367.8 mm3 may be the WRONG target. If mode 0
    under-cuts, `sec_len 10`'s 170017.1 could be nearer the truth, and
    `test_section_length` would then be asserting parity with a broken baseline.
    Settle which side is right before treating either number as correct — the
    reachable contour and the finish pass say what the part should be, not a
    comparison of two roughing strategies against each other. Before re-applying it, put the
    `(debug, ...)` back above `o<mc_decide>` **with the fix in place** and read
    `wfstate` for `lvl=21.016 wf=-53.466667`. If it is still 0 the inserted code
    is not executing; if it is 1 and the volume still does not move, the block
    test is not what admits that cut and the search moves on.
  - **ESTABLISH ANY NEW PROBE THE SAME WAY.** `vol.py` must be shown to
    respond to a change that certainly alters the program — e.g. halve the depth
    of cut, or set `param_sectioning=0` — and if the number does not move, it is
    not re-generating and every "no effect" conclusion drawn from it this
    session is void, including the two reverts above.
  - Gate, once the probe is trusted: volume back to **148367.8 mm3** and
    `test_section_length.py` green with the pass count still rising. The candidates are the back-angle shadow (`Respect tool back
    angle` is on in this project) and the stop contour — i.e. whether a mode 1
    window consults the reachable contour and the stop at all, or only its Z
    span. **The test to write first** is the invariant, not a fix: *total cut
    length is independent of `sec_len`*, which would have caught this the day
    sectioning was built and is the acceptance criterion for the fix.
  - **Not started** — scoped only. It is in `build_sections_gcode`, and the
    verification is the same pair of numbers: pass count and total cut length
    should fall back toward the `sec_len 0` figures, with the Z slicing still
    visible as more, shorter passes rather than more metal.

- [x] **FIXED — confirmed by greatEndian in AXIS, 2026-08-13.**
  ~~Sectioned roughing passes in FRONT of the boss have mixed, crossing paths~~.
  Not fixed deliberately: it was carried away by the roughing work of 12-13 Aug —
  most likely `5790e01` (the floor contour built from the reachable profile,
  which removed a floor collapsed 8 mm too deep across 24 mm of part) and
  `288b936` (the resume envelope reaching the bottom of the last descent).
  Recorded rather than tied to one commit, because it was never reproduced here
  and so cannot honestly be attributed.

- [x] **DONE `e27a858`** — the motion always honoured it; the ENTRY CONTOUR did not, and now sits at `fin + prefin + one depth of cut`. ~~Pre-finish offset = 0.0 is ignored by roughing~~, which still leaves
  something standing off the final contour — visible as the yellow dashed line.
  With the pre-finish offset zeroed, roughing's floor should sit on
  `finish offset` alone.
  - **First look, 2026-08-11 — the G-code path reads correct and the DRAWING
    does not.** `#3156 = [#param_pf_off * #param_pf_on]` arrives as
    `#<prefin_off> = #25`, and `poly_lathe_mill:665` sets
    `#<lvl_d> = fin_off + prefin_off`, so a zero pre-finish offset gives a floor
    of `fin_off` alone — right. The stop contour likewise uses `stock_pair`,
    which is the finish offset alone.
  - But the **yellow dashed line is not built from either offset**:
    `ncam_preview_ui.py:1196` draws it from
    `eoff = ncam.TOOL_TABLE.get_rough_cut()` — **one roughing depth of cut** —
    so it sits the same distance from the profile whatever the offsets are, and
    zeroing the pre-finish offset cannot move it.
  - **SETTLED BY MEASUREMENT, 2026-08-11 — the motion is right, the ENTRY
    CONTOUR is wrong.** testing_15_5, changing only `param_pf_off`:

    ```
    pf_off=0.01   50 level cuts, deepest level X=20.0000
    pf_off=0.0    49 level cuts, deepest level X=19.5080   0.492 deeper
    ```

    Roughing cuts closer when the pre-finish offset is zeroed, so the levels do
    honour it. What does not is the **entry contour** — the surface a level may
    begin cutting on. `build_entry_ramp_gcode` builds it as the profile offset
    by `entry_off` = **one roughing depth of cut alone**
    (`lathe_sections.py:2455`), and `ncam_preview_ui.py:1196` draws the yellow
    dashed twin from `TOOL_TABLE.get_rough_cut()` the same way. Neither adds the
    finish or pre-finish allowance.
  - **It should be offset from the FLOOR, not from the final profile** — the
    floor already stands `fin_off + prefin_off` off the profile, so the entry
    belongs at `fin_off + prefin_off + rough_cut`. As built it sits one depth of
    cut from the finished shape whatever the allowances are.
  - **THIS IS ALSO THE CAUSE OF THE 1.0-OFFSET BUG BELOW.** greatEndian's
    observation there — *"roughing entry is nearer to Z axis as the prefinish
    surface is"* — is exactly what an entry contour that ignores the allowance
    does once the allowance is large: at an offset of 1.0 the entry sits
    **inside** the pre-finish surface. Two reports, one cause.
  - **FIXED AND MERGED**, `e27a858` + `8c6551b`, `analysis/030`.
    The entry is now `fin + prefin + one depth of cut`, anisotropic on the two
    allowances like the floor, and the overlay takes them identically. cfg
    signature unchanged, so no version bump. Blast radius walked: the ENTRY
    table 4200-4400 → `lathe_level_pass:407`, the ramp table built from the same
    `env` (directions are surface tangents, so unaffected), and the overlay.
    Measured on testing_15_5, both tables sampled at Z−50:

    ```
    pf 0.254    entry X30.3540   stop X29.5720   entry outside stop
    pf 0.0      entry X30.0933   stop X29.5720   moved in by 0.2607
    offset 1.0  entry X30.8590   stop X30.0769   entry outside stop
    ```

    Both symptoms gone. `test_ramps`, `test_rough_overlay`, `test_ladder`,
    `test_rough_ends`, `test_all_projects`, `test_stock_to_leave` pass.
  - `test_rough_comp` was rewritten on greatEndian's call — *"the fault was
    real"*. Off overcut went **0.1115 → 0.0503**, matching Native and In CAM, so
    the old gap-based assertion would have demanded roughing be BAD when
    uncompensated. It now asserts the **absolute** overcut, bounded at 0.08,
    which sits between the two measured states rather than beside one of them.

- [x] **PROBABLY FIXED by `e27a858` — needs greatEndian's eye in AXIS.**
  ~~Roughing ignores the separate Z offset and uses the per-side offset~~.
  Measured on testing_15_5 after the entry-contour fix, distances from the
  Z−70.4 wall:

  ```
  sep OFF        cuts 0.5080 | floor 0.7620 | ENTRY 1.2700
  sep ON, Z=2.0  cuts 1.8918 | floor 2.2540 | ENTRY 2.7620
  ```

  Every surface honours the axial value and each stands outside the next in the
  right order — `fin`, then `+prefin`, then `+one depth of cut`. Before the fix
  the ENTRY was at the depth of cut alone, **0.5080 off the wall whatever the
  axial value said**, which is what "follows the per-side offset" looks like on
  screen. So this was the same allowance-blind entry as the other two reports.
  Left ticked but flagged: confirm against the drawing in AXIS, since all three
  reports were read off the 2D view.

- [x] **FIXED, `e27a858`** — ~~Regular offset moved to 1.0 across the part is not
  followed BEHIND the boss segment~~ — in front of it, it is fine. Roughing behind the boss starts
  from the **older offset value**: the 2D view shows the roughing entry sitting
  *nearer the Z axis than the pre-finish surface*, i.e. the entry is inside the
  surface it is supposed to stand off. A stale offset being used for the
  behind-boss region is the obvious suspect, and it may share a cause with the
  missing first pass above.

- [x] **DONE `5790e01` + `288b936`**, and confirmed by greatEndian in AXIS. ~~The missing first pass behind the boss persists with a different offset
  applied** — so it is not specific to the offsets that project was saved with.
  Same item as the one at the top of this file; recorded here because it was
  re-confirmed under new settings.

## From the reference CAM screenshots — `POLYLINE-GAPS.md`

`photo/roughing/{tool,geometry,radii,passes,linking}`, 54 screenshots, the whole
*Profile Roughing* operation, read 2026-08-09. **27 entries.** The file is
tracked and carries each one in full; these are the ones still open.

**Worth building** — small, self-contained, Python-first, in this order:

- [x] **16 — Pecking — DONE**, 2026-08-13, polyline.cfg **1.52**. *Peck length*
  and *Peck retract* on the roughing levels; 0 = off and provably a no-op.
  The retract goes **along the cut**, back into the groove just made, because
  backing out radially would leave the compensated path and re-enter it.
  Measured on testing_15_5 at 10/1: the cut reaches the identical Z−69.6380 on
  the identical radii, and the extra travel is **exactly 170.0 mm = 170
  retracts of 1.0**, so nothing goes anywhere unaccounted for.
  **Peck dwell** added the same day: seconds held AT THE RETRACTED POINT, where
  the chip is already broken and free, so the pause lets it fall clear rather
  than be dragged back into the next cut. Verified from the interpreter's own
  canon output — **85 dwells for 85 pecks**, exactly one each — and asserted to
  move nothing: same moves, same travel, same reach.
  `test_peck.py`. Runtime rather than a Python table, deliberately: the
  interval END is decided by the scan at runtime, so the rule is walked and no
  geometry is computed in the `.ngc`.
- [x] **9 — Tangential extension — DONE**, 2026-08-13, polyline.cfg **1.54**,
  **and completed 2026-08-15, `f7356af`, 1.60 — this entry was premature.** It
  claimed `_pl_begin_z` made roughing start at the extension; roughing in fact
  reached only the contour passes, because the ladder is bounded by Begin X /
  End X. See *Reported 2026-08-15* at the top for the three faults and the gate.
  *Front* and *Back tangential extension*: run the cut on past the drawn
  profile along the direction of its own end segment. Applied in
  `resolve_points` after the Z limits — so it grows "from the Front limit" as
  the reference words it, and every contour, window and table inherits it —
  and `_pl_begin_z` carries the front extension so roughing STARTS there too,
  which is the trap `analysis/025` recorded for the front limit.
  - **Along the tangent, not along Z.** On a wall those disagree completely:
    along Z it would do nothing, along the tangent it runs up the wall.
  - **A bug the end-to-end check caught**: `resolve_points` carries X as a
    DIAMETER, so taking the tangent in (z, x) as given made the radial half
    twice its true size — a 3.0 extension moved the surface 1.5. Fixed to the
    Z/radius plane and asserted there. Verified: front +3.0000 in Z at the
    front-most cutting move, back +3.0000 in radius up the end wall, neither
    touching the other end. `test_extension.py`.
- [x] **DONE — greatEndian ruled 2026-08-13 ("the limitation is real", "angle convention is right"), warning `eab37b1`, toolpath `8b2da4e` (opt-in, off by default).** ~~1 — Tool clearance FRONT — NEEDS A CALL, and it is bigger than the
  spec claimed.** `analysis/037`. The gap notes said the front-angle wiring
  already existed in `lathe_sections`; **it does not** — there is no front
  angle there at all, only `back_deg`. The tool table's front angle is used
  solely to DRAW the tool. So this means adding a front-flank constraint to
  `flank_envelope`, which lands on `finish_profile` and therefore on every
  contour, table, ladder and window — the five-fault blast radius of
  `analysis/032`.
  - **The question that decides the size**: should it change the TOOLPATH, or
    only the reachable-contour warning? Back clearance today changes the path
    (198 of 323 moves on testing_15_2). Warning-only touches
    `unreachable_spans` alone and is small; changing the path re-enters the
    choke point deliberately. Not guessed.
  - Also coupled to gaps **7/11** (undercuts, groove suppression), which need
    the same front flank and are themselves awaiting a decision.

**NEEDS A CALL** — these change what the operation promises, so the answer
decides whether they are work at all:

- [ ] **18 — the wall pass.** Their switch *skips* a cusp cleanup; we have no
  such move, so we are permanently skipped. Is our pre-finish contour pass the
  better trade, or do the levels want their own cleanup?
- [~] **7 / 11 — Machine Undercuts, Groove Suppression — MEASURED, part built**,
  2026-08-13, `analysis/046`. greatEndian's X-comparison rule is now
  `reentrant_spans()`, validated and cross-checked: on testing_15_5 it reports
  `Z−34.4..−69.6, 8.12 mm deep`, and **16 roughing passes lie inside that span**
  — it agrees with the behind-the-boss machinery. `PARAM_MULTI_X` is renamed
  *"Machine undercuts / grooves (always on)"* and its tooltip now maps our
  behaviour onto the reference's vocabulary. cfg 1.59.
  - **What is genuinely missing is only the CHOICE not to machine a pocket**, and
    it is NOT safe as a roughing-only switch: the finish pass follows the record
    array, not `finish_profile`, so a pocket skipped by roughing and pre-finish
    would still be traced at finishing depth into unroughed material — worse
    than machining it. **NEEDS A CALL**: at a suppressed pocket, should the
    finish pass skip it too, or trace across its mouth? The detector is ready
    either way.

- [ ] **12 — rest machining — MEASURED, not built**, 2026-08-13, `analysis/047`.
  `test_leftover` reports **0 wide regions on every demo project**, both
  sectioning states; the only material standing is narrow shoulder spikes
  (0.5681–0.8579 mm), every one narrower than 1.5× the nose. **Within one
  operation with one tool there is nothing to rest-machine** — a pass emitter
  would emit nothing, everywhere.
  - It is inherently a **second-tool** feature: those spikes are nose-radius
    fillets and come out only with a smaller nose. That needs (a) the simulated
    result of one operation carried to the next AT GENERATION TIME — `StockField`
    simulates a finished program in the preview, not per-feature during the walk
    — and (b) an operation whose stock is the previous operation's result rather
    than the Workpiece, or the second polyline roughs from the bar again and cuts
    air. The feature-to-feature mechanism exists (`WORKPIECE_FACE_Z`,
    `analysis/039`), so it is a real design, just a much larger one than the gap
    description implies.

**Re-read against the live parameter list, 2026-09-02.** Two more have closed
since the scan and are struck out below; the rest are written out one per line
rather than buried in a paragraph, so they are countable:

- [x] **26 — angled entry, including the feedrate.** `param_li_ang`,
  `param_li_len` and `param_li_feed` all exist. What remains is a DATUM
  difference only: their *Entry Clearance* is measured from the material,
  ours is a length along the lead.
- [x] **27 — rapid to next cutting depth.** Closed by the High feedrate mode
  (gap 23): `_pl_hf_feed` non-zero converts every positioning move, the
  level-to-level radial descent included, from G0 to G1 at that feed. That is
  exactly the "feed between depths" this asked for.

**Still not implemented** — each is a real difference from the reference. None
is a defect; they are absences, and most were parked deliberately:

- [x] **10 — Tool Limit: cutting edge vs contact point.** DONE 2026-09-02,
  `analysis/072`. `PARAM_X_LIMIT`, Cutting edge / Contact point; the shift is
  one nose radius expressed as a diameter, outward on OD and inward in a bore.
  Measured: 70.0 -> 70.8 with nose R0.400, and the toolpath moves with it.
  **It nearly shipped doing nothing** - the resolver defaulted `nose_r=0.0`, so
  the emitted global moved and the motion was byte-identical; caught only
  because the check measured motion rather than the number.

- [x] **14 — radial limits as REFERENCES, not numbers.** DONE 2026-09-02,
  `analysis/072`. `PARAM_B_X_DAT` / `PARAM_E_X_DAT`, Value / Stock OD / Stock
  ID, the same vocabulary Facing already uses. All five Python consumers and
  both G-code sites take the resolved value, so the datum moves the profile
  ORIGIN with it - `param_b_x` is a limit and a datum at once.

- [x] **Should Contact point move the profile ORIGIN, or only the ladder
  bound?** RULED 2026-09-02 by greatEndian — *"origin should stay put, only the
  ladder bound moves"*. Built: `x_stock_ref` (datum only) serves the origin, the
  sectioning stock envelope and the X-wall stand-off; `x_limit_abs` (datum +
  contact) serves the ladder bound. Measured on testing_15_9 — contact point
  leaves `_pl_b_x` at 70.0000 and still moves the toolpath, the datum moves both.
  cfg 1.70.

- [ ] **The stock datum offsets, it does not CLAMP.** Stock OD with a positive
  offset puts the limit outside the bar — legitimate for an oversize blank, and
  also an easy way to ask for something meaningless. Nothing refuses it.

- [ ] **2 — tool orientation as a programmable B axis.**
- [ ] **3 — Use Tailstock (M21/M22).**
- [ ] **4 — turn in negative diameter.**
- [ ] **5 — coolant modes beyond None/Flood/Mist.**
- [ ] **6 — cutting-data presets.**
- [ ] **17 — Make Sharp Corners.**
- [ ] **19 — grooving split radial / axial.** Blocked on grooving existing at
  all.
- [ ] **20 — Use Canned Cycle as a framing choice.** We have the G7x modes;
  what is missing is their framing of it as a per-operation switch.
- [ ] **21 — Extend to Stock.**
- [ ] **22 — linearisation tolerance.**
- [ ] **24 — approach / retract reference datums, in Z and in X.**
- [ ] **25 — Z Clearance and X Clearance as two stand-offs measured from the
  cut.** We have `param_ret_dist` and `param_zc_ovr`, which are a retract
  distance and a lead-in distance — the same jobs, different datums. Mostly
  naming, and worth checking before adding anything or we end up with four
  parameters doing three jobs.

- [ ] **The finding that outranks the list: it is a CAD-model package and we are
  not.** Much of Geometry and Radii — Model front/back, Chuck front, Selection,
  picked faces, Model OD/ID, *Outermost of…* — exists to point at solid geometry
  we do not have, because **our profile is the input**. Copying that vocabulary
  would leave parameters that can never resolve. What survives the translation
  is pointing at **our own** objects: the Workpiece's stock diameter and face Z.
  That one idea closes the useful half of gaps **8** and **14** at once, and is
  the datum-mode work already recorded under the Z limits.

Done from this scan: **15** separate X/Z stock to leave (`analysis/024`),
**8** the Z limits, front and back (`analysis/025`).

## Bounds do not migrate — found 2026-08-13

- [ ] **A cfg cannot CHANGE a parameter's minimum or maximum on an existing
  project.** `update_features` copies the saved bounds back over the cfg's:

  ```
  cfg declares   min 0.01    max 10.0
  saved project  min -45.0   max 45.0
  after migration min -45.0  max 45.0     the stale bound wins
  ```

  Found narrowing the back angle clearance (`analysis/043`): the new range
  reaches newly added features only, so on every existing project the operator
  can still type −45. The comment above those lines already argues the cfg
  should win — *"a saved copy is just a snapshot of what the cfg said when the
  project was saved"* — but the guard added only covers the cfg DROPPING a
  bound, not changing one.
  - The fix is one line, letting the cfg win, and it touches **every bound of
    every parameter of every migrating feature** — so it needs its own task and
    its own measurement across the demo projects, not a quiet edit.
  - Separately: **nothing clamps a stored VALUE on load**, so a project holding
    an out-of-range value keeps cutting with it until that field is edited.

## Watch list

- [ ] The AXIS crash fixed in `be094c2` was diagnosed by reasoning, not
  reproduced — there was no Python traceback, it is at the GDK level, and AXIS
  cannot run here. If it recurs the next suspects are the `Gtk.MenuButton`
  popup inside the GtkPlug and the `Gtk.Scale` in the transport row. The
  useful detail is **what you were doing at that moment**: closing AXIS,
  switching tabs, or mid-playback.

---

## Done

- [x] **NATIVE: the pre-finish pass collapsed onto the finish contour** —
  2026-08-03. `tip_comp_dia` built D as `2*extra_r + nose_dia`, but with a
  non-zero L the interpreter takes D/2 to BE the nose radius and scales the
  orientation term by it too, so the allowance cancelled itself. Fixed by
  moving the allowance into the CONTOUR - `build_prefinish_contour_gcode`
  offsets it geometrically and the D word carries the bare nose. Separation
  −0.4389/+0.0890 → **+0.5080/+0.5710**, matching Off and In CAM. The table
  shares the CAM parameter window, which is free in Native mode; there was
  nowhere else, since 5060 up is LinuxCNC's.

- [x] **IN CAM: the pre-finish pass collapsed onto the finish contour** —
  2026-08-03. `offset_contour` folded the allowance into the nose radius and so
  scaled the normal AND the orientation term by `nose_r + extra`; on a surface
  parallel to an axis those cancel and the allowance vanished. It now takes
  `extra` separately, the rule `lathe_comp.offset_vector` already implemented.
  Separation +0.5072/+0.5742 → **+0.5080/+0.5711**, matching Off. This is the
  asymmetry recorded on 2026-08-02 as "masked because every caller passes
  extra_r = 0" — **that note was wrong**, `build_cam_comp_gcode` passes a
  non-zero extra for every pass but the last.

- [x] **Restart NativeCAM, from Utilities** — 2026-08-03. `os.execv` replaces
  the process rather than forking, so the pid and therefore the XEmbed socket
  AXIS holds stay valid and the panel returns in place. The project is saved
  first and the restart is abandoned if that fails. LinuxCNC and the machine
  are untouched.

- [x] **Compensation is visible in the preview** — 2026-08-03, teal overlay
  plus the mode in the legend. Established first that the drawn toolpath is
  ALREADY the compensated path and the simulated tool already moves on it -
  Off 0.1094 against Native 0.0080 from the same nose-sweep code, so the
  difference is in the path. What was missing was the line and, more usefully,
  any statement of which mode is in effect: every saved project has it **off**,
  which is what "we see uncompensated" turned out to mean. Draws nothing when
  off, deliberately. `test_comp_overlay.py` makes it a self-check - Python's
  prediction against the interpreter's actual path, **34 contour points, worst
  0.0001 mm**; the five lead moves are excluded and the test fails if they ever
  stop being the only ones that differ. Working in
  `analysis/002-compensated-path-overlay.md`.

- [x] **Pre-finish pass started on the finish contour** — reported from AXIS
  2026-08-03, `photo/prefinishLeadInIssue_0.png`, fixed same day. A regression
  from Step 4: the entry placement was gated on `#<_tip_cam_r>`, which
  `tip_comp_dia` sets to **0 whenever nose comp is off** - and testing_15_2 has
  it off. An Off-mode pass still runs `G41.1 D[2*shift_r] L0` to hold its
  allowance, so the entry has to move by it. Pre-finish first cut
  r 20.7071 → **r 21.2151**, 0.5080 from the finish contour, which is the
  project's Offset per side. With `Passes = 2` the first finish pass now starts
  0.2540 out, half the offset, which nothing tested before. Full working in
  `analysis/001-prefinish-entry-offset.md`.

- [x] **Compensation, steps 1 to 5 — DONE**, 2026-08-02/03. The measured
  surface each mode leaves, against the programmed contour with corners
  excluded:

  | project | Off | Native | In CAM |
  |---|---|---|---|
  | testing_15_2 | 0.1094 | 0.3727 → **0.0080** | 0.0080 |
  | testing_11 | 0.1058 | 0.3624 → **0.0079** | 0.0079 |
  | testing_13_arcs | 0.0211 → **0.0013** | 0.2268 → **0.0014** | 0.8875 → **0.0014** |

  Native and In CAM now agree to the last digit on all three - two independent
  implementations of the same geometry converging. **Accuracy no longer decides
  the CNC-versus-CAM question**; it is now about tool-table behaviour,
  testability and the preview.

  - `a0e189a` **the arc truncation**, and it was in the NATIVE path.
    `_min_segment` kept only the first and last points of the whole contour, so
    the vertex where an arc meets the next item was dropped: R6, remainder
    0.9423 mm against a 0.960 mm limit, missed by 18 µm, cost 0.9386 mm of
    radius. In CAM escaped it only because `build_cam_comp_gcode` asks for
    nose_r 0. So In CAM was right and the yardstick was the broken one.
  - `c16df1f` **the entry ramp**. `lathe_poly_pass` pre-shifted by the plain
    normal instead of the orientation-aware vector, so the first CUT became the
    compensation entry move and a wall programmed straight at r 20.000 came out
    r 20.4000 → r 20.0074.
  - `27cdcc3` **`lathe_comp.py`** - the orientation table was in four places and
    the side rule in five, OD and ID inverted. One table, one `offset_vector`,
    one `lead_width`, and an op registry that is the seam for `turning` and
    `radius_od`: a row, not a refactor. Plus **`/tnrc`**, a compressed knowledge
    pack queried offline.
  - `e750ee3` **the polyline's entry takes its table from Python**. Motion
    byte-identical, which is the acceptance test for a refactor.
  - `test_quadrants.py` **both outside quadrants, every mode**. Orientations 1
    (+X,−Z), 2 (+X,+Z) and 7 (+X,0), both sides, eight surfaces: the nose lands
    on surface + R·normal to 1e-12 for every orientation, and compensating to
    the WRONG side gouges - a control that re-measured the same circle would
    have been a tautology. Uncompensated is exact on a cylinder and a face and
    out by 0.4000 mm on a 45° taper for orientation 2, 0.1657 mm for
    orientation 1.

  Still open in this area: the **default mode** is greatEndian's call;
  `tip_comp_vec.ngc` still has four callers (two ID and paused, `facing` whose
  X references resolve at runtime, and the OD taper).

- [x] **The lead-in on the pre-finish and finish passes — CHECKED**,
  2026-08-02. Deferred from the roughing lead-in work; the answer is that the
  roughing fault does not exist there, and a different one does.

  The contour passes do **not** re-enter behind a boss. They trace the
  reachable contour in one continuous run - on testing_15_2 the pre-finish pass
  is 38 feeds and the finish pass 22 feeds, each spanning Z −69.89…+1.71 and
  Z −70.40…+1.71 without a break - so there is no staircase of short entries to
  start on the contour, which was the whole of the roughing problem.

  What they do have is a **1.0000 mm feed at 45°** at the entry, from
  LinuxCNC's own compensation entry. Measured on four projects:

  | project | entry | verdict |
  |---|---|---|
  | testing_15_2 (OD) | 1.0000 mm at −135° | both ends in air, beyond the face |
  | testing_13_arcs (OD) | 1.0000 mm at −135° | both ends in air |
  | testing_11 (OD) | 1.0000 mm at −135° | both ends in air |
  | testing_14_inside (ID) | 1.0000 mm at +135° | starts in air, **ends in metal** |

  On OD work the contour itself starts beyond the stock face, so the whole
  approach is in free air and the first cut runs along the profile - nothing to
  fix. On ID work it is a real fault, now its own open point above. The lead-OUT
  is in air on both, OD (outward past the OD) and ID (inward into the bore).

- [x] **`test_skip_short` has its case back** — `testing_11.xml`, 578 → 566
  roughing moves with the option on. The test now runs over a list of projects
  and **fails** if the one marked `must_skip` stops skipping, instead of
  printing SKIP and passing. testing_15_2 is kept as its own regression for the
  option-off path, since that is the project the bug was found on.

  A negative control went in with it: the four moves the bug left behind are
  spliced into a clean run and the orphan detector must report them. Without
  that, "no faults found" and "the detector is broken" look identical - which is
  exactly the state this test had drifted into.

- [x] **Roughing pass ENDINGS — CLOSED**, confirmed in AXIS by greatEndian
  2026-08-02. Originally: *the endings stand off the pre-finish contour,
  everywhere.*
  greatEndian in AXIS, 2026-08-02, after step 2b landed: the behind-boss entry
  is now tangent to the artificial section and correct. The remaining gap is at
  the other end, and it is **across the whole part, not only behind the boss**.

  The number is the same constant step 1 identified. The stop uses the floor
  allowance `lvl_d` = **1.016 mm** of radius = finish offset 0.508 + one whole
  roughing depth of cut 0.508, the second from *Space passes from = Final
  contour*. The **pre-finish contour sits at final + 0.508**, so roughing stops
  exactly one roughing depth of cut outside it - a constant radial gap that
  becomes 1.017 to 1.509 mm of Z on the front slope and 1.016 mm against the
  end wall.

  Wanted: the ending **in contact with the pre-finish contour**, i.e. the stop
  measured at the finish offset (0.508) rather than the floor allowance
  (1.016).

  **DONE, 2026-08-02.** A second Python table - the reachable contour offset
  by the finish offset - emitted at `_pl_stop_base`, walked by
  `lathe_level_pass` to extend its stop. The scan keeps the floor allowance.

  | | before | after |
  |---|---|---|
  | end gap, mean / max | 1.112 / 1.509 mm | **0.558 / 0.756 mm** |
  | roughing cut length | 487.0 mm | **502.0 mm** |
  | gouges | 0 | **0** |
  | moves / cutting / level cuts | 243 / 147 / 27 | **unchanged** |
  | starts | - | **unchanged** |

  **Attempt 1, reverted first**, and worth keeping as the reason for the table:
  the obvious one-liner - `lvl_d` from `rough_target` rather than
  `step_target`, which is exactly the finish offset - closes the gap the same
  amount but nearly doubles the cut, 487.0 to **875.6 mm**, puts **10** level
  ends inside the contour and moves the starts too. `cross_t` is not only the
  stop: the same value drives the block test and the multi-crossing scan, so
  halving it lets levels run on through material they were held out of.

- [x] **Lead-in shape after a boss segment — CLOSED**, confirmed in
  AXIS by greatEndian 2026-08-02, all four parts.  Originally: greatEndian's call:
  **repair this first**, ahead of the tool-shape question and everything
  queued behind it. Case: `photo/leadInPresent_0.png` (now) against
  `photo/leadInNewAndRight_1.png` (wanted), on testing_15_2 with lead-in
  length and radius both 0.

  **Agreed specification** — confirmed 2026-08-01, applies to **ROUGHING
  passes only** (check the pre-finish and finish passes later, see below).
  Roughing runs Front to back, so the RIGHT-hand end of each level is where
  it starts.

  1. **Each level starts ON the contour, not short of it.** Today every level
     stops short and leaves a staircase of uncut steps; the orange segments in
     the picture are that missing metal. The level continues at its own
     diameter until it meets the offset contour below.
  2. **The offset contour** is the pre-finish contour copied outward by the
     **roughing depth of cut** — the yellow line in the picture.
  3. **The entry is three pieces**, outside inwards: a straight *real lead-in*
     through air, a tangent *lead-in radius* arc, then a straight segment that
     copies the profile at the **profile's own angle** and meets the contour
     tangentially, so the tool is already travelling parallel to the surface
     when it arrives instead of driving in at 45°.
  4. That copied segment has a **constant length**.

  **Measured on testing_15_2**, on a file that matches greatEndian's own
  screenshot exactly (`147 cutting moves, 96 rapids`):

  - **8 intervals enter the volume behind the peak**, and each starts
    **4.512 mm short in Z** of the ramp - the same figure on all eight, so it
    is one wrong constant, not an accumulating error. **36.1 mm of uncut metal
    in total**, which is the staircase in the picture.
  - The other end of those intervals is fine: they stop 1.016 mm off the end
    wall, which is the floor allowance against a vertical and correct.

  **Step 1 — the constant, printed not derived** (two derivations had already
  come out wrong):

      LVLIN  level=29.652  cross_t=1.016000
      LVLD   lvl_d=1.016  step_target=21.016  final_radius=20.000
             fin_off=0.508  prefin=0.254  rough_cut=0.508

  `cross_t` is **1.016 mm**, applied perpendicular to each contour segment: the
  finish offset 0.508 plus one whole roughing depth of cut 0.508, the second
  from *Space passes from = Final contour* rounding the configured 0.254
  pre-finish allowance up to a whole depth of cut. On the 13° ramp that is
  1.016 / sin 13° = **4.517 mm** of Z. Confirmed.

  So the levels stop exactly on the roughing floor as designed, and step 2 is a
  **specification change**: enter at **one roughing depth of cut** (0.508),
  which is 2.258 mm of Z instead of 4.517.

  **Step 2a — the entry contour, in Python. DONE.** The standing rule
  redirected this: instead of teaching the subroutine to resolve a second
  resume point at a second allowance - which needed a 15th CALL argument the
  interpreter refuses ("Command too long") and a second untestable scan -
  Python offsets the contour once, at generation time, and emits a table.

  - `lathe_sections.entry_contour()` offsets the reachable contour outward by
    one roughing depth of cut, by **exactly the rule lathe_level_pass uses**
    (per-segment outward normal, consecutive ends joined by a straight
    connector), so the entry and the stop are measured off the same
    construction. Side follows the roughing direction, so front-to-back and
    back-to-front both come out right.
  - `build_entry_contour_gcode()` emits it at `_pl_entry_base` / `_pl_entry_n`.
  - Table space: FC_TOP 4400 → 4200, ENTRY 4200-4400. Both bounded, both refuse
    rather than run into a neighbour; `test_table_layout` covers it.
  - The roughing depth of cut reaches generation-time Python by the route the
    flank length already takes - `TOOL_TABLE.save_rough_cut` from the Tool
    Change's own cut depth.
  - On testing_15_2 the table comes out 38 points, and **motion is
    byte-identical**: 244 calls before and after, because nothing reads it yet.

  **A silent factor of two, found by cross-checking rather than by reading.**
  The first version offset the profile in the DIAMETERS `resolve_points`
  returns, using a RADIUS offset. A perpendicular offset is not the same
  construction in the two spaces - the ramp that measures 13° in radius
  measures 24.78° in diameter - so it landed at **Z-48.161 where the
  interpreter's own scan at the same allowance gives Z-49.203**, exactly half
  the shift, with nothing to show for it. Fixed by offsetting in radius.

  | level r | Python entry Z | interpreter scan | error |
  |---|---|---|---|
  | 29.652 | -49.208 | -49.203 | 0.005 mm |
  | 29.144 | -51.408 | -51.404 | 0.004 mm |
  | 28.636 | -53.609 | -53.604 | 0.005 mm |

  The residual is the scan's own `l_eff` epsilon: 0.001 mm of radius over
  sin 13° is 0.0044 mm of Z. **So the Python construction and the subroutine's
  now agree to within their own tolerance**, which is what step 2b needs.

  **Step 2b — DONE.** `lathe_level_pass` gains `z_start`, resolved by walking
  the table Python emitted - no offsetting of its own, no second scan, no extra
  CALL argument. `w_from` still governs the crossing scan, the stop and the
  block test, so the floor allowance is untouched exactly as asked.

  Measured against a baseline generated and parsed under its own library state:

  | | before | after |
  |---|---|---|
  | moves / cutting moves | 243 / 147 | 243 / 147 |
  | level cuts | 26 | **27** |
  | roughing cut length | 466.4 mm | **487.0 mm** |
  | gouges into the reachable contour | 0 | **0** |
  | uncut behind the peak | 36.1 mm | **20.3 mm** |
  | gap per level | 4.512 mm | **2.254 mm** |
  | levels NOT behind the peak | - | **ends unchanged, all 18** |

  2.254 against the 2.258 target - the difference is the scan's own `l_eff`
  epsilon. No extra air moves, one extra interval now reachable, and 20.6 mm
  more metal actually removed.

  *Method note, paid for three times over in this session: an .ngc generated
  earlier in the session is not a safe baseline, and neither is a toolpath
  parsed earlier - `parse_program` re-runs the interpreter against whatever
  `lib/lathe` is on disk AT THAT MOMENT. Generate and parse both sides in one
  run, with the file state you mean.*

- [x] **The block is gone; its reference lines close the tool** — greatEndian
  in AXIS, `photo/toolFlank_3.png`, "now" against "then". Drawn as a square of
  its own it read as a second object floating clear of the tool it belongs to.
  The square is no longer drawn at all. Instead its **near side becomes the
  tool's right-hand reference** and its **far side becomes the tool's bottom**,
  so the silhouette is one continuous body from the nose down.

  Measured on a 0.8 mm nose, orientation 2, front 15 / back 75, 25 mm shank:

  | | |
  |---|---|
  | short front cutting edge | 6.077 mm at 75° from Z, nose → holder face |
  | near side, the holder face | Z −8.400, tangent to the nose on the side **away** from the cut |
  | right-hand reference | Z +2.598, one line of constant Z |
  | bottom | r +37.598 from the tip = insert 12.6 + shank 25 |
  | closing points | 5, up from 3 |
  | radial extent at a 20 mm shank | 32.60 mm — **exactly 5 mm less**, the shank difference and nothing else |

  **The two sides are parallel constant-Z lines, and the front edge is short.**
  Two wrong versions on the way, both corrected in AXIS by greatEndian:

  1. The **front cutting edge run down to the bottom line** put the near side
     on a slant of the front angle — 9.8 mm of Z over 37.6 mm of radius.
     `photo/toolFlank_3_0.png` against the "then" panel: *"you do not have two
     parallel vertical lines now, near radius is angled by front angle which is
     wrong"*. In a plan view a holder has straight sides.
  2. Closing on the **tangent nearest the cut** and dropping the front edge
     altogether gave two parallel sides but lost the edge: *"you are missing
     the opposite radius side feature which is creating small/short cutting
     edge from front by front angle"*.

  Both are answered by the same line — the tangent to the nose on the side
  **opposite** the cut, which `tool_holder` has always used as the holder's
  front face. The front edge leaves the nose at the front angle and runs only
  as far as that face, 6.077 mm on a 0.8 mm nose at 15°; the holder takes over
  from there. The face is no longer drawn on top of the body as a separate
  triangle — it is the body's own near side now, and drawing it twice only left
  a visible seam.

  The collision check still uses the **full 160 mm block**, which the picture
  no longer shows: what fouls a shoulder is the holder running back to the
  turret, and a check that stopped where the drawing stops would be a drawing
  rather than a check. Still 0 hits on the demo program at 12, 25 and 32 mm.

  Two things this broke on the way. The collision body was taking the last
  **three** points of the outline, which silently dropped the new bottom line -
  most of the tool. `tool_silhouette` now reports how many closing points there
  are in `parts['tail']`. And `tool_shank` measured its anchor off the returned
  outline, which now runs down to the bottom line - that set the block one
  whole shank height too far out. It takes the insert corners from `parts`.

- [x] **How the tool is bounded: by its SHANK** — greatEndian supplied the ISO
  holder relationships 2026-08-02, kept in `ref/tool-shank/NOTES.md`. Decided:
  the Tool Change asks for the **shank height** and nothing else; overall
  length, width and insert size all follow from it.

  The old outline closed by extending both cutting edges to a Z-perpendicular
  cap one flank length back. The steep front edge climbs 3.86 mm of radius per
  mm of Z, so it grew without limit — **6 mm flank → 23.3 mm radially, 25 mm
  flank → 94.2 mm**. It is now three nested pieces: nose circle, insert closed
  at its own **edge length along the edge**, and the shank rectangle behind.

  | | before | after, 25 mm shank |
  |---|---|---|
  | insert, 6 mm flank | 6.0 × 23.3 mm | **12.6 × 12.6 mm** |
  | insert, 25 mm flank | 25.0 × 94.2 mm | **12.6 × 12.6 mm, unchanged** |
  | what bounds it | the flank | the insert edge |
  | collisions on the demo program | 0 | **0 at 12, 25 and 32 mm** |

  Derivation is interpolated, not nearest-match: nearest-match with a scale
  factor made a 22 mm shank come out **longer** (165 mm) than a 25 mm one
  (160 mm). The insert edge is not interpolated — 12.2 mm is not a size an
  insert comes in.

  **The block's corner sits on the INSERT, not on the tool tip.** Anchored on
  the tip its top face lies at the cutting radius and sweeps the whole part
  behind the tool: **50 collisions on a program with none, and the same 50 for
  a 12 mm shank as for a 25 mm one** — the identical count is what gave it
  away. A real insert stands proud of its pocket.

  Only a stub of the holder is drawn, one shank height deep; the collision
  check uses the full 160 mm. A field, not a combo of standard sizes, because
  a fixed list of millimetre values breaks on an inch machine and
  ground-to-fit shanks exist — the nearest standard supplies the proportions.

- [x] **Item 3 — the three-piece entry, confirmed in AXIS by greatEndian
  2026-08-02** — `168f703` `9474185` `f4698ed`. The approach copies the
  contour's own angle, taken from the entry table rather than assumed, and
  turns onto the level at the entry point:

      dZ 2.2004   dR 0.5080   length 2.2583   13.00 deg

  The depth of cut is a RADIAL quantity, so it is **projected** onto the
  contour's angle rather than used as a length: one depth of cut of radius
  costs `doc/sin` along the segment and `doc/tan` in Z — 2.2583 and 2.2004 for
  a 0.508 mm cut on a 13° ramp. The first version used 0.508 as the Z extent
  directly, which is the same number in the wrong place. 243 moves → 261, the
  18 being two feeds on each of the nine entries; level cuts, cut length and
  gouge count all unchanged.

  Two lessons kept: the segment first went **inside** the `o<lead_in>` branch,
  which only runs when a lead-in length or radius is set, and the project that
  wants it has **both at 0** — so it did nothing in AXIS and had to be verified
  in the failing configuration itself, not the working one. And a projection is
  not a length.

- [x] **AXIS crash: simulation timer outlived the panel** — `be094c2`. A GLib
  timeout belongs to the main loop, not the widget; it kept firing on dead
  widgets and took LinuxCNC down with an X BadWindow. Stopped on `destroy`,
  plus guards in `_sim_tick` and `_done`, plus three other frame-clock tick
  sources removed.
- [x] **One grey for the whole tool** — `1cb2c8e`.
- [x] **Tool table angles are off the perpendicular; holder face on the back
  of the nose** — `1e81103`. Edge sits at 90 − angle from Z, which also made
  the drawn tool agree with the shadow ramp for the first time.
- [x] **Holder drawn in front of the insert** — `1fbdd9e`, recoloured by
  `1cb2c8e`.
- [x] **Back-angle clearance parameter** — `d2bb5f8`. Default 2°; ramp 15° →
  13° on testing_15_2.
- [x] **Skipped roughing pass no longer feeds into the part** — `163b0e4`.
  Four moves removed per skipped level, one of them a feed into metal.
- [x] **Accessible contour treats the flank as unbounded** — `310a06b`. One
  20-point table for roughing, pre-finish and finish; no pass cuts inside it.
  Paused behind `FLANK_BOUNDS_CONTOUR`, not deleted.
- [x] **Preview draws the contour for the tool actually loaded** — `df19f8d`.
- [x] **Flank length moved to the Tool Change, and drawn** — `2fb8048`.
- [x] **Every lathe op brackets its finishing pass** — `a8118fb`. Facing,
  turning, boring, both tapers, radius_od, polyline.
- [x] **Info and Statistics pages, with a real time estimate** — `4896b94`.
  G94/G95 and G96/G97 handled; unknown-rate moves counted, never guessed.
- [x] **Flat tab: the program as plain G-code** — `068d1a5`. Proved by
  re-running it: 235 moves, worst difference 0.000000 mm.
- [x] **Pane fits the panel** — `859f7d2`. 522 px → 281 px minimum width.
- [x] **Pre-finish passes coloured apart from the rest** — `3b47eb5`.
