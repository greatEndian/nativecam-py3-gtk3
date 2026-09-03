# 086 — the phase-1 handover, measured; and a claim of mine retracted

**Asked**: greatEndian, 2026-09-03 — *"go on with the window walk"* (already
delivered as `085`), so this went on to the only layer left, and then *"show me
the numbers"*.

## The claim being retracted

`analysis/085` and `openPoints` said the boundary of the migration was the
phase-1 handover **reassigning `sect_top_r`** - a runtime outcome feeding back
into the geometry later windows use - and that a table-walking `.ngc` would
have to drop it or keep that decision at runtime.

Measured over 30 configurations, instrumenting all three assignment sites:

```
handover sites fired:  1035 = 0   1116 = 0   1222 = 0
0 of those actually MOVED sect_top_r
```

**Never, on any of the five projects, in any direction, sectioned or not.** The
claim was wrong, and wrong in the direction that mattered: I reported a hard
runtime dependency the stack does not have.

It was reasoned from reading the code, which is exactly the failure mode the
standing rule names. The three sites are real branches and may fire on some
part - they are the BLOCKED handover paths - but nothing here reaches them.

## What does fire

```
_pl_ph1_front_cut (site 1295) = 6 of 30
   15_5 s1 d0, d1, d2
   15_6 s1 d0, d1, d2
```

Narrower, and a different thing. It does not move the ceiling; it records how
far phase 1 actually got, in `_pl_ph1_z_end`, so the phase-2 windows that pass
already covered start one level deeper instead of cutting that radius twice.

## Why this may reduce to nothing

`_pl_ph1_z_end` is `_pl_level_z_end` at the moment phase 1's last level ended -
and `level_stop_z` predicts that value exactly, 1854 of 1854 cutting calls
(`analysis/083`). Whether the site fires at all is gated on `p1_cut`, which the
proved layers determine. So the last runtime dependency may be predictable
rather than a design decision. **That is a hypothesis and it is not tested
here** - it is the next gate, not a result.

## The gap worth understanding first

`test_roughing_windows` counted **27 ceiling phases** over the same 30
configurations, and the flag is set in **6**. A phase-1 window runs in 27 and
hands over in 6. Whatever separates them is the actual condition, and it should
be understood before either number is trusted - a handover that fires in 6 of
27 is a narrow path, and narrow paths are where the wrong general rule hides.

## Method note

The three sites carry identical text, so the instrument inserts by LINE NUMBER
with a content assertion on each line rather than by unique anchor. Anchoring
would have matched the first site three times or refused outright.

## Gates

None changed. This is a measurement over an instrumented scratch copy; no
`.ngc`, `cfg` or Python was edited.
