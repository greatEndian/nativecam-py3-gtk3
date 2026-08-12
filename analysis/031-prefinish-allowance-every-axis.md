# 031 — The pre-finish allowance was radial only

2026-08-12, branch `liveTooling`. greatEndian: *"why I have prefinishing offset
non 0.0 roughing passes are touching the prefinishing contour in the Z direction
(at the boss segment) and offset is only applied at X direction? prefinish offset
has to be constant in the each axis so the tool will have some material to cut
and not to create chattering."*

Right, and it is a machining requirement rather than a preference: a pass that
rubs instead of cutting chatters, and leaves a worse surface than the one it was
sent to improve.

## The asymmetry, by construction

| table | governs | allowance it carried |
|---|---|---|
| `build_floor_contour_gcode` | the level RADII (X) | `fin + prefin` |
| `build_stop_contour_gcode` | where a level ENDS (Z) | **`stock_pair` = `fin` alone** |

So a level was allowed to stop **on** the pre-finish surface wherever the stop
governs — a boss face, a wall, a shoulder — while standing off correctly on
every diameter.

## Two fixes, because the first one alone made it worse

**1. The stop contour carries `fin + prefin`.** Not the roughing FLOOR, which is
what that table exists to stop using: the floor is rounded up to the level grid,
so stopping there left a gap of up to a whole depth of cut. `fin + prefin` is
the allowance actually asked for and sits between the two.

That alone fixed the isotropic case and **broke the anisotropic one**: with the
axial value at 2.000 the deepest level went from stopping 2.0000 off the wall to
**0.7300**.

**2. A clamped stop candidate may not extend the cut.** This is what the probe
found, and it overturned the reasoning that preceded it.

## The probe, and what it refuted

The suspect was `s_reach`, the bound on how far the stop table may extend a cut
— `3.0 * _rough_cut`, scaled to the depth of cut and blind to the allowance.
The arithmetic **refuted it before any edit**: `rough_cut` 0.508 gives 1.524, and
the candidate moved from 1.238 to 1.492 away from the scan's end, still inside
the bound.

So the four numbers were emitted instead of argued about, from
`lathe_level_pass` on the level nearest the wall:

```
PROBE lvl=26.604  zend_scan=-68.146  best=-69.670  have=1  bcl=1  reach=1.524
```

- `zend_scan = -68.146` — **the scan was already right**, 2.254 from the Z−70.4
  wall, because it walks the anisotropic floor contour;
- `best = -69.670` — and `-68.146 - 1.524` is exactly that, so the winning
  candidate was a **clamp**, not a crossing;
- `bcl = 1` — confirming it.

The stop table, whose whole purpose is to *extend* a cut to the pre-finish
surface, was extending past a scan that had already stopped in the right place —
by the full reach, because with the stop contour now equal to the floor contour
there was no real crossing left to find.

**A clamp is a guess at reach, not a measured crossing.** It may pull a cut IN to
a feature the scan could not see; it may never push one PAST where the scan
stopped. That rule is now in `lathe_level_pass`, keyed on `s_bcl` and the scan's
own end captured before the stop block overwrites it.

## Measured

`testing_15_2`, distance from the Z−70.4 wall:

```
                        before        after
isotropic 0.508         0.5080        0.7620      = fin + prefin
axial 2.000             2.0000        2.2540      = fin_z + prefin
```

and on `testing_15_5`, every level now stops **0.2540** short of the wall in all
three comp modes — exactly the pre-finish offset that project carries.

## The two tests that encoded the fault as correct

Both had to be rewritten, and both were asserting the radial-only behaviour:

- `test_stock_to_leave` expected **2.000** and **0.508** — the finish offset
  alone. Now `fin + prefin` on both, and the *isotropic* case is the tighter of
  the two, because that is where a radial-only allowance looks right.
- `test_rough_comp` asserted *"every roughing level reaches the pre-finish
  wall"* — literally requiring the fault. Now *"stops the pre-finish allowance
  short"*, with the bound still rejecting the whole-depth-of-cut fault it was
  written for (0.5080, `photo/leadOutIssue_1.png`), plus a second check that
  nothing cuts INTO the allowance.

## Verified

`test_stock_to_leave`, `test_rough_comp`, `test_all_projects`, `test_ladder`,
`test_rough_ends`, `test_floor_ladder`, `cam_map`, flake8.

## Note for next time

Four hypotheses about this area were wrong before this one, and this one was
refuted on paper and then settled by four numbers from a probe. The probe cost
one generation. Instrument first.
