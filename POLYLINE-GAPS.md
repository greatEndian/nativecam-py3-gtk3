# Lathe polyline — gaps against a reference CAM package

Implementation notes. greatEndian is capturing screenshots from their own CAM
software; each one gets read here, restated **in our vocabulary**, and compared
against what `cfg/lathe/polyline.cfg` already has. **Only what we do NOT have
gets written down.** Anything we already do, under whatever name, is noted as
equivalent and dropped from the list.

Working rule, from `CLAUDE.md`: reference material is read and restated, never
copied. Screenshots live in `photo/` or `ref/<feature>/`, both gitignored, and
are never committed. This file is tracked, because it is what we implement from.

Nothing is implemented off this list without greatEndian confirming the entry
first — `/ref-intake` stops for confirmation before any code.

---

## What our polyline has today

`cfg/lathe/polyline.cfg` version **1.43**, 44 parameters. The baseline any
screenshot is compared against.

| group | parameters |
|---|---|
| **Roughing** | Strategy, Operation, Respect tool back angle, Pre-finish pass, Space passes from, Skip short roughing passes, Skip thin roughing passes, Pause after roughing, Direction, Re-entrant profile, Pre-finish offset (per side), X wall cut, Z section length, Sectioning |
| **Retract / start point** | Retract, Retract distance, Return to start point, Start point X, Start point Z, Z lead-in distance |
| **Finishing** | Tool nose comp, Offset (per side), Passes, Direction |
| **Lead in / out** | Lead-in length / angle / radius / feed, Lead-out length / angle / radius / feed |
| **X axis** | Side, Start Diameter, Final Diameter |
| **Z axis** | Start Z |
| **Geometry** | Items (Line To, Line Polar, Arc To Coords, Arc I,K) |

Depth of cut, feeds and speeds come from the **Tool Change** feature, not from
the polyline: `_rough_cut`, `_finish_cut`, `_rough_feed`, `_finish_feed`, plus
the nose radius / orientation and the back-angle geometry.

Behaviour already implemented that a screenshot may show as a property, and
which we should NOT re-add under a new name:

- roughing levels stop on the **pre-finish contour**, not on the raw profile;
- one roughing **floor per region** of the profile, the ladder re-anchoring on
  each (`analysis/022`);
- the profile-angle **ramp** into each pass, all on one line (`analysis/023`);
- **tool nose compensation**, CNC-side or CAM-side, on the contour passes;
- the **reachable contour** — the tool's back angle shadow — and a warning
  naming any span that cannot be made.

---

## Summary — all five tabs read

`photo/roughing/{tool,geometry,radii,passes,linking}`, 54 screenshots, the
whole *Profile Roughing* operation. **27 entries**, of which the ones that
matter are far fewer than the count suggests.

**Worth building, in the order I would do them** — each is small, self-
contained, and Python-first:

| # | Gap | Why it earns its place |
|---|---|---|
| ~~15~~ | ~~Separate X and Z stock to leave~~ | **DONE 2026-08-09** — `analysis/024`, polyline.cfg 1.44 |
| ~~8~~ | ~~A back Z limit~~ | **DONE 2026-08-09** — `analysis/025`, polyline.cfg 1.45. Front limit and datums still open |
| 16 | **Pecking** | chip breaking has no expression at all; a Python subdivision of an interval we already compute |
| 9 | **Tangential extension** | run the cut past the profile along its own direction, front and back |
| 1 | **Tool clearance FRONT** | we have back only, and the reachable-contour maths already takes a front angle |
| 13 | **Cut below the inner radius** | facing and parting to centre leave a pip without it |

**Worth a decision before any work** — these change what the operation
promises, and greatEndian's answer decides whether they are work at all:

- **18 — the wall pass.** Their switch *skips* a cusp cleanup; we have no such
  move, so we are permanently skipped. Is our pre-finish contour pass the
  better trade, or do the levels want their own cleanup?
- **7 / 11 — Machine Undercuts, Groove Suppression.** Both may be our
  *Respect tool back angle* and *Re-entrant profile* worded differently. Two
  tooltips would settle both.
- **23 — rapids posted as G1.** Real safety on a control that doglegs. Does
  yours?
