#!/usr/bin/env python3
# coding: utf-8
"""Direct unit tests for entry_ramp_dirs and ramp_facing in
lathe_sections.py - pure functions on plain point lists / numbers and a bare
orientation int, no Feature, no NCam, no rs274.
"""
import math
import sys

import lathe_sections as ls

failures = []


def check(name, got, want, tol=1e-6):
    ok = (isinstance(want, (int, float)) and isinstance(got, (int, float))
          and math.isclose(got, want, abs_tol=tol)) or got == want
    print(('PASS' if ok else 'FAIL'), name, '->', got,
          '' if ok else '(want %r)' % (want,))
    if not ok:
        failures.append(name)


def check_tuple4(name, got, want, tol=1e-6):
    ok = len(got) == 4 == len(want) and all(
        math.isclose(g, w, abs_tol=tol) for g, w in zip(got, want))
    print(('PASS' if ok else 'FAIL'), name, '->', got,
          '' if ok else '(want %r)' % (want,))
    if not ok:
        failures.append(name)


# ---------------------------------------------------------------------------
# entry_ramp_dirs(points, look)
#
# PROPERTY: per segment i, walk forward accumulating |dz| starting at
# segment i itself (always evaluated regardless of `look`), and keep the
# segment with the LARGEST |dz| seen while cumulative travel is still <=
# look - the dominant surface just ahead, NOT the segment the pass happens
# to start on. Fallback (0,0,0,0) when nothing in range has any Z component
# (pure-radial / vertical-only segments).
# ---------------------------------------------------------------------------

# 3 segments of increasing dz: 0.1, 10.0, 100.0, at cumulative Z 0, 0.1,
# 10.1, 110.1. With look=5: segment 0 is always evaluated (travelled=0.1,
# still <=5, continue); segment 1 (dz=10) beats it and becomes best
# (travelled becomes 10.1 > 5, loop breaks BEFORE segment 2). So segment 0's
# own answer is segment 1's direction - the dominant surface ahead, not its
# own short first segment - and segment 2 (the largest of all, but beyond
# `look`) is correctly excluded.
pts = [(0.0, 0.0), (0.1, 1.0), (10.1, 3.0), (110.1, 4.0)]
dirs = ls.entry_ramp_dirs(pts, 5)
check('entry_ramp_dirs: 3 segments returned for 3 segments of input',
      len(dirs), 3)
check_tuple4(
    'entry_ramp_dirs: seg0 picks the DOMINANT segment ahead (seg1), not '
    "its own short segment, and seg2 (larger but beyond `look`) is excluded",
    dirs[0], (10.0, 2.0, 0.1, 1.0))
check_tuple4(
    'entry_ramp_dirs: seg1 (itself dominant) reports its own direction',
    dirs[1], (10.0, 2.0, 0.1, 1.0))
check_tuple4(
    'entry_ramp_dirs: seg2, the last segment, has only itself to report',
    dirs[2], (100.0, 1.0, 10.1, 3.0))

# NEGATIVE CONTROL: widen `look` so segment 2 (dz=100, the true largest of
# all) comes into range for segment 0 - the answer MUST change, proving the
# window bound in the first case was actually doing something rather than
# happening to coincide with the dominant answer.
dirs_wide = ls.entry_ramp_dirs(pts, 200)
check_tuple4(
    'entry_ramp_dirs: control - widening `look` changes seg0 to pick seg2',
    dirs_wide[0], (100.0, 1.0, 10.1, 3.0))
check('entry_ramp_dirs: control - the two `look` values give different '
      'answers for segment 0',
      dirs[0] != dirs_wide[0], True)

# Boundary: a purely vertical-only profile (every segment has dz == 0, only
# X changes) - no segment ever has a Z component, so every entry is the
# (0.0, 0.0, 0.0, 0.0) fallback, never left as None or crashing.
pts_vertical = [(0.0, 0.0), (0.0, 5.0), (0.0, 10.0)]
dirs_v = ls.entry_ramp_dirs(pts_vertical, 10)
check('entry_ramp_dirs: all-vertical profile falls back to (0,0,0,0) '
      'for every segment',
      dirs_v, [(0.0, 0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 0.0)])

# Zero-length input.
check('entry_ramp_dirs: empty points -> empty', ls.entry_ramp_dirs([], 10), [])
check('entry_ramp_dirs: single point (no segments) -> empty',
      ls.entry_ramp_dirs([(0.0, 0.0)], 10), [])


# ---------------------------------------------------------------------------
# ramp_facing(orient)
#
# PROPERTY: reads the Z component of NOSE_OFFSET[orient] and returns the
# OPPOSITE sign (the cutting edge faces away from where the nose sits), 0 for
# orientations with no Z component (facing tools / on-the-point) and 0 for
# anything out of range. Verified against lathe_comp.NOSE_OFFSET directly,
# not by re-deriving through the same table entry_ramp_dirs might use.
# ---------------------------------------------------------------------------
import lathe_comp  # noqa: E402  (kept local to this check block on purpose)

for orient in range(1, len(lathe_comp.NOSE_OFFSET)):
    off = lathe_comp.NOSE_OFFSET[orient]
    z = off[1]
    expected = -1 if z > 0 else (1 if z < 0 else 0)
    check('ramp_facing(%d): opposite sign of NOSE_OFFSET Z component' % orient,
          ls.ramp_facing(orient), expected)

# The greatEndian catch this function exists for, 2026-09-01: mirroring a
# tool about X (orient 2 -> orient 1) must flip the facing, not leave it.
check('ramp_facing: control - mirrored tool (orient 1 vs 2) FLIPS facing, '
      "doesn't keep it",
      ls.ramp_facing(2) != ls.ramp_facing(1), True)
check('ramp_facing: orient 2, ordinary right-hand OD tool, faces -Z',
      ls.ramp_facing(2), -1)
check('ramp_facing: orient 1, its X-mirror, faces +Z',
      ls.ramp_facing(1), 1)

# Facing tools / on-the-point orientations express no axial preference.
for orient in (6, 8, 9):
    check('ramp_facing(%d): facing/on-point orientation refuses nothing' % orient,
          ls.ramp_facing(orient), 0)

# Boundary / invalid input: 0, None and out-of-range all resolve to "no view".
check('ramp_facing: orient 0 -> 0', ls.ramp_facing(0), 0)
check('ramp_facing: orient None -> 0', ls.ramp_facing(None), 0)
check('ramp_facing: orient past the table -> 0', ls.ramp_facing(999), 0)


if failures:
    print('\n%d FAILURE(S): %s' % (len(failures), ', '.join(failures)))
    sys.exit(1)
print('\nAll ramp-direction checks passed.')
