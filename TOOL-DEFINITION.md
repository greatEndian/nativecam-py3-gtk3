# The lathe tool, as NativeCAM defines it

What the drawn tool is, line by line, where every number comes from, what the
collision check does and does not treat as tool, and what the machine does with
the nose radius. Valid as of `c21dccd`, confirmed in AXIS by greatEndian
2026-08-02.

This is the **current** definition. It is expected to be replaced wholesale
when the CAM-template rework lands — see the open point of that name in
`openPoints.md`. Until then this file is the reference.

Everything here lives in `ncam_preview.py`: `shank_dims`, `tool_silhouette`,
`tool_shank`, `tool_holder`, `draw_tool`, `collisions`. It is plain Python with
no GTK, and `test_tool_silhouette.py` measures every property below.

---

## 1. Where the numbers come from

| quantity | source | notes |
|---|---|---|
| nose radius R | tool table `#5410` (D), else the `#<_tip_nose_dia>` preference | the same value the G-code compensates with |
| orientation | tool table `#5413` (Q), else `#<_tip_orient>` | 1…9, LinuxCNC's `lathe_shapes` numbering |
| front angle | tool table **I** | measured **off the perpendicular** — the edge sits at 90 − I from Z |
| back angle | tool table **J** | same convention |
| centre-line angle | (I + J) / 2 | preferred over the orientation number when present; they agree numerically |
| **shank height h** | **Tool Change → Holder shank height** | the one new number; everything else about the holder derives from it |
| flank length | Tool Change → Tool flank length | **not** used by the drawn tool any more; it is the reachable-contour shadow's number |

The tool table has no column for a holder, which is why the shank height sits
on the Tool Change and travels the same route the tool number does —
`Tools.save_shank_h` from `ncam_project_io.to_gcode`.

## 2. Derived from the shank height

`shank_dims(h) -> (l1, insert_edge)`, from the ISO holder relationships in
`ref/tool-shank/NOTES.md`:

| h | overall length l1 | insert edge |
|---|---|---|
| 12 mm | 110 mm | 9 mm |
| 16 mm | 125 mm | 9 mm |
| 20 mm | 150 mm | 12 mm |
| 25 mm | 160 mm | 12 mm |
| 32 mm | 180 mm | 16 mm |

- **Width b = h.** External turning holders are square. b never appears in the
  ZX view — it is the Y dimension — but it matters for turn-mill clearance.
- **l1 is interpolated** between bracketing entries and extrapolated
  proportionally outside them, so 25.4 mm (1 in) gives 161.1 mm. Nearest-match
  with a scale factor is **not monotonic**: it made a 22 mm shank come out
  165 mm against a 25 mm shank's 160 mm.
- **The insert edge is not interpolated.** It takes the nearest entry's whole
  value: inserts come in standard sizes and 12.2 mm is not one of them.

## 3. The outline

Worked through on the reference tool used by the tests — R 0.8, orientation 2,
I 15 / J 75, 25 mm shank, tip at Z −10.000 r 25.000. All figures in millimetres
of **radius**, not diameter.

    nose centre        Z  -9.200   r 25.800
    front tangent t_f  Z  -9.973   r 26.007
    back tangent  t_b  Z  -8.993   r 25.027
    short edge foot    Z  -8.400   r 31.877
    holder face        Z  -8.400            (near side)
    shank reference    Z   2.598            (far side)
    bottom             r 62.598
    insert corner e_f  Z  -6.867   r 37.598
    insert corner e_b  Z   2.598   r 28.133

Going round, starting at the front tangent:

1. **The nose arc**, radius R about the centre, from the front tangent round
   the cutting side to the back tangent. Sampled at ≤ 0.15 rad.
2. **The short front cutting edge** — from the front tangent at 90 − I from Z,
   running only as far as the holder face: **6.077 mm** here. This is the
   feature the whole shape hangs on; without the face to stop it, the edge
   either runs to the bottom of the tool (a near side slanted by the front
   angle) or vanishes entirely. Both were drawn and both were rejected.
3. **The holder face** — a line of constant Z, tangent to the nose circle on
   the side **opposite** the cut, i.e. the tip mirrored through the nose
   centre. Z = cz + R. It runs from the foot of the short edge down to the
   bottom.
4. **The bottom** — a line of constant radius, one shank height beyond the
   insert's own far corner: r = e_f + h = 37.598 + 25 = 62.598.
