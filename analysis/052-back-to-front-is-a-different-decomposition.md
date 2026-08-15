# 052 — Back to front is not a reversed traversal

2026-08-15. greatEndian: *"I select Roughing direction front to back - ok, back
to front - is mess, it creates messy preview and mess Gcode... path have to be
same Gcode as Front to back but movement is from last polyline reference to
front, means rough all long passes from last reference to first, then last
recognized section rough, last recognized section - 1, repeating to first/front
section"*. testing_15_6, sectioning on.

**Not fixed.** Measured, one cause ruled out by experiment, and scoped.

## The cuts DIFFER — they are not the same set in another order

The first question worth answering, because it decides whether this is an
ordering job or a decomposition one:

```
front -> back    316 feeds    45 level cuts
back  -> front   307 feeds    40 level cuts

cuts in front-to-back and not back-to-front:  44
cuts in back-to-front and not front-to-back:  40
```

Of 45 and 40 cuts, **one is shared.** The two directions produce almost
entirely disjoint sets.

What they look like is the clearest statement of it. Front to back opens with
long passes down the whole part:

```
r34.532   Z 0.0    -> -68.892
r34.064   Z 0.0    -> -31.209
r34.064   Z-35.0   -> -68.892
```

Back to front opens by roughing one section, at radii the other direction never
uses there:

```
r30.001   Z-70.8   -> -32.5
r29.493   Z-70.8   -> -32.5
r28.985   Z-70.8   -> -32.5
```

So greatEndian's reading is right: it is not the same G-code taken backwards.
It is a different decomposition, and "mess" is a fair description of the result.

## What it is NOT — ruled out by experiment

`lathe_sections` reverses the profile for `rough_dir == 1` in two builders
(`build_sections_gcode`, `build_floor_ladder_gcode`). The obvious theory was
that the sections and the ladder are therefore detected on a reversed profile
and come out different.

Disabling both reversals makes it **worse**, not better:

```
back -> front, reversals disabled    251 feeds   34 level cuts   still disjoint
```

So the Python point order is not the cause, and the cheap fix does not exist.
The reversal at `flank_sides` / the leading-flank mirror is a separate matter
and is genuine direction physics — which face of a boss is shadowed depends on
which way the tool travels — so it must stay whatever else changes.

## Where it actually lives

`param_dir` reaches `poly_lathe_mill` as `rough_dir`, and at `dir == 1` the
whole sweep runs on the **reversed record array** built by
`poly_reverse_lathe`. Every downstream decision — which windows exist, their
order, where each level starts and stops, which section is "first" — is then
taken in that reversed frame. That is why the decomposition differs rather than
the order.

## What the fix has to be

Compute the decomposition in ONE frame — front to back — and reverse only the
**emission**: the order windows are visited, the order sections are taken, and
the direction each pass is cut. greatEndian's own description is exactly that:
the long passes first, walked from the last reference toward the front, then the
sections last-to-first.

That is a rework of direction handling in `poly_lathe_mill`, which is the
machinery five stacked faults came out of in `analysis/032`. It is not a small
change and it is not safe to attempt without its own pass, so it was not
started: a half-reworked sweep is worse than a messy one, because this repo
drives a real machine.

**Both directions** — greatEndian's `rough_dir == 2` — he explicitly leaves as
an open point, and it is untouched here.

## The gate, for whoever takes it

With direction back to front on testing_15_6, sectioning on:

- the SET of level cuts must equal front to back's — same radii, same Z spans,
  same count (45, not 40)
- the ORDER reversed as described: long passes first from the back, then
  sections last-to-first
- front to back byte-identical, hashed
- and `test_x_continuity` and `test_leftover` green in BOTH directions, which
  they have never been asked to be
