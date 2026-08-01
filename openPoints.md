# Open points

The running list of what is not finished. Every new open point gets written
here as soon as it appears, and gets ticked off here as soon as it is done —
not left to be remembered.

**Conventions**

- `- [ ]` open, `- [x]` done. A finished item moves to **Done**, newest first,
  with the commit that closed it.
- A point that needs a decision from greatEndian is marked **NEEDS A CALL** and
  says what the choice is between. Nothing gets guessed twice.
- Numbers, not adjectives: if something is wrong by 9.73 mm, say 9.73 mm.

Branch: `liveTooling`. Last pushed: `be094c2`.

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

  **Measured on testing_15_2, current build.** Every one of the eight levels
  behind the boss starts exactly **4.512 mm short in Z** of the ramp - the
  same figure on all eight, so this is one wrong constant and not an
  accumulating geometry error. Roughing depth of cut is 0.508 mm; the levels
  step 2.2007 mm in Z, which is 0.508 / tan(13°) and correct for the ramp.

  | radius | starts Z | ramp at Z | uncut |
  |---|---|---|---|
  | 29.652 | -51.462 | -46.950 | 4.512 mm |
  | 29.144 | -53.662 | -49.150 | 4.512 mm |
  | … | … | … | 4.512 mm |
  | 26.096 | -66.865 | -62.352 | 4.512 mm |

  **36.1 mm of uncut metal in total.** 4.512 mm along Z at 13° is 1.042 mm
  measured perpendicular to the ramp, which is very close to twice the
  0.508 mm floor allowance (2 × 0.508 / sin 13° = 4.516) - so the first thing
  to check is whether the level stop is applying that allowance twice, or
  applying it normal to the ramp where it should be radial.

- [ ] **Check the same lead-in on the pre-finish and finish passes** once
  roughing is done - deferred deliberately, not forgotten.

## Tool shape — the one live question

- [ ] **NEEDS A CALL — how is the tool bounded?** The silhouette's radial
  extent is large: **48 mm at a 6 mm flank, 85 mm at 16 mm**. The steep 75°
  front edge needs 3.86 mm of travel per mm of Z to reach the cap, so capping
  in Z is what makes it grow. Now that the angles are right this is a real
  property of the construction, not a bug. Candidates: flank measured **along
  the edge** rather than in Z; a separate **holder depth**; a fixed **shank
  height**. Everything under Simulation below waits on this.

- [ ] **A front or back angle over 90° has no defined contour.** The
  construction puts an edge at 90 − angle from Z, so past 90° it leans the
  other way and the shape stops meaning what it means for a normal insert.
  Measured on a 0.8 mm nose, orientation 2, 6 mm flank:

  | front | back | insert | holder |
  |---|---|---|---|
  | 15 | 75 | 6.0 × 23.3 mm | yes |
  | 15 | 105 | 6.0 × 24.7 mm | yes |
  | 95 | 75 | 5.3 × 1.8 mm | **none** |
  | 100 | 110 | 5.5 × 2.0 mm | **none** |
  | 0 | 75 | **none** | none |

  So it does not simply refuse: a front angle over 90° still draws an insert,
  a wrong one, and drops the holder without saying so; an angle of exactly 0
  or 180 draws nothing at all and gives no reason. Needs a defined answer for
  those tools - a different closing line, or a refusal the operator can
  actually see - rather than a quietly wrong picture. Whatever it is has to be
  settled with the bounding question above, since both are about how the
  outline closes.

## Simulation — paused at your word

- [ ] **Collision detection is built and tested but not wired to the pane**
  (`fdfa99d`). Reports rapids into metal and the tool body into metal, 1.5 s
  on testing_15_2. Held back because its output depends on the tool shape
  above — currently 22 hits on a clean program, all artefacts of the
  silhouette's proportions.
- [ ] Timeline marks for collisions, and a Verification line in Stats —
  designed, not built.
- [ ] `Accuracy` slider → `StockField.columns_for`.
- [ ] `Regenerate on rewind` as an option (currently always on).
- [ ] `Programmed Point` toggle (the control-point cross is always drawn).

## Lathe G-code

- [ ] **ID lead-in/out gouge, 1.4929 mm native** — open since the tip-comp
  work.
- [ ] **In-CAM comp is still refused on the five parametric ops**: facing
  refuses outright; tapers and boring accept it.
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
  affects the drawn silhouette.

## Watch list

- [ ] The AXIS crash fixed in `be094c2` was diagnosed by reasoning, not
  reproduced — there was no Python traceback, it is at the GDK level, and AXIS
  cannot run here. If it recurs the next suspects are the `Gtk.MenuButton`
  popup inside the GtkPlug and the `Gtk.Scale` in the transport row. The
  useful detail is **what you were doing at that moment**: closing AXIS,
  switching tabs, or mid-playback.

---

## Done

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
