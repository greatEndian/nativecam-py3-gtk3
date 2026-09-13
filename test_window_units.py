#!/usr/bin/env python3
# coding: utf-8
"""Direct unit tests for pure functions in lathe_sections.py - batch B
(windows, call planning, offsets): protected_flags, level_floors,
window_calls, wrong_way_dirs, curve_offsets, stock_at_normal.

Plain point lists / numbers in, no Feature object, no GTK, no ncam import,
no rs274 - same shape as test_geometry_primitives.py.

Every expected value here is derived BY HAND from the function's own
docstring rule (or, where the arithmetic is long, by an independent
re-implementation of the documented formula run as a calculator - never by
calling the function under test and pasting its output). See CLAUDE.md's
"Research, show the path, fix, self-verify" and analysis/160.

SKIPPED from the batch-B function list, and why (see analysis/160 for the
full writeup):

  rough_nose_terms     - calls _comp_nose(polyline_feature, ...), which does
                          polyline_feature.get_param(...) - needs a Feature.
  roughing_call_plan   - needs a Feature AND reaches detect_sections() /
                          floor_regions() (confirmed by AST call-graph walk)
                          - another session owns that code right now.
  flat_sub_number      - polyline_feature.get_attr('id') - needs a Feature.
  facing_rough_offset  - feature.get_param(...) for six params plus the
                          module-level WORKPIECE_OD/ID globals - needs a
                          Feature.
  unreachable_spans    - resolve_points/finish_profile need a Feature.
  xw_settings          - polyline_feature.get_param(...) - needs a Feature.

Faking a Feature for any of these is out of scope per the worker brief: it
would test the fake, not the code.
"""
import math

import lathe_sections as ls

failures = []


def check(name, got, want, tol=1e-6):
    ok = (isinstance(want, (int, float)) and isinstance(got, (int, float))
          and math.isclose(got, want, abs_tol=tol)) or got == want
    print(('PASS' if ok else 'FAIL'), name, '->', got,
          '' if ok else '(want %r)' % (want,))
    if not ok:
        failures.append(name)


def check_list(name, got, want, tol=1e-6):
    ok = len(got) == len(want) and all(
        (math.isclose(g, w, abs_tol=tol) if isinstance(w, (int, float))
         else g == w)
        for g, w in zip(got, want))
    print(('PASS' if ok else 'FAIL'), name, '->', got,
          '' if ok else '(want %r)' % (want,))
    if not ok:
        failures.append(name)


def _pt_close(p, q, tol=1e-6):
    return math.isclose(p[0], q[0], abs_tol=tol) and math.isclose(
        p[1], q[1], abs_tol=tol)


def check_curve_offsets(name, got, want, tol=1e-6):
    ok = len(got) == len(want)
    if ok:
        for g, w in zip(got, want):
            if g is None or w is None:
                ok = ok and g == w
                continue
            (ga, gb, gr), (wa, wb, wr) = g, w
            ok = (ok and _pt_close(ga, wa, tol) and _pt_close(gb, wb, tol)
                  and math.isclose(gr, wr, abs_tol=tol))
    print(('PASS' if ok else 'FAIL'), name, '->', got,
          '' if ok else '(want %r)' % (want,))
    if not ok:
        failures.append(name)


# ---------------------------------------------------------------------------
# protected_flags(levels, floors, step_target, staged)
#
# PROPERTY: 1 per level that equals the floor currently being AIMED AT. With
# staged=False (or a single floor) that is step_target throughout. With
# staged=True and multiple floor stages, the aim point re-anchors on stage 0
# and steps to the next stage each time a level lands on the current one -
# the last stage never advances further, however many later levels hit it.
# ---------------------------------------------------------------------------

# Unstaged: only the level that equals step_target is flagged.
check_list(
    'protected_flags: unstaged, single floor, only step_target hits',
    ls.protected_flags([10.0, 8.0, 6.0, 4.0, 2.0], [4.0], 4.0, False),
    [0, 0, 0, 1, 0])

# Staged, three stages [6, 3, 1] with step_target = last stage (1.0): the
# walk starts aimed at stage 0 (6), advances to stage 1 (3) the level after
# it hits 6, advances to stage 2 (1) the level after it hits 3, and then
# stays parked on stage 2 - traced by hand against the loop body.
check_list(
    'protected_flags: staged, three floor stages walked in order',
    ls.protected_flags([10.0, 8.0, 6.0, 5.0, 3.0, 2.0, 1.0, 0.5],
                       [6.0, 3.0, 1.0], 1.0, True),
    [0, 0, 1, 0, 1, 0, 1, 0])

