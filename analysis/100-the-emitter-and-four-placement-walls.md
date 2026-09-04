# 100 — the emitter works; the placement does not

**Asked**: greatEndian, 2026-09-04 — *"go on with the emitter"*.

## What works

`build_flat_roughing_gcode()` turns `roughing_call_plan` into G-code, and the
output is correct: on testing_15_5 it emits one sub with **84 calls**, and the
plan behind it still matches the O-code on **36 of 36** configurations.

It needs one argument. `m_pds` and `lvl_d` are each assigned exactly once in
`poly_lathe_mill`, so they are constants for the polyline, and `lvl_d` is
`dirsign * (fin_off + prefin_off)` - known here. Only the record-array pointer
has to be passed.

Three globals are the whole state. `lathe_level_pass` reads exactly
`_pl_w_idx`, `_pl_prev_lvl` and `_pl_level_z_end` of what the loop sets - not
`_pl_prev_thin`, not `_pl_ph1_*`, which are `poly_lathe_mill`'s own and are
what this replaces.

## What does not: every placement is blocked

**The wiring is reverted.** A half-connected flat path in `cfg/` and `lib/` is
worse than none.

| placement | why it fails |
|---|---|
| `[DEFINITIONS]` | runs before `set_insert_orient()`, so `finish_profile` cannot resolve and the plan comes back empty - `plan=False` |
| end of `[AFTER]` | a lib sub can only call a main-program sub the interpreter has ALREADY READ; the definition sits past the call point |
| inside `[AFTER]`'s if | `sub: o|101| found in illegal location` |
| a numbered sub | file-local - `Subroutine 'O90001' not found -- not in offset table` |

Each of those was established by running it, not by reading.

## Four LinuxCNC facts, none of them in the project's notes

1. A sub defined in the MAIN program **is** callable from a `SUBROUTINE_PATH`
   sub, arguments and all.
2. A sub may be defined **after** its call site - but only for a call in the
   same file. A lib sub calling a main sub needs it read first.
3. A sub may **not** be defined inside an `if` block.
4. **Numbered subs are file-local; named subs are global.** This is the one
   that decided the design, and the error message that revealed it names the
   offset table.

## And one about this codebase

**A compile error in a cfg `<exec>` is indistinguishable from an `<exec>` that
printed nothing.** `exec_callback` discards the whole block on any exception,
and an `IndentationError` happens before a `try` inside the block can exist. A
mixed tab/space indent cost an hour: I attributed the empty output to ordering,
moved the block, and only later found the original placement had been right to
try - it fails for a different reason, but I never retested it flat.

**Keep every line of an `<exec>` flat.**

## The way through

Make the flat builder independent of module state - chiefly `INSERT_ORIENT`,
published by `set_insert_orient()` in the AFTER block - so `[DEFINITIONS]` can
build the plan. That is an audit of what `finish_profile` reads, and it is the
next step rather than this one.

## State

Kept and proved: `roughing_call_plan`, `build_flat_roughing_gcode`,
`window_calls`, `level_calls`, `flat_sub_number` (unused, with the numbered-sub
finding recorded on it). Read by nothing. `cfg/` and `lib/` are back at the
last commit apart from the plan diagnostic's writer, which had to follow
`window_calls`' enriched tuple.

## Follow-up, same day

`INSERT_ORIENT` was the blocker and it is now threaded as an argument -
`flank_envelope`, `finish_profile` and `build_flank_gcode` all take `orient`,
with the module global as the default so every existing caller is unchanged.
Proved inert: identical generated output across all 36 configurations.

That removes the reason `[DEFINITIONS]` could not build the plan. The wiring
itself still has to be redone and re-gated.

**And a self-inflicted failure worth recording.** `test_ramps` came back red in
the suite that ran while this threading was being written - I edited
`lathe_sections.py` WHILE a twelve-test suite was importing it, and the run
checked 16 ramps where a clean run checks 68. Re-run alone on a settled tree:
pass. Gate runs and source edits have to be serialised, not just gates against
each other - the same edit could as easily have produced a false PASS on the
change being validated.
