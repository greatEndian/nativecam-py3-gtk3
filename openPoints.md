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

Branch: `liveTooling`. Last pushed: `8c6551b`.

---

## Next — before anything else

- [x] **THE FIRST PASS BEHIND THE BOSS IS MISSING — FIXED**, 2026-08-12,
  `5790e01`, `analysis/032`. The resume-envelope walker and the flag split are
  wired and the suite is green.

  **Root cause of the last fault**: `build_floor_contour_gcode` was built from
  `resolve_points` — the RAW polyline — while `build_stop_contour_gcode` and
  `build_entry_contour_gcode` beside it use `finish_profile`, the **reachable**
  contour. The raw shape contains an undercut the back angle cannot reach, so
  the floor contour collapsed to a **24 mm flat at r20.762** where the machined
  surface tapers r33 → r24.24, and roughing dived into material it must not
  enter.

  ```
  test_rough_comp overcut  Off  7.6277 -> 0.0503 mm   (bound 0.0800)
  topmost behind-boss      off  32.1920 -> 33.2080
                           on   32.1522 -> 33.1273
  ```

  **A stale warning was the whole blocker.** The docstring said building it from
  `finish_profile` "cost testing_15_2 nine of its 29 levels". Re-measured, that
  is no longer true — the fault it described was fixed by intervening work, and
  the warning outlived it. **Re-measure a warning before obeying it.**

  Also fixed on the way, pre-existing: `test_rough_overlay` was red from
  `3df0a4c`, which gave the stop contour `fin + prefin` without moving the drawn
  twin — the overlay sat 0.2540, exactly `pf_off`, inside the line the levels
  stop on.

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


- [~] **RESTART NATIVECAM — CAUSE FOUND AND FIXED, NEEDS A TRY IN AXIS**,
  2026-08-10, `96e91ec`, `analysis/028`. The `os.execv` reasoning was wrong at
  both ends. Keeping the pid was **never needed** — `gladevcp -x {XID}` forces
  an Xlib reparent into AXIS's **Tk frame**, which outlives the process. And
  keeping the pid is **what broke it**: gladevcp frees its HAL component in a
  `finally`, execv never unwinds, HAL sees the name owned by a live pid — the
  same pid — and refuses it, whereupon gladevcp calls **`sys.exit(0)`**. Status
  0, log only: restarts, never comes back, no error. Measured
  (`HAL: ERROR: duplicate component name`) and the fix measured too.
  - Now: fork a detached child that blocks on a pipe, exit cleanly through
    `gtk.main_quit()` so `halcomp.exit()` runs, child then execs the original
    argv (still carrying `-x <XID>`).
  - **greatEndian: please try it in AXIS.** The HAL half is proven here; the
    reparent cannot be — AXIS will not run in this environment, and reasoning
    is what produced the broken first version. If the panel still does not
    come back, look for gladevcp's `XID:` line in the log: it says whether the
    relaunch got that far. Fallback stays what it was — remove the menu item
    rather than let it fail silently.

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

- [ ] **CRASH: toggling the Sectioning property kills the panel** —
  greatEndian 2026-08-04, hard X error, LinuxCNC terminated.

  ```
  Gdk-WARNING: GdkWindow 0x5c00006 unexpectedly destroyed
  Gtk.py:1689: Warning: invalid (NULL) pointer instance
  Gtk.py:1689: g_signal_handler_disconnect: assertion 'G_TYPE_CHECK_INSTANCE' failed
  Gdk-CRITICAL: gdk_frame_clock_end_updating: assertion 'GDK_IS_FRAME_CLOCK' failed  (x3)
  [GladeVCP-ncam][ERROR] GLADE VCP ERROR: X Protocol Error: 3   (BadWindow)
  ```

  **No Python traceback** in `linuxcnc_debug.txt` or `linuxcnc_print.txt` - GTK
  aborts on the X error before anything surfaces. The G-code path is NOT
  implicated: `gen_project.py --set polyline:param_sectioning=1` builds
  cleanly headless.

  **One real defect found and fixed on the way** (not proven to be the cause):
  `NCamPreviewPane._done`'s liveness guard was
  `if self.area.get_window() is None AND self._acc is not None`. `_acc` is a
  cached path-length array that says nothing about whether the panel is alive,
  and it is set to None four lines below - so on the first result after any
  refresh the guard could not fire. A parse finishing after the pane went away
  then ran on through `set_text` / `_render_stats` / `_render_info`, touching
  destroyed widgets. Now tested on the window alone.

  **To pin the actual cause**: re-run with `GDK_SYNCHRONIZE=1` so the X error
  points at the failing call rather than at the next flush. Also worth knowing
  whether the crash needs a preview parse to be in flight - toggle Sectioning
  immediately after a Regenerate versus well after one.

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


