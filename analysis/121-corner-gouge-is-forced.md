# 121 — the corner gouge is forced by native comp, and does not reach the part

**Asked**: greatEndian, 2026-09-09 — *"go on with the corner gouge"*, the
18 um displacement `analysis/120` found where a chorded arc meets another
surface.

**Result: no code change. The gouge is structurally forced under native
compensation, the obvious fix makes things worse and was measured doing so, and
with the settings every project actually ships it never reaches the finished
surface.**

## It is native compensation only

Same project, same profile, the two compensation modes:

| mode | gouge | uncovered | verdict |
|---|---|---|---|
| 1, Native LinuxCNC | **0.0183** | 1 | FAIL |
| 2, In CAM | **0.0000** | 0 | **PASS** |

In CAM computes the offset in Python and joins the corners itself. Native comp
intersects the offsets of the chords it is handed, and the first chord out of
the corner does not point where the arc does.

## Why it cannot be chorded away

The corner at (-3, 8) has a deficit of **87.19 degrees**. Compensation needs the
segment leaving it to be at least about

    R_nose * tan(d/2) = 0.4 * tan(43.6 deg) = 0.381 mm

and the first chord is **0.3926 mm** - already within 3% of that floor. On an R4
arc, 0.3926 mm spans 5.6 degrees, so the chord's direction is 2.8 degrees off the
true tangent, and the offset intersection moves along the flat by

    R_nose * sin(theta/2) = 0.4 * sin(2.87 deg) = 0.0200

against **0.0183** measured. Every term in that chain is forced by the one
before it.

**Measured, not argued.** The obvious fix - split the first and last chord of
each arc in two, halving the angular error - was implemented and run:

- the gouge did **not** improve: 0.0183 -> 0.0187;
- and `testing_13_arc_first`, `_0` and `_1` began aborting with *"Straight feed
  in concave corner cannot be reached by the tool without gouging"*.

The shorter chord is exactly what compensation refuses. The gouge did not move
because `_min_segment` drops the extra point anyway - its `_shrink_need` at an
87 degree corner is ~0.76 mm - while the other tables received the short
segments and died on them. Reverted; the tree is back to 0.0183.

This is the same wall commit B hit from the other side: protecting every
on-profile point put finer segments at this corner and aborted the same project.

## It does not reach the finished surface

**All 40 projects that carry the parameter have `n_comp = 0`** - nose comp Off.
Not one uses Native. The mode 1 figure exists only under `prove_cam_comp`'s
override.

With `n_comp = 0` the finishing pass has `D = 2 * extra_r`, and with no finish
allowance that is zero: no compensation, no chord-direction error, no
displacement on the final surface. What the offset DOES apply to is the
pre-finish pass, which carries an allowance - there the displacement is
`extra_r * sin(theta/2)`, about 0.025 at the measured comp_r of 0.508, and it
comes out of stock that the finish pass removes anyway.

So the defect is real, bounded, and only reaches a part if someone switches the
polyline to **Native** nose comp on a profile where an arc meets a surface at a
sharp corner.

## What would actually fix it

- **Use In CAM** (`n_comp = 2`) on such profiles. Already exact, measured above,
  no work required. Worth saying in the `PARAM_N_COMP` tooltip - not done here,
  because a `.cfg` edit needs a `version` bump and that migrates every saved
  project.
- **Carry arcs as real `G2`/`G3` records** so the interpreter compensates the
  true arc and no chord direction exists to be wrong. That is the route
  `analysis/116` named and greatEndian decided against on 2026-09-09, in favour
  of chording with the `.ngc` kept a walker.

Nothing else in between: the chord length is pinned from below by the
interpreter and from above by the accuracy it costs.

## Consequence for testing_13_arcs

Its last uncovered segment and its 0.0183 gouge are the same corner, so under
native compensation it cannot reach a full PASS by this route. Under In CAM it
already passes. That is the honest end state, not a defect left unfixed.
