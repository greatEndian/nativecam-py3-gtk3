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

## Observations that are not gaps

- **Feed & Speed lives on the OPERATION there, on Tool Change here.** Every
  value exists in ours — CSS on/off (`mode`), surface speed, max spindle,
  feed/rev vs feed/min (`feed_mode`), cutting feedrate. The difference is that
  we cannot vary them per operation without a second Tool Change. Placement,
  not capability — but worth knowing before copying their layout.

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
