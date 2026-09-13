# 190 — reconciling openPoints.md against the analysis/ record

**Asked**: `openPoints.md` had 69 unticked `- [ ]` entries and at least one was
already done — item "1. RESPECT TOOL FRONT ANGLE..." says "FIXED 2026-08-24,
`analysis/064`" in its own body, and had been recommended today as the next
piece of work anyway. Walk every open entry, classify it against the file's
own body and `analysis/` (by grep, not memory), and fix the record. Edits
scoped to `openPoints.md` only — no source, no tests, no generation.

## Method

Read the whole file front to back (4600+ lines at the start), noted every
`- [ ]` and `- [~]` entry with its full body, and cross-checked each claim of
"fixed"/"closed"/"done" against either (a) measured numbers already inline in
the entry's own body, or (b) the cited `analysis/NNN` file, or (c) — twice —
the live repository itself, where the claim was about current code state
rather than a past measurement. Never ticked an entry on the strength of a
bare "fixed" with no analysis number and no measurement behind it.

## Counts

| class | count |
|---|---|
| done (`[x]`, top-level) | 161 |
| blocked (greatEndian / ID pause / real-machine test) | 20 |
| genuinely open, unblocked | 39 |
| `[~]` verified-but-not-wired (one staged migration project) | 8 |
| informational / documented, no action pending | 3 |
| watch, not work | 1 |
| **total top-level entries** | **232** |

Six top-level checkboxes were flipped `[ ]` → `[x]` in this pass (two of them
the entries this task was commissioned over), one nested `[x]` flip
(a NEEDS A CALL answered by the fix beside it), one stale duplicate block
removed (three entries, ~57 lines), and one "NEEDS A CALL" headline corrected
to say the call was already made.

## The two entries this task named, both confirmed and fixed

### 1. "RESPECT TOOL FRONT ANGLE..." — PARTLY DONE, was fully unticked

Body already said: *"FIXED 2026-08-24, `analysis/064`"*, with the measured
result (both flanks ramp at 13.00°, `test_front_flank` and
`test_front_flank_path` both green). Checked `analysis/064-front-angle-
complement.md` directly — it corroborates exactly: `flank_slope(90-front_deg,
clearance)` in, both flanks 13.00° out, matching the body's own table.

A *second* verification was appended later, 2026-09-11, already `[x]`
("THE SIDE IS RIGHT"), confirming the shadow side swaps correctly with
roughing direction on a real profile.

One genuine remainder exists and is correctly still open: a nested "NEEDS A
CALL" (the 2° `back_clear` default applied to the leading flank too, under a
name that means the trailing one) — nobody has answered this, so it stays
`[ ]`. **Fixed**: ticked the outer entry `[x]`, reworded its headline to lead
with "PARTLY DONE... ONE PIECE REMAINS AND IT NEEDS A CALL" so the remaining
scope is what a reader sees first, left the nested NEEDS A CALL open.

### Compensation is all-or-nothing (`taper_id`, `boring`, `facing`) — PARTLY DONE, facing already closed

This is the "second entry... suspected stale in the same way" the task named.
Confirmed by **reading the live files, not memory**:

- `lib/lathe/facing.ngc:99-106`: *"COMPENSATION IS ALL OR NOTHING: roughing
  has no interpreter compensation in any mode, so with nose comp on the
  geometry reaches the COORDINATES... Both 0 unless the operation
  compensates. analysis/124."* — and the roughing loop at line 107 onward
  applies `#<r_ofx>`/`#<r_ofz>` (from `#<_fc_rough_ofx>`/`#<_fc_rough_ofz>`)
  to its own coordinates.
- `lathe_sections.py:4903`, `facing_rough_offset()`: returns a real nonzero
  `(off_z, off_x)` whenever `param_n_comp` is 1 or 2, reusing
  `lathe_comp.offset_vector` — the same primitive `tip_comp_vec` implements.
