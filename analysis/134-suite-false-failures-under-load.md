# 134 — the driver sweep reports false failures when the machine is loaded

## What was asked

Run the full driver suite uncontended and confirm the total, after two parallel
worker sessions landed 10 commits.

## What was measured

`deadsweep6`, all 74 drivers:

```
74 drivers   71 pass   3 fail
  test_rough_ends.py     rc=1     <-- genuine, awaiting greatEndian's tip-vs-cut ruling
  test_sub_spans.py      rc=124   <-- TIMEOUT
  test_x_continuity.py   rc=1
```

Re-run individually, nothing else running:

```
test_sub_spans.py      exit=0   36 configurations, 2612 levels, 119 split into sub-spans
test_x_continuity.py   exit=0   CONTROL: deleting the X32.7000 pass is DETECTED
```

Both had also exited 0 earlier in the same session (task `brs2r84ck`).

## Root cause

Not a code regression. Both are load artifacts of the sweep harness itself:
`rc=124` is a `timeout` kill, and the `rc=1` is a second instance of the same
class. The suite's real state is **73 of 74 passing**, with `test_rough_ends`
the single genuine failure.

## Why it was not caught earlier

It was — three times, under a different name. Concurrency has corrupted
measurements in this project on three prior occasions (two interleaved sweeps,
an agent relaunch, and parallel work during a sweep producing six false
failures in one alphabetical block). Each time it was treated as a one-off
scheduling mistake. It is not: **the sweep is an instrument that returns
false FAILs under load**, and that is a property of the instrument.

## Consequence, and why it matters right now

Three parallel worker sessions are about to run in this tree. Any of them
running a gate while another is busy can see a false FAIL and "fix" a test that
was never broken. The handoff prompts already carry the mitigation — *if a gate
fails in a file you did not touch, re-run it once and report, do not fix it* —
but the harness should not need that instruction.

## Still unknown

- Whether the sweep runs drivers concurrently or the timeout is simply too
  tight for `test_sub_spans` on a loaded machine. Not yet measured.
- The right fix: raise the per-driver timeout, serialise the sweep, or make it
  re-run a failing driver once before reporting. A single re-run on failure
  would have turned this sweep green and cost seconds.
