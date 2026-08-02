#!/usr/bin/env python3
# coding: utf-8
"""Checks a polyline arc still ENDS where it is defined to end.

Standalone, like the other test_*.py here - run it directly, no pytest.

An arc item reaches the finishing passes as chords: resolve_points densifies it
under a sagitta bound, and finish_profile then thins the result with
_min_segment so no segment is shorter than the cutter-compensation shrink. The
thinning kept only the first and last points of the WHOLE contour, so the point
where an arc meets the item after it - a real corner - was fair game. A
densified arc's last chord is whatever the sweep leaves over and is routinely
shorter than the limit, so that corner was being dropped and the path ran from
the last surviving chord vertex straight to the next item's far end.

Measured on testing_13_arcs, a 0.4 mm nose, limit 2.4 x 0.4 = 0.960 mm:

    R4   16 x 5.625 deg densified, kept every 3rd, remainder 0.3925 mm  DROPPED
    R6   20 x 4.500 deg densified, kept every 3rd, remainder 0.9423 mm  DROPPED
    R10  25 x 3.600 deg densified, kept every 2nd, remainder 0.6282 mm  DROPPED

The R6 misses the limit by 18 um. Its 90 degree sweep stopped at 81, and the
19 mm cylinder that follows at r 28.000 was cut as a ramp starting at r 27.061 -
0.9386 mm of radius, confirmed in the rs274 canon before this test existed.

That is also why In CAM measured 0.8875 mm "worse" than Native on that project:
In CAM reaches the arc's true endpoint because build_cam_comp_gcode asks
finish_profile for nose_r 0, which switches the thinning off. Native was the one
in the wrong.

No rs274 here - this is arithmetic, and arithmetic is cheap to check.
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import lathe_sections as ls                                 # noqa: E402

FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name
          + (('  ' + detail) if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def arc_chords(radius, sweep_deg, start=(0.0, 0.0)):
    """The densified chord vertices of an arc, as resolve_points makes them.

    Reproduces _densify_arc's rule rather than calling it, so a change to that
    rule shows up here as a disagreement instead of being copied into the
    expectation.
    """
    step = max(2.0 * math.degrees(math.acos(1.0 - ls.MESH_MAX_SAG / radius)),
               0.05)
    n = min(max(int(math.ceil(sweep_deg / step)), 1), 64)
    out = []
    for i in range(0, n + 1):        # index 0 is the arc's own start point
        a = math.radians(-90.0 + sweep_deg * i / n)
        out.append((start[0] + radius * math.cos(a),
                    (start[1] + radius + radius * math.sin(a))
                    * ls.DIAMETER_MODE))
    return out


def main():
    NOSE = 0.4
    LIMIT = 2.4 * NOSE

    # --- the three arcs of testing_13_arcs, by the numbers ----------------
    for radius, remainder in ((4.0, 0.3925), (6.0, 0.9423), (10.0, 0.6282)):
        pts = arc_chords(radius, 90.0)
        tail = math.hypot(pts[-1][0] - pts[-2][0],
                          (pts[-1][1] - pts[-2][1]) / ls.DIAMETER_MODE)
        # the chord that the thinning measures is the one from the last KEPT
        # point, not the last densified one - walk it the way _min_segment does
        keep = [pts[0]]
        for q in pts[1:-1]:
            if math.hypot(q[0] - keep[-1][0],
                          (q[1] - keep[-1][1]) / ls.DIAMETER_MODE) >= LIMIT:
                keep.append(q)
        left = math.hypot(pts[-1][0] - keep[-1][0],
                          (pts[-1][1] - keep[-1][1]) / ls.DIAMETER_MODE)
        check('an R%g 90 degree arc leaves a %.4f mm last chord' % (radius,
                                                                    remainder),
              abs(left - remainder) < 0.002,
              'measured %.4f, and %.4f between the last two densified points'
              % (left, tail))
        check('   which is under the %.3f mm thinning limit' % LIMIT,
              left < LIMIT,
              '%.4f is not - this arc would not have been truncated' % left)

    # --- the actual regression: the endpoint survives the thinning --------
    # A run of arc chords followed by a long straight, exactly the shape that
    # broke: R6 into a 19 mm cylinder.
    pts = arc_chords(6.0, 90.0)
    end = pts[-1]
    contour = pts + [(end[0] - 19.0, end[1])]

    thin = ls._min_segment(contour, LIMIT)
    check('without protection the arc endpoint is dropped',
          end not in thin,
          'it survived, so this test no longer exercises the fault')
    if end not in thin:
        # how far the shortcut misses the profile, measured at the endpoint's Z
        a = thin[-2]
        b = thin[-1]
        t = (end[0] - a[0]) / (b[0] - a[0]) if abs(b[0] - a[0]) > 1e-12 else 0.0
        miss = abs((a[1] + (b[1] - a[1]) * t) - end[1]) / ls.DIAMETER_MODE
        check('   and the shortcut misses the corner by about 0.94 mm',
              0.85 < miss < 1.0, 'measured %.4f mm' % miss)

    thin = ls._min_segment(contour, LIMIT, [end])
    check('protecting the corner keeps it', end in thin)
    check('   and nothing else is added back',
          len(thin) == len([p for p in ls._min_segment(contour, LIMIT)]) + 1,
          '%d points protected against %d unprotected'
          % (len(thin), len(ls._min_segment(contour, LIMIT))))

    # the thinning must still THIN - protecting corners is not a way to
    # smuggle every densified chord back in, which would put the short
    # segments that abort a compensated pass right back where they were
    check('the arc is still thinned, not returned whole',
          len(thin) < len(contour),
          '%d of %d points kept' % (len(thin), len(contour)))
    shortest = min(math.hypot(b[0] - a[0], (b[1] - a[1]) / ls.DIAMETER_MODE)
                   for a, b in zip(thin, thin[1:]))
    check('   and the only segment under the limit is the protected one',
          sum(1 for a, b in zip(thin, thin[1:])
              if math.hypot(b[0] - a[0],
                            (b[1] - a[1]) / ls.DIAMETER_MODE) < LIMIT) == 1,
          'shortest %.4f mm' % shortest)

    # --- resolve_points hands the corners out -----------------------------
    check('resolve_points takes a vertices argument',
          'vertices' in ls.resolve_points.__code__.co_varnames,
          'nothing can protect what it cannot name')

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('An arc ends where it is defined to end.')


if __name__ == '__main__':
    main()
