# 240 — a checker for openPoints.md, built on cam_map.py's idiom

**Asked**: `openPoints.md` decayed twice in two days — `analysis/190`
(2026-09-13) found six entries already done but still `- [ ]`; one day
later the same file was stale again, six preview entries (`24c0b80`,
`test_preview_wiring.py` passing) still unticked. Build a checker, `cam_map.
py`'s idiom — a check exists because it would have caught a real staleness,
proven by a test per check.

## Signals considered, and which ones made the cut

Three signals were in scope; a fourth was considered and rejected outright.

### C1 — an unnegated closure word naming its own evidence close by: KEPT, high confidence

`analysis/190`'s founding case: *"FIXED 2026-08-24, `analysis/064`"* sitting
in an unticked entry. The naive form — any ALL-CAPS closure word anywhere in
the body — was tried first and immediately produced three false positives on
the CURRENT (already-clean) file:

- `PARTLY DONE — only taper_id and boring remain...` — "DONE" is the very
  first content word, real work genuinely remains.
- `DECIDED, NOT A CALL ANY MORE — the holder model is BUILT...` — "DECIDED"
  answers a QUESTION (leave the flag off), not the underlying real-machine
  test, which is still pending.
- `So the remaining reading is COMPENSATION... CONFIRMED by greatEndian: it
  is the tool tip nose radius` — "CONFIRMED" here confirms a DIAGNOSIS, not
  that a fix landed.

Two refinements, each measured against the real file rather than reasoned
out:

