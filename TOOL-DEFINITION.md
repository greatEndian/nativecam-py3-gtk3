# The lathe tool, as NativeCAM defines it

What the drawn tool is, line by line, where every number comes from, and what
the collision check does and does not treat as tool. Valid as of `c21dccd`,
confirmed in AXIS by greatEndian 2026-08-02.

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

## 7. Known wrong

A front or back angle over 90° leans the edge the other way and the shape stops
meaning what it means for a normal insert. It is bounded now, but a bounded
wrong shape is still wrong, and the 0° case that used to draw nothing now draws
a full-looking insert. Table of measured cases in `openPoints.md`.
