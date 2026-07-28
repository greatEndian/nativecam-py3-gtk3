#!/usr/bin/env python3
# coding: utf-8
"""Checks the lathe tool orientation help drawing in ncam_app_actions.py.

Standalone, like the other test_*.py here - run it directly, no pytest.

The numbers in this dialog are the ones a user will set in the tool table's Q
column, and tool-nose compensation cuts the wrong side of the part if they are
wrong. So this does not check that a dialog appears - it renders every cell to
an image surface and reads back where the nose circle actually landed, against
LinuxCNC's own table.
"""
import math
import os
import sys

sys.argv = ['ncam.py', '-c', 'lathe']
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cairo                                    # noqa: E402
import ncam                                     # noqa: E402,F401
from ncam_app_actions import NCamAppActionsMixin  # noqa: E402

# rs274/glcanon.py, StatCanon.lathe_shapes - the source of truth. Written out
# again here rather than imported, so a silent edit to the copy in
# ncam_app_actions.py fails this test instead of passing it.
LINUXCNC_LATHE_SHAPES = [None, (1, -1), (1, 1), (-1, 1), (-1, -1),
                         (0, -1), (1, 0), (0, 1), (-1, 0), (0, 0)]

SIZE = 84
FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name + (('  ' + detail) if detail else ''))
    if not cond:
        FAILED.append(name)


class Stub(NCamAppActionsMixin):
    pass


def render(app, orient):
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, SIZE, SIZE)
    app.draw_orient_cell(None, cairo.Context(surf), orient, size=SIZE)
    surf.flush()
    return surf


def green_centroid(surf):
    """Centre of the green nose circle, in pixels, or None if it was not drawn."""
    data, stride = surf.get_data(), surf.get_stride()
    xs, ys, n = 0.0, 0.0, 0
    for y in range(SIZE):
        for x in range(SIZE):
            i = y * stride + x * 4
            b, g, r, a = data[i], data[i + 1], data[i + 2], data[i + 3]
            if a > 60 and g > r + 30 and g > b + 30:      # the nose circle only
                xs += x
                ys += y
                n += 1
    return (xs / n, ys / n) if n else None


def main():
    app = Stub()

    check('the table is LinuxCNC\'s own, unmodified',
          app.LATHE_NOSE_OFFSET == LINUXCNC_LATHE_SHAPES,
          '%s' % (app.LATHE_NOSE_OFFSET,))
    check('every orientation 0-9 is described',
          set(app.LATHE_ORIENT_DESC) == set(range(10)))

    # 1-4 are the diagonal corners at R*sqrt(2) - the offset prove_tip_comp.py
    # and CLAUDE.md both rely on for a 90 degree insert
    for n in (1, 2, 3, 4):
        dx, dz = app.LATHE_NOSE_OFFSET[n]
        check('orientation %d sits a diagonal away, R*sqrt(2)' % n,
              abs(math.hypot(dx, dz) - math.sqrt(2)) < 1e-9)
    for n in (5, 6, 7, 8):
        dx, dz = app.LATHE_NOSE_OFFSET[n]
        check('orientation %d sits square on, exactly R' % n,
              abs(math.hypot(dx, dz) - 1.0) < 1e-9)

    # what actually gets drawn: the nose circle must land in the direction the
    # table names, with Z to the right and X up
    centre = SIZE / 2.0
    r = SIZE * 0.19
    for n in range(1, 10):
        got = green_centroid(render(app, n))
        if got is None:
            check('orientation %d draws a nose circle' % n, False)
            continue
        dx, dz = app.LATHE_NOSE_OFFSET[n]
        want = (centre + dz * r, centre - dx * r)
        ok = abs(got[0] - want[0]) < 2.0 and abs(got[1] - want[1]) < 2.0
        check('orientation %d draws the nose %s of the point' % (n, app.LATHE_ORIENT_DESC[n]),
              ok, 'drawn at (%.1f, %.1f), expected (%.1f, %.1f)'
                  % (got[0], got[1], want[0], want[1]))

    # 0 means "not set" and must not claim a direction
    check('orientation 0 draws no directional nose',
          green_centroid(render(app, 0)) is None)

    # 9 is on the point itself, not offset anywhere
    got = green_centroid(render(app, 9))
    where = ('(%.1f, %.1f)' % got) if got else 'nothing drawn'
    check('orientation 9 draws the nose on the point',
          got is not None and abs(got[0] - centre) < 2.0 and abs(got[1] - centre) < 2.0,
          'drawn at ' + where)

    # the cfg the user actually sets must offer exactly these ten
    cfg = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            'cfg', 'lathe', 'tool-change.cfg')).read()
    line = next(ln for ln in cfg.splitlines()
                if ln.startswith('options') and 'From table=0' in ln)
    check('Tool Change offers all ten orientations',
          all(('=%d' % n) in line for n in range(10)), line[:70])

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('All tool orientation tests passed.')


if __name__ == '__main__':
    main()
