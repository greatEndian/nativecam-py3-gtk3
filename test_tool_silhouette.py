#!/usr/bin/env python3
# coding: utf-8
"""Checks the drawn lathe tool is the tool, not a decoration.

Standalone, like the other test_*.py here - run it directly, no pytest.

The silhouette is built from the tool table's nose radius and its FRONT and
BACK angles, plus the flank length off the Tool Change:

  - the nose circle;
  - the two cutting edges, each TANGENT to that circle, at the two table
    angles;
  - two lines perpendicular to Z closing the back - one tangent to the nose
    circle on its leading side, the other one flank length behind it.

Every one of those is a property that can be measured on the returned outline,
which is the only reason this is worth testing: a wedge drawn at roughly the
right angle looks completely convincing and tells the operator nothing true
about clearance. The previous version was exactly that - a fixed number of
PIXELS long, so it changed size when you zoomed.
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import ncam_preview as P                                   # noqa: E402

FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name
          + (('  ' + detail) if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


# a plausible right-hand OD turning tool: 0.8 mm nose, orientation 2, a 60
# degree insert whose centre line is 45 degrees - which is I=15, J=75
POS = (25.0, 0.0, -10.0)          # (x=radius, y, z), as the plot works in
R = 0.8
ORIENT = 2
FRONT, BACK = 15.0, 75.0
FLANK = 6.0


def centre(pos=POS, r=R, orient=ORIENT):
    rz, rx = P.nose_offset(orient)
    return (pos[2] + rz * r, pos[0] + rx * r)


def main():
    poly = P.tool_silhouette(POS, R, ORIENT, FRONT, BACK, FLANK)
    check('a tool with angles and a flank length has a silhouette',
          poly is not None and len(poly) >= 4)
    if poly is None:
        print('FAILED: nothing to measure')
        sys.exit(1)

    cz, cx = centre()

    # --- the nose arc lies ON the nose circle -----------------------------
    on_circle = [p for p in poly
                 if abs(math.hypot(p[0] - cz, p[1] - cx) - R) < 1e-9]
    check('the nose is drawn at the nose radius, not near it',
          len(on_circle) >= 6,
          '%d of %d points sit on the circle' % (len(on_circle), len(poly)))
    check('and nothing is drawn INSIDE the nose circle',
          all(math.hypot(p[0] - cz, p[1] - cx) > R - 1e-9 for p in poly),
          'a point inside the nose means the outline cuts through it')

    # --- the two straight edges are TANGENT to the nose circle -------------
    # the edge runs from the last arc point to the cap; its distance from the
    # centre must be exactly R at the tangent point and grow from there
    def dist_to_line(a, b, c):
        dz, dx = b[0] - a[0], b[1] - a[1]
        n = math.hypot(dz, dx)
        if n < 1e-12:
            return None
        return abs((c[0] - a[0]) * dx - (c[1] - a[1]) * dz) / n

    arc_end, cap_b, cap_f = poly[-3], poly[-2], poly[-1]
    arc_start = poly[0]
    d_back = dist_to_line(arc_end, cap_b, (cz, cx))
    d_front = dist_to_line(cap_f, arc_start, (cz, cx))
    check('the back edge is tangent to the nose circle',
          d_back is not None and abs(d_back - R) < 1e-9,
          'stands off %.6f, nose is %.3f' % (d_back or -1, R))
    check('the front edge is tangent to the nose circle',
          d_front is not None and abs(d_front - R) < 1e-9,
          'stands off %.6f, nose is %.3f' % (d_front or -1, R))

    # --- the edges run at the TABLE angles, not at the centre line ---------
    def ang(a, b):
        return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 180.0

    check('the back edge runs at the tool table back angle',
          abs(ang(arc_end, cap_b) - BACK % 180.0) < 1e-6,
          '%.4f deg, table says %.4f' % (ang(arc_end, cap_b), BACK))
    check('the front edge runs at the tool table front angle',
          abs(ang(cap_f, arc_start) - FRONT % 180.0) < 1e-6,
          '%.4f deg, table says %.4f' % (ang(cap_f, arc_start), FRONT))

    # --- the two cap lines are perpendicular to Z, one flank apart ---------
    check('the back of the tool is a single line perpendicular to Z',
          abs(cap_b[0] - cap_f[0]) < 1e-9,
          'the two ends sit at Z%.4f and Z%.4f' % (cap_b[0], cap_f[0]))
    z_lead = min(p[0] for p in poly)
    check('the leading cap is tangent to the nose circle',
          abs(z_lead - (cz - R)) < 1e-9,
          'leading Z %.4f, tangent is at %.4f' % (z_lead, cz - R))
    check('and the back cap is exactly one flank length behind it',
          abs((cap_b[0] - z_lead) - FLANK) < 1e-9,
          'measured %.4f, flank length is %.4f' % (cap_b[0] - z_lead, FLANK))

    # the silhouette must FOLLOW the flank length, not just be near it once
    for f in (3.0, 12.0, 25.0):
        p2 = P.tool_silhouette(POS, R, ORIENT, FRONT, BACK, f)
        got = (max(q[0] for q in p2) - min(q[0] for q in p2)) if p2 else None
        check('a %g mm flank draws a %g mm long tool' % (f, f),
              got is not None and abs(got - f) < 1e-9,
              'drew %s' % (('%.4f' % got) if got else 'nothing'))

    # --- the body is on the correct side ----------------------------------
    # orientation 2 puts the nose centre at +Z and +radius from the tip, so
    # the body trails at +Z. Drawing it the other way is the mirror-image bug
    # this project already had once.
    check('the body extends the way the nose offset points',
          max(p[0] for p in poly) > POS[2],
          'the tool is on the wrong side of its own tip')
    check('and it stands off the part, not into it',
          min(p[1] for p in poly) >= POS[0] - 1e-9,
          'part of the tool is at a smaller radius than the control point')

    # --- it refuses rather than guesses -----------------------------------
    check('no flank length, no silhouette',
          P.tool_silhouette(POS, R, ORIENT, FRONT, BACK, 0.0) is None,
          'it invented a length')
    check('no tool table angles, no silhouette',
          P.tool_silhouette(POS, R, ORIENT, None, None, FLANK) is None)
    check('no nose radius, no silhouette',
          P.tool_silhouette(POS, 0.0, ORIENT, FRONT, BACK, FLANK) is None)
    check('a flank shorter than the nose itself is refused',
          P.tool_silhouette(POS, R, ORIENT, FRONT, BACK, 0.5) is None,
          'the cap would fall in front of the cutting edges')
    # orientations 6 and 8 point straight along X - there is no Z extent for a
    # Z-perpendicular cap to bound, so there is nothing honest to draw
    for o in (6, 8):
        check('orientation %d has no Z extent and is refused' % o,
              P.tool_silhouette(POS, R, o, 0.0, 180.0, FLANK) is None)

    # --- the mirrored tool, to prove the sides are not hard-coded ----------
    # orientation 1 is the left-hand corner: nose centre at -Z, +radius
    left = P.tool_silhouette(POS, R, 1, 105.0, 165.0, FLANK)
    check('a left-hand tool is built too', left is not None)
    if left:
        check('and it extends the other way in Z',
              min(p[0] for p in left) < POS[2],
              'both hands of tool point the same way')

    # --- and it must reach the canvas ------------------------------------
    # The geometry above can be perfect while draw_tool ignores it. What
    # distinguishes the silhouette from the old wedge on screen is that it is
    # in MILLIMETRES: doubling the scale must double the drawn tool. The wedge
    # it replaced was a fixed count of pixels and did not move at all.
    try:
        import cairo
    except ImportError:
        print('SKIP  cairo is not installed - cannot check the drawing')
    else:
        def drawn_extent(scale):
            W = H = 400
            surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
            cr = cairo.Context(surf)
            P.draw_tool(cr, POS, 'ZX', scale, 300.0, 60.0, R, ORIENT,
                        45.0, 60.0, FRONT, BACK, FLANK)
            surf.flush()
            data, stride = surf.get_data(), surf.get_stride()
            body = tuple(int(c * 255) for c in P.COL['tool_body'])
            xs = [x for y in range(H) for x in range(W)
                  if abs(data[y * stride + x * 4 + 2] - body[0]) < 12
                  and abs(data[y * stride + x * 4 + 1] - body[1]) < 12
                  and abs(data[y * stride + x * 4] - body[2]) < 12]
            return (max(xs) - min(xs)) if xs else 0

        w1, w2 = drawn_extent(6.0), drawn_extent(12.0)
        check('the silhouette is actually drawn', w1 > 4,
              'nothing in the tool-body colour reached the canvas')
        check('and it is drawn in millimetres, not pixels',
              w1 and abs(w2 - 2 * w1) <= 3,
              '%d px at 6x, %d px at 12x - it should double' % (w1, w2))
        check('at the scale it is asked for',
              w1 and abs(w1 - FLANK * 6.0) <= 3,
              '%d px for a %g mm tool at 6 px/mm' % (w1, FLANK))

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('The drawn tool is the tool in the table.')


if __name__ == '__main__':
    main()
