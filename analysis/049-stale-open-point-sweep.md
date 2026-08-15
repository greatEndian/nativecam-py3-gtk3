# 049 — Sweeping the stale open points

2026-08-15, branch `liveTooling`. greatEndian asked for housekeeping after a
fortnight in which the roughing path was rebuilt several times over.

## Why a sweep was needed

`openPoints.md` is the record of what is LEFT, and its value is entirely in
being trustworthy. After ~30 commits of roughing work, several entries were
demanding work that had already shipped — the clearest being *"the stop contour
must carry `fin + prefin`"*, which `3df0a4c` did days earlier. An entry like
that is worse than noise: it is a standing instruction to redo finished work.

## Method

Every `- [ ]` was read and checked **against the code**, not against memory or
against a commit message. The bar for ticking was a grep that proves the change
is present — not a commit that claims it.

Deliberately conservative: **a wrongly-ticked point is worse than a stale one**,
because nobody looks at it again. Where the evidence was partial, the entry was
left open with the partial state recorded.

## Ticked — 8 of 49

| entry | evidence |
|---|---|
| stop contour must carry `fin + prefin` | `stop_x, stop_z = fin_off + pf_off, fin_off_z + pf_off` present — `3df0a4c` |
| document the four overlays | Help > Preview Lines — `65b6672` |
| dashed/solid convention mislabels two | renamed to *limit*, dash-dot class — `efcea35` |
| the entry line's constant gap needs stating | stated in that dialog — `65b6672` |
| gap 1 tool clearance FRONT, NEEDS A CALL | greatEndian ruled 2026-08-13; `eab37b1` + `8b2da4e` |
| gap 1 TOOLPATH half is still a decision | built opt-in, off by default — `8b2da4e` |
| pre-finish offset 0.0 ignored by roughing | the motion always honoured it; the ENTRY contour did not, and now carries the allowances — `e27a858` |
| missing first pass behind the boss, under a different offset | `5790e01` + `288b936`, confirmed by greatEndian in AXIS |

**49 → 41.**

## Left open on purpose, with the reason

- **Rest machining (gap 12)** — `analysis/047` measured that there is nothing to
  cut within one operation, but the feature is not built. Measured is not done.
- **Back angle clearance changes the part** — the range was narrowed to 0.01–10
  (`0cbaca4`), but the underlying caution is a fact about the parameter, not a
  task that narrowing completed.
- Everything else that could not be proved present by reading the code.

## What made entries go stale

Not carelessness so much as the shape of the work: a fault would be recorded,
then fixed three commits later as a side effect of a different fix, with the
commit message naming the fix and not the open point. `5790e01` closed two
entries it never mentions.

The habit that would prevent it is cheap: when a commit closes something in
`openPoints.md`, tick it in the same commit. Two of this session's later
commits did exactly that, and none of those entries needed sweeping.
