# 050 — The tangential extension did not reach roughing

2026-08-15, from `6a193cb`. greatEndian: *"tangential extension works only in
prefinish and finish and it should work for the roughing too"*.

## Measured first

testing_15_5, front extension 3.0:

```
                 roughing front   contour-pass front   lowest level   levels
no extension        Z0.7071            Z0.7071           r20.016        30
front 3.0           Z2.4284            Z3.7071           r20.016        30
```

The contour passes ran on out; roughing stopped 1.28 short. And the ladder did
not change **at all** — same 30 levels, same lowest radius — which named the
fault before any theory did.

The tables were not the problem. All three carry the extension correctly:

```
floor/stop first point   (0.8217, 19.0217) -> (2.9430, 16.9003)
```

3.0 along the 45° tangent, exactly.

## Three faults, not one

**1. The ladder is bounded by the parameters, not the profile.** `#3141` and
`#3142` were `param_b_x` and `param_e_x` — the operation's Begin and End
diameters. An extension that takes the profile past either is simply not
roughed. `rough_radius_bounds()` now widens them to cover the extended profile,
by min/max against the parameter so an extension can only ever ADD levels.

**2. `_pl_begin_z` was adding the extension's LENGTH, not its Z component.** On
a 45° cone a 3.0 extension is 2.121 of Z, so the sweep started 0.88 further
forward than the profile reached — cutting air. Same confusion as measuring a
length in diameters. It now takes `ext_dz(self, 'front')`.

**3. The roughing sweep takes BOTH bounds from the record array**, which is
built from the raw polyline items and never sees an extension: `e_z` is its
first point and `l_z` its last. `l_z` now carries `#<_pl_ext_bk_dz>`, a signed
displacement that is 0.0 when no extension is set — so the added line is a
no-op by construction rather than by comparison.

## After

```
front 3.0    roughing front Z2.8284   contour Z2.8284   lowest r17.8947   35 levels
```

Roughing reaches exactly as far as the contour passes. The ladder gained five
levels to get there. The contour front moved 3.7071 → 2.8284 as well, which is
fault 2 being fixed: it was starting in air.

The back displacement is plumbed and correct, measured directly:

```
wall end,   extension 3.0    dz  0.00000000    a wall has no Z component
taper end,  extension 3.0    dz -2.38762763    matches the contour's own
                                               -40.6043 -> -42.9919 exactly
no extension                 dz  0.00000000
```

It does not show in roughing on either demo project because roughing already
stops short of the un-extended back end there — the part behind is below the
ladder's bottom. That is geometry, not plumbing.

## Byte-identical with no extension

Move lists hashed with the change and with it stashed:

```
testing_15_5   484 moves   d14e9d952c14
testing_15_6   480 moves   c11c9e97d983
testing_15_2   361 moves   d4fd2d64c014
```

Identical both ways.

## A test that encoded a bug

`test_extension` asserted the front-most cut moved by **3.0** — the extension's
raw length. That was fault 2 written down as correct. It now asserts the Z
component, 3.0/√2 = 2.1213, with the reason recorded.

## Found on the way, not fixed here

- **testing_15_5 ignores an End Z limit in roughing entirely** — trimmed at −40,
  roughing still reaches −70.4 while the contour passes stop at −40.6043. That
  is openPoints' existing entry, now with a second measurement behind it; it
  made 15_5 useless for testing the back extension.
- **`test_leftover`'s 15_6 control does not fire**, at HEAD as well as here —
  proven by stashing. Deleting a properly-spaced pass (r28.6360, both
  neighbours a full depth of cut away) leaves 0 leftover regions on that
  project while the same control works on 15_5. So the leftover measurement
  cannot see a missing pass on 15_6, and a clean report from it there means
  nothing. Not caused by this work and not fixed by it: an attempt to make the
  victim selection spacing-aware fixed 15_5's robustness but not 15_6, and was
  reverted rather than left half-done.
