# 071 — the flank shadow follows the insert, not the travel

**Asked**: greatEndian, 2026-09-01 — *"now fix flank_sides"*, after
`analysis/069` closed the same blind spot for the profile-angle ramp and
`analysis/070` flagged this as the deeper version of it.

## What was wrong

```python
def flank_sides(rough_dir):
    return (-1,) if rough_dir == 1 else (1,)
```

Which side of a peak casts a shadow, decided **from the roughing direction**.
But which flank TRAILS is a property of the insert: the tool does not rotate
when the cut direction changes, so the back flank sits behind the cutting edge
in the tool's own frame and the side it shadows is fixed by the orientation.

**And it was worse than the signature suggests.** Every caller reaches it
through `rough_frame_dir`, which collapses directions 0, 1 and 2 to 0 - so
`flank_sides` has ALWAYS returned `(1,)` and the direction argument is
effectively dead. The shadow was hard-wired to the +Z side: right for an
ordinary right-hand insert, wrong for a mirrored one.

## The fix

`insert_flank_side(orient, trailing)` - the cutting edge faces `ramp_facing`,
the trailing flank is behind it and shadows the opposite side, the leading flank
shadows the same side as the facing. Applied inside `flank_envelope._flank`,
the one place both flanks are built.

It could not go in `flank_sides` itself: that function encodes WHICH flank by
being handed a mirrored direction (`flank_sides(mirror_dir(d))` for the leading
one), so an insert override there would have collapsed the two into one side.

`INSERT_ORIENT` is a module-level per-generation constant set by
`cfg/lathe/polyline.cfg` (version 1.67 -> 1.68) in both `[AFTER]` and
`[VALIDATION]`. The operation runs with one tool and every function below asks
the same question about it; threading it through fifteen signatures - including
`finish_profile`, which has seven internal call sites - would have said nothing
extra and touched every caller.

**0 means "no idea" and keeps the old behaviour.** So do the neutral
orientations 6, 8 and 9, which have no axial component: they defer to the
direction rather than removing the constraint, because dropping the shadow
entirely would let roughing reach everywhere, which is a far larger claim than
this can prove.

## Proof that nothing moved

For orientation 2 - the ordinary right-hand OD insert every demo project uses -
the override returns **exactly** what the direction-derived answer already gave:
trailing +1, leading -1.

Measured end to end, motion and the flank/floor tables hashed, 3 projects x 3
directions:

| | shipped Q2, before | shipped Q2, after |
|---|---|---|
| testing_15_9 dir 0 | motion 6cf361a8b8f5, 1575 moves | **identical** |
| testing_15_9 dir 1 | motion 0c77e32ed571, 1545 moves | **identical** |
| testing_15_9 dir 2 | motion 43ae3b94651a, 1670 moves | **identical** |
| testing_15_2, all three | 327 / 309 / 319 moves | **identical** |
| testing_15_5, all three | 458 / 426 / 444 moves | **identical** |

Byte-for-byte, tables included. Every existing project is untouched.

And the mirrored insert genuinely moves it: the flank table goes 42 slots to 24
on testing_15_9 and 15_5, 40 to 32 on testing_15_2, in every direction.

## The wiring check, and why it exists

The unit assertions pass whether or not the cfg ever calls
`set_insert_orient`, so on their own they would let the whole feature be dead
code - the exact shape of the `Retract = Minimal` combo that shipped doing
nothing for months (`analysis/065`). `test_flank_envelope` now generates the
same project against two configs whose only difference is the tool table's Q
and requires the emitted flank table to differ.

## A CONTROL THIS CHANGE COST, recorded rather than papered over

`test_ramp_orient`'s mirror case asserted that a mirrored insert gets its 18
ramps BACK - that was the assertion stopping "0 ramps" being indistinguishable
from "the ramps were deleted". It now reads **0**: with the insert mirrored the
reachable envelope flips too, the entry contour on testing_15_9 halves from 40
segments to 20, and no level arms a ramp on it in either direction.

The tables are consistent - both configs emit a populated ramp table with
`_pl_ramp_face` correctly -1 and +1 - and a large swing is what mirroring a
right-hand tool on a tapered part should produce. But **whether a mirrored
insert SHOULD lose every ramp on this part is not independently proven**, and
the test now says so in its own docstring rather than presenting the zeros as
evidence.

What still discriminates: the SHIPPED pair, 0 ramps back to front against 15
front to back, which a blanket "delete the ramps" fails immediately; the
`_pl_ramp_face` assertions; and the new wiring check above.

## Gates

`cam_map`, `test_cam_map`, `test_leftover` (24/24 control, and it also proves
the 1.68 migration), `test_flank_envelope` (including the new wiring check and
the stale `flank_sides(2)` assertion corrected), `test_front_flank`,
`test_ramp_orient`, `test_bidir_warn`, `test_ramps` (68), `test_sections`,
`test_air_leads`, `test_x_continuity`, `test_ladder`, `test_leads`,
`test_skip_short`.

**`test_flank_envelope` had been failing before this**, on
`set(flank_sides(2)) == {1, -1}` - an assertion that outlived the behaviour it
described, since `analysis/060` deliberately removed the both-sides answer.
Corrected here to state the rule that replaced it.

## Still unknown

- Whether a mirrored insert losing every ramp on testing_15_9 is right.
- The neutral orientations still defer to the direction rather than declaring
  no shadow. A genuinely neutral insert has clearance both ways and arguably
  shadows neither side, but that is a reachability claim that wants a gouge
  check behind it, not a guess.
