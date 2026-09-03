# 088 — the blocked-everywhere part, and what it broke

**Asked**: greatEndian, 2026-09-03 — *"create the blocked-everywhere test
project"*, the case `analysis/087` named as the one that would settle whether
"phase 1 has depth" implies "phase 1 cuts something".

## The part, and why it is constructible

`ceiling()` **excludes points at or above the stock diameter** - a point at full
stock is raw material, not a feature to protect, and counting it would collapse
the ceiling to stock on almost any real profile.

That is the lever. Leave the **front section at full stock diameter** and put
the machined step behind it:

```
stock OD 70          70 dia from Z0 to Z-20     <- raw, excluded from ceiling
                     60 dia from Z-20 to Z-60   <- the step, sets the ceiling
                     70 dia at Z-60 to Z-70     <- closing wall
```

The ceiling comes from the 60 dia step, so phase 1 gets real depth - **r31.0160
against a start of r35.0000, 3.984 mm** - while the window start sits in solid
stock, so every phase-1 level is blocked at `w_from`.

`configs/.../projects/testing_15_blocked.xml`.

## What it fires

The `o<p1_none>` branch, `poly_lathe_mill.ngc:1035` - one of the three
`sect_top_r` mutation sites `analysis/086` measured as firing **0 times over 30
configurations**:

```
handover sites fired: 1=3  2=0  3=0
3 of those actually MOVED sect_top_r
   15_blocked s1 d0/d1/d2  site1  31.0160 -> 34.5720  (3.5560)
```

**So 086's "0 of 30" was a property of the sample, not of the code**, and its
suggestion that the handover "may reduce to nothing" is retracted. It does not
reduce to nothing: the runtime moves the ceiling 3.556 mm and phase 2 starts
from the moved value.

## What it breaks

```
test_ladder_account   FAIL  off-ladder levels the O-code walks: [35.072, 35.572]
                            phantom levels predicted: 31.524 .. 34.064  (6)
test_level_intervals  FAIL  'walk should continue to -25.6868' at level 34.572
test_level_blocked    pass  3496 of 3496
test_sub_spans        pass
test_roughing_windows pass
```

Both predictions are fed the **generation-time** ceiling, 31.0160, while the
runtime walks phase 2 from 34.5720. The ladder therefore misses the levels the
O-code really visits - 35.072 and 35.572, both ABOVE the start radius - and
invents six it never touches.

The three gates that do not consume `sect_top_r` are untouched. The failure is
localised to exactly the two predictions that read it, which is the pattern
that makes the diagnosis trustworthy rather than alarming.

## Gate one passes on a part where gate two fails

`test_ladder_python` **passes** here. It checks only that CUT levels lie on the
ladder, and 35.072 / 35.572 are walked but never cut. That is the asymmetry
`analysis/081` was written about, now demonstrated on a real part instead of
argued: containment one way is not containment both ways.

## Two mistakes of mine on the way, both caught by measuring

1. **A fabricated bug, nearly reported.** The first build left `Final Diameter`
   at 38 mm while the profile bottoms out at 60, asking for ~31 levels below
   anything the part has. The program then did not finish in 120 s and I was one
   step from reporting "the blocked-everywhere profile hangs the interpreter".
   With the diameter corrected it runs in **under a second, 21528 canon lines**.
   There was no hang and no O-code defect - the defect was in my project.
2. The XML carries a stale `metric_value` - `param_od` reads `value`
   2.7559055118 (70 mm) beside `metric_value` 50.0, and the generated program
   uses 70. `value` is authoritative; it was settled by generating and reading
   `_wp_dia_od` back, not by trusting either attribute.

## Left deliberately visible, not green

The project stays in **all five** gates. The two that cannot yet predict it
carry an explicit `SKIP` entry naming the reason and this analysis, and print

```
SKIP  testing_15_blocked.xml - the phase-1 handover moves sect_top_r
      31.0160 -> 34.5720 and these predictions read the generation-time
      ceiling - analysis/088
```

on every run. Deleting the project from those two would have made the suite
green and buried the finding.

## What would close it

The handover is predictable in principle: `level_blocked` already answers, per
level, whether phase 1 can cut anywhere - and it agrees with the O-code on all
3496 calls including this part. Feeding that back into `roughing_ladder` so the
ceiling it uses is the one the runtime will arrive at is the fix. That is a real
piece of work, not a parameter change, and it is the thing standing between here
and a `.ngc` that only walks tables.