- **12 — rest machining.** The only large one, and the preview's `StockField`
  already simulates remaining material, so it is less far off than it looks.

**Recorded and parked** — real differences, but not things to chase now:
Tool Orientation as a B axis (2), tailstock M21/M22 (3), negative diameter (4),
six coolant modes (5), cutting-data presets (6), sharp corners (17), grooving
split radial/axial (19), canned cycle framing (20), extend to stock (21),
linearisation tolerance (22), approach/retract datums (24), Z/X clearance
naming (25), entry clearance datum (26), rapid-to-next-depth (27), and radial
limits as references (14).

**The finding that outranks the list:** it is a CAD-model package and we are
not. A large share of Geometry and Radii — Model front/back, Chuck front,
Selection, picked faces, Model OD/ID, *Outermost of…* — exists to point at
solid geometry we do not have, because **our profile is the input**. Copying
that vocabulary would leave parameters that can never resolve. What survives
the translation is pointing at **our own** objects: the Workpiece's stock
diameter and face Z. That single idea would close the useful half of gaps 8 and
14 at once.

**And what we have that they do not**, worth remembering before treating their
UI as the target: a per-region roughing floor ladder, the reachable-contour
warning that names the span it cannot make in millimetres, and nose
compensation switchable between CNC-side and CAM-side.

---

## Gaps

### From `photo/roughing/tool/` — the operation's **Tool** tab, 15 screenshots

The reference operation is *Profile Roughing*, tabs **Tool / Geometry / Radii /
Passes / Linking**. This folder is the Tool tab only; the other four are still
to come. Sections on it: Tool, Mode, Tool Settings, Feed & Speed, Insert &
Holder.

---

#### 1. Tool Clearance Front

- **What it is** — *"an angle added to the tool angle to provide clearance in
  front of the cutting edge"*; the tooltip's picture shows 30° front and 20°
  back together. *"Sets the amount of relief between the part and the front
  edge of the cutting tool. Allows for less dragging of the insert against the
  tool's leading edge."*
- **In our vocabulary** — a **front** counterpart to Tool Change's
  `param_back_clear` (Back angle clearance), in degrees.
- **Why it is a gap** — we have the back clearance only. The front flank is
  used in the reachable-contour maths (`front_deg` in `lathe_sections`) but
  there is no user angle added to it, so nothing relieves the leading edge.
- **What it would touch** — a `PARAM_FRONT_CLEAR` on `tool-change.cfg` next to
  `back_clear`; `finish_profile`/`unreachable_spans` already take a front angle,
  so the wiring exists.
- **Open question** — does greatEndian want it to change the toolpath, or only
  the reachable-contour warning? Back clearance today changes the path (198 of
  323 moves on testing_15_2).

#### 2. Tool Orientation — a programmable B axis

- **What it is** — *"Use this option if your lathe turret has a programmable B
  axis… The toolpath pass direction is automatically rotated to suit this value
  to avoid tool breakage or deflection."* Shown at 0° and 45°.
- **In our vocabulary** — nothing. **Not** our `param_torient`, which is the
  LinuxCNC insert-corner orientation 1–9 and a different quantity entirely;
  the names collide and must not be merged.
- **Why it is a gap** — we assume the tool is fixed in the turret. A B-axis
  angle rotates the whole pass direction.
- **What it would touch** — everything downstream of the pass direction, plus a
  post that can emit B. Large.
- **Open question** — does greatEndian's machine have a B axis at all? If not
  this is documentation, not work.

#### 3. Use Tailstock

- **What it is** — support for the longitudinal axis on long slender work.
  *"You would typically see M21 (tailstock forward) at the beginning of the
  operation and M22 (tailstock backward) at the end."*
- **In our vocabulary** — a bool on the operation emitting M21 before and M22
  after.
- **Why it is a gap** — we emit neither, and nothing knows a tailstock exists.
- **What it would touch** — a bool in `polyline.cfg` (or Tool Change, if it is
  a per-setup rather than per-operation thing) and two lines of the `[CALL]`
  template. Small.
- **Open question** — does the machine have a programmable tailstock, and are
  M21/M22 its codes? They are not LinuxCNC standard; a remap may be needed.

