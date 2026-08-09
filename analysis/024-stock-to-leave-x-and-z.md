# 024 — Stock to leave, radial and axial

2026-08-09, branch `liveTooling`, from `3f0b8be`. Gap **15** of
`POLYLINE-GAPS.md`, the first one greatEndian picked.

## What was asked

The reference package holds **X Stock to Leave** and **Z Stock to Leave**
separately — radial on the diameters, axial on the walls — and *"for surfaces
that are not exactly horizontal, the program interpolates between the Axial
Stock value (wall) and the Radial Stock values."*

We held one number, `param_f_off`, applied perpendicular to the whole profile.

## The rule, and why it is not a guess

Displace the surface by the vector `(nz·off_z, nr·off_x)`. A diameter has
normal `(0, 1)` and moves `off_x` radially; a wall has normal `(1, 0)` and
moves `off_z` axially. The perpendicular distance that produces is its
projection back on the normal:

```
d = nz² · off_z + nr² · off_x
```

`off_x` on a diameter, `off_z` on a wall, their mean at 45° — the
interpolation the reference describes, derived rather than fitted. With the two
equal it returns that value for **every** normal, which is what makes the
existing path provably untouched.

`stock_at_normal` in `lathe_sections.py`, and it short-circuits on equality so
the isotropic case does not even run the arithmetic.

## Where it could be applied, and where it could not

Four places consume the allowance. Three are Python point tables and take the
pair; one is not:

| consumer | anisotropic? |
|---|---|
| `build_stop_contour_gcode` — where roughing stops | **yes** |
| `build_prefinish_contour_gcode` — the native pre-finish path | **yes** |
| `build_cam_comp_gcode` — the In-CAM pass paths | **yes** |
| `build_floor_ladder_gcode` — the roughing floors | radial only, correctly: a floor **is** a diameter |
| `lathe_poly_pass`'s `G41.1 D[2·shift_r]` | **no — D is a single number** |

So the limit is narrow and worth stating exactly: the **final** finish pass runs
at offset 0 and has no allowance to hold, and the pre-finish traces a Python
table in both modes. Only **intermediate finish passes — Passes > 1 AND Tool
nose comp = Native LinuxCNC** — fall back to the radial value. In CAM has no
such limit. That is in the parameter's own tooltip rather than left to be
discovered.

## Corners

`roll` was one number used for three things: the offset distance, the external
corner arc's radius, and the internal corner's trim reach. With a per-segment
allowance it becomes per-segment, so:

- `_join_offsets` reads `seg['roll']`, falling back to the caller's scalar;
- the trim reach uses the larger of the two meeting segments;
- **`_corner_arc` interpolates its radius across the sweep.** With different
  allowances either side, the offset leaves the vertex at one distance and
  rejoins at another — it is not an arc at all, and interpolating blends the
  two allowances through the corner instead of stepping between them. With
  equal ends it is the plain arc it always was.

## Measured

`test_stock_to_leave.py`, on a profile carrying a diameter, a wall and a 45°
chamfer, with X 0.5 and Z 0.1 — **perpendicular distance from each surface to
the contour**:

```
the diameter          0.5000
the wall              0.1000
the 45 degree chamfer 0.3000
```

And at the machine, on `testing_15_2`: the switch **off** leaves the stop table
byte-identical whatever Z holds; **on**, it moves.

## What the test got wrong twice, and why it is written the way it is

Both failures were the assertions, not the code:

1. `wall_front` picked the **front chamfer**, which sits in the same radius
   band as the wall — reported −0.1378 and looked like a fault.
2. Corrected, it reported −0.4000 against an expected +0.4, and the chamfer
   0.1378 against 0.2. A wall's contour moves **toward** it, and a 45°
   surface's Z shift is the perpendicular distance × cos 45°, not the distance.

Both are sign-and-trigonometry traps in the *measurement*. The allowance is a
perpendicular distance by definition, so the test now measures exactly that —
point-to-polyline — and the three numbers come out flat.

## Still open

- **Negative stock to leave.** The reference allows it, bounded by the nose
  radius — *"you cannot compensate past the theoretical tip of the tool"*. The
  maths here handles a negative value already; the cfg minimum is 0.0 and was
  left alone, because the bound needs the nose radius and belongs with a test.
- **Their UI links the two** — changing X sets Z to match. Ours are independent
  behind a *Separate Z offset* switch, which is what keeps migration exact: a
  saved project cannot silently acquire a different Z allowance.
- The roughing **floor ladder** stays radial. Correct as far as it goes, but it
  means the walls' extra allowance is honoured by where roughing *stops*, not
  by where its levels *sit*. Nothing measured suggests that is wrong; it has
  simply not been examined.

---

## Addendum — the two open points investigated, 2026-08-09

### The floor ladder staying radial is correct — measured, not argued

The question was whether roughing's floors, which are radial, can honour an
axial allowance at all. They do not need to: a floor **is** a diameter, and the
axial allowance reaches roughing through where each level **stops**, which is
the stop contour and is anisotropic.

End to end on `testing_15_4`, roughing only, no pre-finish pass, measuring the
perpendicular gap between the roughed surface and the profile:

```
isotropic 0.5    chamfer (45 deg) left 0.5014    cylinder left 0.5161
X 0.5  Z 0.1     chamfer (45 deg) left 0.3008    cylinder left 0.5161
```

The 45° chamfer takes the mean and the cylinder is untouched, from roughing
alone. Closed.

### Negative stock to leave — it already works, up to a bound it fails silently at

`offset_contour` with a nose of 0.4, measured at an r20 cylinder:

```
extra -0.10   roll +0.300   contour at -0.1000
extra -0.39   roll +0.010   contour at -0.3900
extra -0.40   roll  0.000   contour at +0.0000   <- silently does nothing
extra -0.50   roll -0.100   contour at +0.0000   <- silently does nothing
```

So the contour passes already cut past the model correctly, down to
`extra > -nose_r` — exactly the bound the reference states, *"you cannot
compensate past the theoretical tip of the tool"*. Past it the guard
`nose_r + extra <= EPS` returns the profile unchanged: **ask for 0.5 past the
model and get 0.0, with no warning.** That silence is the hazard, not the
maths.

`entry_contour` with no nose — the roughing case with compensation off —
refuses any negative value the same way, returning the raw profile.

**Not exposed, deliberately.** The parameter minimum stays 0.0. Exposing it
needs the bound enforced loudly rather than silently, and a decision about
roughing, which cannot hold a negative allowance without a nose. Both are real
work, and half of it would be worse than none.
