# 122 — facing roughing is compensated, and its driver had been dead

**Asked**: greatEndian, 2026-09-10 — *"go with compensation all-or-nothing and
all other one by one"*. First item.

**Scope**: `facing` only. The open point's own note is that `boring` and
`taper_id` are ID work, which greatEndian paused on 2026-08-02, and `taper`
already applies the offset to its roughing coordinates. So the gap was facing.

## The gate was broken before any of this

`test_facing.py` did not fail - it **crashed**, on the untouched tree, with
`ValueError: min() arg is an empty sequence`. The cause was load-time:

```
Named parameter #<_fc_below_ir> not defined
```

Four globals that `facing.ngc` and its callees have come to read -
`_fc_below_ir`, `_tbl_scale`, `_tip_cam_r`, `_tip_cam_l` - were missing from the
driver's preamble, so LinuxCNC rejected the whole file and the driver measured
nothing while still printing its own assertions. Repaired from
`create_defaults()`, and `_tip_cam` / `_tip_off_z` / `_tip_off_x` added with
them. **The driver passed on the clean tree before any change was made** - that
is the baseline this rests on.

## The fix

Compensation is all or nothing, so with nose comp on the roughing coordinates
carry the nose geometry - roughing has no interpreter compensation in any mode.
`tip_comp_vec` gives the offset; `z_nom` keeps the pass stepping by `each_cut`
while `z` carries the offset, and `bxc` / `exc` are loop-local compensated
copies of the radial ends so the finish block still sees the commanded values.

**Both components matter, and which one carries the correction depends on the
insert.** The first version applied only the axial part and measured zero,
because for T3 - D2.54, Q3 - the orientation term cancels the axial component
exactly: normal 1,0 gives 1.2700 in Z, orientation 3 gives 1,-1, and the result
is Z 0.0000 with X +1.2700. An insert with the opposite Z orientation gets
2.5400 in Z instead. Taking one component would have applied nothing to half
the tool table.

## Verification

**Driver**, with its negative control:

```
with the fix      nose comp shifts the roughing pass by the insert offset
                  moved Z+0.0000 X+1.2700, wanted Z+0.0000 X+1.2700 for T3 Q3
facing.ngc reverted   moved Z+0.0000 X+0.0000   -> FAIL
```

**Real projects**, A/B over every project containing a facing feature:
`testing_6`, `testing_8`, `testing_9` change and nothing else does. That is
exactly right - their facing carries **no stored `n_comp`**, so migration
supplies `facing.cfg`'s default of 1, Native; `testing_15_*` and `current_work`
store `n_comp = 0` explicitly and are untouched.

On testing_8, tool T2 - D0.8, Q2, nose radius 0.4 - the three roughing feeds
move by **dX -0.4000, dZ +0.0000**, the insert offset exactly, and the two
finish feeds do not move at all, being compensated by the interpreter instead.

Gates: flake8, cam_map, test_lathe_validation, test_facing, test_sections,
test_ramps, test_surface_equality, test_project_sweep - all exit 0.

## Three traps, all of them already written down

- **A nested paren inside a comment** halted `rs274` with "Nested comment
  found". Mine was `(normal (1,0) gives ...)`.
- **A two-line comment** is an unclosed comment. Mine was a wrapped
  explanation.
- **Globals written outside the guard.** `tip_comp_dia` and the `_tip_off_*`
  clears were above `if n_comp GT 0`, so an operation with comp OFF began
  writing globals it had never touched. Moved inside. `r_ofz` / `r_ofx` stay
  outside because they are locals and a local first assigned inside a branch
  fails load-time pre-parse.

## And one wrong conclusion of mine, corrected

Mid-way I found the live `lathe.var` had been rewritten at 09/16:59, between two
fingerprints, and concluded the three changed projects were that. **Wrong.**
`rs274` resolves `lib/lathe/facing.ngc` at PARSE time, not generation time, and
I had restored my modified file before hashing - so both sides of that
comparison measured the same subroutine. Any A/B on a `lib/` change has to keep
the file in place across generation AND parsing, which is what `ab.py` does and
what produced the result above.

The var really did change, and it is worth knowing that it can move Z under a
fingerprint comparison. It just was not this.
