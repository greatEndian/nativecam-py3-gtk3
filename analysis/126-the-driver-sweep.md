# 126 — all 72 drivers run: 1 regression, 3 stale gates, 3 real findings

**Asked**: greatEndian, 2026-09-10 — *"go with 1"*, the dead-driver sweep, after
two of two facing harnesses were found dead in `analysis/122` and `analysis/124`.

**The premise was wrong: no driver is dead.** All 72 run. What the sweep found
instead is one live regression of mine and a set of stale gates.

```
72 drivers:  64 pass · 1 regression (fixed) · 7 pre-existing failures · 0 dead
```

Every one of the 7 also fails at `4a3fb1d`, the commit before this session, so
none is from today's work - `test_rough_ends` and `test_leads` in particular,
which I suspected were mine and were not.

## Fixed

**`test_arc_endpoint` - a live regression** (`b0bdf1d`, `analysis/125`). Commit
`2967a71` rewrote `_min_segment` and this is the guard on that exact function;
it was not in the gates I ran. Its point-count assertion was replaced by the
physical one - no kept segment shorter than its own compensation shrink.

**`test_stock_to_leave` - hardcoded window bounds.** `gen()` scraped
`#4[45]\d\d`, which was the stop table's home until analysis/119 moved it to
4330-4600. The regex then found 62 of its 132 slots, and with the separate-Z
switch on - where the table is shorter and sits entirely below 4400 - it found
**none**, so the result was `[]`, falsy, and "the project generates all three
ways" failed on a program that had generated perfectly well. Now takes
`STOP_BASE`/`STOP_TOP` from the module. **Third instance of this class**, after
`test_through_cut` and `test_rough_overlay`.

**`test_z_limits` - a stale pinned baseline**, re-recorded. Every MOVE COUNT is
unchanged - 1575, 327, 464 - and only coordinates moved, which is the signature
of `analysis/119`'s finer arc chords. Re-stamped **because the change it caught
was intended and had its own gate**, and said so in the file: re-recording
without that evidence turns a tripwire into a gate that cannot fail.

**`test_send_split` - a stale UI expectation.** It counted menu CHILDREN and
demanded two; the dropdown legitimately carries "Send flat G-code" beside the
radio group, with a separator, added deliberately as a separate action. Now
counts RadioMenuItems, which is what it is about.

## Left open, with reasons

**`test_rough_ends`** - `Off Z0.0000, Native Z-0.4000, In CAM Z-0.4000`. Its
assertion is literally *"COMPENSATION DOES NOT MOVE IT"*, but under the
all-or-nothing rule roughing carries the nose in its coordinates when
compensating, so a shift of exactly the nose radius may be correct. This is the
same tip-versus-cut question `analysis/115` could only settle by greatEndian's
own words. **Not re-stamped** - it is a real open question, not a stale number.

**`test_leads`** - chasing it produced the sweep's best finding, recorded as an
addendum to `analysis/121`: with nothing overridden but `param_n_comp`,
`testing_13_arcs` gives Off 3076 moves, **Native an outright abort**, In CAM
3111 moves. Native compensation cannot RUN that profile, where the prover had
only measured an 18 um gouge. Pre-existing.

**`test_air_leads`** and **`test_floor_ladder`** - `310 leads want 309`,
`1319.7 mm want 1319.0`, and `15_4 lands on 1 of 2 floors before and after`.
The floor one may be reporting correct behaviour: `openPoints` records that
15_4's chamfer bottoms at a single point, so 2 of 3 is the right answer there
and 15_4's own count has never been confirmed. Left for measurement, not
re-stamped.

## What the sweep really exposed

Not rot in the drivers - **rot in my routine**. I ran 16 of 72 drivers and
called the suite green, across nine commits. Three of the four faults fixed
here are gates that pin a number, a slot range or a widget count, and every one
of them broke on a change that was correct. The hardcoded-window class alone has
now appeared four times: `test_sections`, `test_surface_equality`,
`test_through_cut`/`test_rough_overlay`, and `test_stock_to_leave`.

`test_project_sweep` and `test_motion_fingerprint` cover the catalogue. Nothing
covered the drivers themselves until this.
