#!/usr/bin/env python3
# coding: utf-8
"""Checks lib/lathe/tip_comp_vec.ngc against the geometry it is supposed to encode.

Standalone, like the other test_*.py here - run it directly, no pytest.

tip_comp_vec.ngc is what makes "In CAM" nose compensation work on the parametric
ops: it returns the vector that native G41.1/G42.1 would have applied, so the sub
can add it to a straight wall's endpoints and run the machine uncompensated.

Two things in it are hand-written and cannot be checked by running one example:

  1. A NINE-WAY BRANCH transcribing LinuxCNC's lathe_shapes orientation table
     into G-code, with each (X, Z) pair deliberately written out in the other
     order because this module works in (Z, radius). One transposed pair puts the
     tool R*sqrt(2) from where it belongs on exactly one orientation - and the
     demo tool table only exercises Q2 and Q4, so seven of the nine would ship
     untested. So the branch is PARSED out of the .ngc here and compared against
     lathe_sections.NOSE_OFFSET, which is the same table the polyline uses.

  2. The COMP SIDE NORMAL, measured with rs274 rather than derived: with u the
     unit travel direction, G42 offsets along (u_x, -u_z) and G41 along
     (-u_x, u_z). Re-derived here from the recorded measurements so a future edit
     that flips a sign has to disagree with a number, not with a comment.
"""
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import lathe_sections as ls  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SUB = os.path.join(HERE, 'lib', 'lathe', 'tip_comp_vec.ngc')
FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name + (('  ' + detail) if detail else ''))
    if not cond:
        FAILED.append(name)


def parse_orient_branch(path):
    """{L: (oz, ox)} as the .ngc actually assigns them."""
    txt = open(path).read()
    out = {}
    # each arm is:  o<tv_or> if/elseif [#<_tip_cam_l> EQ n]  then two assignments
    arms = re.split(r'o<tv_or>\s*(?:if|elseif)\s*\[#<_tip_cam_l>\s*EQ\s*(\d+)\]', txt)
    # arms[0] is the preamble; then (n, body) pairs
    for i in range(1, len(arms) - 1, 2):
        n = int(arms[i])
        body = arms[i + 1].split('o<tv_or>')[0]
        oz = re.search(r'#<tv_oz>\s*=\s*(-?\d+)', body)
        ox = re.search(r'#<tv_ox>\s*=\s*(-?\d+)', body)
        if oz and ox:
            out[n] = (int(oz.group(1)), int(ox.group(1)))
    return out


def side_normal(uz, ux, side):
    """The convention the sub encodes, restated independently here."""
    return (ux, -uz) if side == 42 else (-ux, uz)