- [ ] **AXIS FROZE ON THE PREVIEW'S STOP BUTTON, cause unknown** —
  greatEndian 2026-08-03, AXIS had to be killed, no traceback. Ruled out by
  reading and by measurement: the stop path is cheap (`sim_t = 0`
  short-circuits the field rebuild), `rs274` runs on a worker thread with `-b`
  and a 120 s timeout, and `parse_program` on the live program measures
  **1.76 s / 17 MB peak** — not memory. A double removal of the playback timer
  source was found and fixed, but it fires at the END of playback, not on Stop,
  so it is not claimed as the cause.

  **`_trace()` now logs each coarse UI callback to stderr, flushed** — `play`,
  `stop`, `stop done`, `refresh start`, `done`. A hang leaves only what was
  already flushed, so the last `[ncam-preview]` line names the callback that
  did not return. **Next time it freezes, the last few of those lines are what
  is needed.** `NCAM_NO_TRACE=1` silences it. Working in
  `analysis/003-stop-button-freeze.md`.

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

## Tool shape

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

- [ ] **NEEDS A CALL — is tool radius compensation done by the CNC or by the
  CAM?** Raised by greatEndian 2026-08-02. **Both modes already exist** — the
  `Tool nose comp` combo is Off / Native LinuxCNC / In CAM, and In CAM is built
  for both tapers, boring and the polyline. What is not decided is which is the
  DEFAULT and which one the project commits to. Today the default is
  **the control**:
  `taper`/`taper_id`/`boring`/`facing` switch native comp on through
  `tip_comp_on.ngc` (`G41.1`/`G42.1 D#<_tip_comp_d> L#<_tip_comp_l>`),
  `turning` and `radius_od` use plain `G41`/`G42`, and the polyline finish pass
  uses dynamic comp with `L0` for the geometric offset and `L#5413` only when
  nose comp is on. The CAM emits control points and the interpreter offsets
  them.

  The alternative — and the one the standing rule points at — is to offset the
  path **in Python at generation time**, the way `entry_contour()` and the stop
  table already offset the contour, and emit coordinates the machine walks with
  `G40` throughout.

  What each side actually buys:

  | | CNC-side (today) | CAM-side (Python) |
  |---|---|---|
  | follows the machine's own tool table | yes, no regeneration needed | no, baked in at generation |
  | a re-ground insert | just works | must regenerate |
  | unit-testable | no, only `rs274` end-to-end | yes, plain `python3` |
  | entry/exit rules | a comp entry needs a straight feed ≥ nose radius in free air | none |
  | impossible geometry | control aborts the program | we decide and can warn in the pane |
  | preview agrees with the machine | only if we model comp ourselves | exactly, the points are the path |

  The entry rule is not theoretical: it is why `facing.ngc` **drops its lead-in
  and lead-out arcs** when comp is on, why the ID ops need the retract widened
  by `#<_tip_lead_w>`, and it is the likely root of the 1.4929 mm ID gouge
  below. It is also why comp is refused on some ops at all.

  The realistic answer is probably **both, as a preference** — control comp for
  a shop that edits its tool table between runs, CAM comp for correctness and
  for the preview. But that is a decision, not a guess, and it decides how much
  of `lib/lathe` stays. Nothing else should be built on top of comp until it is
  taken.

  ### Settled since — accuracy no longer decides it

  Steps 1 to 5 in the Done section closed both defects that were making the
  two modes look different. The surface each leaves now, corners excluded:

  | project | Off | Native | In CAM |
  |---|---|---|---|
  | testing_15_2 | 0.1094 | **0.0080** | **0.0080** |
  | testing_11 | 0.1058 | **0.0079** | **0.0079** |
  | testing_13_arcs | 0.0013 | **0.0014** | **0.0014** |

  **Native and In CAM agree to the last digit on all three.** The earlier
  reading - Native 0.37 and In CAM 0.89 - was two separate faults, each
  inflating the OTHER mode's apparent error: the arc truncation was in the
  native path and In CAM only escaped it by asking for nose_r 0, and the entry
  ramp was Native's alone.

  So this decision is now about **tool-table behaviour, testability and the
  preview**, not correctness. The trade-off table above still stands on those
  grounds. My reading remains **both, as a preference**, with the default the
  open question - but it is a preference now, not a correctness call, which
  makes it a smaller decision than it was.

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
- [ ] The **unbounded flank leaves up to 10.0899 mm of radius uncut** behind the
  boss on testing_15_2, Z−70.22 to Z−35.77, from `unreachable_spans` with the
  live arguments. *(The 9.73 mm over Z−70.22..−36.31 recorded here before was
  the clearance-0 figure, from before the 2° default.)* testing_15_4 is the
  same to four decimals. Still a consequence of the tool and the setup, not a
  defect: reaching it needs a second tool or a second setup.
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