#### 4. Turn In Negative Diameter

- **What it is** — *"Specifies that the tool will machine in the negative
  diameter."*
- **In our vocabulary** — nothing. Our X is a diameter and assumed positive.
- **Why it is a gap** — machining across the centreline into −X, which some
  turret/tool-hand combinations need.
- **What it would touch** — the sign conventions throughout the lathe polyline
  maths. Not small, and it interacts with the nose-orientation table.
- **Open question** — is this ever wanted here? Likely not for greatEndian's
  machine; parked unless asked.

#### 5. Coolant modes beyond Flood and Mist

- **What it is** — Disabled, Flood, Mist, Through tool, Air, Air through tool,
  Suction, Flood and mist, Flood and through tool. Nine.
- **In our vocabulary** — Tool Change's `param_cooling`, which offers
  **None / Flood / Mist** and nothing else.
- **Why it is a gap** — six of the nine cannot be expressed. Through-tool in
  particular is ordinary on a lathe with driven tools.
- **What it would touch** — the `cooling` combo, and whatever M-codes the
  machine uses for the extra modes (M7/M8/M9 cover three of them; the rest are
  machine-specific).
- **Open question** — which of the six does greatEndian's machine actually
  support? Adding options that post to nothing is worse than not having them.

#### 6. Cutting-data Presets

- **What it is** — *"Specifies tool's cutting data to use for a material,
  machine, or operation, like roughing. Using presets enables you to quickly
  populate Spindle speed and Feedrates with custom data."* Named, copyable
  between tools of the same type, and may contain expressions.
- **In our vocabulary** — nothing. Speeds and feeds are typed into each Tool
  Change.
- **Why it is a gap** — no library, no reuse, no per-material recall.
- **What it would touch** — a preferences-level store and a picker on Tool
  Change. Self-contained, and it changes no motion.
- **Open question** — worth it for a single-machine shop? It is convenience,
  not capability.

#### 7. Machine Undercuts — NEEDS A CALL, not obviously a gap

- **What it is** — a checkbox under *Insert & Holder*, unchecked in the shot.
  No tooltip captured.
- **In our vocabulary** — the inverse of `param_flank`, *Respect tool back
  angle*: with the back angle respected we deliberately do **not** cut what the
  insert cannot reach, and we warn about the span.
- **Why it may not be a gap** — this may be the same switch worded the other
  way round. If so we have it, and better: ours also names the unreachable span
  (10.0899 mm over Z−70.22…−35.77 on testing_15_2).
- **Open question** — a screenshot of that tooltip would settle it.

---

### From `photo/roughing/geometry/` — the **Geometry** tab, 8 screenshots

Sections: Model, **Front**, **Back**, Groove Suppression, Rest Machining.
Front and Back each carry a Mode, an Offset and a Tangential Extension; Back
also carries a Reference and a Tool Limit.

#### 8. Front and Back Z limits, with a reference datum — **BACK LIMIT DONE**, 2026-08-09, `analysis/025`

- **What it is** — *Front Mode* / *Back Mode* choose what the operation's Z
  limit is measured from: **Stock front, Stock back, Chuck front, Selection,
  Model front, Model back, Origin (absolute)** — each with its own **Offset**
  (−0.100 mm on the front here). Back Mode adds a **Back Reference**, a picked
  face.
- **In our vocabulary** — we have `param_b_z`, *Start Z*, a typed number, and
  nothing at the back at all: the profile's Z extent is wherever the Items
  finish.
- **Why it is a gap** — two things at once. There is no **back limit**, so an
  operation cannot be trimmed to stop short of where the polyline ends; and the
  front limit is an absolute number rather than a reference that follows the
  stock or the chuck when either changes.
- **What it would touch** — a back-Z parameter is small and self-contained. The
  reference datums are not: they assume a model and a stock the operation can
  point at, which is the CAD paradigm below.
- **Open question** — is the back limit wanted on its own? That is the useful
  half and it does not need any of the datum machinery.
