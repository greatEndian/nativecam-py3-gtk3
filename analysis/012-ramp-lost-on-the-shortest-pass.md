# 012 — The last pass behind the boss plunged instead of ramping in

2026-08-04, branch `liveTooling`. greatEndian: *"the last pass lead in behind
the boss segment has wrong lead in.. If I select sectionning the lead in shape
is right .. go and compare it, fix it"*.

## The comparison greatEndian made, in numbers

```
Sectioning ON,  deepest pass behind the boss, r25.8254
   feed 1.0000   straight lead-in at 45
   feed 0.0000   the no-op
   feed 2.2583   RAMP at the contour's own angle
   feed 3.6680   the cut

Sectioning OFF, deepest pass behind the boss, r25.5880
   feed 1.0000   straight lead-in at 45
   feed 2.6397   the cut          <-- no ramp, it plunges straight in
```

Only that one pass. Every other pass behind the boss ramps in correctly with
Sectioning off, which is what made it look like a Sectioning feature.

## Root cause

The approach is three pieces - a straight lead-in, a no-op, then a ramp at the
contour's own angle onto the level - and the ramp is capped so it is never
longer than the cut it enters:

```
o<e_cap> if [#<pa_dz> LT ABS[#<z_end> - #<z_start>]]
```

That cap sat inside the entry block, which runs **before** the stop table
extends the cut to the pre-finish. So it was tested against the SCAN's stop, a
shorter figure than the cut the pass actually makes. On the shortest pass the
stale length did not clear the 2.2004 mm ramp even though the real cut, 2.6397
mm, does.

Sectioning gives that region a longer window, so the same cap passes and the
shape comes out right — which is exactly the difference greatEndian spotted.

**Confirmed before changing anything**: replacing the cap with `LT 99999`
produced the ramp, identical in shape to the Sectioning-ON case.

## The fix

The ramp arming moved out of the entry block to **after** the stop extension,
so its cap is tested against the real cut. Its inputs (`e_best`, `e_bdz`,
`e_bdx`, `e_have`) are found where they always were; only the arming moved.
`#<e_have>` gained a declaration with the other pre-branch locals — it is now
read outside the block that assigns it, and a named parameter first assigned
in a branch fails load-time pre-parse.

## After

```
Sectioning OFF, r25.5880:  1.0000 -> 0.0000 -> 2.2583 ramp -> 2.6397 cut
Sectioning ON,  r25.8254:  1.0000 -> 0.0000 -> 2.2583 ramp -> 3.6680 cut
```

Same shape either way. `check_tangent` PASS min |dot| 1.00000; `test_leads`
24/24; `test_sections`, `test_comp_overlay`, `test_lathe_validation`,
`test_coord_mapping`, `test_vkb` pass; `test_rough_comp`'s overcut and
reaches-the-wall assertions unchanged.

## The test

`test_rough_comp` gained *every pass behind the boss ramps in, none plunges*.
A ramp is told from the 45 degree lead-in by shallowness — the lead-in has
|dz| == |dr|, a 13 degree ramp has |dz| over four times |dr| — so no angle is
assumed, only that a ramp is not a lead-in.

**Negative control run**: with the cap made restrictive, 9 of 9 passes plunge
and the check fails in all three modes.

## Still unknown

- Whether the same stale-`z_end` cap affects anything else armed inside the
  entry block. Only the ramp was moved.
- Roughing's lead-out still has no reference for where its 1 mm ends —
  untouched, still open.
