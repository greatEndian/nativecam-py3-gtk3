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

Branch: `liveTooling`. Last pushed: `0e399e0`.

---

## Next — before anything else

- [ ] **Lead-in shape after a boss segment is wrong.** greatEndian's call:
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

- [ ] **Roughing pass ENDINGS stand off the pre-finish contour, everywhere.**
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

- [ ] **Check the same lead-in on the pre-finish and finish passes** once
  roughing is done - deferred deliberately, not forgotten.

- [ ] **`test_skip_short` has lost its case.** The entry extension lengthened
  every level on testing_15_2 past 2.5x the nose diameter, so nothing is short
  enough to skip there any more and the "does it skip at all" control is
  unexercised - it now prints SKIP with the reason rather than passing
  silently. The orphan-entry check, which is the real regression guard, still
  runs. Needs a project that still has a short level.

## Tool shape

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

## Lathe G-code

- [ ] **NEEDS A CALL — is tool radius compensation done by the CNC or by the
  CAM?** Raised by greatEndian 2026-08-02. Today it is **always the control**:
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

- [ ] **ID lead-in/out gouge, 1.4929 mm native** — open since the tip-comp
  work. Very likely a consequence of the entry rule in the point above; if
  compensation moves into Python it disappears rather than gets fixed.
- [ ] **In-CAM comp is still refused on the five parametric ops**: facing
  refuses outright; tapers and boring accept it. Blocked on the same call.
- [ ] **Grooving** is not implemented — the menu icon is a placeholder, left
  deliberately so it is not forgotten.
- [ ] **Drilling** — same, placeholder only.

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