- **BUILT, the back half.** `param_e_z_on` / `param_e_z`, polyline.cfg 1.45.
  The trim happens once in `resolve_points`, so every contour, window, floor
  and table follows it. Switch off, 341 moves / 29 levels / Z−70.400; on at
  −40, 265 / 20 / Z−40.604. The FRONT limit and the datum modes are still open
  — `param_b_z` is the profile's origin, not a trim, so it cannot double as
  one.

#### 9. Tangential Extension

- **What it is** — *"Creates a tangential extension of the geometry from the
  Front limit"*, shown at 0.0 and 0.300: the profile's end segment is continued
  along its own tangent past the limit. Front and Back each have one.
- **In our vocabulary** — nothing the operator can set. We do extend the first
  segment to Begin Z internally (`analysis/022`), but that is fixed behaviour,
  not a length anyone can ask for.
- **Why it is a gap** — no way to run the cut past the drawn profile along its
  own direction, which is how you clear a face or leave a lead-out on the stock.
- **What it would touch** — `lathe_sections`, where the contour is built; the
  extension is a Python question and belongs there. Two parameters, front and
  back.
- **Open question** — does greatEndian want it measured along the tangent, as
  here, or along Z?

#### 10. Tool Limit — Cutting edge vs Contact point

- **What it is** — *"Limits the X axis position in reference to Radii Limits or
  the Contact point of the tool nose radius. **Cutting Edge** sets a hard limit
  for the X position of the cut… **Contact Point** positions the nose radius of
  the tool to the tangent point of the cut. A larger nose radius will create a
  greater overlap."* It appears twice — on the Back geometry and on the Inner
  Radius.
- **In our vocabulary** — nothing. We compensate the nose, but every limit we
  have is on the control point.
- **Why it is a gap** — with a limit set to a diameter, we cannot say whether
  that diameter is where the *edge* stops or where the nose *touches*. The two
  differ by the nose radius, which is exactly the quantity this whole session
  has been chasing.
- **What it would touch** — wherever a radial limit is applied, plus the nose
  radius already in hand from `tip_comp_inputs`.
- **Open question** — worth it only where a limit exists; on our polyline that
  is Start / Final Diameter.

#### 11. Groove Suppression

- **What it is** — a checkbox, unchecked, no tooltip captured.
- **In our vocabulary** — nothing. Our `param_multi_x`, *Re-entrant profile*,
  is the opposite instinct: it roughs **all** disjoint intervals.
- **Why it is a gap** — no way to tell roughing to leave narrow grooves alone
  for a grooving tool to do properly.
- **Open question** — the tooltip. Whether it suppresses by width, by depth, or
  by aspect ratio changes what would be built.

#### 12. Rest Machining

- **What it is** — a checkbox, unchecked, no tooltip captured. Standard meaning:
  machine only what earlier operations left behind.
- **In our vocabulary** — nothing. Every operation starts from the stock.
- **Why it is a gap** — a second, smaller tool cannot be told to clean up only
  what the first could not reach — which is precisely the 10.0899 mm behind the
  boss that our own unreachable-contour warning names.
- **What it would touch** — a model of remaining material carried between
  operations. Large. The preview's `StockField` already simulates exactly that,
  so the machinery is not absent, only unconnected.
- **Open question** — greatEndian's call, and probably far down the list.

---

### From `photo/roughing/radii/` — the **Radii** tab, 9 screenshots

Three radial bands, each *From* a datum plus an *Offset*: **Clearance**
(orange), **Outer Radius** (light blue), **Inner Radius** (dark blue). The
tooltip's example: Outer = Stock OD, Clearance = Outer + 5 mm.

The *From* list is long and the same for all three — Retract, Stock OD, Model
OD, Outer radius, Inner radius, Model ID, Stock ID, Selection, Radius,
Diameter, **Outermost of…**, **Innermost of…** — with the stated rule
**Clearance ≥ Retract ≥ Outer ≥ Inner** for a valid toolpath.

#### 13. Distance to Cut Below Inner Radius

- **What it is** — *"an adjustment to a Face or Part cut to position the tool
  nose past the Inner Radius position. Use this to cut past the Centreline of
  the part."* Pictured as *Cut up to the CentreLine* against *Cut past the
  CentreLine*.
