# 102 — the flat roughing connected: Python writes every roughing call

**Asked**: greatEndian, 2026-09-04 — *"go on with the second definitions
pass"*, then *"go on with the wiring"*.

## The result

```
36 configurations, flat sub emitted in 36
MOTION IDENTICAL - the flat roughing moves as the loop does
```

With `NCAM_FLAT=1`, `poly_lathe_mill`'s entire window / sub-span / level /
interval nest is skipped and the machine follows calls Python wrote. The motion
is identical on every configuration, including `testing_15_blocked`.

**Default is unchanged**: `NCAM_FLAT` unset means `_pl_flat_sub = 0`, no sub is
emitted, and the loop runs exactly as before. Opt-in until it has cut metal.

## The pipeline change that made it possible

Definitions were collected DURING the walk, before a feature's children - so a
polyline did not yet know its own shape and `resolve_points` came back empty
(`analysis/101`). They are now collected in a **second pass after the body
walk**. They are prepended to the program either way, so the emitted order does
not change; what changes is that a feature's definitions can see its own
geometry.

Gated where it matters, because this touches every machine:

```
IDENTICAL 36 lathe
IDENTICAL mill+plasma
```

The `short_id` risk was real and does not bite: only `polyline.cfg` uses `#ID`
in `[DEFINITIONS]`, and it uses it in the body too, so no feature depends on
definitions to assign its id and the numbering is unchanged.

## Decide during the walk, emit in the second pass

Swapping the passes inverted the roles. The `[AFTER]` block now CLAIMS the sub -
first polyline that can have one - and records the claim **with its feature
id**; the definitions pass emits for that id and no other. One global name, one
sub per program, and a second polyline neither arms nor emits.

## The gate caught its own staleness

First run after the wiring worked reported `flat sub emitted in 0` and refused
to pass. The wiring was fine; the GATE's detector still looked for the numbered
form `o9\d+ sub` from the abandoned design. Without that zero-count check it
would have compared 36 pairs where both sides ran the loop and reported MOTION
IDENTICAL - a convincing pass proving nothing.

Fourth time in this session a zero-count assertion caught an instrument
measuring nothing. It should be the default in every probe.

## What this does NOT do

**The `.ngc` has not shrunk - it has grown.** Every migration kept its fallback.
Deleting the loops, the stage bookkeeping and `lathe_level_next_start`'s scan is
the payoff, and it waits until the flat path has cut on the machine.

Nothing here has cut metal. Every claim in `analysis/080`-`102` is against
`rs274` simulation.
