# 109 — the native lead gouge is ONE point, at the compensation entry

**Asked**: greatEndian, 2026-09-04 — *"fix the native lead"*.

## Not fixed. Located exactly.

**First attempt, and it did nothing.** Following `taper_id.ngc`'s precedent I
widened `lathe_poly_pass`'s ID approach by `_tip_lead_w` when compensating.
The gouge did not move: still 0.8000. Reverted rather than left in - a change
that does not change the number is not a fix.

The approach was not the problem.

## Where it actually is

Instrumented with the prover's own functions - same profile, same calibrated
offset, same bound test - but reporting WHICH points violate:

```
620 sampled points, 1 gouging
   centre Z 0.0000  r 17.4000   bound r 17.0000   into 0.4000  [feed]
```

**One point**, at the bore mouth - the profile's own first point - with the
nose centre at `wall + R`.

That is the compensation ENTRY. LinuxCNC needs a straight feed of at least the
nose radius IN FREE AIR to establish the offset; here the entry move lands
directly on the profile start, so for that one point the tool is positioned
uncompensated and the round nose sits R inside the wall.

`CLAUDE.md` already states the rule: *a comp-entry move must be a straight feed
of at least the nose radius, in free air, and entering comp on the workpiece
gouges it.* This is that, on a bore.

## Why the approach fix could not have worked

The approach positions the tool BEFORE the lead. The gouge is at the end of the
entry - the point where compensation is switched on - which no amount of
standing off beforehand moves. The two are different moves.

## What the fix has to do

Start the compensated feed clear of the wall and let it arrive at the profile
start already compensated, rather than establishing comp on the surface. That
is a change to where `lathe_poly_pass` puts `tip_comp_on` relative to the
lead-in, not to the approach radius - and the arc-entry branch at :284 already
does something like it, running the lead-in UNDER compensation for a reason
the comment there spells out.

## Gate, unchanged and already in place

`--mode 1` on `testing_14_inside_bar` must bring `whole path` to 0.0000 with
the contour still 0.0000 and the wrong-side control still failing; `--mode 2`
and the 36 OD configurations unchanged.

## Kept

`prove_cam_comp --mode`, which is what made native measurable at all. Default 2,
so every existing invocation is unchanged.

## Four readings of this defect, three wrong

`n_comp = 0 invalidates it` - no. `the instrument cannot discriminate` - no.
`the side is inverted` - no. `the approach is too close` - no. Each time the
answer came from instrumenting the thing itself; each wrong reading was a story
told about a number. The fourth measurement - which points, not how much -
took one run and gave a single coordinate.
