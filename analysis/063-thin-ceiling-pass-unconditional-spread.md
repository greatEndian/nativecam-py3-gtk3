# 063 — The thin pass at the boss top, removed unconditionally

2026-08-24. `liveTooling`. Follows `analysis/061` and `analysis/062`.

## What was asked

greatEndian, after checking
`configs/sim/axis/ncam_demo/ncam/catalogs/lathe/projects/testing_15_6.xml`:
*"thin pass is present there .. fix it"*.

## What the project actually holds

Read out of the saved XML rather than assumed:

| parameter | value |
|---|---|
| `param_pf_off` | **0.30** metric — the default pre-finish offset |
| `param_skip_thin` | **0.0** — the shipped skip is OFF |
| `param_pass_from` | 1, Final contour |
| `param_sectioning` | 1, on |

So this is the case `analysis/061` measured and left as a call: the phase-2
ceiling remainder at **0.2591**, which is 0.51 × the 0.5080 depth of cut and
therefore **survived** the `< doc/2` spread trigger by 0.0051 mm. 061 recorded
it as *"NEEDS A CALL if that pass is still unwanted: the threshold is the dial
and wants a number, not a nudge."* greatEndian's answer is that it is still
unwanted.

## The fix, and why it is not a new threshold

The threshold was never the real question. **The remainder-on-the-first-pass
rule belongs to a ladder that starts at the stock**, where the leftover lands
on a full-length cut through oversize material and a partial depth costs
nothing. Phase 2 does not start at the stock: its first pass sits ON the
section ceiling — the profile's highest point plus the roughing allowance — so
the leftover is taken tangent to the boss top, against the part, with the tool
rubbing rather than cutting. That is the wrong place for a partial pass **at
any size**, which is why nudging the threshold from 0.2540 to 0.2600 would have
been the wrong shape of fix.

And the size is not a property of the part. The ceiling floats continuously
with the pre-finish offset while the ladder is anchored on the floor, so the
leftover is `span mod doc` — anything from 0 to a full depth of cut.

So phase 2 is now spaced **evenly, unconditionally**, and `Space passes from`
no longer reaches it. The two anchorings still produce different ladders,
because anchoring reassigns `lad_tgt` to `anch_floor` at
`poly_lathe_mill.ngc:231` — the setting keeps its meaning through the ladder's
TARGET rather than through where its remainder falls.

The `o<p2_an>` if/else and the `o<p2_thin>` conditional are both gone; the dead
`#<p2_sgn>` initialiser with them. The block is 3 lines of arithmetic and a
comment.

## Measured, testing_15_6, min gap across the ladder

| pre-finish offset | before | × doc | after | × doc | levels |
|---|---|---|---|---|---|
| 0.00 | 0.4511 | 0.89 | 0.4582 | 0.90 | 29 → 29 |
| 0.15 | **0.1091** | **0.21** | 0.4207 | 0.83 | 29 → 29 |
| **0.30 — the saved project** | **0.2591** | **0.51** | **0.3832** | **0.75** | 29 → 29 |
| 0.60 | **0.0511** | **0.10** | 0.4109 | 0.81 | 28 → 28 |
| 1.00 | 0.4511 | 0.89 | 0.4165 | 0.82 | 27 → 27 |

**No level was dropped at any offset**, and the thinnest pass anywhere in the
ladder is now 0.75 × doc rather than 0.10. The pass also stops wandering: it
was 5th from the envelope at 0.15, 4th at 0.60 and 3rd at 1.00.

testing_15_2, which is also sectioned, moves from 17 gaps of 0.5080 to 17 gaps
of 0.4991 at the same 18 levels — the ladder every level of which greatEndian
was told would move.

## Gates

- `cam_map.py` — all six checks pass.
- `test_x_continuity` — worst over-step **0.0000** in all four configurations
  of testing_15_6, sectioned and not, both directions; and its own control
  still detects a deleted pass as a 1.0160 over-step, so the check is live.
- `test_sections` — all pass.
- `test_ladder` — see below.

## What `test_ladder` caught, which is a real fault and not this change

The calibrated control written earlier today asks for a threshold just above
the ladder's thinnest gap and requires that only the thin level goes. On a
**uniform** ladder there is no such threshold, and after this change the ladder
is uniform by construction: every gap on testing_15_2 is 0.4991. A threshold of
**0.5070 — which is UNDER the 0.5080 depth of cut** — is above every gap, so
every level is thin against the one above it and `_pl_skip_thin` alternates:
skip, `_pl_prev_lvl` stays, the next is two steps away and is kept. Result 13
levels and a **0.9983** gap.

That widens the hazard recorded in `analysis/062`, which said a threshold
larger than the *depth of cut* halves the ladder. It is the **ladder step** that
matters, and the step is always slightly under the doc. A clamp on the input at
the depth of cut would therefore not be enough; the skip has to refuse to open
a gap larger than a depth of cut. Recorded in `openPoints.md`, not fixed here.

The control was rewritten to guard the range the setting is shipped for — at
the recommended `doc/2` the ladder must stay whole — and to print the
alternating behaviour above the step rather than assert a property no uniform
ladder can have.

## Why it was not caught earlier

061 fixed the case it could measure — a leftover under half a depth of cut —
and left the case just over the line as a question, because greatEndian's rule
was stated as a threshold and applying it literally was the honest reading. The
miss was treating a stated threshold as the specification instead of asking
what the threshold was *for*. Once the question is "where may a partial pass
land", the answer does not contain a number at all.

## What is still unknown

- `_pl_skip_thin`'s alternating mode above the ladder step, above.
- The blindness at window boundaries from `analysis/062` is unchanged: the
  spread removes the passes it would have been asked to catch, so it still has
  no live symptom on these projects.
