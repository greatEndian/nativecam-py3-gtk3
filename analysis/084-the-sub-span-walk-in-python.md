# 084 — the sub-span walk, predicted in Python

**Asked**: greatEndian, 2026-09-03 — *"go on with the sub-span walk"*, the layer
`analysis/083` named as deciding where each interval walk BEGINS.

## What it does

Walked back to front, a level a peak certainly blocks must not be swept as one
span from the window start - it would lead in through the peak.
`poly_lathe_mill`'s `o<wh_seg>` loop breaks the sweep at every split point the
level sits below, taking them **from the back** out of the `#3160` table Python
emits, until a sub-span reaches the window's own front.

A split point counts only when all three hold: the level is at or below the
radius that peak blocks, the point is genuinely past the window start, and it
is still inside the sub-span currently being filled. The table is read **once
across the whole level** - `sg_i` is not reset per sub-span - so each peak can
break the sweep at most once.

`sub_spans()` is that, as a pure function. **Nothing in the toolpath reads it.**

## The gate

`test_sub_spans`. For every level of every window, the whole ordered
decomposition - each sub-span's start and end, and how many there are.
`sg_use`, the decision to read the table at all, is **predicted and checked**
against the recorded value rather than taken from it.

```
30 configurations, 2537 levels, 119 of them split into sub-spans
```

`w_idx`, `w_from`, `w_to` and `z_dirw` come out of the record: they are the
NEXT layer up, poly_lathe_mill's `o<wh_w>` window loop, deliberately not
replicated here. The sub-span walk is judged given its window exactly as the
interval walk was judged given its sub-span.

## What the first run got wrong, and how it hid

Seven of thirty configurations failed - **every one of them `dir=1`** - and the
negative control reported `refusing the split table changes nothing`.

Both had one cause. I predicted `sg_use` from `#<_pl_cut_rev>` read out of the
generated program, and **that global is a RUNTIME value**: `poly_lathe_mill`
sets it from `rough_dir` (line 311-314), and for Both directions
`lathe_level_pass.ngc:1785` flips it after every pass that emitted motion. The
program source only ever shows the defaults block's `0.0`. So `sg_use` came out
False everywhere, and back to front - the only direction that splits - failed.

**And the control was silenced by the same bug.** The `sg_use` mismatch
`continue`s before the control runs, so the 119 split levels never reached it
and it reported nothing rather than reporting a problem. A control only has
teeth once the path reaches it - worth remembering, because a silent control
reads exactly like a passing one.

A second thing surfaced while fixing it: **`rough_dir != 1` zeroes
`_pl_p1s_n`** (`poly_lathe_mill.ngc:1320`) - the split table is cleared at
runtime, so front to back and Both directions have no table at all whatever
Python emitted. That is why Both directions takes one span despite its flag
alternating, and it has to be modelled, not just the flag.

The fix in both cases is the same: **the direction is a cfg parameter, known at
generation time.** Read it there, not from a global the runtime owns.

## Coverage

119 of 2537 levels are genuinely split, asserted rather than hoped. The control
now fires: refusing the table collapses a split level to one span.

## What is left

The **window walk** - `poly_lathe_mill`'s `o<wh_w>` loop - which produces
`w_from` / `w_to` per window, the section table for Natural, fixed `sec_len`
windows for Artificial and unsectioned, and the phase-1 handover that
reassigns `sect_top_r` mid-run. Everything below it is now predicted:

    window  ->  sub-span  ->  interval  ->  level set
    (left)      084          083           080/081/082

That handover is the interesting part and the reason the window layer was left
until last: it is the one place where a runtime OUTCOME - phase 1 stopping on
an obstruction - feeds back into the geometry the later windows use.

## Gates

`test_sub_spans` (new), `test_level_intervals`, `test_level_blocked`,
`test_ladder_account`, `test_ladder_python`, `test_ladder`, `test_leftover`,
`test_x_continuity`, `test_ramps`, `test_sections`, `test_bidir_warn`,
`cam_map`, flake8. Motion untouched: no `.ngc` or `cfg` edited, and the
instrument is proved inert.
