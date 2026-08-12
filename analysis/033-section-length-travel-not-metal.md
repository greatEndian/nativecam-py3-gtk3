# 033 — The section-length "fault" was the test, not the code

2026-08-12, branch `liveTooling`, from `8b94a52`.

## What was left

After `5790e01` built the roughing floor from the reachable profile, the
Z-section-length figures improved from 23.1% / 20.1% to 7.0% / 5.7% **and the
sign flipped** — a sliced program now cut *less* than an unsliced one, where
before it cut more. `test_section_length` still failed.

## Reproduced first

```
sec_len  0.0    51 passes   1111.4 mm of cut
sec_len 10.0   173 passes   1034.0 mm of cut     -7.0%
sec_len 20.0   121 passes   1048.3 mm of cut     -5.7%
```

Confirmed, including the flipped sign. (The failure message said "more" while
`drift` was an `abs()` — a message bug, now gone with the rewrite.)

## The measurement that settles it

Cut length is not metal. The removed **volume**, simulated through the preview's
`StockField` the way the pane does it:

```
sec_len 0.0        volume 205550.4 mm3 ( +0.00%)   cut 1111.4 mm    51 passes
sec_len 10.0       volume 205550.4 mm3 ( +0.00%)   cut 1034.0 mm   173 passes
sec_len 20.0       volume 205550.4 mm3 ( +0.00%)   cut 1048.3 mm   121 passes
CONTROL f_off 3.0  volume 206614.1 mm3 ( +0.52%)   cut  690.1 mm    39 passes
```

**Identical to a tenth of a cubic millimetre at every section length**, while the
control moves — so the measure is live and the equality is a result, not a
flatline.

### One thing the old probe got wrong

The throwaway `vol.py` sized its stock field from **each run's own moves**. Two
programs that cut differently span different Z and X, so it measured them in
different boxes, which is not a comparison. The field is now pinned
(`Z −74..+4`, `r40`, 1560 columns) and lives in the test.

## The conclusion

**The sliced program removes exactly the same metal with less cutting travel.**
A piece stops at its own boundary instead of sweeping ground a neighbouring
piece has already cleared, so the redundant traverse disappears. That is what
slicing is *for*.

Travel is a strategy property; the part is not. The test asserted the strategy
and so encoded a legitimate improvement as a fault — and it was chased as one
across several rounds, including a proposal to add mode 0's radial banding to
mode 1 against an explicit warning in `build_sections_gcode` not to.

**No production code was changed.**

## What the test asserts now

- **removed volume within 0.5%** of the `sec_len 0` baseline — the invariant;
- **cutting travel within 25%**, loosely, as a smoke check that a strategy
  change of that size gets noticed without being called a defect;
- **the pass count still rises**, so a "fix" that merely disables slicing
  cannot pass;
- and a **CONTROL** run at `f_off 3.0` that must move the volume, so the file
  cannot quietly become vacuous the way a flatlined probe would.

## Verified

`test_section_length` (exit 0), `test_rough_comp`, `test_stock_to_leave`,
`test_rough_ends`, `test_rough_overlay`, `test_all_projects`, `test_ladder`,
`cam_map`, flake8. The behind-boss fix holds: topmost behind-boss level
**33.2080** sectioning off, **33.1273** on.

## Note

The lesson from `analysis/032` repeats: a stated fault is not a fault until the
right quantity has been measured. There the floor was read from the raw profile;
here the test read travel for metal. Both cost rounds that a single correct
measurement would have saved.