- [ ] **An End Z limit does not bite on testing_15_5.** An absolute `-40` still
  reaches Z−70.4 there, while the same limit on testing_15_2 correctly reaches
  Z−40.6043. Verified **pre-existing** — identical with the datum work stashed —
  so it is not a regression from it, and it was found only because that work
  needed a project with a known-good limit to anchor its probe against. Worth
  finding out what is different about 15_5 before trusting a Z limit on an
  arbitrary project.
- [ ] **VALIDATION — a `[VALIDATION]` block cannot use `resolve_points`.** It
  runs from `Feature.validate()` part-way through `to_gcode`'s walk, before the
  children are resolvable, so it returns an **empty list** there. A check
  written as "if the trim leaves fewer than two points, refuse" fired on a
  perfectly good profile. Only parameter-against-parameter checks are reliable
  in that block. In `LEARNINGS-LOG.md`.

- [ ] **VALIDATION — `msg_inv` at severity 1 blocks any headless run.** It ends
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

- [ ] **FIX: the stop contour must carry `fin + prefin` too.** It must NOT go
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

- [ ] **Document the four overlays**, in the help section and not only as a
  colour swatch. What each one IS, and — the part that actually confuses —
  whether it is a *surface*, a *toolpath*, or a *construction reference*:

  | legend | colour | what it really is |
  |---|---|---|
  | rough entry path | yellow-green dashed | `#<_pl_entry_*>` — where a roughing level may BEGIN cutting. A construction contour at `fin + prefin + one depth of cut`, walked by `lathe_level_pass:407` and the source of the ramp-direction table. **Not a path the tool follows.** |
  | rough stop path | orange dashed | `#<_pl_stop_*>` — where a level must STOP. Also a construction contour, and built WITH the nose, so it is a tool-CENTRE reference |
  | pre-finish surface | solid | the offset contour, `stock_pair`, nose 0 — a real surface |
  | comp path | teal dashed | the compensated finish toolpath |

- [ ] **The dashed/solid convention mislabels two of them.** The code's own
  comment says *"SURFACES are solid, TOOL PATHS are dashed"*, but `rgh_entry`
  and `rgh_stop` are neither — they are reference contours, and calling them
  "path" in the legend invites exactly the reading that they are where the tool
  goes. Renaming them "rough entry limit" / "rough stop limit", or giving
  references their own dash pattern, would say what they are.
- [ ] **The entry line's constant gap needs stating wherever it is documented**:
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

- [ ] **The TOOLPATH half is still open, and is a decision, not a task.** The
  warning now says which regions the leading flank cannot make; keeping the path
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

- [ ] **Sectioned roughing passes in FRONT of the boss have mixed, crossing
  paths, offset randomly from each other.** Sectioning on. The passes are not a
  clean ladder — they cross one another and sit at inconsistent offsets.

- [ ] **Pre-finish offset = 0.0 is ignored by roughing**, which still leaves
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

- [ ] **The missing first pass behind the boss persists with a different offset
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
- [x] **9 — Tangential extension — DONE**, 2026-08-13, polyline.cfg **1.54**.
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
- [ ] **1 — Tool clearance FRONT — NEEDS A CALL, and it is bigger than the
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
- [ ] **7 / 11 — Machine Undercuts, Groove Suppression.** Both may be our
  *Respect tool back angle* and *Re-entrant profile* worded differently. Two
  tooltips would settle both.
- [ ] **23 — rapids posted as G1.** Real safety on a control that doglegs.
  Does yours?
- [ ] **12 — rest machining.** The only large one — and the preview's
  `StockField` already simulates remaining material, so it is nearer than it
  looks.

**Recorded and parked** — real differences, not worth chasing now: Tool
Orientation as a B axis (2), tailstock M21/M22 (3), negative diameter (4), six
coolant modes (5), cutting-data presets (6), sharp corners (17), grooving split
radial/axial (19), canned cycle framing (20), extend to stock (21),
linearisation tolerance (22), approach/retract datums (24), Z/X clearance
naming (25), entry clearance datum (26), rapid-to-next-depth (27), radial limits
as references (14).

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
