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

Branch: `liveTooling`. Last pushed: `152baec`.

---

## Next — before anything else

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

- [ ] **NATIVE: the pre-finish pass collapses onto the finish contour.**
  greatEndian 2026-08-03. Reproduced and measured on testing_15_2 - separation
  between the two passes is **min −0.4389, mean +0.0890** where it should be
  +0.508. Negative means **the pre-finish pass cuts inside the finished
  surface**, so this is not cosmetic. In CAM had the same symptom from a
  different cause and is fixed; Off was always correct.

  Cause: `tip_comp_dia` builds the D word as `2*extra_r + nose_dia`, but with a
  non-zero **L** the interpreter takes D/2 to BE the nose radius and scales the
  orientation term by it too - so an allowance folded into D cancels itself.
  **An allowance cannot be carried in the D word while L is set.**

  **To finish**: move the allowance into the programmed contour instead.
  `poly_lathe_mill` already loads the pre-finish points from `_pl_fc_base`
  through `cam_load`, so Python can emit that table pre-offset and pass
  `shift_r = 0`, leaving D as the bare nose diameter. Check `taper`, `taper_id`
  and `boring` for the same pattern while there. Working in
  `analysis/004-prefinish-collapses-under-compensation.md`.


- [ ] **NEEDS A CALL — should the saved projects be switched to Native?**
  Every project in the repo has `Tool nose comp = 0`: testing_11, both
  polylines of testing_13_arcs, both of testing_15_2, and one of two in
  testing_15_3. The default for a NEW polyline is 1, the CNC side, so this is
  only the saved ones. It matters because with all of them Off the Native path
  is exercised only by the measurement harness and never by anyone opening a
  project — and Off is why the preview looked uncompensated.

- [ ] **Two zero-length feeds per contour pass.** `(Z−70.4000, r30.0000) →
  (Z−70.4000, r30.0000)`, one at the end of the pre-finish pass and one at the
  end of the finish pass on testing_15_2. Harmless, and noise in every move
  count taken from these programs.

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

- [ ] The **unbounded flank leaves up to 9.73 mm of radius uncut** behind the
  boss on testing_15_2, Z-70.22 to Z-36.31. The unreachable-contour warning
  names the span.
- [ ] **Back angle clearance defaults to 2°**, so every existing project gains
  a small standoff on migration.
- [ ] **Skip short passes is now off by default.**
- [ ] **testing_15_2 and testing_15_3 need their flank length re-entered** on
  the Tool Change, 25 mm each — though with the contour unbounded it now only
  affects the drawn silhouette, and with a shank set it affects nothing at all.
- [ ] **Every project gains a 25 mm / 1 in shank on migration** to
  tool-change.cfg 1.22. That is the common size and it only changes the
  picture, but a 12 mm boring-bar tool will look too big until it is set.

## Watch list

- [ ] The AXIS crash fixed in `be094c2` was diagnosed by reasoning, not
  reproduced — there was no Python traceback, it is at the GDK level, and AXIS
  cannot run here. If it recurs the next suspects are the `Gtk.MenuButton`
  popup inside the GtkPlug and the `Gtk.Scale` in the transport row. The
  useful detail is **what you were doing at that moment**: closing AXIS,
  switching tabs, or mid-playback.

---

## Done

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
