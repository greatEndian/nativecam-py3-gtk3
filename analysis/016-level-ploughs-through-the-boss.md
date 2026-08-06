# 016 — A roughing level swept 45.7 mm through the boss

2026-08-06, branch `liveTooling`. greatEndian, `photo/spaceBehindIssue_8.png`,
with the pre-finish pass unchecked on `testing_15_2`.

## Measured

```
pf ON   r29.8894  ramp Z-46.4204 r30.3974 -> Z-48.6208 r29.8894, cut -48.6208 -> -69.8920
pf OFF  r29.8894  ramp Z-23.5808 r29.3814 -> Z-24.1426 r29.8894, cut -24.1426 -> -69.8920
```

The boss peaks at r32.66, so that 45.7 mm sweep cuts **2.7697 mm into it**.
11 of 31 roughing cuts did it. A crash, not a finish defect.

## Ruled out first, all three correct

- **Section windows** - identical with the pre-finish on and off, 7 windows
  each, same Z spans and radius bands.
- **`lathe_level_next_start`** - returns -50.4335 (pf ON) and -48.1752
  (pf OFF), both safely past the boss.
- **The CALL** - `lathe_level_pass` is handed `lfr=-48.1752` correctly.

Everything upstream was right. Instrumenting the sub itself gave it up at once:

```
ENT lvl=29.889397 wfrom=-48.175207 zdir=1 ehave=1 ebest=-24.142556 zstart=-24.142556
```

## The fault

`lathe_level_pass` overrides its own `z_start` from the entry-contour crossing.
That crossing is **deliberately allowed to sit behind the interval start** -
the backward reach is the room the profile-angle ramp needs - and every
crossing that fires is behind it:

```
pf ON   10 of 10 crossings behind w_from, all by exactly +1.8127 mm
pf OFF  11 of 11 behind, by +24.0327  +25.3235  +28.0773 ...
```

It had **no upper bound**. With the pre-finish off the nearest qualifying
crossing sits on the far side of the boss, and the level starts there.

## The fix

Bound the backward reach to what the ramp can actually use: one roughing depth
of cut of **projected** length along the candidate's own segment,
`doc * |dz| / |dx|`, times 1.5 for the crossing sitting inside a segment rather
than at its end. Both terms are already in hand at candidate time.

A steep segment - the face of a boss - then allows almost nothing, which is
correct: there is no shallow ramp to be had there. The 13 degree taper allows
2.2004 mm, so pf ON's 1.8127 mm survives untouched and that mode is
byte-identical.

## Attempted first and reverted: clamp to `w_from`

It removes the gouge and is too blunt. It takes the 1.8127 mm the ramp needs:

```
Off overcut          0.1116 -> 0.0503   roughing reaches LESS, not better
passes behind boss   1 of 10 lost its ramp and plunged
                     6 test failures
```

That failure is what identified the correct bound - the limit is the ramp's own
length, not the interval boundary.

## After

```
pf ON   cut -48.6208 -> -69.8920   unchanged
pf OFF  cut -48.5752 -> -69.8920   was -24.1426
through-cuts: 0 in both modes
```

`test_rough_comp` back to Off 0.1116 / 0.0394 / 0.0394 with every ramp intact;
`test_leads`, `test_ladder`, `test_sections`, `test_rough_overlay`,
`test_lathe_validation` pass; `check_tangent` min |dot| 1.00000.

## The test, and why nothing existing caught it

`test_through_cut.py`: no level may cut across a Z span where the reachable
contour stands above that level's own radius. **It toggles the pre-finish
pass**, because the fault only appears with it off and every saved project has
it on - a check that did not toggle it would have passed throughout.

`test_rough_comp` saw nothing and could not: its metric is one-sided overcut
past the pre-finish contour, and a level ploughing through a boss is not
overcut of that surface at all.

Negative control: with the bound removed, **11 of 31 cuts through, worst
2.7697 mm**, and pre-finish ON still passes.
