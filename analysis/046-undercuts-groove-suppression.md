# 046 — Undercuts and groove suppression: what we already do, and what we do not

2026-08-13, gaps **7** and **11**. greatEndian: *"here we will use knowledge from
cutting behind the boss element or Xlevel of segmeng -1 is less than Xactive or
Xsegment - 2"*.

## The rule, and what it turns out to be

Walking in cut order, a region is re-entrant where an earlier segment's radius
lies below the **running maximum** — the profile has come back up, so what lies
between is a pocket reachable only from outside. That is `reentrant_spans()`.

**It agrees with the machinery we already have.** On testing_15_5 the rule
reports `Z-34.4..-69.6, 8.12 mm deep`, and **16 roughing passes lie inside that
span** — the behind-the-boss disjoint intervals, a figure established over
several days of work on that exact geometry. The rule and the scan see the same
thing; the rule says it as a property of the profile rather than as a state a
scan happens to be in.

## So POLYLINE-GAPS.md's suspicion was right

It suspected gaps 7/11 were *"our Respect tool back angle and Re-entrant profile
worded differently"*. Measured:

| the reference offers | we have |
|---|---|
| Machine Undercuts on/off | undercuts are **always** machined |
| Groove Suppression | no such control |
| *(their reach limits)* | back-angle **and** front-angle warnings, per span, in mm |

`PARAM_MULTI_X` — *"Re-entrant profile"* — is **legacy and inert**: its own
tooltip says disjoint-interval roughing "is now applied automatically to every
polyline" and "this control no longer changes generated G-code".

So what is genuinely missing is not detection, and not handling. It is the
**choice not to machine a pocket** — leaving a groove for a grooving tool.

## Why the choice was not built here

Suppression cannot be a roughing-only switch. If roughing and pre-finish skip a
pocket while the finish pass still traces it — and the finish pass follows the
record array, not `finish_profile` — the finishing cut descends into an unroughed
pocket at finishing depth. **That is worse than machining it.** A safe
suppression therefore has to reach roughing, pre-finish and finish together,
which is a change across all three and needs a decision about what the finish
pass should do at a suppressed pocket: skip it, or trace across its mouth.

Recorded rather than guessed. The detector is built, validated and ready for it.

## What was built

- `reentrant_spans()` in `lathe_sections`, validated both ways and cross-checked
  against the behind-the-boss ladder.
- `PARAM_MULTI_X` renamed to **"Machine undercuts / grooves (always on)"** with a
  tooltip that maps our behaviour onto the reference's vocabulary, so an operator
  arriving from that package finds where it lives and learns that undercuts are
  always machined here. Renaming is safe: migration matches parameters by
  `attr['call']`, not by display name — checked before touching it.

**Deliberately not a warning.** Every 15_x and 9_x demo project has a pocket,
because that is what those parts are. Reporting "this profile is re-entrant"
would fire on nearly every job and train the operator to ignore it — the trap the
leading-flank survey was held back from. What an operator needs to know is
whether the tool can REACH, and the two flank warnings already say that.

## A flaw the controls caught

The first version reported a **plain step-down** as a pocket: it closed the
trailing span at the end of the profile. A dip that never comes back up is the
part getting smaller, cut from outside like anything else — greatEndian's rule
needs an *active* segment standing above the earlier one. The falling-profile
control caught it before it left the bench.

## Verified

`test_reentrant.py` (rising, falling, one groove, two grooves, too-short, plus
the cross-check against roughing and a plain profile reporting nothing),
`test_all_projects`, `test_leftover`, `cam_map`, flake8. Byte-identical:
testing_15_5 `b849fd15881b`, testing_15_2 `7de894acaec9`. `polyline.cfg` → 1.59.
