# 074 — modelling the holder RESTRICTS the reachable contour. I had it backwards.

**Asked**: greatEndian, 2026-09-03 — *"take the shank into flank_envelope and
measure"*.

## What I predicted, twice, and got wrong

I told greatEndian that modelling the holder would **recover** some of the
10.0899 mm left uncut behind the boss — that far behind an obstruction the
shank is a constant-height block and therefore less restrictive than an
ever-growing wedge.

**The measurement says the opposite.** Across testing_15_2, _15_4 and _15_5,
sampled at 601 points along the reachable contour:

| project | ON lower than OFF | ON HIGHER than OFF |
|---|---|---|
| testing_15_2 | **0 samples** | 360, up to **2.2288 mm of radius** at Z−69.58 |
| testing_15_4 | 0 samples | 360, up to 2.2288 mm at Z−69.58 |
| testing_15_5 | 0 samples | 360, up to 2.2288 mm at Z−69.58 |

The holder model is **never** less restrictive and is up to 2.23 mm MORE
restrictive. It does not give the 10 mm back; it takes a little more.

## Why — and the physics is on the measurement's side

The shadow bound is `env >= rp - d·kk`, and it **decreases** with distance: a
far obstruction imposes a weak bound. I had described the wedge as growing,
which is the wrong way round.

So an unbounded wedge lets the nose sit further and further below a distant
obstruction — 13.6 mm below one 59 mm away, on a 13° flank. A real holder
cannot do that. Its block face sits a fixed **12.0946 mm** below the nose
(measured, 25.4 mm shank, nose R0.4, I15 J75), so past about 52 mm the flat
floor `rp - 12.09` is HIGHER than the wedge's `rp - d·kk` and becomes the
binding constraint.

**The infinite wedge was optimistic at long range, not pessimistic.** It let
roughing dive where a 25 mm holder would foul. The correction is a safety
improvement that costs material, not a productivity one.

## What was built

Three regimes in `flank_envelope`, in place of two:

```
d <= insert reach   the wedge:  rp - d * kk
reach < d <= l1     the BLOCK:  rp - drop      (flat)
d > l1              nothing - the holder has ended
```

`drop` and `l1` come from `ncam_preview.tool_shank` and `shank_dims`, published
by `to_gcode`'s walk like `WORKPIECE_FACE_Z` and `TOOL_NOSE_R`, so the contour,
the drawing and the collision check cannot describe three different tools.

**The wedge ends at the INSERT's own edge length**, derived from the shank —
not at the Tool Change flank length. That distinction matters: the flank length
is what `FLANK_BOUNDS_CONTOUR` used, and that was withdrawn in `310a06b`
because it makes the obstruction stop constraining altogether. Here the wedge
ends and the block takes over, which is a different claim.

Verified in the emitted tables: every contour gains exactly one point
(fc 20→21, entry 34→35, stop 36→37, reachable 6→7) — the flat floor's
breakpoint — and the wedge ends at 11.63 mm, which is 12·cos(13°) = 11.69 to
within the contour tolerance.

## OFF BY DEFAULT, and unchanged

`FLANK_SHANK_BOUNDS` is False. Motion hashed against the `analysis/071`/`072`
baselines: `6cf361a8b8f5`/1575, `e2744cbb6ff0`/327, `128ebb273ba5`/458 — all
three projects, all three directions, byte-identical. An environment override
exists **only** so the model can be re-measured without editing the file, since
generation runs in a subprocess; it can only switch the model on.

## Two instrument faults on the way

**The first comparison measured nothing.** I guessed `_pl_flank_base` /
`_pl_flank_n` for the envelope table; neither exists. It reported 0 points both
ways and would have read as "no change" had the move counts not moved. The real
names are `_pl_res_*` for the reachable contour.

**The move counts alone were misleading.** Feeds fell by exactly 23 on all
three projects, which looked systematic rather than geometric and nearly sent
me chasing a phase being dropped. It was neither: sampling the contour is what
answered the question, and the identical delta is just the three projects
sharing a tool and a stock diameter.

## The decision this leaves

Not mine to take. The model is more correct and cuts less:

- **ON** — roughing stops where a real 25 mm holder actually clears. Costs
  2.23 mm of radius behind the boss on these three parts.
- **OFF** — today's behaviour, which lets the tool reach 2.23 mm deeper than
  the holder allows at long range. Whether that ever fouls in practice depends
  on the setup, and greatEndian has said the material behind the boss is
  unreachable anyway.

Recorded in `openPoints.md` for greatEndian's call.

## Still unknown

- Whether the 2.23 mm the model removes is material that would ACTUALLY have
  fouled, or whether the `drop` derivation is conservative. That wants a real
  cut or a collision-check run, not more geometry.
- Only the trailing flank was reasoned about. The leading flank gets the same
  three regimes automatically, and nothing here measured whether that is right.