# NEGATIVE CONTROL: staged=True but only one floor stage behaves exactly
# like unstaged (docstring: "The last stage IS step_target, so nothing
# changes on a part with one floor").
check_list(
    'protected_flags: staged with one floor == unstaged',
    ls.protected_flags([10.0, 8.0, 4.0, 2.0], [4.0], 4.0, True),
    [0, 0, 1, 0])


# ---------------------------------------------------------------------------
# level_floors(levels, floors, window_floor)
#
# PROPERTY: the floor each level AIMS AT. Re-anchoring on stage 0 fires only
# when window_floor IS the last stage; the write happens ONLY AT THE ADVANCE
# (the level that lands on a floor still reports the OLD floor - the next
# level reports the new one), per the "WRITTEN ONLY AT THE ADVANCE" warning
# in the docstring (analysis/095, 096: writing at the window start broke
# testing_15_5, 466 moves against 472).
# ---------------------------------------------------------------------------

check_list(
    'level_floors: re-anchors on stage 0, advances only after the hit',
    ls.level_floors([10.0, 8.0, 6.0, 5.0, 3.0, 2.0, 1.0, 0.5],
                    [6.0, 3.0, 1.0], 1.0),
    [6.0, 6.0, 6.0, 3.0, 3.0, 1.0, 1.0, 1.0])

# NEGATIVE CONTROL: window_floor is NOT the last stage -> no re-anchor, the
# window's own floor is reported for every level unchanged (fl_i stays -1
# forever, so "0 <= fl_i" never holds).
check_list(
    'level_floors: window_floor != last stage -> flat, no re-anchor',
    ls.level_floors([10.0, 8.0, 6.0, 5.0, 3.0], [6.0, 3.0, 1.0], 5.0),
    [5.0, 5.0, 5.0, 5.0, 5.0])


# ---------------------------------------------------------------------------
# wrong_way_dirs(orient, rough_dir)
#
# PROPERTY: True when the requested direction opposes the insert's own
# cutting face. Derived from lathe_comp.NOSE_OFFSET[orient][1] (the Z
# component) via ramp_facing: orient 2 (1,1) faces -Z (facing=-1, i.e. front
# to back, param_dir=0); orient 1 (1,-1) faces +Z (facing=+1, back to
# front, param_dir=1). rough_dir 2 ("Both directions") is always wrong.
# Neutral orientations (6, 8, 9 - no Z term) are never wrong.
# ---------------------------------------------------------------------------

check('wrong_way_dirs: orient 2 (faces -Z) with front-to-back (0) agrees',
      ls.wrong_way_dirs(2, 0), False)
check('wrong_way_dirs: orient 2 (faces -Z) with back-to-front (1) opposes',
      ls.wrong_way_dirs(2, 1), True)
check('wrong_way_dirs: orient 1 (faces +Z) with back-to-front (1) agrees',
      ls.wrong_way_dirs(1, 1), False)
check('wrong_way_dirs: orient 1 (faces +Z) with front-to-back (0) opposes',
      ls.wrong_way_dirs(1, 0), True)
check('wrong_way_dirs: "Both directions" (2) always wrong for a facing tool',
      ls.wrong_way_dirs(2, 2), True)
check('wrong_way_dirs: neutral orientation (6, on-the-point) never wrong',
      ls.wrong_way_dirs(6, 2), False)
check('wrong_way_dirs: neutral orientation (8) never wrong either direction',
      ls.wrong_way_dirs(8, 1), False)


# ---------------------------------------------------------------------------
# stock_at_normal(nz, nr, off_x, off_z)
#
# PROPERTY: d = nz^2*off_z + nr^2*off_x - off_x on a pure diameter (nr=1),
# off_z on a pure wall (nz=1), their mean at 45 degrees. The isotropic
# shortcut (off_x == off_z) returns off_x exactly, bypassing the projection
# formula entirely - even for a degenerate/off-axis normal.
# ---------------------------------------------------------------------------