- `analysis/122-facing-roughing-compensated.md`: real-project A/B, only
  `testing_6`/`8`/`9` (the ones with no stored `n_comp`, so migration
  supplies facing's Native default) change; `testing_15_*`/`current_work`
  (stored `n_comp = 0`) untouched. Exactly the expected signature.
- `analysis/124-facing-offset-moved-to-python.md`: the same offset, moved
  from O-code computation into `facing_rough_offset()` — a refactor, gated on
  byte-identity across all 24 projects with a facing feature.

So of the four ops the entry names, **three are done**: OD `taper`
(`analysis/005`, cited in the entry's own body), the polyline's roughing
(`analysis/006`, also already cited), and now `facing`. The entry's own text
said *"facing is OD and can be done now"* — stale; it already was done, four
days before this reconciliation. The only remaining scope is `taper_id` and
`boring`, and both are named ID work, paused since 2026-08-02.

**Fixed**: reworded the headline to state the true remaining scope and that
none of it is available work right now. Left unticked (the item as a whole is
not fully closed) rather than force it to `[x]`, since forcing it would
under-report that `taper_id`/`boring` genuinely remain once ID work resumes.

## A finding worth flagging on its own: even the task's own example was stale

The task's "What to do" section gives, as its worked example of a
**BLOCKED ON greatEndian** classification: *"Item 2 (back-to-front lead-in)
is one: both variants are built and measured, awaiting a choice."*

Reading item 2 in full (it runs to ~230 lines with sub-items 2a/2b/2c) shows
this is wrong: 2a was *"APPLIED AND VERIFIED 2026-08-25"*, 2b was *"CLOSED
2026-09-01 by measurement"*, and 2c closed alongside 2b. The nested "NEEDS A
CALL before the fix" (variant A vs variant B) is answered inline: variant A
was applied. The outer item-2 checkbox was still `[ ]`, and — worth noting
plainly — the person or process that wrote this reconciliation task's own
example evidently read only as far as the unanswered NEEDS A CALL and not
the two sub-items below it that resolve it. It is exactly the same failure
mode as the two stale entries the task asked me to find, one level removed:
the file's own structure (an outer checkbox above already-closed lettered
sub-items) is what allowed it.

**Fixed**: ticked item 2 `[x]`, ticked its nested NEEDS A CALL `[x]`
(answered: variant A), reworded the headline to state both faults are closed
and to carry forward the one genuinely separate open finding the 2a gate
turned up (`testing_13_arcs.xml` does not generate in nose-comp Off — kept as
its own item, unrelated to item 2's own closure).

## A duplicate block, self-contradicting — found, checked, resolved

Three consecutive `[x]` entries (`NATIVE-COMP COVERAGE GAP — CLOSED`,
`Front-face reach on testing_13_arcs`, `An 18 µm gouge...`) were each
duplicated verbatim immediately below the first copy — roughly 57 lines
repeated. Both copies of the first two entries were byte-identical. The two
copies of the third **disagreed**: the first said *"The `PARAM_N_COMP`
tooltip now says so... version 1.75 → 1.76"*; the second said *"not done here
because a `.cfg` edit needs a version bump."*

Per the task's own rule — *"where the body and an analysis file disagree,
that is the most valuable thing you can find. Do not resolve it silently"* —
this is the same class of disagreement even though both sides are the file's
own body. Checked which is true rather than guessed:

```
$ grep -n "^version" cfg/lathe/polyline.cfg
2:version = 1.76
$ grep -A3 "PARAM_N_COMP\]" cfg/lathe/polyline.cfg
tool_tip = _("... PREFER IN CAM WHERE AN ARC MEETS ANOTHER SURFACE AT A
SHARP CORNER: arcs reach the interpreter as chords...")
```

The tooltip text and version both match the first copy exactly. The second
copy is a stale leftover, predating the tooltip work, accidentally left
behind a second time. **Fixed**: removed the second (stale) copy of all three
entries, replacing them with a short note recording what was found, why, and
how it was checked — so this is not silently rediscovered as "the file has
two contradictory answers" by the next reader.

## Other reclassifications, each with the evidence used

- **"THE PHASE-1 HANDOVER... MY EARLIER CLAIM RETRACTED"** — ticked `[x]`.
  The chain of corrections (`analysis/086`→`087`→`088`) ends with *"THE
  CAVEAT IS NOW SETTLED... analysis/088"*, and the very next (already `[x]`)
  entry closes the actual fix via `analysis/089`. Kept as its own entry for
  the retraction it records, not merged into the next one.
- **"~~THE STACK IS PREDICTED - NOTHING IS WIRED.~~"** — ticked `[x]`. The
  entry immediately above it already announces *"Superseded text follows"*,
  and the entries after it (`analysis/091`, then the table-driven ladder)
  show wiring actually happening — so the struck-through claim is exactly as
  superseded as its own strikethrough says.
- **"The finding that outranks the list..."** (CAD-model package insight) —
  ticked `[x]`. It is the concluding insight of the reference-screenshot scan
  above it, not a task — the line immediately after it already reads *"Done
  from this scan: 15..., 8..."*
- **"NEEDS A CALL — the holder model..."** — headline corrected, left
  unticked. The body already records greatEndian's answer (*"leave it OFF...
  I will test it at real machine"*) and says outright *"Nothing further to
  decide here."* Not a call any more; what remains is a real-machine test,
  which is external and not a documentation gap. Reworded so a future reader
  does not read this as awaiting input that already arrived.

## The `[~]` state, documented

Eight entries use `- [~]` — a third state the file's own "Conventions"
section never named, meaning *verified/predicted in Python but not yet wired
into the toolpath: the measurement is done and gated, but nothing in `lib/`
reads it, so motion is untouched*. All eight are legitimate uses of exactly
that state (the roughing-ladder-in-Python migration, `analysis/080`-`096`,
and the undercut/groove-suppression measurement, `analysis/046`). Added it to
the Conventions list at the top so the next person does not have to infer it
from context, as I did.

## What is NOT changed, and why

The 39 entries listed as "genuinely open and unblocked" in the new index were
left exactly as they were — each already correctly states what is left, has
no stale "fixed" claim in its own body, and is not gated on a decision, ID
work, or hardware. Re-verifying each one's underlying claim against a fresh
measurement was out of scope (`git diff --stat` must show only `openPoints.md`
changed, and the non-interference rules forbid running `test_project_sweep.py`
/ `test_motion_fingerprint.py` / `test_surface_equality.py` / anything under
`.claude/skills/lathe-gcode-verify/scripts/` while another session may be
using them) — this is a documentation reconciliation, not a re-measurement
pass, exactly as scoped.

The 20 "blocked" entries were left unticked and unedited except where a
headline actively misstated the block (the holder-model NEEDS A CALL, above)
— being blocked on ID work or a decision is not staleness, it is the correct,
current state.

## Gates

```
python3 cam_map.py        exit 0, 9/9
python3 test_cam_map.py   exit 0
git diff --stat           openPoints.md only, 1 file changed
```

No source, test, `lib/`, or `cfg/` file touched.
