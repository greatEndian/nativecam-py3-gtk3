# 120 — the "front-face reach" was two instrument faults and one real 18 um gouge

**Asked**: greatEndian, 2026-09-09 — *"go on with the front-face reach"*, the
open point `analysis/119` left: `testing_13_arcs` mode 1 reporting 2 uncovered
segments because "its finish pass stops at Z-2.6788".

**The premise was wrong.** The pass does not stop at Z-2.6788. It machines the
whole front face, and -2.6788 was merely the first point the prover happened to
SAMPLE as tangent.

## What is actually there

The path over the front flat, read out of the run:

```
feed  Z  0.4000  R 8.4000     <- start, one nose radius clear of the face
feed  Z -2.6375  R 8.4000     <- one 3 mm straight, the whole flat
```

The flat is R8.0000 and the nose is R0.4000, so a centre at R8.4000 is exactly
tangent along its entire length. The face is cut correctly.

**Fault 1 - coverage was sampled only at move endpoints.** `sample_moves`
densely samples arcs and takes only the two ends of a straight, so that 3 mm
feed contributed no coverage between them and segment 0 read as never touched.
Densifying straights for the coverage pass clears it.

**Fault 2 - an unreachable corner would have been reported as a failure.** The
R4 arc is centred at (-7, 8) and so leaves the flat PERPENDICULAR: an **87
degree internal corner** at (-3, 8). A round R0.4 nose cannot enter it and
leaves a 0.4 fillet. `prove_region` now separates "unreachable by this nose"
from "uncovered", judged by construction - walk the segment, place the nose a
radius out along its own normal, and ask whether ANY placement clears every
other segment. If none does, no toolpath could have covered it.

As it happens segment 1 is NOT exempted by that test, because its upper end
*is* reachable - which is what turned the remaining miss into a real finding.

## The real finding: a systematic 18 um gouge at a chorded internal corner

The tool stops at **Z-2.6375** where the true corner position is **Z-2.6182**,
and gouges the fillet by **0.0183**.

The cause is exact and has a formula. Compensation puts the tool at the
intersection of the two offset segments. The true arc leaves (-3, 8) vertically,
but the first CHORD leaves it 2.87 degrees off - half its 5.73 degree angular
span, which is what MESH_MAX_SAG 0.005 gives on R4. Tilting the offset line by
that angle moves its intersection along the flat by

    R_nose * sin(theta / 2) = 0.4 * sin(2.87 deg) = 0.0200

against 0.0183 measured. Both symptoms - the gouge and segment 1 never coming
tangent - are this one displacement.

It is not the chord sagitta (0.0048 here) and finer densification only helps
linearly. It applies at **every corner where a chorded arc meets another
surface**, not just this project, and the cheap targeted fix would be to
subdivide the first and last chord of each arc more finely than the middle,
since those are the only ones that meet neighbouring geometry. Left open: it
costs points in ENTRY, which sits at 200 of 280 after `analysis/119`.

## Scoping the instrument fix, and why

Densifying the sample set for EVERYTHING moved gouge figures too -
`testing_15_3` 0.0110 -> 0.0176, and `testing_14_inside_nat` 0.3621 -> **4.0952**.
That last is not a discovery; it is `profile_bound` taking the outermost radius
on a multi-valued profile, the weakness `analysis/116` already recorded when a
first attempt at a surface-equality gate flagged 4.94 mm on the ID projects.

So the densification is used for **coverage only**. Coverage is a question about
the path's whole length; the gouge figure is a question about where the tool
actually was, and densifying that would quietly restate every number this proof
has ever reported. Verified: after scoping, `testing_15_3` reads 0.0110 and
`testing_14_inside_nat` reads 0.3621 again - identical to their `analysis/116`
baselines - and only the coverage counts move.

## Verification

| project | before | after |
|---|---|---|
| `testing_13_arcs` | 2 uncovered | **1** uncovered, gouge 0.0183 unchanged |
| `testing_15_3` | 26 uncovered, gouge 0.0110 | 25 uncovered, gouge **0.0110** |
| `testing_13_arc_first` | PASS | **PASS**, both modes |
| `testing_9_1` | PASS, gouge 0.0000 | **PASS**, gouge 0.0000 |
| `testing_14_inside_nat` | gouge 0.3621 | gouge **0.3621** |

The wrong-side negative control still FAILS on every one of them, so the proof
has not been made vacuous by the exemption. No generation code changed - this
commit touches only the verification script - so no motion moved.

## Still open

- The 18 um corner gouge above, with its formula and its candidate fix.
- `testing_13_arcs` is now one segment from a native-comp PASS, and that one
  segment is the corner the gouge sits in. The two close together or not at all.