- **In our vocabulary** — nothing. Our Final Diameter is where cutting stops.
- **Why it is a gap** — parting and facing to centre need the nose to travel
  past the axis, or a pip is left. Same family as *Turn In Negative Diameter*
  (gap 4).
- **What it would touch** — the polyline's X limit handling; small on its own.
- **Open question** — is this wanted for facing, for parting, or both? We have
  no parting operation yet.

#### 14. Radial limits as REFERENCES rather than numbers

- **What it is** — Outer and Inner are not typed diameters; they point at the
  stock OD, the model OD, a picked face, or *Outermost of* two of those, and
  follow when those change.
- **In our vocabulary** — `param_b_x` *Start Diameter* and `param_e_x` *Final
  Diameter*, both typed numbers.
- **Why it may not be a gap** — the values exist and produce the same toolpath.
  What is missing is associativity, which presumes a CAD model and a stock body
  to reference. See the paradigm note below.
- **Open question** — greatEndian has a Workpiece feature carrying stock
  diameter. Referencing *that* — "Start Diameter = stock OD" — is a small,
  real improvement that needs none of the CAD machinery.

---

### From `photo/roughing/passes/` — the **Passes** tab, 14 screenshots

Sections: **Cycle and Direction**, **Passes**, **Stock to Leave**. The tab with
the heaviest overlap so far — much of it we already have — but four of the
gaps below are ordinary turning practice we simply cannot express.

#### 15. Separate X and Z stock to leave — **DONE**, 2026-08-09, `analysis/024`

- **What it is** — **X Stock to Leave** *"the amount of material to leave in
  the radial direction"* and **Z Stock to Leave** *"in the axial direction…
  used for leaving stock on the vertical faces being turned"*, 0.100 each here.
  *"For surfaces that are not exactly horizontal, the program interpolates
  between the Axial Stock value (wall) and the Radial Stock values."* Changing
  X sets Z to match; either may then be typed differently. **Negative is
  allowed** — cutting past the model — *"maximum negative stock to leave must
  be less than the tool nose radius… you cannot compensate past the theoretical
  tip of the tool."*
- **In our vocabulary** — `param_f_off`, *Offset (per side)*, a **single**
  value applied as a true normal offset to the whole contour, and its minimum
  is **0.0**.
- **Why it is a gap** — we cannot leave more on the walls than on the
  diameters, which is ordinary when a face is finished by a different tool or
  a different pass. Nor can we go negative.
- **What it would touch** — `offset_contour` in `lathe_sections`, which offsets
  perpendicular by one distance; an X/Z pair means interpolating by segment
  angle exactly as the tooltip describes. Python, and testable.
- **Open question** — the negative case needs the nose-radius bound they state,
  and we have that number already in `tip_comp_inputs`.
- **BUILT.** `param_f_off_sep` (*Separate Z offset*, default off) and
  `param_f_off_z`, polyline.cfg 1.44. The rule is `stock_at_normal`:
  `nz²·off_z + nr²·off_x`, which is off_x on a diameter, off_z on a wall and
  their mean at 45°. Measured 0.5000 / 0.1000 / 0.3000 on those three surfaces.
  Roughing, the pre-finish pass and the final finish pass all honour both;
  **intermediate** finish passes under Native comp cannot, because `G41.1 D` is
  a single number — that is in the tooltip. Negative stock still not exposed.

#### 16. Use Pecking

- **What it is** — *"Pecking creates multiple steps across the length of the
  cutting direction. Between Pecking Depths the tool retracts along its path by
  the specified Pecking retract distance. Use this if your material creates
  long strings of chips."* Illustrated at 18 mm peck with 3 mm retract.
- **In our vocabulary** — nothing. A roughing level is one continuous cut from
  its start to its stop.
- **Why it is a gap** — chip breaking on long cuts in gummy material has no
  expression at all.
- **What it would touch** — `lathe_level_pass`, which walks one interval; the
  peck points are a Python question — a length and a retract, subdivided from
  the interval Python already knows. Two parameters.
- **Open question** — retract *along the path*, as here, or radial?

#### 17. Make Sharp Corners

