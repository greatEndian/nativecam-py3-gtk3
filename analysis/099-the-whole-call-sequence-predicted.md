# 099 — the whole roughing call sequence, predicted from the Feature alone

**Asked**: greatEndian, 2026-09-04 — *"go on with the emitter"*, then *"go on
with roughing_call_plan"*.

## The result

```
36 configurations match, 0 differ
```

`roughing_call_plan()` produces every `lathe_level_pass` call the program will
make - window by window, level by level, interval by interval, skips included -
**from the Feature alone**, with nothing read back out of the generated
program. Compared call for call against the running O-code.

## Why this is sound rather than hopeful

`lathe_level_pass` is **the only thing in poly_lathe_mill's loop nest that
emits motion**. Inventoried, not assumed: over lines 648-1445 the only
subroutine calls are one `lathe_level_pass` and four `lathe_level_next_start`,
and the latter is a scan. There is no bare G-code between them.

So a flat sequence making the same calls with the same arguments and the same
global state reproduces the motion exactly. That is what makes emitting them as
literal G-code a sound plan.

Two facts settled it on the way:

- **A sub defined in the main program IS callable from a `SUBROUTINE_PATH`
  sub**, arguments and all - tested directly. So the generated program can
  define `o<ncam_flat> sub` and `poly_lathe_mill` can call it in place of its
  loop.
- **The flat sub needs ONE argument.** `m_pds` and `lvl_d` are each assigned
  exactly once, so they are constants for the polyline; `lvl_d` is
  `dirsign * (fin_off + prefin_off)`, which Python knows. Only the record-array
  pointer has to be passed.

## What the composition found that no layer could

**The phase-1 handover moves the THIN REFERENCE, not just the ladder.**

First run: 33 of 36 matched. The three that did not were `testing_15_blocked`
sectioned, where the plan emitted level 34.572 and the O-code's first phase-2
call is 34.516.

A phase-2 window takes `_pl_prev_thin` from `sect_top_r`, and where phase 1
handed over that is the MOVED value - 34.572, not the nominal 31.016. The first
level of every later window then sits exactly zero from its own thin reference
and is skipped. Feeding the nominal ceiling emitted three calls the runtime
never makes.

**No earlier gate could have caught this.** Every layer was proved with
`prev_thin0` taken from the instrumented record, so the coupling only appears
once the whole plan is built from the Feature. It is the fourth distinct thing
`testing_15_blocked` has exposed.

## Three more data/emitter splits

`z_limit_band()` and `split_peaks()`, and `ext_dz` was already a function.
Both gated byte-identical against the file as it stood immediately before them.

The first attempt used a generic splitter and produced a syntax error; restored
from backup and done by hand. A mechanical helper for a mechanical job is worth
having, but not at the cost of a mangled file - the backup made that a
30-second loss.

## The diagnostic is env-gated

The plan is compared through an `<exec>` that writes it out only when
`NCAM_PLAN_FILE` is set, so normal generation does nothing and no motion can
depend on it.

## Left

The emitter itself - formatting the plan as `o<ncam_flat> sub` - and
`poly_lathe_mill` calling it instead of looping. Gates: motion identical, and a
check that the flat path is actually taken. Then the deletion pass, which is
where the `.ngc` finally shrinks.

`band` remains unprovable: `band=0` across the whole sweep.
