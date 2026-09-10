# 125 — commit B changed the thinning rule and left its guard asserting the old one

**Found**: 2026-09-10, by the dead-driver sweep greatEndian asked for -
`test_arc_endpoint` exits 1. Not a dead driver: it runs, and it is a
**regression I introduced and did not catch**.

`analysis/119` (commit `2967a71`) replaced `_min_segment`'s blanket
`2.4 * nose_r` with the per-corner shrink. `test_arc_endpoint` exists to guard
exactly that function and was **not in the list of gates I ran**. It passed
before `2967a71` and failed after.

## What it was really saying

Three assertions failed, and only one was a genuine problem with the test.

```
the arc is still thinned, not returned whole            22 of 22 points kept
   and the only segment under the limit is the protected one   shortest 0.4711
   and the shortcut misses the corner by about 0.94 mm  measured 0.4712
```

The first two encode a **point count** as the safety property, with the reason
written beside them: *"protecting corners is not a way to smuggle every
densified chord back in, which would put the short segments that abort a
compensated pass right back where they were."*

That worry is exactly right - it is the failure commit B hit on its first
attempt, when protecting every on-profile point aborted `testing_13_arcs` with
"concave corner cannot be reached". But the MEASURE was wrong. Under the
per-corner rule 22 of 22 is the correct answer: each of those chords is long
enough for its own corners, which is the actual thing compensation requires.

So the count assertion is replaced by the physical one:

    no kept segment is shorter than its own compensation shrink,
    R*tan(deficit/2) at each end

derived in the test rather than by calling `_shrink_need`, so it is not
checking the implementation against itself.

The third, the 0.94 mm shortcut, is a magnitude that legitimately moved: more
of the arc survives unprotected now, so the shortcut from the last surviving
vertex is **0.4712 instead of 0.9386**. Half the damage, same fault - the
endpoint is still dropped without `protect`, which the test still asserts and
which still passes.

## A wrong turn in the repair, recorded

My first edit inverted the unprotected assertion to "the endpoint is present
without protection too". Wrong: `thin` is REASSIGNED between the two blocks, so
the "22 of 22" I was reasoning from was the PROTECTED result. Unprotected, the
endpoint is still dropped - which is the whole point of the test. Restored.

## The real lesson

**I ran 16 of 72 drivers and called the suite green**, repeatedly, across nine
commits. `test_arc_endpoint` is the guard on the exact function commit B
rewrote, and nothing in my routine touched it. The sweep that found this was
commissioned for a different reason - stale harnesses - and found a live
regression instead.
