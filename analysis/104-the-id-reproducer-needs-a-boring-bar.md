# 104 — the ID gouge needs a boring bar to see, and two wrong diagnoses first

**Asked**: greatEndian, 2026-09-04 — *"fix the prover on ID work"*.

## The prover did not need fixing. I misdiagnosed it twice.

**First wrong call**: `testing_14_inside` has `n_comp = 0`, so I declared the
reproduction invalid. It does not matter - `prove_cam_comp` OVERRIDES the
project when it generates (`n_comp 2, op 2, one finish pass, no pre-finish`),
so it always tests In-CAM finishing whatever the project saved.

**Second wrong call**: identical results across three reproducers looked like an
instrument that could not discriminate. Same cause - all three were tested as
In-CAM, so identical is the CORRECT outcome.

Both are corrected in `analysis/103`. I reached for "the instrument is
untrustworthy" - true four separate times earlier that day - without first
reading what the tool does to the project.

## The third reading, which the measurement supports

`testing_14_inside` uses **T2 - a Q2 OD turning tool - on inside work**. The
profile is a stepped bore:

```
seg 0  Z0      r17  ->  Z-20  r17
seg 1  Z-20    r17  ->  Z-20  r12      the step
seg 2  Z-20    r12  ->  Z-40  r12
seg 3  Z-40    r12  ->  Z-40  r10
```

The emitted path runs the first bore correctly at nose centre r16.6 - exactly R
inside a r17 wall - then cuts ONE DIAGONAL to r11.99, leaving segments 1, 2 and
3 untouched. That is not a compensation fault: the finish passes follow the
REACHABLE contour, and an OD tool cannot reach into that step. The prover
measures against the DRAWN profile, so it reports the shortfall as uncovered
segments.

## With a real boring bar, the actual defect appears

`testing_14_inside_bar.xml` - the same part with T14, a right-hand boring bar,
Q3:

```
                    T2 (OD tool)          T14 (boring bar)
offset vector       (0.4000,  0.4000)     (0.4000, -0.4000)
tangent points      2                     42
segments uncovered  3                     0
contour gouge       0.3542                0.8000
```

Full coverage, and a gouge of **exactly 2R** - the nose sitting a full diameter
into the wall. That is the shape of the recorded ID gouges, and this is the
first clean reproducer for it.

**Still not settled**: the wrong-side control also gouges 0.8000, so the proof
cannot yet separate a genuine side error from something else on a bore. That is
the next question, and it is a real one rather than the assumed instrument
fault I twice reached for.

## Kept

`testing_14_inside_bar.xml`. The `_cam` and `_nat` reproducers are pointless -
the prover overrides `n_comp` - and are left only because deleting them would
lose the record of why.

## The lesson worth keeping

Three readings of one failure, two of them wrong, and each was resolved by
reading what the tool actually does rather than by reasoning about what it
should do. The project's own tool number was the answer to a defect I had
already blamed on the instrument twice.
