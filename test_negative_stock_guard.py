#!/usr/bin/env python3
# coding: utf-8
"""offset_contour must refuse loudly past its bound, not return silently.

Standalone, like the other test_*.py here - run it directly, no pytest.

Covers openPoints.md's "Negative stock to leave ... fails SILENTLY past its
bound": offset_contour already cuts past the model correctly for
-nose_r < extra < 0 (measured -0.10 -> -0.1000, -0.39 -> -0.3900 with a 0.4
nose), but at extra <= -nose_r the old guard returned the profile unchanged
with no warning - ask for 0.5 past the model and silently get 0.0. See
analysis/260.

This is the GUARD half only. Exposing the parameter (lowering the cfg
minimum below 0.0) is explicitly out of scope and remains greatEndian's call.
"""
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
    prof = [(0.0, 40.0), (-20.0, 40.0)]

    # --- last good value: strictly inside the bound, still honoured --------
    out = ls.offset_contour(prof, R, 9, 1, -0.39)
    check('extra=-0.39 with a 0.4 nose still offsets (-0.3900 effective)',
          all(abs(x - 40.02) < 1e-9 for _z, x in out),
          str(out))

    # a second in-bound point, further from the edge
    out2 = ls.offset_contour(prof, R, 9, 1, -0.10)
    check('extra=-0.10 with a 0.4 nose still offsets (-0.1000 effective)',
          all(abs(x - 40.6) < 1e-9 for _z, x in out2),
          str(out2))

    # --- the boundary exactly at -nose_r: the FIRST refused value -----------
    try:
        ls.offset_contour(prof, R, 9, 1, -0.40)
        check('extra == -nose_r exactly (-0.40 with a 0.4 nose) is refused',
              False, 'no exception raised')
    except ValueError as e:
        check('extra == -nose_r exactly (-0.40 with a 0.4 nose) is refused',
              True, str(e))

    # --- past the boundary: still refused, not silently 0.0 -----------------
    try:
        ls.offset_contour(prof, R, 9, 1, -0.50)
        check('extra past -nose_r (-0.50 with a 0.4 nose) is refused', False,
              'no exception raised')
    except ValueError as e:
        check('extra past -nose_r (-0.50 with a 0.4 nose) is refused', True,
              str(e))

    # --- the established no-op must still be silent, not refused -----------
    # nose_r=0, extra=0: no nose and no allowance requested at all - the
    # existing contract test_offset_contour.py pins ("a zero nose radius
    # returns the profile") and this guard must not disturb.
    check('nose_r=0, extra=0 is still a silent no-op, not a refusal',
          ls.offset_contour(prof, 0.0, 9) == prof)

    # nose_r=0 with a REAL positive extra is the pure-geometric-offset path
    # build_prefinish_contour_gcode relies on - must still offset normally.
    out3 = ls.offset_contour(prof, 0.0, 0, 1, 0.508)
    check('nose_r=0 with a positive extra still offsets (pure geometric path)',
          all(abs(x - 41.016) < 1e-6 for _z, x in out3), str(out3))

    print('\n%d failed' % len(FAILED))
    return 1 if FAILED else 0


if __name__ == '__main__':
    sys.exit(main())
