# 045 — CNC-side compensation as the default

2026-08-13, branch `liveTooling`, from `cb54890`. greatEndian: *"Comp: CNC-side
or CAM-side as default ... CNC side"*.

## What was already true

Six of the seven lathe operations carrying `PARAM_N_COMP` already defaulted to
Native LinuxCNC (`value = 1`):

```
taper_oda  1     taper_ida  1     boring    1     polyline  1
taper_idl  1     taper_odl  1     facing    0   <- the only one
```

**`facing` disagreed with its own tooltip**, which read *"Native LinuxCNC ... the
default"* while the value said Off. So the ruling was one line, not seven.

## Why facing had drifted, and what changing it means

`facing.ngc` **skips its lead-in/out arcs when compensation is on** — an arc
cannot establish compensation — in favour of a straight run-in beyond the OD.
So turning comp on visibly changes the motion of a facing cut. That is almost
certainly why the default drifted to Off, and it is a real thing for an operator
to notice rather than a bug.

It is now stated in the tooltip in those words, so the change of motion is
predicted rather than discovered.

## The scope of the ruling, measured

**A cfg default is read when a feature is ADDED. A saved project stores its own
value per parameter and keeps it through migration.** So this changes nothing
that already exists. Move lists hashed before and after the change:

```
testing_15_5   484 moves   b849fd15881b   identical
testing_15_2   361 moves   7de894acaec9   identical
testing_15_6   472 moves   d5d3b06f1ee0   identical
```

and the stored values are why:

```
testing_15_5   Facing          Tool nose comp = 0   (Off)
               Lathe Polyline  Tool nose comp = 2   (In CAM)
```

**So an operator wanting Native on an EXISTING feature must set it there.** The
alternative — forcing stored values to follow the cfg — is a far larger change
and a worse idea: a saved value is the operator's own choice, and overriding it
silently is worse than the mismatch. Recorded as a known scope limit, not a
defect.

This is the same asymmetry `analysis/043` found for the back-clearance BOUNDS:
saved parameters carry their own copies. Bounds and values behave alike.

## Verified

`test_comp_default.py` (new): every operation with a comp parameter defaults to
Native; all three modes stay available on each, because In CAM is the only mode
that survives a concave corner smaller than the nose; and testing_15_5's stored
values are unchanged, which is the assertion that would fail if a default ever
started overriding an operator's choice.

`test_all_projects`, `test_rough_comp`, `test_lathe_validation`, `cam_map`,
flake8. `facing.cfg` → 1.26.
