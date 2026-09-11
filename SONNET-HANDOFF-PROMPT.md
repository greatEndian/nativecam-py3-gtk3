# Handoff prompt for a Sonnet 5 session (written 2026-09-11)

Paste the block below into a fresh `claude` session started in
`/home/user/nativeCamDev`. It is scoped to the two open items that CANNOT change
generated motion, which gives a cold session a hard, checkable gate and keeps
geometry away from it while nothing has been cut yet.

---

Repo: /home/user/nativeCamDev   Branch: liveTooling (stay on it; never push to main)

Read CLAUDE.md first and follow it exactly - especially "Python first, O-code last",
"Research, show the path, fix, self-verify", "Plan the whole blast radius first", and
the Action buckets. Also read openPoints.md (the list of what is LEFT) and
analysis/114-127 (this week's findings). Do not start editing before you have read them.

## Your two tasks

Both are chosen because NEITHER MAY CHANGE GENERATED MOTION. That is your hardest
acceptance gate - see "Prove you changed no motion" below.

### A. Show the raw code behind a tree item (primary)
openPoints: "EVERY TREE ELEMENT SHOULD OPEN ITS OWN RAW CODE". Build only the
READ-ONLY half: selecting a feature in the NativeCAM tree can open a window showing
the template that feature carries.

The backing store already exists - a saved project embeds it on the feature element:
`call=`, `definitions=`, `before=`, `after=`, `validation=`, `init=`, with `src=`
naming the cfg it came from. Show those, labelled, read-only, non-modal, with the
`src=` path visible. GTK3 (this is a Gtk.Box embedded in AXIS).

Do NOT build editing or write-back. The hard part is migration - a cfg `version` bump
REPLACES the stored template, which is how a user's edit would be silently lost - and
that needs a decision from greatEndian that has not been made.

GTK3 gotchas from the port, in CLAUDE.md: dynamically created menus/toolbars need an
explicit `show_all()`; dialogs need `parent=` + `DESTROY_WITH_PARENT` or you get
phantom windows on exit.

### B. Rebuild the coverage sweep (secondary, only if A is finished and verified)
openPoints: "THE COVERAGE SWEEP STILL NEEDS REBUILDING ON THE SETTLED FRAME."
analysis/123 settled the frame: build_stop_contour_gcode emits CONTROL-point frame
when the polyline compensates (param_n_comp 1 or 2) and CONTACT frame when it does
not - all 40 shipped projects are n_comp 0, so contact. Radial measurements are
frame-independent on axis-parallel stretches; axial ones are NOT.

It is an instrument, not a gate: it must not change any generated file.
Before building it, read test_leftover.py and test_x_continuity.py - they already own
part of this ground, and if you cannot state what yours measures that they do not,
say so and stop rather than build a third overlapping instrument.

## Rules that have actually cost this project time - do not rediscover them

O-code (lib/**/*.ngc):
- A comment must close on the SAME line. A two-line `(...)` is "Unclosed comment".
- NO nested parens inside a comment - `(normal (1,0) gives ...)` halts rs274 with
  "Nested comment found".
- A local first assigned inside an `if` fails load-time pre-parse. Assign it outside.
- Anything writing a GLOBAL must sit inside the guard that decides whether the feature
  is active, or an operation that is switched OFF starts leaking state.
- A global read anywhere in lib/ MUST have a `create_defaults()` entry in ncam.py, or
  the whole file fails at load with "Named parameter not defined".

cfg (cfg/**/*.cfg):
- A cfg edit does nothing until `version` is bumped - a saved project keeps the STORED
  template until migration.
- An `<exec>` inside `[CALL]` must be INDENTED (the file is INI-parsed; column 0 ends
  the value) and must be FLAT (no mixed indentation inside the exec body).

Tests:
- NEVER hardcode a parameter-window slot range or base. Import LVL_BASE, FLANK_BASE,
  FC_BASE, STOP_BASE ... from lathe_sections. This class has bitten four times.
- Assert the PROPERTY, not a measured number. Seven of eight driver failures this week
  were gates pinning a hash, a slot range, a widget count or an exact item count, each
  broken by a change that was correct.
- Every check needs a NEGATIVE CONTROL: prove it fails on the bug it exists for. If the
  control passes, you do not have a gate - say so and do not ship it.
- Never re-record a pinned baseline without stating the evidence that the change was
  intended.

Running things:
- Run ONE heavy sweep at a time. Two writing the same file interleave silently and
  produce duplicate rows that look like real results.
- rs274 resolves lib/ subroutines at PARSE time, not generation time. An A/B on a lib/
  change must keep the file in place across generation AND parsing.
- Never point rs274 at the live .var; the helpers already copy it to scratch.

## Prove you changed no motion (the gate for both tasks)

    python3 test_motion_fingerprint.py --write /tmp/before.txt     # BEFORE you edit
    ...make your change...
    python3 test_motion_fingerprint.py --baseline /tmp/before.txt  # must be 0 changed

"0 changed of 46" is required. Anything else means you touched generation and must
stop and explain.

## Before any commit

    flake8 ncam.py pref_edit.py restore_lcnc.py ttt graphics/source/create_icons.py \
      --builtins="_" --select=E9,F63,F7,F82
    flake8 ncam_*.py lathe_sections.py --builtins="_" --select=E9,F63,F7,F82
    python3 cam_map.py && python3 test_cam_map.py
    python3 test_lathe_validation.py && python3 test_coord_mapping.py && python3 test_vkb.py
    python3 test_project_sweep.py          # ~8 min, 45 clean of 46 expected
    python3 test_surface_equality.py

All must exit 0. The one known failure in the suite is test_rough_ends.py - it is
awaiting a decision from greatEndian, so leave it failing and do not "fix" it.

## Deliverables

- Write analysis/NNN-slug.md for every finding AT THE TIME, with the actual numbers,
  the root cause, why it was not caught earlier, and any attempt that failed.
- Tick what you finish in openPoints.md and add anything new you discover.
- Commit per logical change, message stating what moved and the number that proves it.
- If something needs a decision from greatEndian, STOP and write the options with
  measurements - do not guess. Several items on that list are marked NEEDS A CALL and
  are his, not yours.

## Do not

- Touch anything under "ID work - PAUSED at greatEndian's word, 2026-08-02".
- Change any default in a cfg (the nose-comp default question is open and In-CAM was
  measured UNSAFE - it breaks five projects that use T0 and so have no nose radius).
- Change generated motion at all, in either task.
