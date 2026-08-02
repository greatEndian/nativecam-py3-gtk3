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
