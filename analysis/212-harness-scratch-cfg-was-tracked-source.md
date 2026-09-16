# 212 — A committed harness's "scratch" cfg was the tracked repo, and nothing noticed

2026-09-16, branch `liveTooling`. Found while verifying the restart-rebuild
worker's `cb39306` before recommending a merge — the branch was good, but its
proof harness modified the repository on every run.

## The symptom

After running `test_restart_rebuild.py`, the worktree showed
`M cfg/lathe/facing.cfg`, with `version` bumped `1.27 → 2.27` and `PARAM_B_X`
renamed to `"Begin diameter EDITED"` — exactly the strings PROOF 1 writes into
what it believes is a scratch copy. File mtime `07:57:24` against the run log's
`07:57:25`. Reproduced on every run.

## Why the obvious explanation was wrong

The harness looks careful. At setup it replaces the scratch
`<scratch>/ncam_demo/ncam/cfg` symlink with a real copy:

```python
cfg_link = os.path.join(dst, 'ncam', 'cfg')
if os.path.islink(cfg_link):
    os.remove(cfg_link)
shutil.copytree(os.path.join(HERE, 'cfg'), cfg_link)
```

A replica of setup lines 81–93, run alone, proves that works: after the guard,
`cfg_link` is a real directory under `/tmp`, and `facing.cfg` resolves to
`/tmp/...`, **not** to tracked source. An audit hook on the real run confirms
the same two events actually happen:

```
REMOVE    /tmp/restart_rebuild_5l25i_rn/ncam_demo/ncam/cfg
COPYTREE  src=<worktree>/cfg dst=/tmp/restart_rebuild_5l25i_rn/ncam_demo/ncam/cfg
```

So the guard fires, and the write still lands in the repo. Both measurements
are correct; the conclusion drawn from either alone is not.

## The actual cause

`sys.addaudithook` on the real run caught the write and the path pair is the
whole answer:

```
*** WRITE INTO TRACKED: <worktree>/cfg/lathe/facing.cfg
    raw path passed to open(): /tmp/restart_rebuild_5l25i_rn/ncam_demo/ncam/cfg/lathe/facing.cfg
```

The raw path is scratch; its **realpath** is tracked. An ancestor became a
symlink *between* setup and the write — and the thing in between is
`ncam.NCam()` itself. `update_user_tree` (`ncam_app_actions.py:115–143`), for
each of `LIB_DIR`, `GRAPHICS_DIR`, `CFG_DIR`:

```python
if os.path.isdir(srcdir) and not os.path.islink(srcdir):
    move_files(s); shutil.rmtree(srcdir)      # deletes the real copy
...
if not os.path.lexists(srcdir):
    os.symlink(tdir, srcdir)                  # tdir = SYS_DIR/<s>
```

So NativeCAM's own startup **deletes** a real `NCAM_DIR/cfg` and replaces it
with a symlink to `SYS_DIR/cfg` — the tracked tree. The order in the harness
was:

1. setup makes a real scratch cfg copy;
2. `NCam()` starts, deletes it, symlinks `ncam/cfg` → tracked `cfg/`;
3. PROOF 1 writes "its scratch copy" straight into source.

Independent forensic confirmation: a leftover scratch directory from the
worker's 01:00 run — which died at a modal dialog *before* startup completed —
still has `ncam/cfg` as a **real directory** holding `version = 1.27` and no
`EDITED`. A later run's scratch has it as a **symlink** into the worktree.

## What it means

- **PROOF 1 was never testing an isolated copy.** It passed, but it was
  reading back an edit it had made to the real cfg.
- **Every run mutated tracked source.** In a worktree that shows up as a dirty
  `git status`; run in the main tree the same code edits the main tree's cfg,
  because `SYS_DIR` is wherever `ncam.py` lives.
- The rebuild feature itself is unaffected — all 21 proofs pass, and
  `_rebuild_panel` does not call `update_user_tree`.

## The fix

`099be90` on `worker/restart-rebuild`: the cfg copy now happens **after**
`NCam()` has started, plus a setup assertion that fails loudly if the scratch
cfg ever resolves inside the repo again. Verified: 21 proofs pass, `rc=0`, and
`cfg/lathe/facing.cfg` is untouched afterwards.

## The generalised guard, and its negative control

A single fixed harness is not the lesson — nothing in the suite was looking at
the tree. `run_tests.py` now snapshots `git status --porcelain -uno` before and
after every driver and compares them **as sets**, so a tree that was already
dirty is never blamed on a driver, and untracked scratch files do not trigger
it. A driver that modifies a tracked file is listed as `DIRTIED TRACKED` and
the run exits non-zero however the driver itself reported.

Validated both ways, because a gate that cannot fail is worth nothing
(`analysis/127` is this project's own precedent):

```
running test_dirty_control.py   PASS  (0.0s)  [DIRTIED TRACKED: M CAM-MAP.md]
  dirtied tree:    1  test_dirty_control.py
runner rc=1
```

The control driver exits 0 while editing a tracked file — the guard still fails
the run — and the pre-existing `M run_tests.py` in the same tree was correctly
**not** attributed to it. The control is a throwaway in the session scratchpad,
deliberately not committed.

## Why it was not caught earlier

The harness's own analysis did check the tracked file — with
`diff <(git show HEAD:cfg/lathe/facing.cfg) ...` — but at a moment when the
comparison still passed. Nothing re-checked after the run, and no gate in the
suite looked at the working tree at all. Reading the harness makes it look
correct; only running it and watching the filesystem shows otherwise.

## Still unknown

Whether other harnesses that build a real `ncam.NCam()` and touch
`NCAM_DIR/{cfg,lib,graphics}` have the same shape. They are now covered:
`run_tests.py` will fail any run that dirties tracked files.