1. **Drop `DECIDED` from the word list entirely.** It structurally means "a
   question was answered," which is a different claim from "the work is
   done" — no proximity rule rescues it, since the very entry that broke the
   naive version puts "DECIDED" as its first word with the caveat ("NOT A
   CALL ANY MORE") immediately AFTER, outside any before-the-word negation
   window.
2. **Require a date or an `analysis/NNN` within 100 characters AFTER the
   word**, not merely negation-free before it. An "early in the body" cutoff
   was tried first and rejected by measurement: the founding case itself,
   "FIXED 2026-08-24, `analysis/064`," sits **842 characters** into its own
   entry (after a `greatEndian` quote and a full technical explanation) — a
   cutoff generous enough to keep that case would have been too generous to
   exclude the "CONFIRMED by greatEndian" false positive at 921 characters.
   Proximity to the closure WORD, not to the start of the entry, is what
   distinguishes a stated verdict ("FIXED 2026-08-24, analysis/064" — six
   characters apart) from a diagnosis described in passing ("CONFIRMED by
   greatEndian: it is the tool tip nose radius" — no date or analysis
   reference anywhere near it).

With both fixes: 0 false positives on the current file (down from 3), and
the founding case still caught when run against `f610fbd:openPoints.md`
(the commit immediately before `ce28d71`'s reconciliation).

A closure word found WITHOUT nearby evidence is not discarded — it is
reported separately as an **unverified claim**, per the task's own rule
("a claim of fixed with no analysis number and no measurement... is a
finding, not a closure"). Today's one instance is the bare "CONFIRMED"
case above — correctly not promoted to a finding, but visible so a human
can decide whether "confirmed" deserves better wording.

### C2 — a citation to an analysis/NNN with no file on disk: KEPT, high confidence

Trivial and exact: `glob` the `analysis/` directory for the cited number.
Zero interpretation needed, so zero false-positive risk beyond a citation
typo — which is exactly the thing worth catching. Verified every real
citation in the current file is 3 digits, zero-padded, matching the files on
disk (checked directly: the shortest digit run cited anywhere is 3), so the
negative control uses the same shape rather than an unrealistic short number.

### C3 — a backtick-quoted UI term whose distinctive word now matches a declared Python identifier: KEPT, but as a HINT only

This is the one that would have caught the preview case, and it is also the
one with the least precision — tested both directions on the real file:

- **True positive, clean**: `` `Accuracy` slider → `StockField.columns_for`. ``
  → marker "accuracy" → `ncam_preview_ui.py:136`, `self.accuracy_divisor =
  6.0`. Exactly right.
- **True positive, wrong evidence**: `` `Regenerate on rewind` as an option
  ``. → marker "regenerate" → matched `ncam.py:2413`,
  `self.send_regenerates = ...` — an unrelated, pre-existing preference
  about the Send button, matched purely because "regenerate" is a substring
  of "regenerates." The REAL implementing symbol is `regen_on_rewind`
  (abbreviated "regen," not "regenerate"), which this substring search
  cannot find. **The entry is genuinely stale; the evidence handed over for
  it is not the right line.** Recorded as a real, caught false positive —
  this is exactly why C3 is a hint and never auto-acted on.
- **False negative**: `` `Programmed Point` toggle ``. The real identifier is
  `show_point` — no word in "Programmed Point" is a substring of it. C3
  finds nothing here at all.
- **Two entries with no backtick term to search on**: "Collision detection
  is built and tested but not wired to the pane" and "Timeline marks for
  collisions, and a Verification line in Stats" name no quoted UI phrase,
  so C3 has nothing to extract.

**So C3, alone, catches 2 of the 5 real stale preview entries — one cleanly,
one with misleading evidence — and misses 3 outright.** This is reported
honestly as a hint, never promoted to a finding, and never used to tick
anything by itself.

**What closes the gap**: `_section_siblings()`, not a symbol check at all —
a plain structural fact. Every OTHER open entry sharing a hint's `##`
heading is listed alongside it ("N other open entries share its heading,
worth the same look"). This is `analysis/240`'s own actual lesson made
durable: staleness clustered, six entries under one heading stale for the
identical reason, and once ANY one of them surfaces (by any signal), the
other four are a ten-second read away rather than a rediscovery. Verified:
today's Accuracy/Regenerate hints each list the other 4 members of the
"Simulation" cluster (Collision detection, Timeline marks, and — via the
Accuracy hint's own sibling list — Programmed Point, the one C3 could not
find on its own evidence at all).

### Rejected outright: NLP/fuzzy matching between a UI phrase and an unrelated identifier name

Considered building a fuzzier matcher (edit distance, synonym lists) to
catch "Programmed Point" → `show_point`. Rejected: there is no reliable
textual relationship between those two strings, and the general problem
("does this prose describe that code") is not solvable by string
similarity — a looser matcher would only convert today's few honest misses
into tomorrow's flood of coincidental hits on a codebase this size. The
sibling-listing mechanism above closes the practical gap for exactly the
shape of miss that mattered (a co-located cluster) without pretending to
solve the general case.

## Verified against the answer key, not assumed

`test_openpoints_check.py`, 13 checks:

- **C1** against `f610fbd:openPoints.md` (the real, historical, unfixed
  file) — catches the front-angle case by name, and (found while writing the
  test, not planned) ALSO independently catches "THE PHASE-1 HANDOVER..."
  at that same historical commit — one of `analysis/190`'s other five ticks,
  reproduced by an entirely mechanical rule with no knowledge of that
  reconciliation's specific reasoning.
- **C1 negative controls**, all three of `analysis/190`'s own hard cases,
  read from git history / the current file rather than fabricated: PARTLY
  DONE, DECIDED-not-yet-executed, bare CONFIRMED. All three correctly silent.
- A **fourth, broad negative control**: every OTHER entry in the historical
  snapshot besides the two real stale ones must not appear in `findings` —
  the widest net this checker can cast against a real file.
- **C2** both ways: a fabricated missing citation caught, a real one (3-digit,
  matching the file's own convention) left alone.
- **C3** against the real, currently-open Accuracy entry, checked for both
  the hit itself and the sibling list.
- **C3 negative control**: a nonsense term matching nothing in the tree
  produces no hint.

## What it finds today, run on `openPoints.md` as it stands

```
HIGH-CONFIDENCE FINDINGS (0)
UNVERIFIED CLOSURE CLAIMS (1)
  L3306  "So the remaining reading is COMPENSATION..."
         CONFIRMED with no date/analysis/NNN nearby - correctly still open
         (analysis/190: confirms a DIAGNOSIS, not a fix)
HINTS (3, covering the 5-entry Simulation cluster via siblings)
  L2298  `facing` matches lathe_sections.py:1924 - already correctly
         described as done in that entry's own text, nothing to do
  L2822  `Accuracy` slider -> ncam_preview_ui.py:136 - genuinely stale
  L2823  `Regenerate on rewind` -> ncam.py:2413 - genuinely stale entry,
         coincidentally wrong evidence (see C3 above)
```

Exit code 0 — no HIGH-CONFIDENCE finding, by design (a hint never fails the
gate; it asks for ten seconds, not a blocked commit).

## Fixed, following the checker's own hints

The Accuracy hint's sibling list named all five "Simulation" entries.
Confirmed each of the five individually against `24c0b80`'s diff and
`test_preview_wiring.py`'s passing output (not ticked on the hint's word
match alone — the hint is evidence to look, not evidence to act):
`ncam_preview_ui.py:834-838` calls `collisions_checked()`/`collisions()` on
the worker thread and marks the timeline/Stats verdict; `accuracy_divisor`
feeds `StockField.columns_for(divisor=...)`; `show_point` gates the
control-point cross; `regen_on_rewind` gates the backwards-scrub rebuild.
All five ticked in `openPoints.md`, each citing `24c0b80` and the specific
test names that assert it.

The `facing` hint on line 2298 needed no action — that entry (my own
`analysis/220` wording) already correctly describes `facing` as done and
`taper_id`/`boring` as the real remainder; the hint is a harmless echo of
information already stated in the entry's own text.

## Gates

```
flake8 openpoints_check.py test_openpoints_check.py   exit 0
python3 cam_map.py                                     exit 0, 9/9
python3 test_cam_map.py                                exit 0
python3 test_openpoints_check.py                       exit 0, 13/13
python3 openpoints_check.py                            exit 0 (0 findings)
```
