# 035 — The leftover check: measuring the metal instead of the recipe

2026-08-12, branch `liveTooling`, from `288b936`. greatEndian's idea, after four
turns in which the roughing ladder was pronounced correct from its own tables
while he could see material standing in AXIS.

## Why it exists

Every check on the ladder so far inspected the **recipe** — breakpoints,
crossings, the Z each pass starts at. All of those can read correct while a pass
is missing, and on 2026-08-12 they did, three times running. A ladder is only
correct if the metal is gone.

So: sweep the real nose along the roughing moves, and ask what is left.

> after roughing, does the remaining material stand more than one depth of cut
> above the surface roughing is meant to leave?

## What it excludes, and why each exclusion is forced

**Unreachable material.** Behind a boss the back angle casts a shadow the tool
cannot enter. `test_rough_comp`'s docstring already records what happens if this
is not handled: an earlier attempt compared roughing against the FINAL profile
and reported **5.0452 mm on the known-good baseline** — *"a metric that fails the
baseline is not a metric"*.

The escape is that **the finish pass itself bridges the shadow**, crossing it as
one straight taper, so its programmed path *is* the reachable contour. Taking the
target from that path excludes the shadow at the root, with no window to guess
at. On testing_15_6 the finish contour crosses Z−35.30 → −70.40 as a single
taper while the drawn profile dips away underneath.

**Near-vertical segments.** At an end face there is no single radius at that Z,
and comparing against one of the two reports the whole height of the wall —
`radius_at` returns None there, the same guard as `radius_span` and for the same
reason (4.7405 mm at Z−69.4, in every mode including Off).

**Material above the first pass.** The stock is modelled one depth of cut above
the topmost roughing pass; what lies above that is the operator's stock setting,
not a pass the ladder failed to make.

**Narrow spikes — and this one was found by the tool itself.** Reporting only
pass/fail hid something: there *are* points over the one-depth-of-cut threshold
on both projects.

```
testing_15_5 sect off   worst standing 0.7219 mm at Z-19.38
testing_15_5 sect ON    worst standing 0.8579 mm at Z-19.43
testing_15_6 sect off   worst standing 0.6473 mm at Z-18.72
testing_15_6 sect ON    worst standing 0.5935 mm at Z-18.72
```

Every one is **narrower than the nose**. testing_15_5's shoulder at Z−19.51
rises 0.93 mm in 0.04 mm of Z; a r0.4 nose cannot reach into that corner and
leaves a fillet standing. No ladder of straight cuts can remove it, and the
pre-finish pass is what takes it.

A **missing pass is wide** — it spans at least the ladder's own Z step, 2.2004 mm
on these projects. The two are an order of magnitude apart, so the width bound
(1.5 × nose) does not have to be delicate, and the control below proves it still
fires.

Printing only the verdict would have concealed this. The tool now reports the
worst standing figure whether or not it qualifies: 0.02 mm proud and 0.50 mm
proud both pass, and only one of them is comfortable.

## The negative control

One radius of roughing moves is deleted from the **parsed program** — nothing
generated is touched, so the suppression is exact — and the same measurement must
find the hole:

```
testing_15_5 without r29.1440   1 region, worst 0.6683 mm at Z-52.58   DETECTED
testing_15_6 without r29.6520   1 region, worst 0.6630 mm at Z-53.72   DETECTED
```

## THE ANSWER: testing_15_6 has no leftover metal

```
                        wide leftover regions
testing_15_5 sect off            0
testing_15_5 sect ON             0
testing_15_6 sect off            0
testing_15_6 sect ON             0
```

Roughing removes everything down to its target on both projects, in both
sectioning states. **There is no missing pass behind the boss on 15_6.**

## So what is greatEndian seeing? The pre-finish band

The two projects are geometrically identical and differ in exactly one
parameter: **Pre-finish offset, 0.254 mm on 15_5 against 1.000 mm on 15_6.**

Roughing stops at `Offset + Pre-finish offset` from the part:

```
testing_15_5   0.508 + 0.254 = 0.762 mm
testing_15_6   0.508 + 1.000 = 1.508 mm     nearly DOUBLE
```

So on 15_6 there is a **1.5 mm band of uncut material between the last roughing
pass and the part**, where 15_5 leaves 0.76 mm. That band is correct — it is the
allowance he asked for, and the pre-finish pass takes it — but it is twice as
wide, and against the drawn contours it reads exactly like a pass that should be
there and is not.

That is consistent with everything: the ladder is regular, the tables agree, the
metal is gone down to target, and the visible gap is the setting.

## Not proven, and worth saying

This measures the **motion**. If what greatEndian sees is an overlay drawn in the
wrong place rather than the band itself, the candidate is the rough entry path
(yellow-green dashed), which since `e27a858` sits at
`Offset + Pre-finish + one depth of cut` — **2.016 mm out on 15_6** against
1.270 mm on 15_5. The preview has already misled twice this session, with that
same yellow line and with the pre-finish surface.

## Verified

`test_leftover` itself, plus `test_rough_comp`, `test_stock_to_leave`,
`test_rough_ends`, `test_rough_overlay`, `test_behind_boss_ladder`,
`test_all_projects`, `test_ladder`, `test_section_length`, `cam_map`, flake8.
Only a new file was added; no production code changed.
