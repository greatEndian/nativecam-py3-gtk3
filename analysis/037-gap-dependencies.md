# 037 — What each remaining gap depends on

2026-08-13, branch `liveTooling`, from `bd50c55`. greatEndian: *"focus of each
point dependency .. therefore you have to know what depends at what"*.

Written **before** any code, which is the point of it.

## The two choke points, and why they decide everything

**`resolve_points`** — the profile every builder reads. The Z limits, the
tangential extension (`bd50c55`) and the merge radii all live in it, and the
contours, section windows, floor ladder, entry/stop/CAM tables and the
resume envelope are all derived from what it returns.

**`finish_profile`** — the *reachable* contour: `resolve_points` with the
back-angle flank shadow applied. `build_entry_contour_gcode`,
`build_floor_contour_gcode`, `build_stop_contour_gcode`,
`build_prefinish_contour_gcode`, `build_finish_contour_gcode`,
`build_cam_comp_gcode` and `unreachable_spans` all call it.

Anything that changes either changes all of that at once. That is not a
theoretical worry: the roughing floor being built from `resolve_points` (raw)
instead of `finish_profile` (reachable) is what produced five stacked faults and
took eleven rounds to find — `analysis/032`, `036`.

**So the ordering rule is: leaf operations first, choke points last and only
with a decision behind them.**

## Gap 13 — Cut below the inner radius

| | |
|---|---|
| **Changes** | `cfg/lathe/facing.cfg` (one parameter), `lib/lathe/facing.ngc` (the end of the cut), `ncam.py` `create_defaults` (one global) |
| **Consumers** | `o<facing>` has exactly **one** caller, `facing.cfg:280`. Nothing else reads its `end_x`; no table, no window, no shared code path |
| **Parameter window** | **none needed** — a scalar global, not a table |
| **Choke points touched** | **none.** It never goes near `resolve_points` or `finish_profile` |

**Verification**: the face's last cut must reach past centre by the distance
asked for, and the untouched case is that a distance of 0 leaves the program
byte-identical.

**Which gaps it changes**: none. It makes nothing else easier or harder, which
is exactly why it goes first.

**The spec's open question — "facing, parting, or both?" — answers itself.**
There is no parting operation in this codebase (`ls cfg/lathe/` has no
`parting.cfg`; `get_tool_width` exists for a groove/part insert and its own
docstring says callers must *refuse to generate a groove* rather than assume).
So "both" is not available and the answer is facing, with parting inheriting the
same parameter when it is built. No guess is required.

**Why the polyline is the wrong home for it.** The polyline's `param_e_x` is the
final diameter of a *turning* region, and `#3142 = param_e_x / _diameter_mode`
reaches `poly_lathe_mill` as `final_radius`. Cutting a turning pass past the
spindle axis is not a thing; the pip the reference is describing is left by a
*face*. Putting it on the polyline would add a parameter that can never
sensibly be used.

## Gap 1 — Tool clearance FRONT: **BLOCKED, and the spec's premise is false**

`POLYLINE-GAPS.md` says *"the front flank is used in the reachable-contour maths
(`front_deg` in `lathe_sections`)"* and *"`finish_profile`/`unreachable_spans`
already take a front angle, so the wiring exists"*.

**Measured: it does not.** There is no `front_deg` anywhere in
`lathe_sections.py`, and no front angle of any kind:

- `flank_slope(back_deg, clearance)` → `eff = 90 - back_deg - clearance`
- `flank_envelope(points, back_deg, ...)`, `finish_profile(..., back_deg, ...)`,
  `unreachable_spans(..., back_deg, ...)` — **back only**

The tool table *does* carry the front angle: `tool[6]` (I), read by
`TOOL_TABLE.get_tool_front_angle`. Its **only** consumers are `ncam.py:908`
`tool_wedge` and `ncam_app_actions.py:230` — both of which **draw the tool**.
Nothing geometric uses it.

So gap 1 is not "a parameter next to `back_clear`". It is:

1. **a new geometric constraint** — a front-flank shadow in `flank_envelope`,
   which today models one flank only; then
2. a clearance angle on it, by analogy with `back_clear`.

Step 1 lands squarely on `finish_profile`, the choke point above, and therefore
on every contour and table in the operation.

**And its own open question is unanswered and decides the size of the work**:
*"does greatEndian want it to change the toolpath, or only the reachable-contour
warning? Back clearance today changes the path (198 of 323 moves on
testing_15_2)."*

- **Warning only** → `unreachable_spans` alone, nothing else moves. Small, safe.
- **Change the path** → `finish_profile` moves, and with it the entry, floor,
  stop, pre-finish, finish and CAM tables, the ladder and the windows. That is
  the five-fault blast radius, deliberately re-entered.

Those are not variations of one job; they are different jobs with different
risk. Guessing which one would be exactly the mistake this project has paid for
repeatedly, so **gap 1 is not built here** and the question goes back to
greatEndian with the numbers above.

**What it would make easier if built**: a front flank in `flank_envelope` is
also what gaps 7 and 11 (Machine Undercuts / Groove Suppression) would need,
and both of those are already on the "needs a call" list. So gap 1 is coupled to
two gaps that are themselves awaiting a decision — another reason it is not a
first move.

## Build order

1. **Gap 13** — leaf, one caller, no window, no choke point, open question
   answered by the absence of a parting operation.
2. **Gap 1** — blocked pending greatEndian's answer, and larger than the spec
   claims.

## Correction to POLYLINE-GAPS.md

Gap 1's "what it would touch" line is wrong and has been corrected there: the
front-angle wiring it relies on does not exist.