- **What it is** — *"Forces a sharp toolpath intersection on all external
  corners. When unchecked the toolpath will roll around all external sharp
  corners, creating a toolpath that flows to avoid sudden changes in
  direction."* With the note: *"Only the toolpath is affected. The part will
  always have a sharp intersection. Using a tool with a smaller nose radius can
  gouge the part."*
- **In our vocabulary** — nothing. Our contour passes roll every external
  corner, because that is what dynamic cutter compensation does.
- **Why it is a gap** — no way to ask for the sharp intersection where the
  machine prefers it.
- **Open question** — under LinuxCNC comp the roll is the interpreter's, not
  ours. Forcing sharp may mean leaving comp and computing the corner in Python
  — which is the direction we are going anyway.

#### 18. Wall pass / cusp cleanup — we do not have the thing being skipped

- **What it is** — *Skip Wall Pass*, *"skips the cusp cleanup move after every
  cutting move… use to reduce the number of tool movements to save time, then
  follow up with a finishing toolpath."* The pictures show the difference: with
  it, each level climbs the wall to clear the cusp it left.
- **In our vocabulary** — our levels lead out and retract; **there is no cusp
  cleanup move at all**. So we are permanently in the "skipped" state.
- **Why it is a gap** — the inverse of how it reads: the missing feature is the
  **wall pass itself**, not the switch. On a steep wall each roughing level
  leaves a cusp that only the pre-finish pass removes.
- **Open question** — worth it? Our pre-finish contour pass already cleans the
  walls in one go, which may be the better trade. Needs greatEndian's view.

#### 19. Grooving — radial and axial, separately

- **What it is** — *"allow or restrict undercut toolpath motion. Can be used to
  keep the tool from dipping into channels along the diameter, face or end."*
  Four states: **Don't allow / Allow Radial / Allow Axial / Allow Radial and
  Axial**.
- **In our vocabulary** — `param_multi_x`, *Re-entrant profile*, is two states:
  stop at the first crossing, or rough all disjoint intervals. Plus
  `param_flank`, which keeps the tool out of what its back angle cannot reach.
- **Why it is a partial gap** — we can say "all or nothing"; we cannot say
  "radial channels yes, axial channels no". The distinction is about which way
  the channel faces, and the tool's ability to enter it differs by direction.
- **Open question** — does the reachable-contour work already cover the real
  need here? It refuses what the insert cannot enter, which is the physical
  version of the same question.

#### 20. Use Canned Cycle

- **What it is** — a checkbox under Cycle and Direction, unchecked, no tooltip
  captured. Standard meaning: post the machine's own roughing cycle rather than
  every move long-hand.
- **In our vocabulary** — `param_mode`, *Strategy*, already offers **G71
  Contour Roughing** and **G72 Face Roughing** for LinuxCNC 2.9+, beside our own
  Profile Shift. So the capability exists — but it is a *strategy*, chosen
  instead of ours, not a posting option applied to it.
- **Why it may not be a gap** — probably ours is equivalent. Recorded so the
  difference in framing is not mistaken for a missing feature.

#### 21. Extend to Stock

- **What it is** — *"applies the finish allowance (defined by Stock to Leave) to
  the stock in addition to the model. The toolpath does not dip as it comes off
  the shoulder; instead it continues in a straight line, leaving a finish
  allowance on the stock as well."*
- **In our vocabulary** — nothing named, though it is close to work already
  done: our stop contour is extended to the pre-finish contour, and the first
  segment is extended to Begin Z (`analysis/019`, `022`).
- **Why it is a gap** — those extensions are internal rules, not a switch, and
  they do not cover the shoulder-to-stock case this describes.
- **Open question** — is the dip it prevents something greatEndian has seen? If
  not, this is a solution to a problem we may not have.

#### 22. Linearisation tolerance

- **What it is** — *Tolerance*, 0.010 mm, *"used when linearizing geometry such
  as splines and ellipses… taken as the maximum chord distance"*, with a long
  note on data starving from too-tight values.
- **In our vocabulary** — a hard-coded **0.005** handed to `poly_mesh_lathe` in
  `poly_lathe_mill.ngc`. Nobody can change it.
- **Why it is a small gap** — our items are lines and arcs, and arcs are emitted
  as arcs, so there is far less to linearise than in a spline-based package. But
  the number exists and is invisible.
