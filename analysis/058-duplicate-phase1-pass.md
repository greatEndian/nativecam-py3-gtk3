# 058 — The duplicate phase-1 roughing pass

greatEndian, 2026-08-17: *"fix the duplicate roughing pass"*. Found in
`analysis/057`, pre-existing in BOTH roughing directions, and present since
long before the back-to-front work started.

## What was wrong

`lib/lathe/poly_lathe_mill.ngc`, the phase-1 level loop `o<wh_lvl> while [1]`:

```
iter 1   lathe_level_pass from w_from=0    -> cut Z0 .. -31.209
         not blocked, resume found at -34.171
         -> _pl_ph1_front_cut = 1, _pl_ph1_z_end = -31.209, ph1_fin = 1
         -> l_fr = -34.171, loop
iter 2   lathe_level_pass from -34.171     -> NO CUT, _level_blocked
         -> "nothing was cut at all"       -> _pl_ph1_front_cut = 0
         -> o<wh_00> break
```

The comment on that branch reads *"nothing reachable from w_from itself - stop
here, nothing was cut at all so phase 2 must still do this exact radius
fresh"*. **That is true only on the FIRST iteration.** On a later one the first
interval has already been cut and the flag has already been set to 1. Zeroing
it makes phase 2's window redo the whole radius, so the front interval is cut
twice with a full retract between — the second time in air.

`#<ph1_fin>` could not be used as the guard: it is deliberately not reset per
level (comment at ~line 830 — resetting it once dropped the sectioned program
from 44 level cuts to 9).

## The deeper cause: the block is a disagreement about WHERE, not WHETHER

The minimal fix — don't zero the flag on a later iteration — leaves phase 1
handing over half a level. Investigating why iteration 2 blocks at all gives a
better answer:

- `lathe_level_next_start`'s **scan** answers `-34.171`, which lands just
  *inside* the rise it found. Clear ground starts at `-35.000`.
- `lathe_level_pass` starting there finds the profile already above the level
  at its own start, and reports blocked.
- The resume **envelope** answers the same question and lands clear, at
  `-34.600`. That is the pick phase 2's own blocked branch already uses, and it
  is where phase 2's window cut from.

So the block does not mean "there is no more to cut"; it means "that resume
point is unusable". The fix retries from the envelope pick, searching from the
last CUT end rather than from the unusable resume point, and **finishes the
level in phase 1** instead of handing half of it over.

A progress test stops that from looping: a candidate not past where the blocked
pass already started is refused, so the same point cannot be retried forever.

**This is why the fix holds in both directions**: it never consults the window
table, which is the thing that differs between them.

## Measured

Cut lists dumped per project/direction from a worktree at `1c5e256` (with its
own copied config — see the trap in `057`) and from the working tree, then
compared as multisets:

```
testing_15_6 f2b   45 cuts / 44 distinct  ->  44 cuts / 44 distinct
testing_15_6 b2f   45 cuts / 44 distinct  ->  44 cuts / 44 distinct
testing_15_5 f2b   47 cuts / 46 distinct  ->  46 cuts / 46 distinct
testing_15_5 b2f   47 cuts / 46 distinct  ->  46 cuts / 46 distinct

SET lost 0, SET gained 0   in all four cases
duplicates before 1, after 0
   was duplicated:  X34.0636  Z-31.209 .. 0.000  x2      (testing_15_6)
   was duplicated:  X33.1273  Z-30.147 .. 0.000  x2      (testing_15_5)
```

**Lost 0 and gained 0 is the assertion that matters.** It says a duplicate was
removed and not a pass — the difference `test_x_continuity` exists to police,
and the failure mode that would leave metal standing.

`cuts == distinct` now holds, which it never has in this work: the "45 cuts, 44
distinct" arithmetic quoted through `analysis/054`, `055`, `056` and `057` was
this bug all along.

## The gate

| item | result |
|---|---|
| duplicate gone, both directions | **PASS** — 45→44 and 47→46 |
| cut SET otherwise unchanged | **PASS** — lost 0, gained 0, four cases |
| `test_leftover` | **PASS** 46/46, control fired 21 of 21 |
| standing metal unchanged | **PASS** — 0.7219 / 0.8579 / 0.6473 / 0.5681, identical between directions |
| `test_x_continuity` | **PASS** 17/17, worst gap 0.0000 in all four combinations |
| overcut past the pre-finish contour | **PASS** — 0.0503 both directions (bound 0.08), 107 rough moves each |
| tangency | **PASS** — min \|dot\| 1.00000 over 128059 canon events |
| O-code syntax (nested parens, unclosed comments, bracket balance, CR) | **PASS** — 0 problems |
| `cam_map` / `test_lathe_validation` / flake8 | **PASS** 6/6 / 40 calls / clean |

Standing metal being **bit-identical** is the confirmation that the removed
pass was cutting air. Had it been removing metal, dropping it would have shown
up here immediately.

`test_x_continuity`'s pass counts move exactly where they should: sectioning ON
drops 47→46 and 45→44, sectioning OFF is unchanged at 45 and 42 — the duplicate
is a phase-1/phase-2 artefact and only exists when sectioning is on.

## The bonus that did NOT land

`analysis/057` left the interval order at 15 of 16 back-first, the residue being
X34.0636 — whose leading interval was this duplicate. The expectation, written
into the brief, was that removing it would close that at **16 of 16**.

**It did not.** Measured after:

```
X34.0636  b2f  [-31.21 -> 0.00] [-68.89 -> -35.00]      still FRONT-first
b2f multi-interval levels: back-first 15, front-first 1
```

The duplicate is gone (three intervals became two), but the level is still not
back-first, and now for a different reason: **phase 1 now finishes the level
itself**, cutting both intervals in its own front-to-back order, and phase 1 is
not window-driven, so `_sections_back_to_front` never sees it.

Not a regression — that level was not strictly back-first before either — but
the prediction was wrong and is recorded as wrong. Closing it would mean
teaching phase 1 about the emission direction, which is a separate change.

## Why it survived this long

The duplicate is invisible to every gate the project had:

- it removes no metal, so `test_leftover` cannot see it;
- it duplicates an existing pass rather than deleting one, so
  `test_x_continuity` cannot see it;
- it cuts inside the pre-finish envelope, so the overcut probe cannot see it;
- it is tangent-continuous, so `check_tangent` cannot see it.

It surfaced only because `057` compared **cuts against distinct cuts** while
proving the two directions emit the same set — an arithmetic side-effect of a
different question. Four analyses quoted "45 cuts, 44 distinct" as a property
of the part before anyone asked why the two numbers differed.

**A count and a distinct-count are different measurements, and where they
disagree there is something to explain.**

## What is still unknown

- **Sectioning OFF is unaffected**, as expected, but the same
  scan-versus-envelope disagreement could in principle block a level there
  too. Not observed on any demo project.
- **The progress test is the risk surface.** It refuses a candidate not past
  where the blocked pass started. On a profile where the only usable resume
  sits exactly at that point, phase 1 would stop and hand over — which is the
  old behaviour, so it fails safe, but it has not been seen in practice.
- Whether other projects carry duplicates was being swept when the run that
  produced this change was interrupted; the four cases above are measured, the
  full 39-project sweep is not.