check('stock_at_normal: pure diameter (normal along r) -> off_x',
      ls.stock_at_normal(0.0, 1.0, 0.508, 2.0), 0.508)
check('stock_at_normal: pure wall (normal along z) -> off_z',
      ls.stock_at_normal(1.0, 0.0, 0.508, 2.0), 2.0)
check('stock_at_normal: 45 degree normal -> the mean',
      ls.stock_at_normal(1.0 / math.sqrt(2), 1.0 / math.sqrt(2), 0.508, 2.0),
      (0.508 + 2.0) / 2.0)
check('stock_at_normal: isotropic shortcut ignores the normal entirely',
      ls.stock_at_normal(0.3, 0.9, 1.5, 1.5), 1.5)


# ---------------------------------------------------------------------------
# curve_offsets(pts, side, nose_r, off_x, off_z)
#
# PROPERTY: per segment, the offset endpoints and rolled-in allowance. With
# off_x == off_z every segment is offset by the plain formula (isotropic
# path). With them different, a vertex INTERIOR TO A CURVE (turn < 20 deg)
# blends the two segments' normals and both sides land on the SAME joint
# point; a CORNER (turn >= 20 deg) keeps each segment's own normal/allowance
# with no blending. All expected values below were derived by hand by
# re-implementing the documented formula (_unit + stock_at_normal projection)
# independently of curve_offsets itself - see analysis/160 for the arithmetic.
# ---------------------------------------------------------------------------

# Isotropic (off_x == off_z): a 2-segment corner, plain offset both sides,
# no blending machinery invoked at all (short-circuits before the joint
# loop). Round numbers, verified by direct arithmetic.
check_curve_offsets(
    'curve_offsets: isotropic path, corner kept plain (round numbers)',
    ls.curve_offsets([(0.0, 10.0), (5.0, 10.0), (5.0, 5.0)], 1, 0.5, 0.5, 0.5),
    [((0.0, 9.0), (5.0, 9.0), 1.0),
     ((4.0, 10.0), (4.0, 5.0), 1.0)])

# Anisotropic, single cylindrical (diameter) segment: normal is purely
# radial (0, -1) for this point order/side, so the allowance is pure off_x.
# roll = nose_r + off_x = 0.5 + 0.508 = 1.008.
check_curve_offsets(
    'curve_offsets: anisotropic, one diameter segment -> off_x allowance',
    ls.curve_offsets([(0.0, 10.0), (10.0, 10.0)], 1, 0.5, 0.508, 2.0),
    [((0.0, 8.992), (10.0, 8.992), 1.008)])

# Anisotropic, SHARP CORNER (diameter meets wall at 90 degrees, well past
# CURVE_TURN_DEG=20): each segment keeps its OWN allowance, no shared joint.
# Diameter segment -> off_x (roll 1.008); wall segment -> off_z (roll 2.5).
check_curve_offsets(
    'curve_offsets: anisotropic corner, each surface keeps its own allowance',
    ls.curve_offsets([(0.0, 10.0), (5.0, 10.0), (5.0, 5.0)], 1, 0.5, 0.508,
                     2.0),
    [((0.0, 8.992), (5.0, 8.992), 1.008),
     ((2.5, 10.0), (2.5, 5.0), 2.5)])

# Anisotropic, SMOOTH CURVE (turn ~16.26 degrees, inside the 20 degree cut):
# both segments blend to the SAME joint point at the shared vertex. Chosen
# with 3-4-5 direction vectors so the turn angle and every projection are
# exact rationals; joint arithmetic cross-checked with an independent
# re-implementation of _unit/stock_at_normal (analysis/160).
check_curve_offsets(
    'curve_offsets: smooth interior vertex blends to one shared joint',
    ls.curve_offsets([(0.0, 0.0), (3.0, 4.0), (7.0, 7.0)], 1, 0.5, 0.508,
                     2.0),
    [((1.5703040000000001, -1.177728),
      (4.240265294201205, 2.7597347057987953), 1.9628800000000002),
     ((4.240265294201205, 2.7597347057987953),
      (7.927072, 5.763904), 1.54512)])


