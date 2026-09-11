#!/usr/bin/env python3
# coding: utf-8
"""Direct unit tests for the pure point-geometry helpers in lathe_sections.py
that take plain point lists / numbers - no Feature, no NCam, no rs274.

Cluster: ceiling, apply_merge_radii, region_cut_length.

Every expected value here is derived BY HAND from the function's own
docstring rule, not by calling a neighbouring function in the module - see
CLAUDE.md's "Research, show the path, fix, self-verify" and the worker brief
this was written under.
"""
import math
import sys

import lathe_sections as ls

EPS = 1e-6
failures = []


def check(name, got, want, tol=1e-6):
    ok = (isinstance(want, (int, float)) and isinstance(got, (int, float))
          and math.isclose(got, want, abs_tol=tol)) or got == want
    print(('PASS' if ok else 'FAIL'), name, '->', got,
          '' if ok else '(want %r)' % (want,))
    if not ok:
        failures.append(name)


def check_points(name, got, want, tol=1e-6):
    ok = len(got) == len(want) and all(
        math.isclose(gz, wz, abs_tol=tol) and math.isclose(gx, wx, abs_tol=tol)
        for (gz, gx), (wz, wx) in zip(got, want))
    print(('PASS' if ok else 'FAIL'), name, '->', got,
          '' if ok else '(want %r)' % (want,))
    if not ok:
        failures.append(name)


# ---------------------------------------------------------------------------
# ceiling(points, stock_x=None)
#
# PROPERTY: the largest X anywhere, EXCLUDING points at (or within EPS of)
# stock_x when stock_x is given - because a point sitting at raw stock
# diameter isn't a machined feature. Falls back to every point when nothing
# survives the exclusion (an all-stock profile).
# ---------------------------------------------------------------------------

# No stock_x: plain max.
check('ceiling: plain max, no stock_x',
      ls.ceiling([(0, 10.0), (1, 50.0), (2, 30.0)]),
      50.0)

# A boss (30) below full stock (50): stock points excluded, boss is the ceiling.
check('ceiling: stock points excluded, boss found',
      ls.ceiling([(0, 10.0), (1, 50.0), (2, 10.0)], stock_x=50.0),
      10.0)

# NEGATIVE CONTROL: without the stock_x exclusion this would wrongly report
# 50.0 (stock itself) instead of the real feature height 10.0 - the exact
# failure the docstring says this guards against ("silently erasing the
# 'one full-length pass first' phase").
check('ceiling: control - excluding stock changes the answer',
      ls.ceiling([(0, 10.0), (1, 50.0), (2, 10.0)], stock_x=50.0) !=
      ls.ceiling([(0, 10.0), (1, 50.0), (2, 10.0)]),
      True)

# Fallback: every point is at stock diameter -> nothing survives exclusion,
# falls back to the full candidate set rather than returning an empty max().
check('ceiling: all-stock profile falls back to full set',
      ls.ceiling([(0, 50.0), (1, 50.0)], stock_x=50.0),
      50.0)

# Boundary: a point exactly at stock_x - EPS (the module's own EPS = 0.0001)
# is NOT strictly less than stock_x - EPS, so it is treated as "at stock" and
# excluded too - this is the "exactly on a limit" edge the brief calls out.
check('ceiling: point exactly at the stock_x-EPS boundary is excluded',
      ls.ceiling([(0, 10.0), (1, 49.9999)], stock_x=50.0),
      10.0)

# Single point.
check('ceiling: single point', ls.ceiling([(0, 7.0)]), 7.0)


# ---------------------------------------------------------------------------
# apply_merge_radii(points, merges)
#
# PROPERTY: a vertex with merges[j+1] > 0 and a neighbour on both sides is
# replaced by its two tangent points, computed in true (Z, radius) space -
# NOT diameter space, a fillet is not scale-invariant. Derived independently
# here via plain trig on a 90-degree corner, not by calling _fillet_vertex.
# ---------------------------------------------------------------------------

# A 90-degree corner: (0,40)dia -> (10,40)dia -> (10,20)dia, i.e. in radius
# units (0,20) -> (10,20) -> (10,10). Two legs of length 10 each, meeting at
# a right angle. For a fillet radius R (radius units), the tangent length
# along each leg is R / tan(45deg) = R (since tan(45)=1). With R=2:
#   t1 = vertex - 2*(leg1 direction) = (10,20) - 2*(1,0) = (8,20)  -> dia (8,40)
#   t2 = vertex - 2*(leg2 direction) = (10,20) - 2*(0,1) = (10,18) -> dia (10,36)
pts_corner = [(0.0, 40.0), (10.0, 40.0), (10.0, 20.0)]
check_points(
    'apply_merge_radii: 90deg corner, R2 -> hand-derived tangent points',
    ls.apply_merge_radii(pts_corner, [0.0, 0.0, 2.0]),
    [(0.0, 40.0), (8.0, 40.0), (10.0, 36.0), (10.0, 20.0)])

