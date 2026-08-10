#!/usr/bin/env python3
# coding: utf-8
"""An anisotropic offset of an arc must be as smooth as an isotropic one.

Standalone, like the other test_*.py here - run it directly, no pytest.

greatEndian, `photo/klingyArc_0.png`, testing_15_2 with X 0.508 and Z 2.000:
the dashed lines go jagged on the boss's rising arc while every other curve
stays smooth - *"without separated offset its smooth also"*.

An allowance that depends on the surface normal is CONSTANT along a chord and
jumps at every vertex, so the offset of a chorded arc was a staircase: a flat
run at one distance, a step, another flat run. On this arc, 75 reversals and
0.02580 mm from the same contour built at 8x the sampling, against 0 reversals
and 0.00007 mm isotropic - a 368x error, and 0.00224 mm once fixed.

`curve_offsets` fixes it by offsetting along the CURVE'S OWN normal - the
bisector of the two chords - at any vertex interior to a curve, so both sides
land on the same point and the result sits on the true offset curve.

THE METRIC IS SIGN ALTERNATION, NOT TURN SIZE. A legitimately curved polyline
turns by a couple of degrees at every vertex, so counting large turns measures
curvature, not roughness. What makes a staircase a staircase is that it turns
one way then back the other. A smooth convex offset never reverses.

THE NEGATIVE CONTROL IS TWO-SIDED, which is the point of this file. Both ways
of getting CURVE_TURN_DEG wrong are real, and each was written before it was
guarded:

  0 degrees   nothing counts as a curve, every vertex keeps its own normal
              - the original staircase, and the state the bug was reported in
  180 degrees everything counts as a curve, so a real corner is bisected too
              - which bleeds a wall's axial allowance into the diameter beside
                it and left the diameter carrying 0.3744 where 0.500 was asked
                for. That was a fix I shipped into the tree and this suite
                caught the same day.
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name
          + (('  ' + detail) if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def arc_pts(n, r=12.66, cz=-30.0, cr=18.0, a0=-88.0, a1=2.0):
    """A rising arc, chorded n ways - the shape of the boss front."""
    return [(cz + r * math.cos(math.radians(a0 + (a1 - a0) * k / n)),
             cr + r * math.sin(math.radians(a0 + (a1 - a0) * k / n)))
            for k in range(n + 1)]


def build(L, pts, ox, oz):
    """`entry_contour` works in RADIUS - every production call divides by
    DIAMETER_MODE on the way in. Passing diameters here doubled the geometry
    and the measured allowance came out at exactly half, 0.45 for 0.9.

    nose_r is 0 so the number measured off the contour IS the allowance, with
    nothing to subtract back off.
    """
    return L.entry_contour(list(pts), dist=ox, dist_z=oz, nose_r=0.0,
                           rough_dir=0)


def alternations(L, c):
    """How often the path turns one way and then back the other."""
    signs = []
    for i in range(1, len(c) - 1):
        u = L._unit(c[i][0] - c[i - 1][0], c[i][1] - c[i - 1][1])
        v = L._unit(c[i + 1][0] - c[i][0], c[i + 1][1] - c[i][1])
        t = math.degrees(math.atan2(u[0] * v[1] - u[1] * v[0],
                                    u[0] * v[0] + u[1] * v[1]))
        signs.append(1 if t > 0.05 else (-1 if t < -0.05 else 0))
    return sum(1 for a, b in zip(signs, signs[1:]) if a and b and a != b)


def deviation(coarse, fine):
    """Worst distance from the coarse contour to the 8x-sampled one."""
    worst = 0.0
    for p in coarse:
        best = 1e9
        for a, b in zip(fine, fine[1:]):
            dz, dx = b[0] - a[0], b[1] - a[1]
            n2 = dz * dz + dx * dx
            t = 0.0 if n2 < 1e-18 else max(0.0, min(
                1.0, ((p[0] - a[0]) * dz + (p[1] - a[1]) * dx) / n2))
            best = min(best, math.hypot(p[0] - (a[0] + t * dz),
                                        p[1] - (a[1] + t * dx)))
        worst = max(worst, best)
    return worst


def measure(L, ox, oz):
    c, f = build(L, arc_pts(40), ox, oz), build(L, arc_pts(320), ox, oz)
    return alternations(L, c), deviation(c, f)


def diameter_allowance(L, ox, oz):
    """What a plain diameter is actually left, with a wall next to it.

    Perpendicular distance from a point on the diameter to the offset contour -
    the allowance is a perpendicular distance by definition, and measuring it
    as an X or Z shift instead is a trap analysis/024 records falling into
    twice.
    """
    prof = [(0.0, 20.0), (-10.0, 20.0), (-10.0, 26.0), (-20.0, 26.0)]
    c = build(L, prof, ox, oz)
    sz, sr = -5.0, 20.0
    best = 1e9
    for a, b in zip(c, c[1:]):
        dz, dr = b[0] - a[0], b[1] - a[1]
        n2 = dz * dz + dr * dr
        t = 0.0 if n2 < 1e-18 else max(0.0, min(
            1.0, ((sz - a[0]) * dz + (sr - a[1]) * dr) / n2))
        best = min(best, math.hypot(sz - (a[0] + t * dz),
                                    sr - (a[1] + t * dr)))
    return best


def main():
    import lathe_sections as L

    OX, OZ = 0.508, 2.000

    iso_alt, iso_dev = measure(L, OX, OX)
    ani_alt, ani_dev = measure(L, OX, OZ)
    print('      isotropic %.3f      %d alternations, %.5f mm from 8x'
          % (OX, iso_alt, iso_dev))
    print('      X %.3f  Z %.3f  %d alternations, %.5f mm from 8x'
          % (OX, OZ, ani_alt, ani_dev))

    check('an isotropic offset of an arc never reverses direction',
          iso_alt == 0, '%d alternations' % iso_alt)
    check('AN ANISOTROPIC ONE DOES NOT EITHER', ani_alt == 0,
          '%d alternations - the offset is a staircase, which is what '
          'photo/klingyArc_0.png shows' % ani_alt)
    check('   and it stays on the true offset curve', ani_dev < 0.02,
          '%.5f mm from the 8x sampling, against %.5f isotropic'
          % (ani_dev, iso_dev))
    check('   within an order of magnitude of the isotropic case',
          ani_dev < max(iso_dev * 20.0, 0.02),
          '%.5f against %.5f' % (ani_dev, iso_dev))

    # a diameter beside a wall must keep its OWN allowance
    d_iso = diameter_allowance(L, OX, OX)
    d_ani = diameter_allowance(L, 0.5, 0.1)
    check('a diameter beside a wall keeps the radial allowance',
          abs(d_ani - 0.5) < 1e-3, 'left %.4f, wanted 0.5' % d_ani)
    check('   and the isotropic case is unchanged', abs(d_iso - OX) < 1e-3,
          'left %.4f, wanted %.4f' % (d_iso, OX))

    # ---------------------------------------------------------------- controls
    # A check that cannot fail proves nothing. Both ways of getting the
    # curve/corner cut wrong are real bugs, so drive both.
    keep = L.CURVE_TURN_DEG
    try:
        L.CURVE_TURN_DEG = 0.0     # nothing is a curve - the reported bug
        bad_alt, bad_dev = measure(L, OX, OZ)
        # asserted as a RATIO, not an absolute: the deviation scales with the
        # geometry and with the offset, and an absolute threshold here was
        # first written from a harness that was accidentally working in
        # diameters - it read 0.35660 mm for what is 0.02580 at true scale
        check('CONTROL: with no curve vertices the arc goes back to a '
              'staircase',
              bad_alt > 20 and bad_dev > max(ani_dev * 5.0, 0.01),
              'only %d alternations and %.5f mm against %.5f - the '
              'measurement cannot see the bug it exists for'
              % (bad_alt, bad_dev, ani_dev))
        print('         (%d alternations, %.5f mm - the reported state)'
              % (bad_alt, bad_dev))

        L.CURVE_TURN_DEG = 180.0   # everything is a curve - the bad fix
        bled = diameter_allowance(L, 0.5, 0.1)
        check('CONTROL: bisecting every vertex bleeds the wall into the '
              'diameter', abs(bled - 0.5) > 0.05,
              'the diameter still measures %.4f, so this test would not have '
              'caught the fix that shipped 0.3744' % bled)
        print('         (the diameter is left %.4f instead of 0.5)' % bled)
    finally:
        L.CURVE_TURN_DEG = keep

    check('   and the threshold is restored', L.CURVE_TURN_DEG == keep)

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for x in FAILED:
            print('   -', x)
        sys.exit(1)
    print('The anisotropic offset of an arc is as smooth as the isotropic one.')


if __name__ == '__main__':
    main()