5. **The shank reference** — a line of constant Z at the insert's far corner,
   Z = e_b. Parallel to the holder face and 11.0 mm from it. This is the front
   face of the block.
6. **The back cutting edge** — from the insert's far corner back to the back
   tangent, one whole insert edge length (12 mm) at 90 − J from Z.

20 points, 37.598 mm radially by 12.598 mm in Z.

**The two sides are parallel lines of constant Z.** In a plan view a holder has
straight sides; a cutting edge is not a boundary below the nose.

## 4. The block, which is not drawn

`tool_shank()` returns the holder as a rectangle **h × l1** — 25 × 160 mm here,
Z 2.598…162.598, r 37.598…62.598. Its corner is on the **insert's far
corners**, not on the tool tip: an insert stands proud of its pocket. Anchored
on the tip, the block's top face lies at the cutting radius and sweeps the whole
part behind the tool — 50 collisions on a program that has none, and the *same*
50 for a 12 mm shank as for a 25 mm one.

It is not drawn at all. The outline above already ends on its near reference
lines, so the two are one solid, and the drawn tool's bottom is exactly the
block's far side.

## 5. What the collision check treats as tool

| surface | rapid | feed |
|---|---|---|
| nose arc | tested | **not** tested |
| short front cutting edge | tested | **not** tested |
| back cutting edge | tested | tested |
| holder face | tested | tested |
| bottom | tested | tested |
| shank reference | tested | tested |
| the full 160 mm block | tested | tested |

A rapid is not entitled to remove metal, so the whole outline is tested. During
a feed the cutting surfaces are excluded: the nose is the cut and the front edge
is where the chip comes off, and testing them reports every roughing pass as a
collision — 21 hits on a clean program, all of them the front edge doing its
job.

`tool_silhouette` reports how many trailing points are non-cutting in
`parts['tail']` — 5 with a shank, 3 on the old flank-length outline. Hard-coding
it silently dropped the bottom line, which is most of the tool.

The check uses the **full l1**, which the picture never shows. What fouls a
shoulder is the block running back to the turret, and a check that stopped where
the drawing stops would be a drawing rather than a check.

## 6. Fallback: no shank height

With h = 0 the older construction is used unchanged: the two edges are extended
to a line of constant Z placed one **flank length** behind the nose's leading
tangent. It is not a bound — the steep front edge climbs 3.86 mm of radius per
mm of Z, so a 6 mm flank draws 23.3 mm radially and a 25 mm flank draws 94.2 mm.
Kept only so a project that has never been given a shank draws what it drew
before.

With neither a shank nor a flank, or with no tool-table angles, `tool_silhouette`
returns **None** and `draw_tool` falls back to a schematic wedge. A silhouette
drawn at invented dimensions is a claim about the tool that nothing supports,
and this one is used to judge clearance.

## 7. Tool tip radius compensation

The nose radius is a **tool** property, so what the machine does with it belongs
in this file too. Everything below is in `lib/lathe/`, wired per operation from
the `.cfg`.

### The three modes

Each op that offers compensation carries a `PARAM_N_COMP` combo, threaded as a
**trailing** `[CALL]` argument (`#7` on the tapers and boring, `#14` on facing):

| value | mode | what happens |
|---|---|---|
| 0 | Off | no nose compensation at all; the nose-off branch reproduces the original code verbatim, so it is a provable no-op |
| 1 | Native LinuxCNC (**default**) | `G41.1`/`G42.1 D… L…` — the interpreter offsets, no geometry of ours in the path |
| 2 | In CAM | we offset the toolpath here and the machine runs uncompensated |

### The three shared subroutines

- **`tip_comp_dia.ngc CALL [extra_r] [nose_on]`** — resolves the nose diameter
  (tool table `#5410`, else `#<_tip_nose_dia>`) and orientation (`#5413`, else
  `#<_tip_orient>`) into `#<_tip_comp_d>` / `#<_tip_comp_l>`, and sets
  `#<_tip_lead_w>` = nose_dia × `#<_diameter_mode>`, the minimum radial
  clearance a comp entry or exit needs. Split out from the switch-on because the
  polyline needs the diameter *before* comp goes on.
- **`tip_comp_on.ngc CALL [side]`** — emits `G41.1`/`G42.1 D#<_tip_comp_d>
  L#<_tip_comp_l>`, guarded on D > 0.0001.
