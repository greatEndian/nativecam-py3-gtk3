# 127 — the verification skill passed a program that aborted

**Found**: 2026-09-11, by finally invoking `/lathe-gcode-verify` as a skill
instead of running its scripts by hand. That was the process debt I had flagged
three times and not paid; paying it turned up two faults in the verifier
itself.

## Fault 1 — "error" matched inside comments

`check_nose_tangent.py` and `prove_tip_comp.py` both did:

```python
if 'error' in canon.lower() and 'error_code' not in canon.lower():
    print('[VERDICT: FAIL - interpreter errors ...]')
```

A substring search over the WHOLE canon. This codebase comments heavily, so any
program carrying a line like *"COMPILE error and exec_callback discards the
whole block in silence"* failed instantly. Measured: `testing_8` runs clean at
156 moves and was reported as "interpreter errors".

`check_tangent.py` and `test_facing.py` already filtered per line and excluded
`COMMENT(`. The other two now do the same, and print the offending line.

## Fault 2 — the serious one: an aborted run was verified and PASSED

`run_rs274` raised only when rs274 produced **no output file**. An interpreter
error part way through truncates the canon and leaves it looking perfectly
well-formed - the toolpath simply stops - so every check above it measured a
partial path and reported a confident PASS.

Measured, on `testing_13_arcs` under native compensation, which aborts at
"Straight feed in concave corner cannot be reached":

```
check_tangent  ->  Parsed 2383665 canon events
                   Tangent continuity: min |dot| = 1.00000
                   [VERDICT: PASS]
```

**A program that refuses to run passed the gate**, on 2.38 million events of
partial motion.

`ncam_preview` has had this right all along, and says so in a comment:
*"Ignoring the exit code showed a partial path with a confident 'N cutting
moves' under it, which is the worst of both: wrong, and reassuring."*

### Why the exit code, and why -t matters

Measured both ways:

```
good    -t absent  rc=0   canon 34383
good    -t present rc=0   canon 34381
aborts  -t absent  rc=0   canon 2404851      <- abort INVISIBLE
aborts  -t present rc=1   canon 2402449      <- stderr names the line
```

The exit code only carries the abort when the tool table is passed, which is
why `ncam_preview` calls `-t` "NOT optional". `run_rs274` already resolves it
from the ini, so the code is trustworthy there - it simply was not read.

`run_rs274` now raises on a non-zero exit with the interpreter's own message.
All three scripts already wrap it in `try/except`, so the failure surfaces as a
normal verdict line.

## Verified both directions

```
aborting program   [VERDICT: FAIL - rs274 aborted (exit 1): Straight feed in
                    concave corner cannot be reached ...]
good program       [VERDICT: PASS]  min |dot| = 1.00000
```

Consumers unaffected: `test_facing`, `test_comp_side`, `test_surface_equality`
and `prove_cam_comp` all still pass, the last with its wrong-side control still
failing correctly.

## What this says

The verifier this project is told to run before every commit **could not fail
on a program that does not run**. It has been in that state for the whole of
the tip-comp and roughing work. Every PASS it issued on a program that aborted
was worthless, and nothing would have said so.

It also means my own habit of running the scripts directly rather than invoking
the skill hid this: the skill's step 4 says *"Read the verdict, don't just
glance at it"*, and the verdict was the thing that was broken.

## Not fixed here

`prove_tip_comp --op facing` cannot judge a project that also contains a
polyline - it measures every move against the flat face and reports a 4.616 mm
gouge, with the free-side control failing too. It needs a facing-only program,
which is what `test_facing.py` builds. Worth teaching the prover to bracket by
operation.