# NEGATIVE CONTROL: radius 0 must be a true no-op (byte-identical points).
check_points('apply_merge_radii: control - radius 0 is a no-op',
             ls.apply_merge_radii(pts_corner, [0.0, 0.0, 0.0]),
             pts_corner)

# Boundary: a radius so large the tangent point would run past the leg
# (tangent > leg length) - the vertex must stay sharp (kept, not clamped).
check_points(
    'apply_merge_radii: radius too large for the leg -> vertex stays sharp',
    ls.apply_merge_radii(pts_corner, [0.0, 0.0, 20.0]),
    pts_corner)

# Boundary: a collinear (straight, theta==pi) vertex cannot be filleted -
# stays sharp regardless of the radius given.
pts_straight = [(0.0, 40.0), (5.0, 40.0), (10.0, 40.0)]
check_points('apply_merge_radii: collinear vertex stays sharp',
             ls.apply_merge_radii(pts_straight, [0.0, 0.0, 2.0]),
             pts_straight)

# Boundary: end vertices (index 0 and len-1) are never merged even if given
# a radius, since they have no neighbour on one side.
check_points(
    'apply_merge_radii: end vertices never merged',
    ls.apply_merge_radii(pts_corner, [5.0, 0.0, 0.0, 5.0]),
    pts_corner)

# Zero-length input.
check('apply_merge_radii: empty points is a no-op',
      ls.apply_merge_radii([], [1.0, 1.0]), [])


# ---------------------------------------------------------------------------
# region_cut_length(points, z_from, z_to, floor, allowance, samples=24)
#
# PROPERTY: sums, over the Z overlap of [z_from,z_to] with each segment, the
# fraction of that segment where (profile radius + allowance) < floor - i.e.
# where material still stands above the level. Verified with clean analytic
# cases (flat fully above/below the floor, and a linear ramp with an exact
# 50% crossing) rather than by re-deriving through region_floor/floor_regions.
# ---------------------------------------------------------------------------

pts_flat = [(0.0, 10.0), (10.0, 10.0)]  # constant diameter 10 -> radius 5

# Floor well above the material (radius 5 < floor 10) everywhere -> full length.
check('region_cut_length: flat segment fully cuttable -> full length',
      ls.region_cut_length(pts_flat, 0.0, 10.0, 10.0, 0.0), 10.0)

# Floor below the material everywhere (radius 5, floor 1) -> nothing to cut.
check('region_cut_length: floor deeper than the material -> zero',
      ls.region_cut_length(pts_flat, 0.0, 10.0, 1.0, 0.0), 0.0)

# NEGATIVE CONTROL: raising the floor from "always cuts" to "never cuts"
# must move the answer - a check that reported 10.0 in both cases would not
# be testing the floor comparison at all.
check('region_cut_length: control - the floor comparison actually matters',
      ls.region_cut_length(pts_flat, 0.0, 10.0, 10.0, 0.0) !=
      ls.region_cut_length(pts_flat, 0.0, 10.0, 1.0, 0.0),
      True)

# A linear ramp, diameter 0 at Z0 to diameter 20 at Z10 (radius = Z exactly).
# A floor of radius 5 is crossed at Z=5 -> exactly half the span is above the
# floor (material stands for Z in [0,5)). With 24 midpoint samples spaced
# evenly this lands on an exact half without quantization error (verified:
# 12 of 24 sample midpoints fall below Z=5).
pts_ramp = [(0.0, 0.0), (10.0, 20.0)]
check('region_cut_length: linear ramp, exact half crossing',
      ls.region_cut_length(pts_ramp, 0.0, 10.0, 5.0, 0.0), 5.0)

# z_from/z_to given reversed - the function must take min/max itself.
check('region_cut_length: order-independent z_from/z_to',
      ls.region_cut_length(pts_ramp, 10.0, 0.0, 5.0, 0.0), 5.0)

# The allowance shifts the comparison: with allowance=5 added to every
# sampled radius, floor=10 now never exceeds (radius+5), i.e. is only beaten
# when radius < 5, same 50% crossing as above pushed to floor=10.
check('region_cut_length: allowance shifts the crossing, not the length',
      ls.region_cut_length(pts_ramp, 0.0, 10.0, 10.0, 5.0), 5.0)

# Zero-length range.
check('region_cut_length: zero-length range -> zero',
      ls.region_cut_length(pts_flat, 3.0, 3.0, 10.0, 0.0), 0.0)

# Query range outside the profile's own Z span -> no segment overlaps -> zero.
check('region_cut_length: query range outside the profile -> zero',
      ls.region_cut_length(pts_flat, 20.0, 30.0, 10.0, 0.0), 0.0)


if failures:
    print('\n%d FAILURE(S): %s' % (len(failures), ', '.join(failures)))
    sys.exit(1)
print('\nAll geometry-primitive checks passed.')
