---
name: ref-intake
description: "Use when the user points at a ref/<feature>/ folder of screenshots or pasted help text captured from another CAM package, to specify a NativeCAM feature from it. Reads the material, restates it as a parameter table plus behaviour description in this project's own vocabulary, and stops for confirmation before any code is written. Not for specifying a feature the user describes in prose - that is /spec-builder, which this hands off to."
---

# /ref-intake

The user runs another CAM package and mines its function descriptions for
features NativeCAM lacks. This skill is the intake path for that material.

It exists because the failure mode is silent: a screenshot is read slightly
wrong, the misreading is never stated out loud, and it surfaces three hours
later as a toolpath that looks plausible and cuts the wrong shape. So the skill
ends in a **restatement the user can correct in one message**, not in code.

It does not overlap `/spec-builder`. That skill interviews the user *in prose* to
pin down goal, boundaries and edge cases. This one ingests *reference material*
and produces the restatement that spec-builder then consumes. Hand off; do not
re-interview.

## Steps

1. **Read everything in the folder.** Every image (the Read tool renders png/jpg
   directly) plus `NOTES.md`. If told "the newest", use
   `.claude/scripts/find_latest.py` rather than `ls -t` — it sorts by
   `st_mtime_ns`, and `ls -t` has already returned a stale file twice in this
   project (see `md_files/LEARNINGS-LOG.md`).

2. **Produce the restatement artifact, then stop.** Three parts, no code:

   - **Parameter table**: *their name → our name → type → units → default →
     range*. Mark every cell you are inferring rather than reading.
   - **Behaviour**, in NativeCAM's vocabulary — levels, windows, the offset
     profile, lead-in/out, `#<_diameter_mode>` — not the vendor's. If their
     concept has no counterpart here, say so plainly instead of forcing a
     mapping onto the nearest thing.
   - **Unknowns**: everything the material does not settle. This list is the
     point of the whole step. An empty unknowns list on a first pass means you
     have assumed something without noticing.

   Wait for confirmation before going further.

3. **Hand off.** A genuinely new operation goes to `/spec-builder` and then
   `/init-custom` for the `.cfg` + `catalogs/<machine>/menu.xml` + `lib/` sub
   wiring — all three, since a `.cfg` with no menu entry silently never appears
   in the tree. A parameter added to an existing operation skips straight to
   implementation, threaded as a trailing `[CALL]` argument with the sibling
   `.cfg` files that call the same sub updated too, and the `version` bumped so
   saved projects migrate.

4. **Make their worked example the acceptance test.** If the material includes
   inputs and the resulting toolpath, build an rs274 harness from those exact
   numbers under `/lathe-gcode-verify` and prove our output matches, rather than
   eyeballing the backplot. This is the highest-value thing in the folder.

5. **Write our own wording.** Parameter names and tooltips are ours. Never paste
   vendor text into a `.cfg`, and never commit the reference images — `ref/` is
   gitignored for exactly this reason.

## Gotchas & Edge Cases

- **A dialog shows the last-used value, not the default.** Never record a default
  from a screenshot; ask. This one is easy to get wrong because the number is
  right there and looks authoritative.
- **Confirm the vendor's unit mode before using its numbers as an oracle.**
  Diameter vs radius, mm vs inch. Ours is settled by `#<_diameter_mode>`, and a
  scratch harness must run in radius mode (`= 1.0`) or the checkers report
  "cutting air" while the geometry is in fact perfect.
- **Equivalent-looking parameters diverge at the limits.** Every lead-in/out bug
  in this project lived at a limit — zero room left, a radius larger than the
  straight length available to blend it, a pass ending exactly on a window edge.
  Ask specifically what their implementation does at 0 and at the maximum; the
  screenshot will not show it.
- **Text beats screenshots.** If their help is text or HTML, ask for it pasted —
  OCR ambiguity on a decimal point is a wrong toolpath.
- **One feature per folder.** A folder mixing three operations produces a
  restatement that hedges on all three.
- Prose in a vendor dialog often describes the *intent* while the diagram
  describes the *geometry*. Where they disagree, trust the diagram and list the
  disagreement under unknowns.
