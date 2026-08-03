# Session 1 — 2026-08-02, branch `liveTooling`

From `f4698ed` to `7ebf785`. Pushed, tree clean. `openPoints.md` is the record
of what is left; this is the record of what happened.

## Delivered

**Item 3 confirmed** — `0e399e0`. greatEndian checked the three-piece roughing
entry in AXIS and passed it. Moved to Done with its numbers: dZ 2.2004,
dR 0.5080, length 2.2583 on a 13° ramp, 243 moves → 261.

**Tool radius compensation is a decision, not a task** — `0e399e0`. Recorded as
NEEDS A CALL. Today it is the control everywhere: `tip_comp_on.ngc`, plain
`G41/G42` on turning and radius_od, dynamic `G41.1/G42.1` on the polyline
finish. The alternative is offsetting in Python at generation time and running
`G40` throughout. The comp-entry rule — a straight feed of at least the nose
radius in free air — is why `facing.ngc` drops its lead-in arcs, why the ID ops
widen their retract, and probably why the 1.4929 mm ID gouge exists; those two
open items are now flagged as blocked on the same call.

**The tool is bounded by its shank** — `7ebf785`. Closes the longest-standing
NEEDS A CALL. greatEndian supplied the ISO holder relationships; kept in
`ref/tool-shank/NOTES.md` (gitignored). Decided: ask for the **shank height**,
derive length, width and insert size from it.

| | before | after, 25 mm shank |
|---|---|---|
| insert, 6 mm flank | 6.0 × 23.3 mm | **12.6 × 12.6 mm** |
| insert, 25 mm flank | 25.0 × 94.2 mm | **12.6 × 12.6, unchanged** |
| what bounds it | the flank | the insert edge |
| collisions on the demo program | 0 | **0 at 12, 25 and 32 mm** |

Three pieces now: nose circle, insert closed at its own edge length **along the
edge**, shank rectangle behind. A stub is drawn, one shank height deep; the
collision check uses the full 160 mm.

## Decisions taken (do not re-litigate without asking)

- Shank height is the **only** new input. `shank_dims()` derives l1 and the
  insert edge; flank length keeps its own separate meaning for the
  reachable-contour shadow.
- A **float field, not a combo** of standard sizes — a fixed list of millimetre
  values breaks on an inch machine, and ground-to-fit shanks exist.
- Draw a stub, **check the full length**.
- Compensation CNC-side vs CAM-side is **not decided**. Nothing else gets built
  on comp until it is.

## What went wrong

**Two wrong constructions, both caught by measuring rather than reading.**

- `shank_dims` first matched the nearest standard size and scaled. It is not
  monotonic: a 22 mm shank came out **165 mm long against a 25 mm shank's
  160 mm**. Interpolating between the bracketing entries fixes it. Caught by
  printing a sweep, not by inspecting the function.
- The shank was first anchored on the **tool tip**. That puts its top face at
  the cutting radius, so the block sweeps the whole part behind the tool:
  **50 collisions on a program with none**. The tell was that a 12 mm shank
  reported the *same 50* as a 25 mm one — a bound that does not respond to its
  own parameter is not a bound. A real insert stands proud of its pocket, so
  the corner belongs on the insert's far corners.

