# Lanes — rules every parallel Sonnet worker follows

Read this before your own prompt. Several terminals run at once against one
machine; these rules are what stop them corrupting each other's work.

## 1. Which tree you work in

| lane | where | why |
|---|---|---|
| **GEOMETRY** (anything that changes or measures generated motion) | main tree `/home/user/nativeCamDev`, **one worker at a time** | the 46 test projects live only in the gitignored `configs/sim/axis/ncam_demo/ncam/catalogs/lathe/projects/` — a worktree has none of them, so fingerprints and sweeps cannot run there |
| **GUI / pure Python** (no motion change) | your own worktree: `python3 worker_worktree.py create <name>` from the main tree, then work in `~/nativecam-worktrees/<name>` | `git status`/`git add` there can only ever see your own files |
| **PLAN** (read and measure, write only an analysis file) | main tree, read-only except your `analysis/NNN` | |

`lathe_sections.py` has exactly one writer at a time: the GEOMETRY worker.

## 2. The rs274 lock — mandatory

Anything that runs `rs274` or generates projects — `test_project_sweep.py`,
`test_motion_fingerprint.py`, `test_surface_equality.py`, `run_tests.py` over
motion drivers, `gen_project.py`, the `lathe-gcode-verify` scripts, a preview
harness — runs under the shared lock:

```bash
flock /tmp/ncam-rs274.lock python3 test_project_sweep.py
```

It queues you behind whoever holds it instead of racing them. `analysis/134`
and `analysis/230`: two sessions loading the machine at once produce false
FAILs on healthy code. flake8, `cam_map.py`, and pure-Python unit tests need no
lock.

## 3. Git

- Stage by explicit path only. **Never** `git add -A`, `git add .`, `git commit -a`.
- Local commits only. **Do not push, do not merge.** Worktree workers leave
  their work on `worker/<name>`; greatEndian merges.
- Commit messages end with:
  `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`

## 4. Records

- Use only your assigned `analysis/` number range.
- Write the analysis file **as you go**, not afterwards: what was asked, the
  numbers measured, the root cause, the attempts that failed, what is unknown.
- A finished item: tick it in `openPoints.md` in the same commit, with the hash
  in the next one if needed. A new open point found on the way: add it.

## 5. Hands off

- The live `configs/sim/axis/ncam_demo/ncam/scripts/ncam.ngc`, any `.var`
  file, and starting LinuxCNC/AXIS: ask greatEndian first.
- ID (inside-diameter) work is paused.
- `test_rough_ends.py` is a known failure awaiting greatEndian's tip-vs-cut
  ruling — not yours, not a blocker.
- A gate failing in a file you did not touch: re-run it once under the lock,
  then report it. Never "fix" code outside your task.

## 6. Done means

Every gate run by you with its exit code in the report, the commit hash, and
the analysis file path. "Fixed" with the work uncommitted is not done — that
has happened here more than once.