- **What it would touch** — one parameter, threaded to the existing call.

---

---

### From `photo/roughing/linking/` — the **Linking** tab, 14 screenshots

Sections: **Linking**, **Approach & Retract**, **Clearance**, **Angled Entry**,
**Retract**. Completes the five tabs.

Much of this is our lead-in / lead-out and retract machinery under other names,
and the *Angled Entry* group is very nearly ours exactly. Four gaps.

#### 23. High Feedrate Mode — rapids posted as G1

- **What it is** — *"Specifies when rapid movements should be output as true
  rapids (G0) and when they should be output as high feedrate movements (G1)"*,
  six choices: preserve all, preserve axial **and** radial, preserve axial only,
  preserve radial only, preserve single-axis, or **always use high feed**.
  *"Usually set to avoid collisions at rapids on machines which perform
  'dogleg' movements at rapid."*
- **In our vocabulary** — nothing. Every rapid we emit is G0.
- **Why it is a gap** — a G0 with both axes moving is not a straight line on
  many controls; it doglegs. Our retreats and returns move both axes, and
  `test_rough_ends` proves they clear the **stock**, not that they clear it
  along the path the machine will actually take.
- **What it would touch** — the rapid emission in `lathe_level_pass` and
  `poly_lathe_mill`, plus a feed to run them at. Small, and it is real safety.
- **Open question** — does greatEndian's control dogleg? On LinuxCNC a G0 is
  coordinated, so this may not bite here. Worth confirming before building.

#### 24. Approach / Retract reference, in Z and in X

- **What it is** — **Approach Z** and **Retract Z**: *Safe Z* (from the Setup)
  or *First / Last toolpath point*. **Approach X** and **Retract X**:
  *Clearance* or *First / Last toolpath point* — *"can improve toolpath
  efficiency as the tool does not travel a further distance to start at the
  clearance height"*. Plus **Override Setup Safe Z**, redefining the safe-Z
  datum as WCS or Stock-back plus an offset.
- **In our vocabulary** — `param_ret_mode` (*Full — above stock* / minimal) and
  `param_ret_dist`, plus Tool Change's `rx` / `rix` / `rz`, and the polyline's
  own `park_on` / `park_x` / `park_z`.
- **Why it is a partial gap** — we have the retract heights, but not the choice
  of **where the first approach and the last retract are measured from**. Ours
  always goes to the clearance plane; theirs can start at the first cut's own X
  or Z and save the air move.
- **Open question** — this is cycle-time trimming, not capability. Low value
  unless the air moves are actually costing something.

#### 25. Z Clearance and X Clearance as separate distances

- **What it is** — **Z Clearance** *"in reference to the start of the cut"* and
  **X Clearance** *"in reference to the farthest cut on the profile"*, 0.600
  each here. Two independent stand-offs.
- **In our vocabulary** — one `param_ret_dist` (1.016) plus `param_zc_ovr`,
  *Z lead-in distance*. So we have a Z one and a radial one, but they are not
  the same pair: ours are a retract distance and a lead-in distance rather than
  two clearances measured from the cut.
- **Why it is a small gap** — mostly naming. Worth checking against ours before
  adding anything, or we end up with four parameters doing three jobs.

#### 26. Angled Entry — we have it, except the feedrate

- **What it is** — a group with its own on/off: **Entry Angle** 45.0 deg
  *"with respect to the positive Z axis, of the entry move to the start of the
  cutting pass"*, **Entry Clearance** 2.00 mm *"the incremental distance from
  the material at which the entry move begins"*, and **Entry Feedrate**
  120.00 mm/min.
- **In our vocabulary** — `param_li_ang` (Lead-in angle, default 45),
  `param_li_len` (Lead-in length), `param_li_feed` (Lead-in feed), and the
  group toggles off by setting the length to 0. **We have all three.**
- **Why it is recorded at all** — their *Entry Clearance* is measured **from the
  material**, ours is a length along the lead. Same intent, different datum;
  worth knowing if the two are ever compared on the same part.

#### 27. Rapid to Next Cutting Depth

