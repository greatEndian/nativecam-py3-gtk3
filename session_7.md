# Session 7 — 2026-10-05/09, orientation after the break, and the plan

Short session: work out where session 6 stopped, then plan. No code changed.
`openPoints.md` is what is LEFT; this is what HAPPENED.

## Delivered

- Where we stand, checked against the files rather than memory. The working
  is in `analysis/310`.
- The plan below, put to greatEndian and **not yet approved**. Phases 1 and 2
  edit `ncam.py`, `lib/` and `lathe_sections.py`, all on the ask-first list.
  Nothing starts until greatEndian says go.
- `openPoints.md`: the header's stale `Last pushed` fixed, plus two new entries
  (crash-capture gap, stale branches to remove).

## The numbers that matter

- `cam_map.py` 9/9 PASS. `openpoints_check.py` 0 high-confidence stale.
- openPoints index: **36** open and unblocked, **20** blocked, **8** worked out
  in Python but not wired, **162** done.
- `worker/restart-rebuild` and `worker/crash-hunt` both merge into
  `liveTooling` (and into each other) **without conflicts**, checked with
  `git merge-tree`.
- The app has **zero** crash-capture hooks (`faulthandler`, GDK log handler).
  That is why the vanishing-panel crash leaves nothing on disk.

## Waiting on greatEndian

1. **AXIS tests from session 6:** regenerate repeatedly with Both directions
   (the `%` preview error should be gone); a Z limit outside the profile and
   one leaving too little (both should warn; an old project should migrate to
   1.77); if the panel vanishes, the terminal that launched LinuxCNC.
2. **Merge** `worker/restart-rebuild` and `worker/crash-hunt`: yes or no.
3. **Decisions:**
   - the 2° `back_clear` is also applied to the leading flank (one number
     for both flanks, or a separate one);
   - a roughing level that clears the pre-finish allowance by 0.0423 mm but
     not the floor allowance (let it through, leaving 0.5503 instead of 0.762,
     or keep the split);
   - the front limit's lead-in goes 0.707 mm past the limit (keep the 45°
     lead, or approach radially);
   - should `turning`/`radius_od` get a nose-comp parameter;
   - should negative stock to leave be shown in the UI;
   - the wall pass;
   - the pre-finish gap width;
   - `ini_file` vs `INI_FILE_NAME` as the contract.
4. **Go / no-go** on the plan below.

## The plan, as proposed

- **Phase 1 — make the crash record itself** (UI work, worktree lane).
  - Turn on `faulthandler` and a GLib/GDK log handler, both writing to a file.
  - Gate: a deliberately segfaulting child leaves its traceback in the log;
    46/46 motion fingerprint identical.
- **Phase 2 — `analysis/300` stages 0–2** (geometry lane, main tree).
  - Stage 0: `_pl_flc_n > 1` on 46/46 projects.
  - Stage 1: a Python shadow of `s_reach`/`s_flat`/`e_reach`, matching the
    608 + 850 captured rows to 1e-4 mm.
  - Stage 2: a per-segment table replaces the runtime formula blocks; 46/46
    byte-identical motion plus the ladder/ramp/rough-comp tests.
  - Stages 3–4 stay blocked behind the ladder-order migration.
- **Phase 3 — finish OD polyline roughing** (greatEndian's order, 2026-09-03).
  - Front-to-back + 5 mm sectioning gives bad sections.
  - One extra lead on `testing_15_9`, still unexplained.
  - First stage ends on a light cut.
  - The back-angle section and comp disagree.
  - Three ramp/flank-shadow questions.
  - 0.0042 mm rapid overlap.
  - Each item: measure in the configuration it was reported in, then the
    46-project fingerprint.
- **Phase 4:** the parametric-op roughing comp (taper OD), then the
  `POLYLINE-GAPS.md` features, each specced first.
- **Parked:** ID work (paused by greatEndian), grooving/drilling comp, the
  first real cut.
- **Execution:** Phases 1 and 2 as two forked agents running in parallel.
  Each gate gets re-run here before anything is relayed. Phase 3 follows
  Phase 2 in the main tree, because geometry cannot run in a worktree.

## What keeps running after /clear

Nothing: no background jobs, no agents, no watchers were started this session.

## Process notes

- Fast orientation that worked:
  - read the newest `session_N.md`;
  - read only the openPoints **Index** (L26–115 — the file is 4888 lines);
  - run `git log liveTooling..<branch>` and `git merge-tree --write-tree --name-only` per worker branch;
  - run `cam_map.py` and `openpoints_check.py`.

  About ten tool calls in all.
- CLAUDE.md still says polyline roughing is "NOT compensated" (dated
  2026-08-03). openPoints L2086 says that is now satisfied through Python
  tables. CLAUDE.md is out of date on that line and was not edited here,
  because it is shared and goes through review.

## Still true, and it outranks the list

**Nothing has cut metal.**
