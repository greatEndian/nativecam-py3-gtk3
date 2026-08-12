# 034 — The behind-boss ladder stopped partway down

2026-08-12, branch `liveTooling`, from `c32ee68`.

## What was reported

greatEndian, in AXIS: on `testing_15_6.xml` the **first and last** roughing
passes behind the boss segment are missing; on `testing_15_5.xml` it is correct.
Pre-finishing itself now behaves as wanted — this is only the roughing ladder.

## The two projects are geometrically IDENTICAL

Dumped both the raw profile (`resolve_points`) and the reachable one
(`finish_profile`) for each. Behind Z−28 they match point for point, including
the back-angle shadow, which collapses everything from Z−35.304 to Z−70.400
into a **single straight taper**:

```
REACH (both projects)
  ... -33.911,65.158  -35.304,64.681  -70.400,48.476  -70.400,70.000
```

So nothing about the shape explains the difference. The projects differ only in
parameters, and the one that matters is the **pre-finish offset**: 0.254 mm on
15_5 against **1.000 mm** on 15_6. That shows up directly in where roughing
stops — 0.762 mm off the Z−70.4 wall on 15_5, 1.508 mm on 15_6.

## The fault, measured

Only the **last** passes were genuinely missing. The behind-boss ladder must end
by running out of material; instead 15_6's stopped with a real cut still in
front of it:

```
before, testing_15_6      before, testing_15_5
  ... r28.1280  len 7.7919      ... r26.0960  len 3.0525
      r27.6200  len 5.5915          r25.5880  len 0.8522   <- tapers out
      (stops)                       (stops)
```

5.5915 mm remaining against a 2.2004 mm step means two more levels — 27.1120 and
26.6040 — had genuine cuts and were dropped.

The **first** pass is NOT missing and never was. 15_6's floor contour peaks at
X34.1641, so level 34.2240 clears the boss and runs full length while 33.7160
splits — correct. 15_5's peaks at 33.4193, so two levels clear it. Both ladders
are complete from the top; the truncated tail made the whole thing look wrong.

## Root cause

`resume_envelope`'s crossing test is **strict at a segment's lower end**:

```python
if px >= lev > cx:
```

so a descending segment never yields a breakpoint at its **own** bottom — it can
only get one from a **later** segment that descends past it. Behind a boss the
back-angle shadow makes the last descent one long taper with nothing after it,
so the envelope simply stopped partway down.

On 15_6 that taper is a single floor-contour segment:

```
Z -36.1330  X 33.7997   ->   Z -68.8918  X 26.2368
```

Its vertex radii are 33.7997 and 26.2368, and the minimum is skipped by the
strict test. The envelope's lowest breakpoint was therefore **27.2313** — a
vertex radius from elsewhere on the profile, whose crossing lands on the taper
at Z−64.5839. Levels 27.1120 and 26.6040 fall below it, get the walker's
**out-of-range fallback** (which returns the last breakpoint's Z), and at
Z−64.5839 the floor is 27.2313 — so both were judged inside the part and cut
nothing.

**15_5 escaped only by luck.** Its lowest breakpoint, 25.5146, happens to sit
near its own taper end at 25.2989, so the levels that fell outside the table had
nothing to cut anyway. A 0.746 mm larger allowance is all it took to expose it.

## The fix

`resume_envelope` now extends to the bottom of the last descent: after the main
loop, the deepest descending segment END that lies **behind** the current last
breakpoint is appended, subject to the same monotone lead-in clamp. Only
descents behind it count — a deeper descent in front is a different feature and
would put the resume in front of where the level already is.

Python only; no `.ngc`, `.cfg` or parameter change, so nothing to migrate.

```
envelope lowest breakpoint      before            after
  testing_15_5                  25.5146 @ -68.7036   25.2989 @ -69.6378
  testing_15_6                  27.2313 @ -64.5839   26.2368 @ -68.8918
```

15_5's lowest breakpoint moved too — the old one collapsed as collinear with the
new endpoint, so its envelope is now exact where it had been approximate. Its
ladder is unchanged.

## Measured after

```
testing_15_6 behind the boss        testing_15_5 (unchanged)
  r27.6200  len 5.5915                r26.0960  len 3.0525
  r27.1120  len 3.3911  <- restored    r25.5880  len 0.8522
  r26.6040  len 1.1908  <- restored    (stops)
  (stops)
```

15_6 goes 44 → 46 level cuts, 422 → 438 moves. 15_5 stays at 49 level cuts and
458 moves, topmost behind-boss 33.2080 sectioning off / 33.1273 on.

## `test_behind_boss_ladder.py`

The invariant asserted is **the ladder ends by running out of material**: the
last, shortest pass behind the boss must be shorter than one step of the ladder.
If it is longer, the next level down still had a real cut and the ladder was
truncated — the shape of this bug on any project and any offset. Asserting
"levels 27.1120 and 26.6040 exist" would have needed those exact numbers and
held for one project only.

Plus a fast unit case on `resume_envelope` with a synthetic boss-and-taper
contour, and a check that no level is skipped *inside* the ladder.

**Negative control run**: with the fix removed the file reports 3 failures — the
unit case on both counts, and 15_6's ladder stopping with 5.5915 mm left.
**testing_15_5 passes without the fix**, which is exactly greatEndian's report
and confirms the test is specific rather than blanket.

## Verified

`test_behind_boss_ladder`, `test_rough_comp`, `test_stock_to_leave`,
`test_rough_ends`, `test_rough_overlay`, `test_all_projects`, `test_ladder`,
`test_floor_ladder`, `test_ramps`, `test_section_length`,
`test_resume_envelope`, `cam_map`, flake8.
