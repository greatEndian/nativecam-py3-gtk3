# 096 — lvl_floor, fl_i and the loop's termination, together

**Asked**: greatEndian, 2026-09-04 — *"go on with lvl_floor + fl_i +
termination together"*, the change `analysis/095` said was the only way
`lvl_floor` could move.

## What changed

`o<if_next>` still fires on `current_radius EQ lvl_floor` and still carries
`p1_end` and the break - **the phase-1 handover hangs off exactly that branch
and was not touched**. What moved is the answer to *"is there another floor
stage below this one"*:

- **with the table**: the run itself is the answer. Its last entry IS the
  part's deepest floor, so the loop ends when the run does and the whole stage
  bookkeeping - `fl_i`, the `#3380` re-read, `fl_n`, the `cut_step` recompute -
  is skipped.
- **without it**: the runtime walks the stages exactly as before.

`lvl_floor` now comes from a per-level array, **written only at the advance**.
That is the fix for `analysis/095`'s failure: the window-start write landed
before the arming block, which decides whether to arm `fl_i` by testing
`lvl_floor` against the LAST stage, and overwriting it disarmed the machinery.
The window's own floor is still the runtime's, so `:826`'s thin reference and
the arming both read what they always did.

## Confirmed to be doing something

Motion-identity proves the two rules AGREE. It cannot tell "the table now ends
the loop" from "`fl_go` fell through to the stage walk every time and nothing
moved". So that was measured separately:

```
if_next fired and CONTINUED : 90 via the table,  9 via the stage walk
if_next fired and ENDED     : 176 via the table, 15 via the stage walk
```

**The table terminates the loop 176 times.** The 15 stage-walk terminations are
`testing_15_blocked`, where the phase-1 handover clears `lvl_tbl` and the
fallback takes over - so both paths are exercised and neither is vestigial. The
probe exits non-zero if the table never terminates, so "the runtime is still
quietly deciding" would have failed loudly rather than read as success.

## A near miss worth recording

The first attempt at this patch asserted on a multi-line block that did not
match - `o<if_next>` is followed by COMMENT lines, not by `o<fl_more>`. The
assert fired **before any write**, so the file was untouched, and the motion
gate then re-tested the old state and reported `MOTION IDENTICAL`.

**A passing gate on an edit that never happened looks exactly like a passing
gate on a correct edit.** It was caught only because the traceback shared the
output. Every subsequent patch prints an occurrence count of the new names
beside the gate result, so "the edit landed" is evidence rather than
assumption.

## Gates

```
36 configurations, emitted in 36, absent in 0
MOTION IDENTICAL - on equals off, everywhere
176 table terminations, 15 fallback terminations
```

Suite green: twelve gates, `cam_map`, `test_lathe_validation`, flake8.

## Left

The decisions - thin, blocked, out of band, split into intervals. The ramp and
stop machinery. The deletion pass, once this has cut on the machine: with
termination now table-driven, the stage bookkeeping is the first block that can
actually be DELETED rather than merely bypassed, which is where the `.ngc`
finally shrinks.
