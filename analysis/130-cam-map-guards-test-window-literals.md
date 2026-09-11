# 130 — cam_map gains a check on the tests themselves, and catches a live fifth case

**Asked**: stop a `test_*.py` from ever retyping a parameter-window bound again.
This class has now bitten four times — `test_sections`, `test_surface_equality`,
`test_through_cut`/`test_rough_overlay`, and `test_stock_to_leave` (analysis/126)
— each stale in a different way once `lathe_sections`' own value moved, each
reporting a perfectly good program as broken. `cam_map.py`'s existing checks
(C1b/C1c, `LITERAL_WINDOWS`) all guard the O-code side of this; nothing looked
at the tests.

## What the two historical shapes actually were

Read from git history rather than guessed:

- **Retyped constant** (`test_sections`, `test_surface_equality`,
  `test_through_cut`/`test_rough_overlay`, before their fixes):
  `ENTRY_BASE, ENTRY_TOP = 4200, 4400` — a bare local re-declaration with a
  literal, instead of importing the name from `lathe_sections`.
- **Slot-range regex** (`test_stock_to_leave`, before its fix):
  `re.findall(r'#4[45]\d\d = (-?[\d.]+)', txt)` — a hand-rolled digit range
  standing in for `STOP_BASE`/`STOP_TOP` entirely.

Both go stale the same way and for the same reason: the window moves in
Python, the test's own copy of the bound does not.

## The check — `cam_map.test_window_literals()`, wired in as C8

Two textual sub-checks over every `test_*.py` (excluding `test_cam_map.py`
itself, which deliberately carries both bad shapes as fixture strings for its
own negative control — see below):

1. A line matching `NAME[, NAME2] = <int>[, <int>]` where any `NAME` is one of
   `lathe_sections`' own `*_BASE`/`*_TOP` constant names.
2. A quoted 3-4 digit string literal (`'3160'`, not `str(L.LVLSPLIT_BASE)`)
   that numerically equals a *current* window value.

Deliberately text-only, matching every other check in `cam_map.py` — no import
of the test files, which would run their module-level code.

## A live fifth instance, found by building this, not invented for it

`test_sections.py:685-693` scraped every `#3\d\d\d` broadly (fine, a wide
collector) and then looked up `slots.get('3160')` / `slots.get('3161')` by
**hardcoded string key** — the exact value of `LVLSPLIT_BASE` (3160), typed a
second time, in a file that already does `import lathe_sections as L` and
already uses `L.LVLSPLIT_BASE` two lines earlier at line 576 for something
else. Not currently wrong — `LVLSPLIT_BASE` is still 3160 — but exactly the
fragility the other four hit: nothing would tell this test if it moved.

Fixed to `str(L.LVLSPLIT_BASE)` / `str(L.LVLSPLIT_BASE + 1)`. `test_sections.py`
still passes in full (33 checks, `python3 test_sections.py` exit 0).

## Proven both ways

`test_cam_map.py` gained `C8a`/`C8b`, following the file's own convention —
a known-bad copy written to a scratch tree, `cam_map.check_all()` run against
it, the check demanded to fail:

```
PASS  C8a catches a test retyping a window bound as a bare literal
PASS  C8b catches a test quoting a slot number instead of the name
```

And on the real tree, `python3 cam_map.py` — before the `test_sections.py`
fix — genuinely failed:

```
FAIL  no test_*.py retypes a window bound instead of importing it
      test_sections.py:687 quotes '3160' where LVLSPLIT_BASE belongs; ...
```

After the fix, all 9 checks pass, `test_cam_map.py`'s baseline check ("the
repository passes every check to begin with") passes, and the "must be
SPECIFIC" control is unaffected (C8 is not part of that assertion since it is
a different axis — text files, not `lathe_sections.py`/`lib/`).

## The self-referential trap, caught before it shipped

First run of `test_cam_map.py` with the new negative controls **failed the
baseline check** — `cam_map.check_all()` on the real repo flagged
`test_cam_map.py` itself, because its own negative-control fixtures
(`"ENTRY_BASE, ENTRY_TOP = 4200, 4400"`, `"slots = {'4330': ...}"`) are string
literals inside a file matching `test_*.py`. Excluded `test_cam_map.py` from
the scan with a comment explaining why — it is the checker's own meta-test,
not a test of the CAM system's windows, the same way cam_map's other checks
never scan their own bad-copy-generating code.

## Beware, stated so it is not rediscovered as a false positive

The cfg CALL-scratch block `#3141`-`#3159` (`cfg/lathe/polyline.cfg`) is a
deliberate hardcoded range, not a window bound, and is not in
`lathe_sections.windows()`'s value set — C8 does not and must not flag it.
Confirmed: neither 3141 nor 3159 collides with any window value.

## Not touched

No `cfg/`, `lib/`, or `ncam.py` generation code — `cam_map.py`, `test_cam_map.py`
and `test_sections.py` only. `test_motion_fingerprint.py`: 46 identical, 0
changed, of 46 (shared gate for this session's three tasks, see analysis/132).