**And one measurement that proved nothing.** The first collision run used a
made-up stock cylinder (radius 0…42.7, taken from the tool's own retract) and
reported 15 hits before and 50 after. Both figures were meaningless. With the
real bar — 60 mm OD, Z −72…0, read out of the program's own workpiece block —
the before figure is 0. *Take the stock from the program, not from the
toolpath's extent.*

---

# Session 1, continued — 2026-08-02 / 08-03

The session ran well past the range above. From `7ebf785` to `78e5214`.
Everything pushed, tree clean apart from an untracked AXIS
`autosave.halscope`.

## Delivered

**Tool shape, settled.** `7ebf785` the tool is bounded by its SHANK, not the
flank — insert 6 mm flank 23.3 mm radially → 12.6 × 12.6 at a 25 mm shank.
`5b14d7f` both sides became constant-Z lines. `c21dccd` the short front cutting
edge came back, 6.077 mm at 75°, ended by the tangent on the far side of the
nose. `a7047ed` `TOOL-DEFINITION.md` — the whole tool written down.

**Compensation, steps 1–5 of the plan.**

| project | Off | Native | In CAM |
|---|---|---|---|
| testing_15_2 | 0.1094 | 0.3727 → **0.0080** | 0.0080 |
| testing_11 | 0.1058 | 0.3624 → **0.0079** | 0.0079 |
| testing_13_arcs | 0.0211 → **0.0013** | 0.2268 → **0.0014** | 0.8875 → **0.0014** |

- `a0e189a` **arcs stopped 9° short** — `_min_segment` dropped the vertex where
  an arc meets the next item. R6 remainder 0.9423 against a 0.960 limit, missed
  by 18 µm, cost 0.9386 mm. It was in the NATIVE path; In CAM escaped only by
  asking for nose_r 0, so In CAM was right and the yardstick was broken.
- `c16df1f` **the entry ramp** — the pre-shift used a plain normal instead of
  the orientation-aware vector, so the first CUT became the comp entry move and
  a wall programmed at r 20.000 came out 20.4000 → 20.0074.
- `27cdcc3` **`lathe_comp.py`** — one orientation table where there were four,
  one side registry where there were five, plus **`/tnrc`**, a compressed
  knowledge pack queried offline by `kb.py`.
- `e750ee3` the polyline entry takes its table from Python; `d5899e3` both
  outside quadrants proved to 1e-12.

**The pre-finish collapse, two bugs with one symptom.** `cfb5ccd` the entry
gate; `141a98b` In CAM — `offset_contour` scaled the orientation term by
`nose_r + extra` so the allowance cancelled; `8e50db1` Native — an allowance
**cannot be carried in the D word while L is set**, so it moved into the
contour. Separation −0.4389/+0.0890 → **+0.5080/+0.5710** on all three modes.

**Preview.** `79ec962` a teal compensated-path overlay plus the mode in the
legend, agreeing with the interpreter to **0.0001 mm over 34 contour points**.
`152baec` a double-removal of the playback timer, and `_trace()`.

**`141a98b`** Utilities ▸ **Restart NativeCAM** — `os.execv` keeps the pid so
the XEmbed socket stays valid; LinuxCNC untouched.

**`78e5214`** the OD taper compensates its roughing, under the new
all-or-nothing rule.

## Decisions taken (do not re-litigate without asking)

- **Compensation is all-or-nothing** — roughing and the artificial sections
  included. `CLAUDE.md` + memory.
- **Every analysis gets `analysis/NNN-slug.md`** as it is done, failed attempts
  included. `CLAUDE.md` + memory. Five written.
- The tool is bounded by the **shank**; ask for the height, derive the rest.
- **ID work is paused**; grooving and drilling stay open until the outside
  polyline is finished.

## What went wrong, and the method it produced

- **A plausible mechanism that does not move the number is not the mechanism.**
  The first pre-finish fix was reverted, not committed: it corrected the scale
  when the *gate* was false before the scale was ever reached.
- **A latent-bug note is only worth its survey of callers.** The `extra_r`
  asymmetry was recorded as "masked because every caller passes 0". It was the
  live bug — `build_cam_comp_gcode` passes non-zero for every pass but the last.
- **A comparison between two lists of different length is not a measurement.**
  "21 of 21 moved, max 16.1588 mm" was index drift from one extra move.
- **Measure the pass you changed.** Step 4 sampled the finish phase only, where
  `shift_r = 0` hides the fault; the pre-finish bug shipped because of it.
- Two comment traps hit again: an unclosed paren and a nested paren, both of
  which halt `rs274` silently.

## Next, in order

1. **`lathe_level_pass.ngc` — the polyline's roughing has zero `tip_comp_*`
   references.** The biggest remaining gap under the all-or-nothing rule, and
   what greatEndian sees behind the boss. Note roughing is level-based with
   entry/stop tables, so the taper's approach — offset the coordinates, since
   there is no interpreter comp to double up with — is the shape to copy, but
   the level geometry is not a single wall.
2. `taper_id`, `boring`, `facing` — same shape as the taper was.
3. The **artificial sections** — design question first: a back-angle shadow is
   a surface the TOOL leaves, so "compensate it toward the part" may be the
   wrong target.
4. The **stop-button freeze** — unsolved; the next occurrence needs the last few
   `[ncam-preview]` lines.
