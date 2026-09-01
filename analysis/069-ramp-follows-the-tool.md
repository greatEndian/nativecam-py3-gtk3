# 069 — the profile-angle ramp now follows the tool

**Asked**: greatEndian, 2026-09-01 — *"there is present of artificial parallel
lead in/out at last last section-from the front side ... first when we have back
to front direction .. it should not be there there should be just the generic
lead in/out .. but there is the catch, if we have tool which is mirrored in the
X axis and if we have taper character part we have to create same behaviours"*.

Clarified with numbers rather than guessed: the **back-most** section (last
counted from the front), the **tool orientation code** as the definition of
"mirrored in X", on **testing_15_9**.

## The gap

Nothing in the ramp path saw the tool at all. `entry_ramp_dirs(points, look)`
took only the profile, and the sole gate in `lathe_level_pass` — `o<pa_side>` —
tests that the approach comes from the stock side **radially**. That is a
different question: it says "come in from outside", never "come in from the end
the tool can cut".

So a ramp was armed wherever the geometry allowed one, whichever way the insert
faced. On testing_15_9 roughed back to front with T2 — `I15 J75 Q2`, the
ordinary right-hand OD insert — 18 ramps ran Z−66.5667 → −64.3663, travelling
**+Z against a tool that cuts toward −Z**, with the trailing flank leading.

## The fix

`ramp_facing(orient)` in Python: the Z direction the insert cuts in, from
`NOSE_OFFSET`, whose Z component is where the nose centre sits relative to the
programmed point — so the edge faces the other way. It reaches the runtime as
one global, `#<_pl_ramp_face>` (+1, −1, or 0), emitted by `build_rough_nose_gcode`
which already had the orientation. **No cfg change and no version bump.**

`lathe_level_pass` arms the ramp only where the pass TRAVELS that way. The
`.ngc` decides no geometry — it compares its own runtime direction against a
number Python worked out.

Orientations 6, 8 and 9 have no Z component — facing and on-the-point tools —
so they express no preference and refuse nothing. A program generated before
the global existed reads 0 and behaves exactly as it always did.

**A first attempt refused nothing**, because it tested the stored *surface*
direction (−17.3728 here) instead of the ramp's *travel*. Those are not the
same thing: the surface direction is where the profile goes; the travel depends
on `z_dir` and `_pl_cut_rev`. `z_dir` is 1 when `w_from GE w_to`, so a forward
pass runs toward DECREASING Z and travels `−z_dir`; a reversed pass travels
`+z_dir`.

## Numbers — and the control is the point

Only the tool table's `Q` differs between the halves, in a scratch copy of the
config, so nose radius, both flank angles and every parameter are identical and
the orientation is the only variable.

| tool | direction | `_pl_ramp_face` | ramps |
|---|---|---|---|
| T2 as shipped, Q2 | back → front | −1 | **0** (was 18) |
| T2 as shipped, Q2 | front → back | −1 | **15**, unchanged |
| T2 mirrored, Q1 | back → front | +1 | **18 restored** |
| T2 mirrored, Q1 | front → back | +1 | **0** |

Perfectly symmetric: the ramps follow the tool. Assertion 3 is what stops this
being "the ramps were deleted" — without it an empty ramp list passes the
reported case trivially.

Both directions keeps its forward half: 7 ramps, roughing feed 1556.5 → 1445.8.
Back to front: 1359.6 → 1319.0 mm, which is exactly 18 × 2.2583 = 40.6.

**T1 was tried first as the mirror and is a bad control** — it carries Q1 but
also nose R1.27 against R0.4 and different flank angles, so its ramps stayed at
0 for reasons that had nothing to do with orientation. One variable at a time,
or the control proves nothing.

## THE RISK THIS CARRIED, and how it was actually settled

These ramps CUT. Dropping the climbing ramp is what once left a 0.4255 mm tooth
at the top of every level on a taper — and `test_leftover`'s threshold is one
depth of cut, 0.508, so **that gate would not have caught it**.

So the leftover was compared directly, before and against: `test_leftover`'s own
calibrated model, its `worst standing` figure for all 12 reported cases across
24 projects, both sectioning states and all three directions.

**Byte-for-byte identical.** Not "under the threshold" — unchanged to four
decimal places. Removing the 18 ramps leaves no additional metal anywhere.

A homemade "material above the roughing floor" probe was written for this first
and thrown away: it reported 11822 of 12000 samples proud and the same 1.3234 mm
for both directions, because roughing legitimately leaves a staircase above the
floor. Reusing the calibrated instrument was the answer, not building a second
one.

## Gates

`cam_map`, `test_cam_map`, `test_leftover` (24/24 control, and the identical-worst
comparison above), `test_ramps` (68), `test_x_continuity`, `test_ladder`,
`test_leads`, `test_sections`, `test_skip_short`, `check_tangent`
(min |dot| 1.00000), `test_air_leads`, and the new **`test_ramp_orient`** — 15
assertions over the four tool × direction combinations.

`test_air_leads` expectations for back-to-front and both-directions were updated:
1359.6 → 1319.0 and 1556.5 → 1445.8, the ramps this change legitimately removes.
Its rapid-count bound was widened while the DEPTH bound stayed hard — the count
drifts with geometry (60 → 76 hits at the same 0.0042 mm discretisation floor),
the depth is what would reveal a real collision.

## Still unknown

- The same blind spot exists in `flank_sides`, which decides which side of a
  peak casts a shadow **from the roughing direction alone**. That is the deeper
  version of this fault: it assumes the tool's trailing flank sits on the side
  the travel implies, which is exactly what a mirrored insert breaks. Not
  touched here, and not measured.
- Whether a ramp should also be refused when the tool faces the right way but
  the surface is steeper than its front angle. That is the front-flank question,
  and `Respect tool front angle` is off by default.
