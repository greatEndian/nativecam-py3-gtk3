# 270 — isolating parallel worker sessions with `git worktree`

**Asked**: `SONNET-PROMPT-WORKTREES.md` — build a documented, actually-run
way to run N Sonnet worker sessions against this repo without the three
recurring incidents (cross-session file sweep `8c38722`/`1e08a93`,
`analysis/130` numbered twice, `analysis/134`'s false failures under load).

## Result

```
Script:  worker_worktree.py (create / remove / list / link-sim)
Doc:     WORKTREES.md
Full lifecycle actually run twice this session (see below), not just written.
Finding: the sim/rs274 lane BREAKS in a fresh worktree by default, and is
         only partially fixed (symlinks recreated, NOT run through rs274)
         by link-sim.
0 bugs found in the tooling; 1 real limitation found and documented (below).
```

## What was actually run, with real output

1. **Create.** `git worktree add -b wt-demo-branch ~/nativecam-worktrees/wt-demo
   liveTooling` from the main tree. Checked out cleanly (920 files), `git
   worktree list` showed both trees.
2. **Sim path, measured not assumed.** `ls configs/sim/axis/ncam_demo/` in
   the new worktree showed only the 7 tracked files (`*.ini`, `README`) —
   `ls configs/sim/axis/ncam_demo/ncam/` failed with "No such file or
   directory". Confirmed against `.gitignore` line 218
   (`configs/sim/*/ncam_demo/ncam/`) and against the main tree, where the
   same path is 3 absolute symlinks (`cfg`, `graphics`, `lib`, each
   pointing at `/home/user/nativeCamDev/...`) plus 3 real directories
   (`catalogs`, `my-stuff`, `scripts`).
3. **Cheap gates.** `python3 test_vkb.py` and `python3 cam_map.py` inside
   the worktree — both exit 0, output identical in shape to the main tree's.
4. **Trivial commit.** Added `WORKTREE_SMOKE_TEST.txt`, committed on
   `wt-demo-branch`.
5. **Merge back.** From the main tree: created a throwaway integration
   branch `wt-merge-scratch` off `liveTooling` (not `liveTooling` itself —
   this dry run produced nothing worth keeping), `git merge --no-ff
   wt-demo-branch`, confirmed the file arrived with `ls`/`cat`, switched
   back to `liveTooling`.
6. **Teardown.** `git worktree remove ~/nativecam-worktrees/wt-demo`,
   `git branch -D wt-demo-branch wt-merge-scratch`, `rmdir
   ~/nativecam-worktrees`. Confirmed `git worktree list` back to one row
   and `git status --short` on `liveTooling` unchanged (same untracked
   files as before the run, modulo other sessions' own new files appearing
   independently — `openpoints_check.py` showed up mid-session, not mine).
7. **Repeated the whole cycle a second time through the finished script**
   (`create script-smoke` → `link-sim script-smoke` → cheap gates → `remove
   script-smoke`) to prove the delivered tool does what the manual dry run
   did, not just that the manual steps work. `readlink` on all three
   symlinks confirmed they point inside `~/nativecam-worktrees/script-smoke`,
   never at the main tree. Re-running `link-sim` printed "already correct"
   for all three instead of re-linking.

## The sim-path finding, stated plainly (as the prompt asked)

**A worktree breaks the embedded-sim path by default.** Read (not
assumed) `ncam.py`'s own startup chain:

- `require_ini_items` resolves `NCAM_DIR` from the ini's `[DISPLAY]NCAM_DIR`
  value, relative to **the ini's own directory** — inside a worktree, that
  is the worktree's own `configs/sim/.../ncam`, which does not exist.
- `update_user_tree` (`ncam_app_actions.py:33`) creates that directory when
  `SYS_DIR != NCAM_DIR`, but its `fromdirs` is `[CATALOGS_DIR, CUSTOM_DIR]`
  only — it never creates `cfg`/`lib`/`graphics`.
- `require_ncam_lib` then requires `[RS274NGC]SUBROUTINE_PATH` to resolve to
  a real, existing directory under `NCAM_DIR/lib` — which does not exist —
  and calls `err_exit` before anything resembling `rs274` motion runs.

Grepped the whole codebase for whatever creates these three symlinks in the
first place: nothing does, in the current tree. `restore_lcnc.py` symlinks
unrelated system files (`ncam.py`, `pref_edit.py`, locale `.mo` files) into
`/usr/share/...`, not this. The five `test_*.py` files that call
`os.symlink(lib, ...'ncam/lib')` (`test_ladder_account.py`,
`test_level_intervals.py`, etc.) do it for their own scratch temp dirs, not
for the shipped demo configs. The farm under `configs/sim/*/ncam_demo/ncam/`
is manual and untracked, on this machine as much as it would be on any
fresh worktree.

This matches `analysis/057`'s incident from the other direction: that one
was `gen_project.py --repo <worktree>` run against the **shared, main-tree**
ini while a worktree existed, which let NCam's own startup (`SYS_DIR` =
`os.path.dirname(os.path.realpath(__file__))`, resolving inside the
worktree once `ncam.py` ran from there) re-point the *live* config's
symlinks into the worktree. Different direction, same root cause: the farm
is manual, untracked, and has no worktree-aware code path.

