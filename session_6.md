# Session 6 — 2026-09-15/17, coordinator + four parallel workers

Written before a week's break, so next week starts from the record rather than
from memory. `openPoints.md` is what is LEFT; this is what HAPPENED.

## Delivered on `liveTooling` (all pushed)

| commit | what |
|---|---|
| `486577e` | **Phase 2 no longer re-cuts phase 1's ceiling level.** Found uncommitted in the working tree from a stopped worker; gated here, not taken on trust. |
| `c23c36d` | `SONNET-LANES.md` + four worker prompts. |
| `4a61349` `2d11f60` | `offset_contour` refuses loudly past its negative-stock bound (worker). |
| `9ca0eee` | Ramp/stop O-code → Python migration **plan** (`analysis/300`), plan-only. |
| `59f8aa9` | `analysis/211` — the preview's ini comes only from `INI_FILE_NAME`. |
| `332ffd1` | `run_tests.py` fails any driver that modifies a tracked file + `analysis/212`. |
| `5a838d2` | Prompt to re-run the crash hunt with a live preview. |
| `f361f11` `d656a46` | **Z limits: outside-the-profile and too-little-to-machine now caught** (worker) — new `z_limit_span.py`, `polyline.cfg` 1.76→1.77, `analysis/250`. |
| `2595aae` | `analysis/213` — regenerate truncates the file the preview is reading. |
| `551056c` | **`ncam.ngc` is now written atomically** — new `atomic_write.py`, `test_atomic_write.py`. |
| `86ab0f4` | openPoints index listed five finished entries as open; corrected. |

## The numbers that matter

- **Ceiling duplicate**: 46-project fingerprint 39 identical / 7 changed, and
  the 7 are exactly the ones the duplicate sweep named. All 7 **lose** moves,
  none gains (9_5 280→274 … 12_0 192→180). Distinct Z-cut level counts and top
  radii identical, so nothing went missing — the real risk, since a level the
  `analysis/058` skip flag still expected would have become a MISSING pass.
- **Atomic write**: negative control (the old non-atomic write, same reader)
  tore **12824 of 13718** reads; `write_atomic` tore **0 of 11850**. 46/46
  fingerprint-identical — only *how* the file is written changed.
- **Negative-stock guard** and **Z-limit validation**: both 46/46 identical,
  verified here rather than relayed.
- **Crash hunt, second run**: previews now genuinely parse (rs274 `rc=0`, 456
  and 472 moves at the gate) against the first run's 197 × `rc=1` with zero
  motion. 250 iterations, no crash captured.

## Branches NOT merged — greatEndian's explicit instruction

Pushed to origin for safety only. **Do not merge without saying so.**

- `worker/restart-rebuild` — `cb39306` in-process rebuild (21 proofs pass,
  verified by running it here) + `099be90`, which fixes the harness writing
  into tracked `cfg/` on every run.
- `worker/crash-hunt` — through `f7e6dc6`: the ini fix, the re-run,
  `analysis/291`/`292`, and the torn-read occurrences pinned.
- `crash-hunt-relay` — an agent worktree branch, fully contained in
  `worker/crash-hunt`.

## What to test next week

1. **Regenerate repeatedly in AXIS, especially with Both directions.** The
   intermittent `File ended with no percent sign (%)` preview error should be
   gone — that was a torn read of `ncam.ngc`, now fixed.
2. **Z limits**: set a limit that falls outside the profile, and one that
   leaves too little to machine. Both should now say so. Existing saved
   projects must migrate (`polyline.cfg` 1.77) — open an old project and
   confirm the check appears.
3. **THE CRASH IS STILL OPEN AND STILL NEEDS YOU.** It is not the torn read:
   you confirmed the panel *disappears*, and a torn read only draws an error
   in the status line. A vanishing panel with no Python traceback points at
   the GDK/X level, and **both harnesses built so far watch Python-level
   signals only**, so neither can see it. When it happens, capture the
   terminal that launched LinuxCNC — that output is the whole unblock.

## Waiting on a decision

The crash symptom detail above · back angle 2° (changes the part) · which
nose-comp setting · may a roughing level pass an obstruction · front limit
lead-in 0.707 mm · the wall pass · pre-finish gap width · `ini_file` vs
`INI_FILE_NAME` as the contract · negative-stock exposure · whether
`turning`/`radius_od` get a nose-comp parameter · and whether to merge the
three branches.

## Process notes worth keeping

- **Geometry work cannot run in a git worktree** — the 46 test projects live
  only in the gitignored sim catalog. Geometry queues in the main tree; GUI
  work gets a worktree. Every `rs274` run takes `flock /tmp/ncam-rs274.lock`.
- **Two committed harnesses were wrong in ways reading could not show.** One
  edited tracked `cfg/` on every run (NCam's own `update_user_tree` deletes a
  real `NCAM_DIR/cfg` and symlinks it back at `SYS_DIR`); one ran 250
  iterations whose previews parsed nothing at all. Both were caught by running
  them and watching, not by review — and `run_tests.py` now fails any driver
  that dirties the tree.
- **The staleness checker never checked its own index**: five finished entries
  sat under "genuinely open" for three days while the tool reported clean.

## Still true, and it outranks the list

**Nothing in this session has cut metal.** Every result is `rs274`, a unit
test, or a headless Xvfb run.
