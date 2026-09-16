# 213 — Regenerate truncates `ncam.ngc` while the preview is still reading it

2026-09-16, branch `liveTooling`. Found while verifying the crash-rerun
worker's second hunt (`crash-hunt-relay`) rather than relaying its summary.

## What the run actually contained

The re-run fixed what `analysis/211` identified — the preview now resolves a
real ini, so `rs274` exits `rc=0` with real motion (gate: `testing_15_7`
456 moves, `testing_15_8` 472 moves) instead of the previous 197 × `rc=1` with
zero motion. 250 iterations, `regen_ok=250`, no Python exception, no GLib
critical. The worker's headline is again "did not reproduce".

**But the log is not clean.** Two of 165 previews failed:

```
[ 268.747] PREVIEW DONE: moves=486 error='File ended with no percent sign (%) or
           program end (M2) | o<poly_lathe_mill> endsub' ok=False
[ 640.566] PREVIEW DONE: moves=470 error='File ended with no percent sign (%) or
           program end (M2) | o<poly_lathe_mill> endsub' ok=False
```

Steps ~22 and ~108, both `testing_15_7`, each recovering on the very next
pass. `rs274` hit **EOF in the middle of a subroutine**. That is a truncated
*file*, not a bad *program* — a bad program fails the same way every time.

## The mechanism, read from source

`write_ngc()` (`ncam_app_actions.py:909`) is **not atomic**:

```python
with open(fname, "w") as f:
    f.write(self.to_gcode())
```

`open(fname, "w")` truncates the live `ncam.ngc` at once, then writes ~2270
lines into it. For the duration of that write the file on disk is short.

The preview reads **that same live path**, on a thread:

```python
t = threading.Thread(target=self._worker, args=(fname, stock, tool), ...)   # :529
def _worker(self, fname, stock, tool):
    tp = ncam_preview.parse_program(fname, self.ini_path)                    # :534
```

`refresh()` (`ncam_preview_ui.py:499`) does have a guard — `self._busy` with a
`_pending` slot, so a second Regenerate during a parse keeps only the newest
request "rather than queueing interpreter runs". **That guard is about the
preview's own concurrency. It does nothing about the file.** `action_regen`
calls `write_ngc()` *before* `refresh_preview(fname)`
(`ncam_app_actions.py:234`), so the next regenerate truncates and rewrites the
path while the previous `_worker`'s `rs274` may still be reading it.

Two writers of the same path, one reader, no atomic swap, no snapshot.

## Why this matters

greatEndian's standing report is *"BOTH DIRECTIONS + REGENERATE CRASHES, AND IT
IS RANDOM"*, confirmed intermittent, with no traceback ever captured. An
intermittent, timing-dependent failure that only appears when regenerates
overlap a preview is the right shape, and it is almost certainly **not
specific to Both directions** — that setting widens the window by adding
dialogs and slowing generation, which is also why it would seem to follow that
option around.

**Stated honestly: this is not yet proof of the reported crash.** A truncated
parse lands in `tp.error` and shows `Preview: <error>` in the status line
(`ncam_preview_ui.py:571`) — an error message, not a dead panel. So this is a
real intermittent fault and the best candidate yet, but whether it is *the*
crash needs either a captured traceback or greatEndian saying what "crashes"
looks like: does the panel vanish, does AXIS die, or does it show an error?

**ANSWERED, 2026-09-16 — and the answer rules this out as the cause.**
greatEndian: *"it many times crash line disappearing everyhing"* — the
panel/line **disappears**. This race cannot do that: `parse_program` puts
failures in `.error` rather than raising (`ncam_preview.py:261`), `_worker`
catches nothing fatal, and the pane simply draws the error text. So the torn
read is a **separate** fault. It is still being fixed (greatEndian: *"go
#3"*), because a truncated `ncam.ngc` also reaches LinuxCNC when it loads the
file — but the disappearing-panel crash remains open and unexplained, and no
one should treat this fix as having addressed it.

## Why no earlier run could have seen it

The first hunt (`c3c678d`) never parsed motion at all — every one of its 197
interpreter runs aborted at the first o-word (`analysis/211`), so a truncated
read was indistinguishable from the constant failure. Only a run whose
previews genuinely succeed can show two of them failing.

## APPLIED, 2026-09-16 — greatEndian: *"go #3"*

`atomic_write.write_atomic()` (new module, GTK-free and importing nothing from
`ncam`, the `lathe_sections.py` shape) writes a temp file **in the target's own
directory** — `os.replace` is only atomic within one filesystem — `fsync`s it,
reapplies the existing file's mode, and `os.replace`s it into place. Created
with a plain `open()` rather than `mkstemp`, whose 0600 would have silently
downgraded `ncam.ngc` from 644; the temp file is removed if anything fails.

Wired at the two paths a *second* reader consumes concurrently:
`write_ngc()` (`ncam_app_actions.py:931`) and the flat listing handed straight
to `send_to_linuxcnc` (`:204`).

**`test_atomic_write.py`, validated both ways** — the negative control runs the
same reader against a copy of the old non-atomic write, because a race test
that cannot catch the original bug proves nothing (`analysis/127`):

```
control (old non-atomic write): 13718 reads, 12824 torn
atomic write:                   11850 reads,     0 torn
```

Also asserted: mode stays 644, no temp litter left beside the target, and a
write into a missing directory raises rather than half-succeeding.

Gates: flake8 `rc=0`, `cam_map rc=0`, `run_tests.py` 4/4 with `dirtied tree:
0`, and **46/46 projects fingerprint-identical** — this changes only *how* the
file is written, never its content, and that run exercised `write_ngc`
end-to-end 46 times.

## Consumer survey — why only those two files

Every other `open(..., 'w')` in the project writes something no second process
reads while it is being written: `M123` is created once at startup and only
when absent (`ncam.py:3296`), and the rest are preferences, cfg and project
saves read by NativeCAM itself on demand. Making those atomic would be churn,
not a fix.

## The original proposal, for the record

Either or both, and it is greatEndian's call because it touches the live
generated file everything else depends on:

1. **Write atomically** — `write_ngc()` writes a temp file in the same
   directory, flushes, then `os.replace()`s it over `ncam.ngc`. A reader then
   sees either the old file or the new one, never a short one.
2. **Parse a snapshot** — `_worker` copies the file before handing it to
   `rs274`.

(1) is the smaller change and fixes it for every reader, including LinuxCNC
itself loading the file.

## Not done here

No code changed. The crash-rerun session was told (cross-session message) to
record the two failures in its own analysis with iteration and delay numbers,
and to say whether its harness can raise the hit rate deliberately — the
shortest delays (0/5/15 ms) are the ones that overlap a write with a read.