- **What it is** — *"Rapid linking move to the next depth of cut"*, a checkbox,
  ticked.
- **In our vocabulary** — our level-to-level move is always a rapid, with no
  option to feed it.
- **Why it is a tiny gap** — the ability to *feed* between depths, for a
  machine or material where a rapid plunge to the next level is unwelcome.
  Related to 23.

---

---

## Observations that are not gaps

- **Feed & Speed lives on the OPERATION there, on Tool Change here.** Every
  value exists in ours — CSS on/off (`mode`), surface speed, max spindle,
  feed/rev vs feed/min (`feed_mode`), cutting feedrate. The difference is that
  we cannot vary them per operation without a second Tool Change. Placement,
  not capability — but worth knowing before copying their layout.

- **It is a CAD-model CAM package and we are not.** Half of the Geometry and
  Radii tabs — Model front/back, Chuck front, Selection, a picked Face, Model
  OD/ID, *Outermost of…* — exist to point at solid geometry that we do not
  have. Our profile IS the input, drawn as Items. Those entries are not gaps to
  close but a difference in kind, and copying their vocabulary would leave
  parameters that can never resolve to anything.
  **What survives the translation** is the part that references OUR own
  objects: the Workpiece's stock diameter and face Z. Those we do have, and
  pointing a limit at them costs nothing.

- **Our Retract already carries the Clearance idea.** `param_ret_mode`
  (*Full — above stock* / minimal) with `param_ret_dist`, plus Tool Change's
  `rx` / `rix` / `rz`. What the reference adds is choosing the datum it is
  measured from, which is the same associativity question as gap 14.

---

## Read and dismissed

Shown in these screenshots and already present, under our own names:

| Reference | Ours |
|---|---|
| Tool (library pick) | Tool Change → `dnum`, Tool number |
| Turning Mode: Outside / Inside profiling | Polyline → `side`, Side |
| Spindle Rotation forward / reverse | Tool Change → `spindle_dir` (No / CW / CCW) |
| Tool Clearance **Back** | Tool Change → `back_clear`, Back angle clearance |
| Use Constant Surface Speed | Tool Change → `mode` (Constant surface speed / RPM) |
| Surface Speed | Tool Change → `surf_speed` |
| Maximum Spindle Speed | Tool Change → `speed`, Max spindle |
| Use Feed per Revolution | Tool Change → `feed_mode` (G94 / G95) |
| Cutting Feedrate | Tool Change → `r_feed` roughing, `f_feed` finishing |
| Coolant: Disabled / Flood / Mist | Tool Change → `cooling` (None / Flood / Mist) |

From the **Passes** tab:

| Reference | Ours |
|---|---|
| Cycle: Horizontal / Vertical / Back Cutting | Polyline → `mode`, Strategy — Profile Shift, G71 Contour, G72 Face |
| Direction: Front to Back / Back to Front / Both Ways | Polyline → `dir`, Direction — the same three |
| Maximum Depth of Cut | Tool Change → `c_dpt`, Cut depth |
| Even Depths of Cut | Polyline → `pass_from`, *Space passes from = Stock* spaces evenly; *Final contour* takes whole depths |
| Machine Multiple Regions | Polyline → `multi_x`, *rough all disjoint intervals* — along Z. **Theirs also spans OD and ID in one operation, ours does not**; recorded as a difference, not yet a gap |
| No Dragging | our roughing retreat already clears the stock and no rapid removes material (`test_rough_ends`). Probably the same thing; no tooltip captured to confirm |

From the **Linking** tab:

| Reference | Ours |
|---|---|
| Angled Entry — Entry Angle | Polyline → `li_ang`, Lead-in angle (45 default) |
| Angled Entry — Entry Feedrate | Polyline → `li_feed`, Lead-in feed |
| Angled Entry — on/off | Polyline → `li_len` = 0 turns it off |
| Retract Distance, *"the lead out move after each roughing cut"* | Polyline → `lo_len`, Lead-out length — **exactly ours**, and the same pictures: a longer value lifts the tool further off each finished level |
| Safe Z / clearance plane | Tool Change → `rz` retract Z, `rx` / `rix` retract X; polyline `ret_mode`, `ret_dist` |
