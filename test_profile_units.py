#!/usr/bin/env python3
# coding: utf-8
"""Direct unit tests for the pure functions in lathe_sections.py's batch A
list (SONNET-PROMPT-UNITS-A.md) that take plain point lists / numbers - no
Feature, no NCam, no rs274, and no path through detect_sections() or
floor_regions() (both under active rewrite by another session right now).

Cluster: boundary_height, set_insert_orient, ladder_consts, ladder_phases.

Every expected value below is derived BY HAND from the function's own
docstring/formula, then cross-checked by running the function once while
writing the test - not the other way around. See test_geometry_primitives.py
for the shape this follows.
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


def check_dict(name, got, want, tol=1e-6):
    ok = set(got.keys()) == set(want.keys()) and all(
        math.isclose(got[k], want[k], abs_tol=tol) for k in want)
    print(('PASS' if ok else 'FAIL'), name, '->', got,
          '' if ok else '(want %r)' % (want,))
    if not ok:
        failures.append(name)


def check_tuple(name, got, want, tol=1e-6):
    ok = len(got) == len(want) and all(
        math.isclose(g, w, abs_tol=tol) for g, w in zip(got, want))
    print(('PASS' if ok else 'FAIL'), name, '->', got,
          '' if ok else '(want %r)' % (want,))
    if not ok:
        failures.append(name)


# ---------------------------------------------------------------------------
# boundary_height(points, z_b)
#
# PROPERTY: the highest X any segment crossing z_b reaches - "for a step it
# is the top of that wall; for a peak it is the peak itself." A vertical
# wall (constant Z) contributes BOTH its endpoints; a sloped segment
# contributes its one interpolated X at z_b. 0.0 when nothing crosses z_b.
# ---------------------------------------------------------------------------

# A step: flat-10 -> vertical wall to 30 -> flat-30, boundary at the wall's
# own Z. The wall's own two endpoints (10 and 30) are both hits, and the
# flats on either side each interpolate to their own constant value (10 and
# 30) at that same Z - the max of all of them is the top of the wall, 30.
pts_step = [(0.0, 10.0), (5.0, 10.0), (5.0, 30.0), (10.0, 30.0)]
check('boundary_height: step -> the top of the wall',
      ls.boundary_height(pts_step, 5.0), 30.0)

# NEGATIVE CONTROL: the boundary height must be the wall's TOP, not its
# bottom or its own segment's own starting value - a check that couldn't
# tell 10 from 30 would not be testing this at all.
check('boundary_height: control - it is not the wall\'s bottom (10)',
      ls.boundary_height(pts_step, 5.0) != 10.0, True)

# The docstring's own example: a peak formed by two sloped segments meeting
# - the boundary height is the peak's own X.
pts_peak = [(0.0, 10.0), (5.0, 30.0), (10.0, 10.0)]
check('boundary_height: peak between two sloped sections -> the peak itself',
      ls.boundary_height(pts_peak, 5.0), 30.0)

# A plain sloped ramp, no boundary structure at all - just linear
# interpolation at z_b=3 on a 0->20 rise over Z 0->10: x = 20*(3/10) = 6.0.
check('boundary_height: plain ramp, linear interpolation',
      ls.boundary_height([(0.0, 0.0), (10.0, 20.0)], 3.0), 6.0)

# Boundary: z_b outside every segment's span -> no hits -> 0.0 fallback.
check('boundary_height: z_b outside the profile -> 0.0',
      ls.boundary_height([(0.0, 10.0), (5.0, 20.0)], 100.0), 0.0)

# Zero-length input.
check('boundary_height: empty points -> 0.0', ls.boundary_height([], 5.0), 0.0)


# ---------------------------------------------------------------------------
# set_insert_orient(orient)
#
# PROPERTY: remembers int(orient or 0) in the module global INSERT_ORIENT
# and always returns '' (a no-op cfg <exec> hook). Real mutation, not a
# pure function - tested as the state change it documents itself as being.
# Restores the module's prior value afterwards so this file has no effect
# on any other test run in the same process.
# ---------------------------------------------------------------------------

_prior_orient = ls.INSERT_ORIENT
try:
    ret = ls.set_insert_orient(3)
    check('set_insert_orient: returns the empty string (a no-op cfg hook)',
          ret, '')
    check('set_insert_orient: remembers the int it was given',
          ls.INSERT_ORIENT, 3)

    ls.set_insert_orient(None)
    check('set_insert_orient: None coerces to 0', ls.INSERT_ORIENT, 0)

    ls.set_insert_orient(0)
    check('set_insert_orient: boundary - orient 0 stays 0', ls.INSERT_ORIENT, 0)

    ls.set_insert_orient('5')
    check('set_insert_orient: a numeric string coerces via int()',
          ls.INSERT_ORIENT, 5)

    # NEGATIVE CONTROL: it is real mutation, not a pure computation that
    # happens to look stateful - calling it with a DIFFERENT value must
    # change the remembered global, not leave the previous call's value.
    ls.set_insert_orient(7)
    check('set_insert_orient: control - a second call overwrites, not stacks',
          ls.INSERT_ORIENT != 5, True)
finally:
    ls.INSERT_ORIENT = _prior_orient


# ---------------------------------------------------------------------------
# ladder_consts(start_r, final_r, fin_off, prefin_off, doc, pass_from=False,
#               floors=())
#
# PROPERTY: rough_target/step_target are the profile's own targets plus
# offsets signed by travel direction (dirsign); lad_tgt is step_target
# unless more than one floor stage exists, in which case it is the first
# (shallowest) floor; passes is LinuxCNC's own FUP (round away from zero) of
# the ladder span over doc; pass_from reassigns cut_step to a WHOLE depth of
# cut and re-anchors step_target/lad_tgt outward to the nearest whole
# multiple of doc from rough_target, changing first_step accordingly.
# ---------------------------------------------------------------------------

# OD direction (start_r >= final_r, dirsign=+1), not anchored, no floors.
# rough_target = 10 + 1*0.5 = 10.5; step_target = 10.5 + 1*0.3 = 10.8;
# lad_tgt = step_target (no floors); span = |10.8-20| = 9.2;
# passes = FUP(9.2/2.0) = FUP(4.6) = 5 (round away from zero);
# cut_step = first_step = (10.8-20)/5 = -1.84.
check_dict(
    'ladder_consts: OD direction, not anchored, no floors - hand-derived',
    ls.ladder_consts(20.0, 10.0, 0.5, 0.3, 2.0),
    {'dirsign': 1, 'rough_target': 10.5, 'step_target': 10.8,
     'lad_tgt': 10.8, 'cut_step': -1.84, 'first_step': -1.84,
     'rough_passes': 5})

# The mirror direction (start_r < final_r) flips dirsign to -1 and every
# signed quantity's sign with it, same magnitudes - proves dirsign is
# actually driving the signs rather than a hardcoded OD assumption.
check_dict(
    'ladder_consts: control - the mirror direction flips dirsign and signs',
    ls.ladder_consts(10.0, 20.0, 0.5, 0.3, 2.0),
    {'dirsign': -1, 'rough_target': 19.5, 'step_target': 19.2,
     'lad_tgt': 19.2, 'cut_step': 1.84, 'first_step': 1.84,
     'rough_passes': 5})

# len(floors) > 1: lad_tgt takes floors[0] (shallowest), NOT step_target.
# rough_target=step_target=10.0 (zero offsets); lad_tgt=floors[0]=15.0;
# span=|15-20|=5; passes=FUP(5/2)=FUP(2.5)=3; cut_step=(15-20)/3=-1.6667.
check_dict(
    'ladder_consts: multiple floors -> lad_tgt is floors[0], not step_target',
    ls.ladder_consts(20.0, 10.0, 0.0, 0.0, 2.0, floors=(15.0, 12.0)),
    {'dirsign': 1, 'rough_target': 10.0, 'step_target': 10.0,
     'lad_tgt': 15.0, 'cut_step': -5.0 / 3, 'first_step': -5.0 / 3,
     'rough_passes': 3})

# NEGATIVE CONTROL: a SINGLE floor must NOT trigger the floors[0] override -
# lad_tgt stays step_target (10.0), not floors[0] (15.0) - the whole ladder
# then spans start_r(20) to step_target(10): passes=FUP(10/2)=5,
# cut_step=first_step=(10-20)/5=-2.0.
check_dict(
    'ladder_consts: control - a single floor does not override lad_tgt',
    ls.ladder_consts(20.0, 10.0, 0.0, 0.0, 2.0, floors=(15.0,)),
    {'dirsign': 1, 'rough_target': 10.0, 'step_target': 10.0,
     'lad_tgt': 10.0, 'cut_step': -2.0, 'first_step': -2.0,
     'rough_passes': 5})

# Boundary: start already exactly at the target (abs(lad_tgt-start_r)<=EPS)
# -> cut_step/first_step collapse to 0.0 and passes stays at its 1 default,
# never divides by a zero span.
check_dict(
    'ladder_consts: boundary - start already at the target -> zero step',
    ls.ladder_consts(10.0, 10.0, 0.0, 0.0, 2.0),
    {'dirsign': 1, 'rough_target': 10.0, 'step_target': 10.0,
     'lad_tgt': 10.0, 'cut_step': 0.0, 'first_step': 0.0,
     'rough_passes': 1})

# pass_from=True (anchored): cut_step becomes a WHOLE +-doc (not a spread
# division), and step_target/lad_tgt re-anchor outward from rough_target by
# whole multiples of doc.
# rough_target = 10 + 0.5 = 10.5; step_target(pre) = 10.5 + 1.0 = 11.5;
# lad_tgt(pre) = 11.5 (no floors); sgn = -1 (step_target < start_r);
# cut_step = sgn*doc = -2.0;
# k_min = FUP(|11.5-10.5|/2.0) = FUP(0.5) = 1;
# anch_floor = rough_target - sgn*k_min*doc = 10.5 - (-1*1*2.0) = 12.5;
# step_target = lad_tgt = 12.5 (no floors so lad_tgt takes it too);
# passes = FUP(|12.5-20|/2.0) = FUP(3.75) = 4;
# first_step = (12.5-20) - cut_step*(4-1) = -7.5 - (-2.0*3) = -7.5+6.0 = -1.5.
check_dict(
    'ladder_consts: pass_from=True re-anchors to a whole depth of cut',
    ls.ladder_consts(20.0, 10.0, 0.5, 1.0, 2.0, pass_from=True),
    {'dirsign': 1, 'rough_target': 10.5, 'step_target': 12.5,
     'lad_tgt': 12.5, 'cut_step': -2.0, 'first_step': -1.5,
     'rough_passes': 4})

# NEGATIVE CONTROL: the docstring's own warning - conflating step_target's
# re-anchor with the configured allowance left roughing holding 1.016 off
# the profile where 0.762 was configured. Assert step_target/lad_tgt after
# anchoring is NOT simply rough_target + prefin_off (11.5) - it must be the
# whole-depth-of-cut-rounded 12.5 instead.
check('ladder_consts: control - anchored step_target is not rough_target+prefin_off',
      ls.ladder_consts(20.0, 10.0, 0.5, 1.0, 2.0, pass_from=True)['step_target']
      != 11.5, True)


# ---------------------------------------------------------------------------
# ladder_phases(start_r, lad_tgt, step_target, cut_step, first_step, doc,
#               dirsign, sect_on, sect_count, sect_top_r=None)
#
# PROPERTY: with Sectioning off, everything passes through unchanged - the
# 5-tuple is exactly (step_target, cut_step, first_step, cut_step,
# first_step). With Sectioning on, `top` resolves from sect_top_r only when
# BOTH sect_count > 0 and sect_top_r would not overshoot the ladder's own
# span (clamped to step_target on one side, start_r on the other); the two
# phase step sizes are then recomputed independently around whatever `top`
# ends up being - phase 1 in whole depths of cut (like pass_from), phase 2
# spread evenly (NOT whole steps, per the function's own comment).
# ---------------------------------------------------------------------------

# Sectioning off: pure passthrough, whatever sect_count/sect_top_r say.
check_tuple(
    'ladder_phases: Sectioning off is a pure passthrough',
    ls.ladder_phases(20.0, 10.0, 15.0, -2.0, -1.0, 2.0, 1, False, 0, None),
    (15.0, -2.0, -1.0, -2.0, -1.0))

# NEGATIVE CONTROL: the SAME inputs with Sectioning on must NOT be the same
# passthrough tuple - sect_count=0 still recomputes the phase steps (only
# the sect_top_r override needs sect_count>0, not the phase math itself).
check(
    'ladder_phases: control - Sectioning on changes the answer even with '
    'sect_count 0 (the two gates are not the same gate)',
    ls.ladder_phases(20.0, 10.0, 15.0, -2.0, -1.0, 2.0, 1, True, 0, None) !=
    (15.0, -2.0, -1.0, -2.0, -1.0),
    True)

# Sectioning on, sect_count 0: top stays step_target (15.0, the override
# needs sect_count>0), but phase 1/2 are recomputed around it.
# p1 (start_r=20 -> top=15): n=FUP(5/2)=3, sgn=-1, p1_step=-2.0,
#   p1_first=(15-20)-(-2.0*2)=-5+4=-1.0
# p2 (top=15 -> lad_tgt=10): n=FUP(5/2)=3, p2_step=(10-15)/3=-1.6667 (SPREAD)
check_tuple(
    'ladder_phases: sect_count 0 - top stays step_target, phases recompute',
    ls.ladder_phases(20.0, 10.0, 15.0, -2.0, -1.0, 2.0, 1, True, 0, None),
    (15.0, -2.0, -1.0, -5.0 / 3, -5.0 / 3))

# Sectioning on, sect_top_r WITHIN the ladder's own band (no clamp): top
# takes sect_top_r itself.
# p1 (20 -> 18): n=FUP(2/2)=1, p1_step=-2.0, p1_first=(18-20)-(-2*0)=-2.0
# p2 (18 -> 10): n=FUP(8/2)=4, p2_step=(10-18)/4=-2.0 (SPREAD, same here
#   only because it divides evenly)
check_tuple(
    'ladder_phases: sect_top_r within band -> top takes it, both phases '
    'recompute around it',
    ls.ladder_phases(20.0, 10.0, 15.0, -2.0, -1.0, 2.0, 1, True, 3, 18.0),
    (18.0, -2.0, -2.0, -2.0, -2.0))

# Boundary: sect_top_r past the floor it is aiming at (5.0, below
# step_target 15.0) is clamped BACK UP to step_target - same result as the
# sect_count=0 case, proving the clamp actually engaged rather than just
# passing sect_top_r through.
check_tuple(
    'ladder_phases: boundary - sect_top_r past the floor clamps to '
    'step_target',
    ls.ladder_phases(20.0, 10.0, 15.0, -2.0, -1.0, 2.0, 1, True, 3, 5.0),
    (15.0, -2.0, -1.0, -5.0 / 3, -5.0 / 3))

# Boundary: sect_top_r above the stock it starts from (25.0, past start_r
# 20.0) clamps DOWN to start_r. With top == start_r, phase 1's own "abs(top
# - start_r) > EPS" gate is false, so p1 stays the UNCHANGED passthrough
# (cut_step, first_step) - distinct values (-3.0, -1.5) used here so a
# recomputed p1 could never coincidentally match the passthrough.
check_tuple(
    'ladder_phases: boundary - sect_top_r above stock clamps to start_r, '
    'and phase 1 becomes a true no-op there',
    ls.ladder_phases(20.0, 10.0, 15.0, -3.0, -1.5, 2.0, 1, True, 3, 25.0),
    (20.0, -3.0, -1.5, -2.0, -2.0))


if failures:
    print('\n%d FAILURE(S): %s' % (len(failures), ', '.join(failures)))
    sys.exit(1)
print('\nAll profile-units checks passed.')
