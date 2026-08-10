# 029 — The behind-the-boss pass, lost to two scans reading two sources

2026-08-10, branch `liveTooling`, from `1f7a97b`. greatEndian: *"one issue came
back that are missing first pass behind the boss segment … it has section on or
off there is no change"*, `testing_15_5`.

## Measured

Roughing level cuts lying entirely behind the boss (Z < −33.5):

```
                              topmost such level    count
HEAD, sectioning OFF              32.1920            14
HEAD, sectioning ON               32.1522            14
```

Same both ways, as reported. The level ladder steps 0.508, so between the last
full-length pass at 33.7160 and the first behind-boss pass at 32.1920 there is a
**1.524 mm bite** — three times the depth of cut. Levels **33.2080** and
**32.7000** have a front interval and no behind-boss one.

The geometry says both should exist. From the emitted floor contour (119
points), the boss peaks at **X33.4207**, and behind it the floor drops back
below 33.2080 at Z ≈ −35.24 and below 32.7000 at Z ≈ −37.4, staying below all
the way to the end wall.

## Root cause — found by bisection, not by reading

Disabling `build_floor_contour_gcode` and regenerating:

```
floor contour ON  (HEAD)     topmost behind-boss 32.1920    14 passes
floor contour OFF            topmost behind-boss 33.2080    16 passes
```

So `6fefc09` — *the roughing floor becomes a contour Python builds* — is the
cause. It moved **`lathe_level_pass`'s stop scan** onto the Python floor contour
and left **`lathe_level_next_start`'s resume scan** walking the record array
offset perpendicular by a scalar. `lathe_level_next_start.ngc` contains no
reference to `_pl_flc_*` at all.

Two scans, two sources. They disagree about where an obstruction is **by
construction**, whatever either one says on its own: the stop scan blocks the
level against a boss whose floor peaks at 33.4207, and the resume scan then
looks for the re-entry on a differently-shaped curve and does not find it. The
level is never resumed, and its behind-boss interval is simply lost.

This is the exact class `cam_map` exists for — a table moved in Python, a
consumer left behind — and `cam_map` does **not** catch it: its checks cover
window literals, globals, order names and subroutine definitions, not *which
scan walks which profile*. Noted as a gap in the checker.

## The fix that works, and the one that does not

Giving `lathe_level_next_start` the same floor-contour branch restores every
missing pass:

```
with the branch, sectioning OFF   topmost 33.2080   26 behind-boss passes
                 sectioning ON    topmost 33.1273   26
```

33.2080 resumes at Z−34.2507 and 32.7000 at Z−36.4467, and the resume points
follow the real contour instead of marching back in a straight 2.2 mm per level
line, which is what the scalar offset produced.

**It also breaks `test_rough_ends`, and that is why it is not committed.** Six
failures, all the same shape:

```
Off     the retreat leaves 0.4700 mm standing in a rapid's way:
        Z-42.8230 r31.8160 -> Z-42.8230 r22.2311
Native  0.4482 mm   Z-43.9951 r31.8160 -> Z-43.9951 r22.2311
```

A **rapid plunging through standing metal**. Following the true contour, the
resume points are no longer monotonic — level 31.1760 resumed at Z−40.7954
while 31.6840 directly above it resumed at Z−40.8518, so the plunge went down
where the level above had not yet cut.

A monotonic clamp was written — hold a candidate back to the level above's
start, which is safe at both ends since the material above is gone there and the
floor is already below this level — and it **did not change the failing
numbers at all**, byte for byte. So the offending plunge does not come from
`lathe_level_next_start`; something else in the phase-2/section machinery
produces it. That is where the next session starts.

(One real bug was found and fixed inside that attempt and is worth keeping if it
is rewritten: the guard latched on the FIRST level forever, because it recorded
only when `_pl_res_have` was 0. It has to key on the level changing, or every
level is compared against a stale value far in front of it.)

## State left in the tree

**Reverted.** `lib/lathe/lathe_level_next_start.ngc` and `ncam.py` are back to
`1f7a97b`, the suite is green, and the reported bug is still there. Shipping a
rapid that cuts metal would have been worse than shipping the missing pass.

## What to do next

The standing rule already names it: **the intervals belong in Python.** Level,
floor contour and ladder are all known at generation time, so the whole set of
disjoint intervals per level — including monotonicity of the plunge points,
which is a *ladder-wide* property no single subroutine call can see — is a table
to compute and emit, with the `.ngc` walking it. That also retires the resume
scan rather than teaching a second scan to agree with the first.

Until then the two scans must not be left reading different sources; if the
Python interval table is not built soon, the honest interim is to make the stop
scan fall back to the record array whenever the resume scan cannot follow it.
