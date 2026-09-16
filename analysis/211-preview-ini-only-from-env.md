# 211 — The preview's ini comes only from `INI_FILE_NAME`, and a committed negative result rests on it

2026-09-16, branch `liveTooling`. Found while verifying the crash-hunt
worker's commit `c3c678d` ("did not reproduce standalone") before relaying it,
per the standing rule that an agent's result is checked, not repeated.

## The chain, each link confirmed

`ncam_preview_ui.py:1206`:

```python
ini = getattr(self, 'ini_file', None) or os.getenv('INI_FILE_NAME')
```

- **`self.ini_file` is never assigned anywhere.** `grep -rn "ini_file"` over
  `ncam.py`, `ncam_app_actions.py`, `ncam_project_io.py`, `ncam_ui_chrome.py`
  returns nothing but this read. That half of the expression is dead code.
- So the preview's ini comes **solely from the environment**. `INI_FILE_NAME`
  is only ever READ in this project — here and at `ncam.py:3053` — and set
  nowhere, in the repo or in either worker harness.
- **LinuxCNC exports it**: `/usr/bin/linuxcnc:802`,
  `INI_FILE_NAME="$INIFILE"; export INI_FILE_NAME`. **So a panel embedded in
  AXIS is unaffected**, which is why no user has seen this.
- Any run that passes the ini on the command line instead — a test harness, or
  `ncam.py -i <ini>` — leaves `ini` as `None`. `PreviewPane` stores it, and
  `_worker` calls `ncam_preview.parse_program(fname, self.ini_path)`
  (`ncam_preview_ui.py:534`) with `None`.
- `_canon_dump` (`ncam_preview.py:215`) then sets
  `cwd = os.path.dirname(os.path.abspath(ini_path or path))` — with no ini
  that is the **`.ngc`'s own directory** (`…/ncam/scripts`), not the ini's —
  and omits `-t`, which its own comment at `:201` calls "NOT optional". The
  ini's relative `SUBROUTINE_PATH` (`ncam/my-stuff:ncam/lib/lathe:…`) cannot
  resolve from there, so the program dies at its first o-word.

## Measured, both shapes

Freshly generated `testing_15_7` (generation itself is healthy, `rc=0`,
2270 lines):

```
rs274 -b -g <ngc> <canon>                      (cwd = repo root, no -i/-t)
    rc=1,   0 motion lines
    stderr: EOF in file:/tmp/rcprobe.ngc seeking o-word: o<facing> from line: 392

rs274 -b -g -i lathe-mm.ini <ngc> <canon>      (cwd = the ini's directory)
    rc=0, 457 motion lines
```

The first is exactly the command shape `/tmp/crash_hunt_main.log` recorded
**197 times**, every one `rs274 run done rc=1`.

## What that does to `c3c678d`

The crash-hunt harness built a real `ncam.NCam()` under Xvfb with the ini on
`sys.argv`, so the preview's ini was `None` and **every one of its 197
interpreter runs aborted at the first o-word with zero motion**. Its 250
iterations genuinely exercised the edit → `action_regen()` → `msg_inv` dialog
path (the "Both directions … directional insert" dialog did fire and was
auto-dismissed), but **never a preview that parsed a toolpath**. Since the
suspected crash involves the preview's worker thread interleaving with the
next edit, the most likely window was not covered.

The result is therefore **narrower than "did not reproduce in 250
iterations"** — it is "did not reproduce with the preview failing identically
every time". Re-run with `INI_FILE_NAME` exported (or the scratch ini passed
to the pane) before treating the negative as meaningful.

Not a criticism of the harness's other halves: its instrument validation is
real (a forced main-thread exception, a forced thread exception and a forced
GLib critical, all three caught), and its 44 `Timeout (0:00:25)!` entries are
**not** hangs — `faulthandler.dump_traceback_later(25, repeat=True)` is armed
once and never cancelled, and 1112 s ÷ 25 ≈ 44.5 matches the 44 dumps.

## Why it was not caught

- The harness logged the interpreter's exit code but **asserted nothing about
  motion**; `regen_ok=250` counts Python exceptions escaping `action_regen()`,
  not whether a toolpath appeared.
- `analysis/291` never mentions `rc=1` at all.
- `parse_program` is deliberately forgiving — failures land in `.error` rather
  than raising (`ncam_preview.py:261`), and a run that fails part way still
  returns its partial path. So the pane keeps working and shows
  `Preview: <error>` in the status line (`ncam_preview_ui.py:571`) plus the
  error text on the canvas. Visible to a human watching, invisible to a
  headless loop that only reads exit codes.
- Under AXIS the env var is always set, so the dead `self.ini_file` half has
  never mattered in production.

## What is still unknown

Whether the "Both directions + Regenerate" crash reproduces once the preview
actually parses motion. That is the re-run this finding asks for, and it is
the only way the standing open point moves.

## Open point recorded

`openPoints.md`: the preview's ini resolution, and the qualification on
`c3c678d`'s negative result.