- **`tip_comp_off.ngc`** — `G40`.
- **`tip_comp_vec.ngc CALL [side] [dz] [dx] [extra]`** — the In CAM path: turns a
  travel direction into `#<_tip_off_z>` / `#<_tip_off_x>`, the vector the op adds
  to its own coordinates. Returns a zero offset when there is no radius.

### Comp side is per operation, and inverted between OD and ID

Do not copy one rule to another op.

| sub | default | flips to |
|---|---|---|
| `taper.ngc` (OD) | 42 | 41 when `begin_z LT end_z` |
| `taper_id.ngc` | 41 | 42 when `begin_z LT end_z` |
| `boring.ngc` | 41 | 42 when `begin_z LT end_z` |
| `facing.ngc` | 41 | 42 when `z_factor GT 0` |

### Which operation does what, as of `c21dccd`

| op | Off | Native | In CAM |
|---|---|---|---|
| `taper_oda`, `taper_odl` | yes | yes | yes |
| `taper_ida`, `taper_idl` | yes | yes | yes |
| `boring` | yes | yes | yes |
| `facing` | yes | yes | **refused by validation** |
| `polyline` finish pass | yes | yes | yes, needs a nose radius and orientation of 1–9 |
| `turning` | — | built in, `#<comp>` = 41/42/40 | — |
| `radius_od` | — | built in, `#<comp>` = 41/42 | — |
| grooving, drilling | not implemented |

`turning` and `radius_od` have **no comp parameter at all**. Their native comp
was proven geometrically correct rather than rewritten. Two notes on `turning`:
its straight cuts are uncompensated by design — comp resolves to `G40` when the
radius is ≤ the nose — so only its corner-radius modes (2 and 3) compensate; and
both it and `radius_od` error with a large nose, "concave corner cannot be
reached without gouging".

Facing refuses In CAM because *its approach moves place the tool past the
finished face before the cut, and the tangency proof reports a gouge there that
Native does not*. The cutting coordinates themselves match.

### The entry rule, and what it costs

**A comp entry move must be a straight feed of at least the nose radius, in
free air.** An arc cannot establish compensation, and entering comp on the
workpiece gouges it. That single rule is behind three op-specific behaviours:

- `facing.ngc` **skips its lead-in and lead-out arcs** when `n_comp > 0`, in
  favour of a straight run-in beyond the OD. This changes the produced motion,
  so it is stated in the parameter tooltip.
- On ID work (`taper_id`, `boring`) the post-comp radial retract is **widened by
  `#<_tip_lead_w>`**, or the trailing round nose swings back into the finished
  wall at the deep corner — a ~0.9 mm gouge.
- It is the likely root of the open **1.4929 mm ID lead-in/out gouge**.

Sidestepping it is the main argument for In CAM, and is why the CNC-versus-CAM
question in `openPoints.md` is still open rather than settled by preference.

### Proving a change

`prove_tip_comp.py` is the acceptance test, not code review: it runs `rs274`,
places the nose circle at each compensated control point, and asserts tangency
to the target profile with no gouge and full coverage. The correct side must
PASS **and** the wrong `--freeside` must FAIL — a single profile line is tangent
from both sides, so without the free-side flag a wrong side passes. Test the
finish pass only (`_tool_usage=2`) so uncompensated roughing does not pollute the
check.

Three traps that have each cost a session: the control-point → nose-centre offset
for a 90° insert corner is **R√2**, and it is a raw vector — normalising it to
R·unit mis-measures. `rs274` runs with `cwd` = the ini directory, so a
repo-relative `--tbl` silently aborts the run at `T<n> M6`. And the live
`lathe.var` is rewritten by the running GUI, so copy it in a retry loop and pass
it with `--var`; a truncated var also aborts at `T<n> M6`, with no error in the
output.

### Where compensation and the drawn tool disagree

Nothing above feeds the silhouette, and the silhouette feeds nothing above. The
nose radius and orientation are the only two numbers they share. In particular
the collision check knows nothing about the compensated path — it tests the
programmed one. That is a gap, not a decision.

## 8. Known wrong

A front or back angle over 90° leans the edge the other way and the shape stops
meaning what it means for a normal insert. It is bounded now, but a bounded
wrong shape is still wrong, and the 0° case that used to draw nothing now draws
a full-looking insert. Table of measured cases in `openPoints.md`.