`link-sim` fixes the FIRST failure (missing symlinks) by recreating the
three symlinks inside the given worktree only, pointed at that worktree's
own `cfg`/`lib`/`graphics`. This is as far as this session verified it —
**`rs274`/`ncam.py` were not run through it**, per the prompt's own
instruction not to run `rs274` or generate projects while another session
may own that machine. `WORKTREES.md` says this explicitly rather than
implying the sim lane is proven: it is unproven, not fixed, until someone
runs it for real. The honest per-lane verdict: worktrees suit the
non-`rs274` lanes outright; the `rs274` lane needs `link-sim` first and even
then is unverified end to end.

## `analysis/NNN` collisions — branch-per-worker does not solve this

Checked whether anything better falls out of branch-per-worker, as the
prompt asked. It does not, for this specific problem: two workers on two
branches each choosing `analysis/200-<different-slug>.md` merge into
`liveTooling` with **zero conflict**, because git only conflicts on
identical paths and the filenames differ. The 2026-09-13 `analysis/130`
collision would reproduce exactly the same way across two worktrees as it
did in one shared tree — the number, not the file, is what collided, and
no amount of directory isolation touches that. The hand-assigned range
convention (already in use — this file is `270`, in the `270`-`279` range
the prompt assigned) remains the entire mitigation.

What worktrees DO fix outright, by construction rather than by convention,
is incident 1's mechanism: a bulk `git add -A`/`git add .` inside one
worktree can only ever add files that physically exist in that worktree's
own directory. Another session's in-flight file is not merely excluded by
discipline — it is not present on disk to be swept in the first place.

## What remains shared regardless

**The machine.** `analysis/134` already measured concurrent `rs274` load
producing false `FAIL`s on healthy drivers. Worktrees give each worker its
own files and its own git index; they do not give two `rs274` processes
their own CPU or the sim's LinuxCNC lock. Two workers, each correctly
isolated in its own worktree, each running `rs274` at the same moment,
still contend for the same shared machine `analysis/134` describes.
`run_tests.py`'s retry-once behaviour (from the non-interference rules)
reports this correctly; it does not prevent the contention, and nothing in
this deliverable attempts to — actual serialisation (a lock file or a
"one rs274 run at a time" queue) is out of scope here.

## `lathe_sections.py` as a single-writer resource — confirmed, not assumed

`git log --oneline -18 -- lathe_sections.py`: all 18 of the most recent
commits touching Python geometry code in this project touch this one file
(`feat(lathe)`/`fix(lathe)`/`refactor(lathe)`/`perf(lathe)`, from the ladder
head through the ramp-direction table to the just-landed `detect_sections`
fix, `f610fbd`). `offset_contour` confirmed still at line 4220. File-level
worktree isolation lets two sessions each hold their own uncommitted edit
to their own copy without an immediate collision, but every substantial
geometry feature in this project's own history was built as a sequence of
edits to this same file, each on top of the last — not as independent
pieces two sessions could genuinely work on in parallel. Worktrees turn a
same-line collision from silent (today: two sessions' uncommitted edits in
the one shared tree simply clobber each other with no signal) into a merge
conflict (visible, at least) — they do not make the file safe for two
concurrent geometry writers. That remains a scheduling decision, recorded
here rather than solved.

## Verification

```
flake8 worker_worktree.py --builtins="_" --select=E9,F63,F7,F82   exit 0
python3 cam_map.py                                                 exit 0
python3 test_cam_map.py                                            exit 0
git worktree list                                                  1 row (main tree only) - clean
git status --short                                                 unchanged from session start (own files only added)
```

No `rs274` run, no project generated, per instruction. The two throwaway
worktrees (`wt-demo`, `script-smoke`) and their three branches
(`wt-demo-branch`, `wt-merge-scratch`, `worker/script-smoke`) were all
removed before this file was written; `~/nativecam-worktrees` does not
exist on disk at the end of this session (created twice, `rmdir`'d twice,
once per verification pass).

## What is still unknown

- Whether `link-sim`'s symlink farm actually lets `ncam.py`/`rs274` complete
  a real generation run from inside a worktree — not run here, on
  instruction. The next session that owns the machine should try it.
- Whether greatEndian wants the machine-contention problem (the one thing
  this doc says is still fully shared) addressed with actual serialisation
  — a lock file, a queue, or a standing "only one rs274 at a time" rule.
  Out of this deliverable's scope; recorded as the open question worktrees
  do not answer.
