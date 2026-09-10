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

## Addendum — a second, independent run, and one genuine false green

The worker that was stopped mid-task delivered its own classification after
all. It agrees with the clean sweep exactly: 72 drivers, the same 68 passing,
the same four failures, with the four repairs above showing as PASS. Two
independent runs concurring is worth more than either alone, and it settles the
concern it raised on the way out - there were no false passes hiding in the
contaminated data.

It also classified four drivers VACUOUS. Checked rather than relayed, and only
**one** of the four is real:

- `test_paned.py` - 20 lines, **0 asserts, 0 checks**, `# Gtk.main()` commented
  out. A scratch reproduction of the GTK3 Paned size-allocate recursion, named
  `test_*`, swept every time, always green, proving nothing.
- `test_coord_mapping.py` - has **2 real asserts**. False positive of a
  PASS-token rule.
- `test_project_sweep.py` - does real work, prints its own format.
- `test_motion_fingerprint.py` - a tool, not a gate, by its own docstring and
  by design.

**The genuine one was NOT converted into a test.** It was rewritten as one -
the guard asserted, with a negative control - and the control PASSED: without
the guard the handler still settles, because a headless run never drives the
allocation loop hard enough to re-enter. A check whose negative control passes
is the same false green in a better disguise, so the file is renamed
`demo_paned_recursion.py` and left as an explicit hand-run demo. 71 drivers now.

Also noted, not chased: `test_menu_layout` emits **22 tracebacks** to its
output while passing - GTK signal-callback noise on no-selection clicks. It
does not affect the verdict, but a passing test printing tracebacks is where a
real one would hide.

## Addendum 2 — two of the four failures resolved, and they were tests

`test_floor_ladder` and `test_air_leads`, the two I judged measurable. Both
turned out to be gates asserting the wrong thing, not defects.

### testing_15_4 cannot land on its second floor, and never could

Measured on the profile: the minimum radius **19.0000 is touched at exactly
ONE point**, Z0.0000, with **no segment lying on it**. The only real flat is
r20.000 running 44.4 mm. A roughing level is one radius held across a sweep, so
it needs a surface; a floor belonging to a chamfer that bottoms at a point has
nothing to cut and is correctly blocked. **1 of 2 is the right answer**, and
`openPoints` already said so.

The check now counts REACHABLE floors from the floor contour the program
already carries - the profile offset by the floor allowance, where a flat is
still a flat - and asserts the ladder lands on all of them.

**A length threshold was needed and the first version did not have it.**
Counting any constant-radius run made `testing_15_4` report two reachable
floors, because its floor contour carries a **0.066 mm** sliver at r33.421
beside the real 17.888 mm run at r20.762. 1 mm separates them cleanly:
testing_13_arcs' four flats are 2.3, 8.0, 20.0 and 18.2 mm.

The check keeps its teeth - `testing_13_arcs` wants 2 and lands 2, so a
re-anchoring failure taking it to 1 still fails.

### test_air_leads pinned three numbers where it meant three properties

Its own comment says these counts "drift with the geometry", and it had already
been re-baselined once - yet `cut_n` was compared with `==`. On art1 it read
310 against 309, one extra cutting lead and 0.7 mm more feed.

The check is named *keeps every lead that cuts metal*: fewer is the failure,
more is not. Both it and the distance check now assert a floor. And the third,
*back to front keeps every retreat, setting or not*, compared against a
recorded 1319.0 when what it means is that `lo_air` changes nothing - now a
difference between the same project with and against the setting, which is
immune to the direction's own feed drifting.

**The +1 lead is still unexplained** - it predates `4a3fb1d` and was never
traced. Recorded in `openPoints` rather than buried under a passing test.
