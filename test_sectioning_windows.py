#!/usr/bin/env python3
# coding: utf-8
"""Direct unit tests for split_by_length and floor_regions in
lathe_sections.py - pure functions on plain point lists / numbers.

floor_regions calls detect_sections() internally. Its test profiles below are
deliberately restricted to FALLING and FLAT sections only - detect_sections
has a known, separately-reported defect for RISING sections that are not a
profile's own first section (analysis/130): it reports that section's far end
as its min_x instead of its own start, which IS its true minimum for a
monotonic rise. Using only falling/flat shapes here tests floor_regions' own
logic (the region_floor formula per region, and the merge rule) without that
dependency's known flaw contaminating the expected values.
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


def check_seq(name, got, want, tol=1e-6):
    def close3(g, w):
        return len(g) == len(w) == 3 and all(
            math.isclose(a, b, abs_tol=tol) for a, b in zip(g, w))
    ok = len(got) == len(want) and all(close3(g, w) for g, w in zip(got, want))
    print(('PASS' if ok else 'FAIL'), name, '->', got,
          '' if ok else '(want %r)' % (want,))
    if not ok:
        failures.append(name)


# ---------------------------------------------------------------------------
# split_by_length(sections, points, sec_len)
#
# PROPERTY: sec_len<=0 is the identity ("Natural" mode). Otherwise every
# section longer than sec_len is subdivided into
# n = ceil(length/sec_len) EQUAL pieces (never sec_len-sized with a short
# remainder), each piece's min_x taken from linear interpolation along the
# real polyline at its own two Z endpoints. Natural boundaries between input
# sections are never merged.
# ---------------------------------------------------------------------------

# sec_len <= 0: identity, whatever the sections/points are.
one_section = [(0.0, 10.0, 0.0)]
straight_pts = [(0.0, 0.0), (10.0, 20.0)]
check('split_by_length: sec_len 0 is the identity',
      ls.split_by_length(one_section, straight_pts, 0), one_section)
check('split_by_length: negative sec_len is also the identity',
      ls.split_by_length(one_section, straight_pts, -5), one_section)

# Boundary: length exactly equal to sec_len -> kept as one piece.
check('split_by_length: length == sec_len exactly -> no split',
      ls.split_by_length([(0.0, 5.0, 0.0)], [(0.0, 0.0), (5.0, 10.0)], 5.0),
      [(0.0, 5.0, 0.0)])

# Boundary: length just over sec_len (past the EPS guard) -> splits into 2
# EQUAL halves, not a full sec_len chunk plus a 0.001 sliver.
got = ls.split_by_length([(0.0, 5.001, 0.0)],
                          [(0.0, 0.0), (5.001, 10.002)], 5.0)
check('split_by_length: just-over-length splits into 2 EQUAL pieces, not '
      'sec_len + a sliver remainder',
      len(got), 2)
if len(got) == 2:
    lens = [abs(b - a) for a, b, _ in got]
    check('split_by_length: the two pieces are equal length',
          math.isclose(lens[0], lens[1], abs_tol=1e-6), True)
    # NEGATIVE CONTROL: the naive "sec_len chunk + short remainder" split
    # this docstring explicitly rejects would give lengths 5.0 and 0.001 -
    # nothing like the ~2.5/2.5 the equal-piece rule produces.
    check('split_by_length: control - not the naive remainder split',
          math.isclose(lens[0], 5.0, abs_tol=1e-3), False)

# A straight line, Z 0..10 with diameter 0..20 (radius = Z*2, linear).
# sec_len=3 -> n=ceil(10/3)=4, step=2.5. Expected diameters at the boundaries
# 0, 2.5, 5.0, 7.5, 10.0 are 0, 5, 10, 15, 20 (hand-computed from the known
# linear slope, not via _interpolate_x).
pieces = ls.split_by_length([(0.0, 10.0, 0.0)], straight_pts, 3)
check_seq('split_by_length: 4 equal pieces, hand-computed boundary diameters',
          pieces,
          [(0.0, 2.5, 0.0), (2.5, 5.0, 5.0), (5.0, 7.5, 10.0),
           (7.5, 10.0, 15.0)])

# Multi-section input: a natural boundary at Z=5 must survive as a boundary
# in the output even though both sides get subdivided - never merged across.
multi_sections = [(0.0, 5.0, 0.0), (5.0, 10.0, 0.0)]
multi_pts = [(0.0, 0.0), (5.0, 10.0), (10.0, 20.0)]
got = ls.split_by_length(multi_sections, multi_pts, 3)
z_boundaries = sorted(set([a for a, b, _ in got] + [b for a, b, _ in got]))
check('split_by_length: the natural boundary at Z=5 survives subdivision',
      5.0 in z_boundaries, True)
# And it's not just present by accident - it must be where one piece ENDS
# and the next STARTS, i.e. two pieces meet there.
ends_at_5 = sum(1 for a, b, _ in got if math.isclose(b, 5.0, abs_tol=1e-6))
starts_at_5 = sum(1 for a, b, _ in got if math.isclose(a, 5.0, abs_tol=1e-6))
check('split_by_length: Z=5 is a real piece boundary (one ends, one starts)',
      (ends_at_5, starts_at_5), (1, 1))

# Zero sections.
check('split_by_length: empty sections -> empty', ls.split_by_length([], [], 3), [])


# ---------------------------------------------------------------------------
# floor_regions(points, fin_off, prefin_off, rough_cut, anchored)
#
# PROPERTY: one entry per distinct floor detect_sections' own regions are
# entitled to (region_floor applied per section), with neighbours merged
# when they land on the identical floor AND are Z-adjacent. rough_cut<=EPS
# or fewer than 2 points always returns [] (guard, not a real answer - the
# ladder needs rough_cut to mean anything).
# ---------------------------------------------------------------------------

# Falling-then-flat, two distinct floors (avoids the rising-section
# detect_sections flaw entirely - see module docstring above).
step_pts = [(0.0, 30.0), (2.0, 30.0), (2.0, 20.0), (8.0, 20.0)]

# not anchored: region_floor is a pure step_target = min_dia/2 + fin_off + prefin_off.
# Region A: min_dia=30 -> 15.0+0.2+0.1=15.3.  Region B: min_dia=20 -> 10.0+0.2+0.1=10.3.
check_seq('floor_regions: not anchored, two distinct hand-computed floors',
          ls.floor_regions(step_pts, 0.2, 0.1, 0.3, False),
          [(0.0, 2.0, 15.3), (2.0, 8.0, 10.3)])

# anchored: floor steps OUTWARD by whole depths of cut from rough_target.
# fin_off=0.2, prefin_off=1.0, rough_cut=0.3.
# Region A: rough_target=15.2, k_min=ceil(1.0/0.3 - eps)=4 -> 15.2+1.2=16.4
# Region B: rough_target=10.2, same k_min=4               -> 10.2+1.2=11.4
check_seq('floor_regions: anchored, hand-computed whole-depth-of-cut steps',
          ls.floor_regions(step_pts, 0.2, 1.0, 0.3, True),
          [(0.0, 2.0, 16.4), (2.0, 8.0, 11.4)])

# NEGATIVE CONTROL: anchored vs not anchored must give DIFFERENT floors here
# (16.4 != 15.3) - a check that couldn't tell them apart would not be testing
# the anchored stepping at all.
check('floor_regions: control - anchored actually changes the floor',
      ls.floor_regions(step_pts, 0.2, 1.0, 0.3, True)[0][2] !=
      ls.floor_regions(step_pts, 0.2, 1.0, 0.3, False)[0][2],
      True)

# Merge rule: falling-then-flat that lands on the IDENTICAL floor and are
# Z-adjacent must collapse into one region, not stay as two.
same_floor_pts = [(0.0, 20.0), (3.0, 10.0), (6.0, 10.0)]
check_seq('floor_regions: same-floor Z-adjacent regions merge into one',
          ls.floor_regions(same_floor_pts, 0.0, 0.0, 0.5, False),
          [(0.0, 6.0, 5.0)])

# Guard: rough_cut <= EPS always returns [] regardless of anchored.
check('floor_regions: rough_cut == 0 -> []',
      ls.floor_regions(step_pts, 0.2, 0.1, 0.0, False), [])
check('floor_regions: rough_cut negative -> []',
      ls.floor_regions(step_pts, 0.2, 0.1, -1.0, False), [])

# Guard: fewer than 2 points -> [].
check('floor_regions: single point -> []',
      ls.floor_regions([(0.0, 10.0)], 0.2, 0.1, 0.3, False), [])

# Zero-length input.
check('floor_regions: empty points -> []',
      ls.floor_regions([], 0.2, 0.1, 0.3, False), [])


if failures:
    print('\n%d FAILURE(S): %s' % (len(failures), ', '.join(failures)))
    sys.exit(1)
print('\nAll sectioning-window checks passed.')
