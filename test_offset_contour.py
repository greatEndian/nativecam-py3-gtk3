#!/usr/bin/env python3
# coding: utf-8
"""Checks the CAM-side nose offset in lathe_sections.py.

Standalone, like the other test_*.py here - run it directly, no pytest. Pure
geometry, so it runs instantly.

Covers what is FINISHED: the per-segment offset, and the orientation vector
being applied as a raw R*sqrt(2) rather than a normalised R. Corner joining is
not implemented, so there is no test claiming it is - see the last case, which
pins the known-bad corner output so that finishing the joining has to change it.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import lathe_sections as ls  # noqa: E402

FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name + (('  ' + detail) if detail else ''))
    if not cond:
        FAILED.append(name)


def main():
    R = 0.4

    # the table must stay LinuxCNC's own
    check('the nose table matches rs274/glcanon.py lathe_shapes',
          ls.NOSE_OFFSET == [None, (1, -1), (1, 1), (-1, 1), (-1, -1),
                             (0, -1), (1, 0), (0, 1), (-1, 0), (0, 0)])
    # and 1-4 are a RAW diagonal, not a normalised one - normalising mis-places
    # the tool, which is why CLAUDE.md calls it out
    for n in (1, 2, 3, 4):
        dx, dz = ls.NOSE_OFFSET[n]
        check('orientation %d is a raw R*sqrt(2) diagonal' % n,
              abs(math.hypot(dx, dz) - math.sqrt(2)) < 1e-12)

    # --- a plain cylinder ---------------------------------------------------
    cyl = [(0.0, 40.0), (-20.0, 40.0)]

    # orientation 9 puts the nose ON the control point, so the control point is
    # simply the profile lifted by one radius - a diameter rise of 2R
    e = ls.offset_contour(cyl, R, 9)
    check('orient 9 lifts the control point by 2R in diameter',
          all(abs(x - (40.0 + 2 * R)) < 1e-9 for _z, x in e),
          str([(round(z, 3), round(x, 3)) for z, x in e]))
    check('orient 9 does not shift Z', all(abs(z - p[0]) < 1e-9
                                           for (z, _x), p in zip(e, cyl)))

    # orientation 2 sits the nose +X +Z of the control point, so the control
    # point drops back by R in both: the nose CENTRE must still land on 40+2R
    e2 = ls.offset_contour(cyl, R, 2)
    for (z, x), (pz, _px) in zip(e2, cyl):
        nose_r = x / 2.0 + R          # nose centre radius, from the table's +X
        check('orient 2 puts the nose centre on the offset surface at Z%.1f' % pz,
              abs(nose_r - (20.0 + R)) < 1e-9, 'nose centre r%.4f' % nose_r)
        check('orient 2 pulls the control point back by R in Z',
              abs(z - (pz - R)) < 1e-9, 'Z%.4f vs %.4f' % (z, pz - R))

    # --- the offset distance is the radius, whatever the segment angle ------
    for ang in (0.0, 30.0, 45.0, 60.0):
        dz, dr = -math.cos(math.radians(ang)) * 10, math.sin(math.radians(ang)) * 10
        seg = [(0.0, 40.0), (dz, 40.0 + 2 * dr)]
        e3 = ls.offset_contour(seg, R, 9)
        # perpendicular distance from the original line to the offset one
        uz, ur = ls._unit(dz, dr)
        p0 = (seg[0][0], seg[0][1] / 2.0)
        q0 = (e3[0][0], e3[0][1] / 2.0)
        dist = abs((q0[0] - p0[0]) * -ur + (q0[1] - p0[1]) * uz)
        check('a %.0f deg segment is offset by exactly R' % ang,
              abs(dist - R) < 1e-9, 'measured %.6f' % dist)

    # --- side flips it for a bore ------------------------------------------
    inner = ls.offset_contour(cyl, R, 9, side=-1)
    check('side -1 offsets into the bore instead',
          all(abs(x - (40.0 - 2 * R)) < 1e-9 for _z, x in inner),
          str([(round(x, 3)) for _z, x in inner]))

    # --- degenerate input --------------------------------------------------
    check('a zero nose radius returns the profile', ls.offset_contour(cyl, 0.0, 9) == cyl)
    check('an empty profile returns empty', ls.offset_contour([], R, 9) == [])
    check('a single point is returned unchanged',
          ls.offset_contour([(0.0, 40.0)], R, 9) == [(0.0, 40.0)])
    check('a zero-length segment is dropped, not divided by',
          len(ls.offset_contour([(0.0, 40.0), (0.0, 40.0), (-10.0, 40.0)], R, 9)) == 2)

    # --- corners are joined, and the result is a toolpath -------------------
    boss = [(0.0, 40.0), (-20.0, 40.0), (-20.0, 50.0), (-50.0, 50.0),
            (-50.0, 40.0), (-80.0, 40.0)]
    eb = ls.offset_contour(boss, R, 9)

    # a path that doubles back is not a toolpath; this is what corner joining
    # exists to fix, and it was the pinned gap before it was implemented
    zs = [z for z, _x in eb]
    check('the path never doubles back in Z',
          all(b <= a + 1e-9 for a, b in zip(zs, zs[1:])),
          str([round(z, 2) for z in zs]))

    # internal corner: the nose stops R short in Z and stays R clear in radius,
    # leaving a fillet of its own radius - unavoidable, and what a real nose does
    check('an internal corner is trimmed, leaving the nose radius as a fillet',
          any(abs(z - (-20.0 + R)) < 1e-6 and abs(x - (40.0 + 2 * R)) < 1e-6
              for z, x in eb),
          'expected a trimmed point at Z%.2f D%.2f' % (-20.0 + R, 40.0 + 2 * R))

    # external corner: every joining point sits exactly R from the vertex, which
    # is what makes it a roll rather than a miter
    vertex = (-20.0, 25.0)
    arc_pts = [(z, x / 2.0) for z, x in eb if -20.01 < z < -19.59 and x > 49.9]
    check('an external corner is rolled at exactly the nose radius',
          arc_pts and all(abs(math.hypot(z - vertex[0], r - vertex[1]) - R) < 1e-6
                          for z, r in arc_pts),
          '%d arc points' % len(arc_pts))
    # a miter would hold the nose R*(sqrt(2)-1) too far out at 90 degrees
    check('and is not a miter join',
          not any(abs(z - (-19.6)) < 1e-6 and abs(x - (50.0 + 2 * R)) < 1e-6
                  for z, x in eb))

    # --- the whole point: the nose circle must never enter the material -----
    def dist_to_profile(pz, pr):
        best = None
        for (z0, x0), (z1, x1) in zip(boss, boss[1:]):
            az, ar = z0, x0 / 2.0
            bz, br = z1, x1 / 2.0
            dz, dr = bz - az, br - ar
            L2 = dz * dz + dr * dr
            t = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, ((pz - az) * dz + (pr - ar) * dr) / L2))
            d = math.hypot(pz - (az + dz * t), pr - (ar + dr * t))
            best = d if best is None else min(best, d)
        return best

    worst = min(dist_to_profile(z, x / 2.0) for z, x in eb)   # orient 9: nose on the point
    check('the nose circle never cuts into the profile',
          worst >= R - 1e-6, 'closest approach %.6f against R %.4f' % (worst, R))
    check('and it does touch the profile, rather than hovering off it',
          worst <= R + 1e-6, 'closest approach %.6f' % worst)

    # --- the per-pass allowance schedule -----------------------------------
    # These have to agree with what poly_lathe_mill.ngc hands NATIVE
    # compensation as its D word, or the same settings cut a different part in
    # the two modes. The .ngc arithmetic they mirror:
    #   pre-finish  shift = rough_target - final_radius, rough_target being
    #               final_radius + dirsign*fin_off               -> fin_off
    #   finish i/n  shift = fin_off * (n - i) / n                -> 0 on the last
    fin_off, pf_off = 0.5, 0.3
    sched = ls.cam_pass_offsets(fin_off, pf_off, 3)
    check('there is one allowance per pass, pre-finish first', len(sched) == 4,
          str(sched))
    check('the pre-finish allowance is the finish offset, not finish+pre-finish',
          abs(sched[0] - fin_off) < 1e-12,
          'got %.4f, and fin_off+pf_off would be %.4f' % (sched[0],
                                                          fin_off + pf_off))
    check('the finish passes step down evenly',
          all(abs(sched[i] - fin_off * (3 - i) / 3.0) < 1e-12
              for i in (1, 2, 3)), str(sched[1:]))
    check('the LAST finish pass lands on the profile with no allowance left',
          abs(sched[-1]) < 1e-12, 'got %.6f' % sched[-1])
    check('one finish pass gives one zero-allowance pass',
          ls.cam_pass_offsets(fin_off, pf_off, 1) == [fin_off, 0.0],
          str(ls.cam_pass_offsets(fin_off, pf_off, 1)))
    check('zero finish passes still describes the pre-finish pass',
          ls.cam_pass_offsets(fin_off, pf_off, 0) == [fin_off])

    # --- refusing is not the same as emitting nothing -----------------------
    # In CAM mode the machine compensates nothing, so an empty table would mean
    # tracing the raw profile and cutting undersize by the nose radius with a
    # backplot that looks right. Every early return must therefore SAY so - the
    # runtime turns a table-less CAM pass into an (ABORT,).
    class _StubParam(object):
        def __init__(self, v):
            self.v = v

        def get_ngc_value(self):
            return self.v

    class _StubFeature(object):
        """Enough of a Feature for build_cam_comp_gcode, with no ncam import."""

        def __init__(self, params):
            self.params = params

        def get_param(self, name):
            return self.params.get(name)

    feat = _StubFeature({'param_side': _StubParam('0'),
                         'param_f_off': _StubParam('0.5'),
                         'param_f_pass': _StubParam('1'),
                         'param_pf_on': _StubParam('1'),
                         'param_pf_off': _StubParam('0.3')})
    for why, args in (('no nose radius', (0.0, 2)),
                      ('a nose radius of None', (None, 2)),
                      ('an out-of-range orientation', (0.4, 0)),
                      ('orientation 10', (0.4, 10))):
        out = ls.build_cam_comp_gcode(feat, *args)
        check('%s is refused out loud, not silently' % why,
              out.startswith('(WARNING') and '_pl_cam_n' not in out,
              repr(out[:60]))

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('All offset contour tests passed.')


if __name__ == '__main__':
    main()
