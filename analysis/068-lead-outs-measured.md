# 068 — what the roughing lead-outs actually cost

**Asked**: greatEndian, 2026-08-31 — *"measure lead outs first"*, after
`analysis/067` left them as the bulk of the remaining air.

## The measurement, roughing passes only

| case | roughing feed | retreat leads | of which cut metal |
|---|---|---|---|
| Artificial front→back | 1352.9 mm | **266 × 1.0000 mm = 266.0 mm** | **0.0 mm** |
| Artificial back→front | 1359.6 mm | 2.0 mm air | **304.6 mm** |
| Both directions | 1556.5 mm | 339.6 mm air | 37.1 mm |
| Natural, testing_15_5 | 1144.4 mm | 45.0 mm | 0.0 mm |
| Natural, testing_15_2 | 530.0 mm | 27.0 mm | 0.0 mm |

Front to back, **every one of the 266 lead-outs is exactly 1.0000 mm, purely
outward in X, and removes nothing at all** — 19.7% of the roughing feed
distance.

Back to front is the opposite and must not be touched: its retreats ARE the
climbing profile-angle ramp (`pa_out`), which cuts 304.6 mm. Dropping that is
what once left a 0.4255 mm tooth at the top of every level on a taper.

## Turning them off, measured

`param_lo_len=0`, `param_lo_rad=0`, Artificial front to back:

| | roughing feed | air leads | rapids | rapids in standing metal |
|---|---|---|---|---|
| lead-outs on | 1352.9 mm | 275.0 mm (20.3%) | 4574.8 mm | none of 799 |
| lead-outs off | **1086.9 mm** | 9.0 mm (0.8%) | 4928.1 mm | none of 799 |

- **266.0 mm of feed removed**, exactly the 266 × 1.0 mm.
- Leads that cut metal are **identical**: 54 moves / 67.9 mm either way. Nothing
  the lead-outs remove goes unremoved.
- Rapid distance rises 353.3 mm, because the retract now starts at the cut end
  instead of 1 mm clear of it. Total distance is therefore slightly HIGHER
  (5927.7 → 6015.0 mm) — the gain is that 266 mm moves from feed rate to rapid
  rate, not that the tool travels less.
- No rapid enters standing metal either way.

## What is NOT settled by measurement

Geometrically the lead-out is removable. Whether it should be removed is a
machining-practice question: it backs the tool away from the end wall at a
controlled feed before the rapid, which is what avoids a witness mark at the
stop point and lets a deflected tool recover before direction changes. The
numbers cannot decide that, so it is greatEndian's call.

## Two instrument faults, both found before any conclusion was drawn

**The finish passes were in the retreat bucket.** `m.op == 'Lathe Polyline'`
alone includes the pre-finish and finish contour passes, whose long moves are
not level cuts and do not precede one, so they classified as retreats — a
**35.0032 mm** "lead-out" was the giveaway. On testing_15_2 that is 170.9 mm of
the 700.9 total. `not m.subs` is required for the classification.

**But NOT for the material model.** Filtering the finish out of the model as
well made a legitimate rapid over finish-cleared ground read as a 0.2842 mm
collision, and a lead-outs-off run report 10.4974 mm. The material state must
take EVERY cut; only the reporting is roughing-only. Both numbers vanished once
the two concerns were separated.

## Correction to analysis/066 and 067

The "roughing feed" figures quoted there — 1951.1 → 1540.6 mm and the rest —
include the pre-finish and finish contour passes. The comparisons are valid,
because both sides use the same definition, but the label is wrong: the
roughing-only figures for Artificial front to back are 1352.9 mm with the
current gate. The "273.6 mm of retreat air" quoted at the end of 067 is
likewise inflated by finish moves; the roughing-only figure is **266.0 mm**.

---

## Built: a parameter, not a behaviour change

greatEndian chose *"Make it a parameter"*. `PARAM_LO_AIR` — **Skip lead-out in
cleared metal**, Off=0 / On=1, default **Off**, `cfg/lathe/polyline.cfg` at
version 1.66, threaded as the global `#<_pl_lo_air>`.

**What On tests**: that a shallower pass has already run over this ground, so
the column the retreat rises into is cleared. Sectioned, that is this window's
own `#2800` record — which still holds the PREVIOUS pass's level at that point,
because a pass writes its own only after it cuts. Unsectioned, `_pl_prev_lvl`
says the same thing. 999999 means the window has cut nothing yet, so its first
pass keeps its lead-out.

**FORWARD PASSES ONLY, and that bound is measured.** The test says only that a
shallower pass has run, which is enough for a forward pass — its retreat
RETRACES the cut just made. A reversed pass retreats at the *other* end, the
entry-contour end, where nothing of the sort follows. Applied there it took the
roughing feed from 1359.6 to 1110.6 mm and put **2 of 799 rapids 7.5622 mm into
standing metal**. Bounded to `_pl_cut_rev LE 0`; in Both directions the reversed
half simply keeps its lead-outs.

The climbing profile-angle ramp is emitted by its own `pa_out` block and nothing
here can reach it, so back-to-front keeps the 304.6 mm its retreats really cut.

### Measured, roughing passes only

| case | Off | On | rapids in standing metal, On |
|---|---|---|---|
| Artificial front→back | 1352.9 mm | **1103.9 mm** (−249.0) | none of 799 |
| Artificial back→front | 1359.6 mm | 1359.6 mm — declines | 60 @ 0.0042, pre-existing |
| Both directions | 1556.5 mm | **1435.5 mm** (−121.0) | none of 799 |
| Natural, testing_15_5 | 1144.4 mm | **1103.4 mm** (−41.0) | none of 136 |
| Natural, testing_15_2 | 530.0 mm | **505.0 mm** (−25.0) | none of 82 |

**The leads that cut are identical On and Off in every case** — that equality is
the whole proof that nothing goes unremoved, and `test_air_leads.py` asserts it
as a pair rather than as two separate numbers.

Off is byte-for-byte the original motion, so a project that does not ask for
this sees no change at all.

### The old expectations in test_air_leads were wrong, and are corrected here

They counted the pre-finish and finish contour passes as roughing feed. The
roughing-only figures are the table above; the assertions now use them, and the
material model still takes every cut because the metal a finish pass removes is
gone regardless of what the report counts.
