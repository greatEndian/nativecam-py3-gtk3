# 053 — The leftover gate could not fail on most geometry

2026-08-15, branch `liveTooling`, from `c552c51`.

## What was asked

`test_leftover.py`'s negative control did not fire on testing_15_6: deleting a
roughing pass from the parsed program left **0 leftover regions**, while the
same control worked on testing_15_5. Confirmed pre-existing at HEAD by stashing.

`test_leftover` is one of the two gates this project relies on — the one that
measures METAL rather than tables, and the one that proved rest machining had
nothing to cut. A control that cannot fail proves nothing.

## What was actually wrong — much more than the reported project

The reported symptom was the small end of it. Surveying **all 21 runnable demo
projects**, the old control — delete one radius, chosen at `len(radii) // 3` —
fired on **7 of 21**.

Deleting one pass is not a valid mutilation, for two independent reasons, both
measured:

**A shallow pass is usually redundant.** The final roughed surface at any Z is
the *deepest* pass covering it. On a monotone profile every pass runs the whole
length, so only the deepest shapes the result. On testing_10, removing each of
the seven outermost radii in turn left the worst standing figure identical to
four decimal places — **0.2505 mm at Z−14.47, every time**.

**Where it is not redundant, it is narrow.** A pass is the deepest only in the
sliver the pass below does not reach, and on a rising profile that sliver is
thin. On testing_15_6, deleting r29.6520 leaves **0.9580 mm standing — nearly
twice the threshold — across 0.350 mm of Z**, which `MIN_RUN` (0.600) discards.
The band shrinks monotonically down that ladder, 3.75 mm at the top to 0.05 mm
at the bottom: fourteen of its twenty-six passes are invisible to the gate.

So the detector was not missing metal on 15_6. It was being handed a mutilation
that leaves a ridge the width of a nose fillet.

## This falsified the file's own justification for MIN_RUN

The constant carried the claim that *"a missing pass is WIDE: it spans at least
the ladder's own Z step, 2.2 mm on these projects, so the two are an order of
magnitude apart"*. The survey above shows that is false. The comment now says
so, and the bound stays anyway — the case it excludes is real, and admitting
every 0.05 mm ridge would make the gate fire on correct programs.

## Two selection rules tried and rejected, with numbers

**The two deepest radii** — geometry-independent in principle, since the deepest
passes are what the final surface is made of. **20 of 21.** It failed on
testing_14_inside, which is *bored*: its passes climb r13.36 → r16.24, so its
final surface is the LARGEST radius and the two smallest are the passes furthest
from the part. Deleting them changes nothing, exactly as a redundant shallow
pass does.

**The two radii nearest the target**, meant to fix that without guessing the
direction — **16 of 21**, worse. Being near the target does not mean being the
surface over any length of it.

A third attempt, reading the OD/ID side by counting passes above or below the
target, got testing_14_inside wrong too and was abandoned. At that point the
work had become heuristic-tuning, which is the wrong mode.

## What it does now

**It leaves a Z window unroughed.** Every roughing move is trimmed out of a 6 mm
slice — split, not deleted, so cutting outside the window survives and exactly
one unroughed slice remains. That is the failure worth catching (a region no
pass reached — the shape the behind-the-boss bug had), and it is
geometry-independent in a way no choice of radius was: metal nothing cut stands
at stock, whatever the ladder looks like.

**Where the window goes is measured, and needs both halves:** the longest
stretch where roughing already machines to within one depth of cut, AND where
roughing demonstrably cut (the intact surface stands a depth of cut below the
stock).

- Without the first, a mid-span window lands behind a boss or on a wall and
  removing it changes nothing — **missed on current_work, 15_2, 15_3, 15_4**.
- Without the second, a stretch where the STOCK already sits near the target
  counts as well machined and breaking it removes nothing that was there —
  which is how **testing_15_3** slipped through.
- With both: **21 of 21**.

Choosing where to break it from the intact program is not circular — the
detector is never told where to look, only asked whether it noticed.

**And it now runs on every demo project that can carry it**, not on one. The
16 that cannot are named with the reason: no polyline offsets in the XML, no
polyline roughing and finish pass, or rs274 refuses the program.

## The judgement that had to be made twice

Neither "more regions" nor "worse worst-excess" is sufficient alone:

- on current_work the worst excess is **1.7434 intact and 1.7434 after**,
  because the global worst sits on a feature the window never touches while the
  new metal appears elsewhere;
- on testing_14_inside a region already stands proud, so the new metal merges
  into it and the **count does not move**.

The assertion is that the report gets worse in *either* reading.

## The limitation that stands, and is now written down

**This gate cannot see a single missing pass on most geometry.** That is not a
threshold to tune: in the redundant case the metal genuinely is not there to
find, and in the narrow case it is indistinguishable by width from a nose
fillet. `test_x_continuity` is what catches a missing pass — and it, not this
file, is what caught the missing pass behind the boss on testing_15_6.

The two gates are complementary and neither replaces the other. Believing
otherwise is what this file's docstring previously invited.

## Verified

`test_leftover` (21/21 control), `test_all_projects`, `test_x_continuity`,
`test_behind_boss_ladder`, `cam_map`, flake8 on both lists. Runtime about 4
minutes; it generates one program per project.

## Not changed

No G-code path, and no detector threshold. The only production-side finding is
recorded, not acted on: `leftovers()` models the stock from the moves it is
given, so a mutilation that removes the outermost pass also lowers the modelled
stock. It was measured and is **not** what caused this — fixing it changed
nothing, 7 of 21 either way — but it is a latent wart in a measurement helper.
