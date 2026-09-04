# 101 — why the flat sub has nowhere to live

**Asked**: greatEndian, 2026-09-04 — *"go on with the wiring"*, after
`analysis/100` identified `INSERT_ORIENT` as the blocker.

## The orient was not the blocker

It was threaded out anyway - `flank_envelope`, `finish_profile` and
`build_flank_gcode` now take `orient`, module global as the default, identical
output across 36 - and that change is worth keeping. But the plan was still
empty at definitions time, and the gate said so rather than passing:

```
36 configurations, flat sub emitted in 0
THE FLAT SUB WAS NEVER EMITTED - nothing was actually compared
```

## The real reason

```
(FLAT EMPTY - bounds=(35.0, 19.0) pts=0 fc=False stock=70.0 doc=0.508)
```

**`pts=0`.** `resolve_points` returns nothing because the polyline's ITEM
CHILDREN HAVE NOT BEEN WALKED YET. `ncam_project_io`'s recursive walk collects
`get_definitions()` for a feature, then its `before` and `call`, and only THEN
recurses into its children - so at definitions time a polyline has no geometry
at all.

Nothing can be threaded around that. It is not missing module state, it is a
feature that does not yet know its own shape.

## Five placements, all closed

| placement | why it fails |
|---|---|
| `[DEFINITIONS]` | the item children are not walked yet - `pts=0` |
| top of `[AFTER]` | `[AFTER]` is ALREADY inside `o<#self_id_active> if`, which opens in `[BEFORE]` |
| end of `[AFTER]` | same if, and a lib sub cannot call a main sub the interpreter has not read |
| inside `[AFTER]` | `sub: o|101| found in illegal location` |
| numbered sub | file-local - `not found -- not in offset table` |

Closing and reopening that `if` around a definition would work in principle and
is not worth it: the condition is `#param_act AND in_polyline EQ 0`, and
`in_polyline` changes across the block, so the reopened guard would not be the
same guard.

## What would actually work

**Collect definitions in a SECOND pass, after the body walk.** They are
prepended to the program either way, so the emitted order does not change; what
changes is that a feature's definitions could then see its own children. That
is a `ncam_project_io.to_gcode` change and it affects mill and plasma as much
as lathe, so it wants its own gate - byte-identical generated output on the 36
lathe configurations AND on a mill project.

`short_id` looks safe under that reordering: `to_gcode` deletes it per feature
at the start of the walk, so the body would assign it and the definitions pass
would reuse the same value.

That is a pipeline change, and it is where this stops for now rather than being
slipped in at the end of a long session.

## State

Wiring reverted - `cfg/` and `lib/` are back at the last commit. Kept: the
`orient` threading (proved inert), and the whole predictor stack, still read by
nothing. The plan remains 36/36.