def main():
    check('the subroutine file exists', os.path.exists(SUB), SUB)
    if not os.path.exists(SUB):
        sys.exit(1)

    # --- 1. the orientation table -------------------------------------------
    got = parse_orient_branch(SUB)
    check('all eight non-zero orientations are branched on',
          sorted(got) == [1, 2, 3, 4, 5, 6, 7, 8],
          'found %s' % sorted(got))

    for n in range(1, 10):
        table = ls.NOSE_OFFSET[n]          # (X, Z) as LinuxCNC lists it
        want = (table[1], table[0])        # (Z, radius) as this module works in
        # 9 is on-centre and is the branch's default, so it has no arm
        have = got.get(n, (0, 0))
        check('orientation %d transposed correctly: (Z,x)=%s' % (n, want),
              have == want, 'ngc has %s' % (have,))

    # a transposed pair must actually be detectable, or the comparison above is
    # only checking that two identical-looking things are identical
    asym = [n for n in range(1, 10)
            if ls.NOSE_OFFSET[n][0] != ls.NOSE_OFFSET[n][1]]
    check('the table has asymmetric entries, so a transposition would show',
          len(asym) >= 4, 'asymmetric at %s' % asym)

    # --- 1b. the preview's copy of the same table ---------------------------
    # ncam_preview draws the tool holder from its own transcription of
    # lathe_shapes, in (Z, x) order. A third hand-written copy of a table that
    # has already caused one wrong-side bug gets checked like the others.
    import ncam_preview
    for n in range(1, 10):
        want = (ls.NOSE_OFFSET[n][1], ls.NOSE_OFFSET[n][0])
        check('preview NOSE_DIR[%d] matches lathe_shapes: %s' % (n, want),
              ncam_preview.NOSE_DIR[n] == want,
              'preview has %s' % (ncam_preview.NOSE_DIR[n],))

    # --- 2. magnitudes ------------------------------------------------------
    for n in (1, 2, 3, 4):
        oz, ox = got[n]
        check('orientation %d is a raw sqrt(2) diagonal, not normalised' % n,
              abs(math.hypot(oz, ox) - math.sqrt(2)) < 1e-12,
              '|(%d,%d)| = %.6f' % (oz, ox, math.hypot(oz, ox)))
    for n in (5, 6, 7, 8):
        oz, ox = got[n]
        check('orientation %d is a unit edge offset' % n,
              abs(math.hypot(oz, ox) - 1.0) < 1e-12)

    # --- 3. the comp-side normal, against the rs274 measurements ------------
    # recorded runs, D0.8 (R=0.4) L0 so the shift is the pure normal:
    #   travel -Z at radius 40 : G41 -> r39.6      G42 -> r40.4
    #   travel -X at Z-5       : G41 -> Z-4.6      G42 -> Z-5.4
    R = 0.4
    for (uz, ux), side, want in (((-1, 0), 41, (0.0, -R)),
                                 ((-1, 0), 42, (0.0, +R)),
                                 ((0, -1), 41, (+R, 0.0)),
                                 ((0, -1), 42, (-R, 0.0))):
        nz, nx = side_normal(uz, ux, side)
        got_v = (R * nz, R * nx)
        check('travel (%2d,%2d) under G%d offsets by %s' % (uz, ux, side, want),
              abs(got_v[0] - want[0]) < 1e-12 and abs(got_v[1] - want[1]) < 1e-12,
              'computed %s' % (got_v,))

    check('the two sides are exact opposites',
          side_normal(-0.866, 0.5, 41) == tuple(-v for v in
                                                side_normal(-0.866, 0.5, 42)))

    # --- 4. the whole vector, against the measured OD taper -----------------
    # 60->40 dia at 30 deg from Z0, tool T2 (R0.4, Q2), side 42. rs274 put the
    # compensated wall end at Z-17.5205 r29.9464 against a nominal -17.3205/30.
    R, side = 0.4, 42
    wall = (-17.32051, 30.0)
    uz, ux = -0.866025, 0.5
    nz, nx = side_normal(uz, ux, side)
    oz, ox = got[2]
    off = (R * nz - R * oz, R * nx - R * ox)
    endp = (wall[0] + off[0], wall[1] + off[1])
    check('the OD taper wall end lands where rs274 put it',
          abs(endp[0] - (-17.5205)) < 5e-4 and abs(endp[1] - 29.9464) < 5e-4,
          'computed Z%.4f r%.4f' % endp)

    # and the same construction must reproduce lathe_sections.offset_contour,
    # which the polyline uses - the two paths to the same geometry must agree
    prof = [(0.0, 40.0), (-17.32051, 60.0)]      # diameters
    oc = ls.offset_contour(prof, R, 2, side=1)
    check('it agrees with lathe_sections.offset_contour on the same wall',
          abs(oc[-1][0] - endp[0]) < 1e-4 and abs(oc[-1][1] / 2.0 - endp[1]) < 1e-4,
          'offset_contour gives Z%.4f r%.4f' % (oc[-1][0], oc[-1][1] / 2.0))

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('All tip_comp_vec checks passed.')


if __name__ == '__main__':
    main()