# ---------------------------------------------------------------------------
# window_calls(levels, protected, floor_contour, resume_env, split_table,
#              w_from, w_to, w_rlo, w_rhi, stock_r, dirsign, doc, ...)
#
# PROPERTY: [(level, why, [(from, to, first, blocked), ...])]. `why` is only
# set by the band/thin/stock gate (never by the interval walk); a level that
# passes the gate always gets a call list, whether or not that list ends up
# cutting anything. Traced by hand against the function bodies of
# level_stop_z / _level_scan / level_calls / sub_spans (all read-only, no
# detect_sections/floor_regions reach - confirmed by AST walk, see
# analysis/160), not by executing window_calls itself first.
# ---------------------------------------------------------------------------

FLAT_OPEN = [(0.0, 0.0), (-10.0, 0.0)]     # floor sits at r=0 everywhere:
                                            # never blocks any level > 0
FLAT_HIGH = [(0.0, 10.0), (-10.0, 10.0)]   # floor sits at r=10 everywhere:
                                            # blocks any level < 10 from the
                                            # very start of the window
NO_RESUME = []                             # len < 2 -> resume_z always (False, 0)

# Level cleanly inside the band, floor never in the way: one call spanning
# the whole window, first=True, blocked=False (cut happened), why=''.
check(
    'window_calls: unobstructed level -> one call, blocked=False',
    ls.window_calls([5.0], [0], FLAT_OPEN, NO_RESUME, [],
                    0.0, -10.0, 0.0, 10.0, 20.0, 1, 0.6),
    [(5.0, '', [(0.0, -10.0, True, False)])])

# Level fully blocked from the window's own start (the floor stands above
# it everywhere): the interval walk still records the attempted call, with
# blocked=True and no resume found - why is STILL '' (the level ran, it just
# cut nothing), which is the "why is '' when the level ran" distinction the
# docstring calls out explicitly.
check(
    'window_calls: level blocked at the start -> why="", blocked=True',
    ls.window_calls([5.0], [0], FLAT_HIGH, NO_RESUME, [],
                    0.0, -10.0, 0.0, 10.0, 20.0, 1, 0.6),
    [(5.0, '', [(0.0, -10.0, True, True)])])

# Level outside the radius band -> 'band', no calls made at all.
check(
    'window_calls: level above w_rhi -> band, no calls',
    ls.window_calls([15.0], [0], FLAT_OPEN, NO_RESUME, [],
                    0.0, -10.0, 0.0, 10.0, 20.0, 1, 0.6),
    [(15.0, 'band', [])])

# Level at/past stock in the travel direction (dirsign) -> 'stock'.
# dirsign=1, stock_r=5.0: dirsign*(r-stock_r) >= 0 for r=5.0 (r == stock_r).
check(
    'window_calls: level at stock_r with dirsign=1 -> stock',
    ls.window_calls([5.0], [0], FLAT_OPEN, NO_RESUME, [],
                    0.0, -10.0, 0.0, 10.0, 5.0, 1, 0.6),
    [(5.0, 'stock', [])])

# Thin skip: both levels sit within skip_thin of prev_thin AND leave the
# next level within one depth of cut - both dropped as 'thin'. Neither
# level is protected, so the thin branch is reachable for both.
check(
    'window_calls: two levels both within skip_thin -> both "thin"',
    ls.window_calls([10.0, 9.9], [0, 0], FLAT_OPEN, NO_RESUME, [],
                    0.0, -10.0, 0.0, 20.0, 20.0, 1, 0.6,
                    skip_thin=0.5, prev_thin0=10.0),
    [(10.0, 'thin', []), (9.9, 'thin', [])])

# PROTECTED FLOOR IS NEVER DROPPED: same geometry that would satisfy the
# thin test above, but protected[0]=1 -> the thin branch is refused
# ("not protected[i]" fails), stock_r is set far away so the stock branch
# does not fire either, so the level actually runs (why='', one clean call,
# unobstructed floor -> blocked=False).
check(
    'window_calls: protected floor overrides the thin skip',
    ls.window_calls([10.0], [1], FLAT_OPEN, NO_RESUME, [],
                    0.0, -10.0, 0.0, 20.0, 20.0, 1, 0.6,
                    skip_thin=0.5, prev_thin0=10.0),
    [(10.0, '', [(0.0, -10.0, True, False)])])


# ---------------------------------------------------------------------------
print()
if failures:
    print('%d check(s) FAILED: %s' % (len(failures), ', '.join(failures)))
    raise SystemExit(1)
print('All checks passed.')
