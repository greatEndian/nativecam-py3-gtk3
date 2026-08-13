# 047 — Rest machining has nothing to cut, and why that is the finding

2026-08-13, gap **12**. The largest of the reference gaps, and the one
greatEndian independently reinvented: *"compare each first fake section from to
outside side and if there will be some missing passes we will implement it in
the second scan"*.

**Not built. Measured, and the measurement says the simple form has no input.**

## What rest machining would cut

Regions standing proud after roughing. `test_leftover.py` already answers that
for any project, with a validated negative control. Run over the demo projects:

```
testing_15_5  sect off/ON   worst standing 0.7219 / 0.8579 mm   0 wide regions
testing_15_6  sect off/ON   worst standing 0.6473 / 0.5681 mm   0 wide regions
```

**Zero wide regions, everywhere.** The only material left is narrow spikes at
shoulders, every one of them narrower than 1.5x the nose — and `test_leftover`'s
own docstring records why, from when it was written and validated: *"a r0.4 nose
cannot reach into the shoulder at Z-19.51, which rises 0.93 mm in 0.04 mm of Z.
A missing pass is wide, spanning at least the ladder's 2.2004 mm step, so the two
are an order of magnitude apart."*

So within one operation, with one tool, **roughing already leaves nothing that
another pass of the same tool could take**. A "find the leftovers and emit passes"
feature would emit nothing on every project we have — unverifiable, and by the
leftover check's own measure, correctly nothing.

That is not a disappointment. It is the leftover check doing the job it was built
for: telling us a feature is unnecessary before it is written.

## What rest machining actually is

A **second tool**. The material standing at those shoulders is a nose-radius
fillet; it comes out only with a smaller nose. So the feature is inherently
cross-operation: operation N+1 must know what operation N's tool left, and cut
only the remainder.

What that needs, which we do not have:

- the simulated result of one operation carried to the next at **generation
  time**. `StockField` does the simulation, but today it runs over a finished
  program in the preview, not per-feature during the tree walk;
- an operation whose stock is **the previous operation's result** rather than the
  Workpiece. Without that, a second polyline roughs from the bar again and cuts
  air down to where the first one finished.

The mechanism for feature-to-feature state exists — `to_gcode`'s walk already
publishes the tool change's values, and `WORKPIECE_FACE_Z` (analysis/039) uses it
— so this is a real design rather than a wish. It is simply much larger than the
gap description implies, and it is the whole feature, not a pass emitter.

## A probe of mine that was wrong, recorded so it is not repeated

To test "are the leftovers nose-limited", I swept the same roughing moves with
smaller nose radii and compared removed volume:

```
nose 0.40  removed 633179.3 mm3
nose 0.20  removed 629117.4 mm3   -0.64%
nose 0.02  removed 456227.8 mm3   -27.95%
```

A smaller nose removes LESS. That measures a smaller disc sweeping a smaller
volume along the same path — trivially true, and silent on reachability. The
question needed material standing above the TARGET, not volume swept, and the
half of the probe that would have measured it silently printed `n/a` because it
referenced a symbol `test_leftover` does not export.

Caught by reading the numbers against expectation instead of reporting them. The
conclusion above rests on `test_leftover`'s own validated finding, not on this.

## Status

Gap 12 stays open, and is now open with a measurement behind it: nothing to cut
within an operation, and a named architecture for the cross-operation form.
