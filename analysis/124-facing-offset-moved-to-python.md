# 124 — the facing roughing offset, moved into Python

**Asked**: greatEndian, 2026-09-10 — *"redo the facing offset in python"*, after
asking whether the run had been verified as the habits list says. It had not:
`analysis/122` shipped the offset as new O-code, growing `facing.ngc` by 55
lines, which is the opposite of the standing rule that the `.ngc` shrinks.

## What moved

`facing.ngc` used to resolve the tool table (`tip_comp_dia`), pick a
compensation side from `z_factor`, and call `tip_comp_vec` - at runtime, every
time. All three inputs are known at generation time, so
`lathe_sections.facing_rough_offset` resolves them there and the subroutine now
reads two numbers:

```
#<r_ofz> = #<_fc_rough_ofz>
#<r_ofx> = #<_fc_rough_ofx>
```

**No new geometry was written.** It reuses `lathe_comp.offset_vector`, the same
primitive `tip_comp_vec` implements, so the two cannot drift into different
answers.

`facing.ngc`: **+7 / -46** against the version it replaces - 39 lines smaller.
Against the original, before facing roughing was compensated at all, it is +16,
for a capability that did not exist.

## A global, not a CALL argument

`facing.cfg` already carries `_fc_below_ir` this way, with its reason written
next to it: *"a subroutine is re-read at runtime while a saved project keeps its
stored template until it is loaded, so a new argument lands on one side only."*
Two new trailing `[CALL]` args would have been live in the `.ngc` immediately
and absent from every saved project until migration. The globals default to 0
in `create_defaults`, so an unmigrated project simply gets no offset - the
behaviour it had.

`cfg/lathe/facing.cfg` 1.26 -> **1.27**.

## Verification

**The gate is byte-identity**, because this is a refactor and not a behaviour
change: the Python offset must reproduce what the O-code computed. A/B over all
24 projects containing a facing feature, O-code version against Python version:

```
IDENTICAL
```

The primitive was also checked directly against the two numbers `analysis/122`
measured: T3 D2.54 Q3 at side 41 gives Z 0.0000 X +1.2700, and T2 D0.8 Q2 gives
Z 0.0000 X -0.4000 - and `testing_8` emits `#<_fc_rough_ofx> = -0.80000000`,
the same figure in machine units.

Gates: flake8, cam_map, test_cam_map, test_lathe_validation, test_facing,
test_comp_side, test_sections, test_ramps, test_surface_equality,
test_project_sweep - all exit 0.

## A second dead driver, found the same way

`test_comp_side.py` was failing before this change and after it, identically -
*"facing produces a compensated cut: no feed moves - the harness did not run"*.
Same cause as `test_facing.py` in `analysis/122`: its header lacked
`_fc_below_ir`, so the file failed at load and the harness measured nothing
while still reporting a facing assertion. Repaired, and it now passes four
checks it had not been running at all, including *"facing leaves the face at
the same Z in every comp mode"*.

That is two of two facing harnesses found dead by looking. Neither failure was
visible as a load error - both surfaced as an assertion about geometry.

## The cfg trap this hit

An `<exec>` line inside `[CALL]` must be INDENTED. The file is INI-parsed, so a
line at column 0 ends the value and `configparser` raises
`Source contains parsing errors ... [line 300]`. polyline.cfg's execs are all
indented; mine was not, and generation failed outright rather than silently -
which is the good kind of failure.
