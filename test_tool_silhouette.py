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

    # Both table angles are measured off the PERPENDICULAR, so an edge sits
    # at 90 - it from Z. photo/toolFlank_1.png labels them that way - the
    # "back angle" is between the Z axis and the shallow edge, the "front
    # angle" between the RADIAL direction and the steep one - and it is the
    # same reading flank_slope has always used: a J75 insert ramps at 15 deg.
    # Taking them as directions from Z swaps the two edges.
    check('the back edge sits at 90 - the table back angle',
          abs(ang(arc_end, cap_b) - (90.0 - BACK)) < 1e-6,
          '%.4f deg, want %.4f' % (ang(arc_end, cap_b), 90.0 - BACK))
    check('the front edge sits at 90 - the table front angle',
          abs(ang(cap_f, arc_start) - (90.0 - FRONT)) < 1e-6,
          '%.4f deg, want %.4f' % (ang(cap_f, arc_start), 90.0 - FRONT))
    check('so the back edge is the SHALLOW one, as the shadow ramp is',
          ang(arc_end, cap_b) < ang(cap_f, arc_start),
          'the two edges are the wrong way round')

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

    # --- the holder in front of the insert --------------------------------
    # A third line perpendicular to Z, tangent to the nose, is the holder's
    # front face; the surface between it and the insert's back edge is the
    # block behind the cutting corner. photo/toolFlank_0.png is the shape.
    hold = P.tool_holder(POS, R, ORIENT, FRONT, BACK, FLANK)
    check('a holder comes back with the insert', hold is not None
          and len(hold) == 3)
    if hold:
        cz2, cx2 = centre()
        check('its front face is a single line perpendicular to Z',
              abs(hold[0][0] - hold[1][0]) < 1e-9,
              'Z%.4f vs Z%.4f' % (hold[0][0], hold[1][0]))
        check('that face is tangent to the BACK of the nose circle',
              abs(hold[0][0] - (cz2 + R)) < 1e-9,
              'face at Z%.4f, back tangent at Z%.4f' % (hold[0][0], cz2 + R))
        check('which is one nose diameter behind the leading cap',
              abs(hold[0][0] - min(p[0] for p in poly) - 2 * R) < 1e-9,
              'face is %.4f behind the cap, nose diameter is %.4f'
              % (hold[0][0] - min(p[0] for p in poly), 2 * R))
        check('the top corner is where the face meets the insert edge',
              hold[0][1] > cx2 + R,
              'it starts at the nose, so the face and the edge are not crossing')
        check('the far corner sits on the insert, so the two meet flush',
              any(abs(hold[2][0] - p[0]) < 1e-9 and abs(hold[2][1] - p[1]) < 1e-9
                  for p in poly),
              'the holder corner %s is not on the insert' % (hold[2],))
        check('nothing in the holder is in front of its own face',
              all(q[0] >= hold[0][0] - 1e-9 for q in hold))
        check('it reaches as deep as the insert does',
              abs(max(q[1] for q in hold) - max(p[1] for p in poly)) < 1e-9)
        # a bow tie fills perfectly happily and looks like a shape
        def side(a, b, c):
            return ((b[0] - a[0]) * (c[1] - a[1])
                    - (b[1] - a[1]) * (c[0] - a[0]))
        check('the outline is a simple triangle, not a bow tie',
              abs(side(*hold)) > 1e-9)
    check('no insert, no holder',
          P.tool_holder(POS, R, ORIENT, None, None, FLANK) is None)
    check('no flank length, no holder',
          P.tool_holder(POS, R, ORIENT, FRONT, BACK, 0.0) is None)

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
        def drawn_extent(scale, want=None):
            W = H = 400
            surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
            cr = cairo.Context(surf)
            P.draw_tool(cr, POS, 'ZX', scale, 300.0, 60.0, R, ORIENT,
                        45.0, 60.0, FRONT, BACK, FLANK)
            surf.flush()
            data, stride = surf.get_data(), surf.get_stride()
            # the fills are laid down at 0.9 alpha on a transparent surface,
            # so cairo stores them PREMULTIPLIED - matching the raw colour
            # finds nothing and reads as "it was never drawn"
            body = tuple(int(c * 0.9 * 255) for c in (want or P.COL['tool_body']))
            xs = [x for y in range(H) for x in range(W)
                  if abs(data[y * stride + x * 4 + 2] - body[0]) < 12
                  and abs(data[y * stride + x * 4 + 1] - body[1]) < 12
                  and abs(data[y * stride + x * 4] - body[2]) < 12]
            return (max(xs) - min(xs)) if xs else 0

        # The holder is drawn in the SAME grey as the insert, so it cannot be
        # found by colour. Its own area can: a point inside the holder
        # triangle and outside the insert must still come out tool-coloured,
        # and would be background if the holder were never drawn.
        def inside(poly, p):
            hits = False
            for a, b in zip(poly, list(poly[1:]) + [poly[0]]):
                if (a[1] > p[1]) != (b[1] > p[1]):
                    t = (p[1] - a[1]) / (b[1] - a[1])
                    if p[0] < a[0] + (b[0] - a[0]) * t:
                        hits = not hits
            return hits

        mid = (sum(q[0] for q in hold) / 3.0, sum(q[1] for q in hold) / 3.0)
        check('the holder covers ground the insert does not',
              not inside(poly, mid),
              'its centroid %s is inside the insert, so this proves nothing'
              % (mid,))
        W = H = 400
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
        cr = cairo.Context(surf)
        P.draw_tool(cr, POS, 'ZX', 6.0, 300.0, 60.0, R, ORIENT, 45.0, 60.0,
                    FRONT, BACK, FLANK)
        surf.flush()
        px, py = int(mid[0] * 6.0 + 300.0), int(mid[1] * 6.0 + 60.0)
        data, stride = surf.get_data(), surf.get_stride()
        inked = (0 <= px < W and 0 <= py < H
                 and data[py * stride + px * 4 + 3] > 0)
        check('and that ground is inked, so the holder really is drawn',
              inked, 'nothing at the holder centroid (%d, %d)' % (px, py))

        w1, w2 = drawn_extent(6.0), drawn_extent(12.0)
        check('the silhouette is actually drawn', w1 > 4,
              'nothing in the tool-body colour reached the canvas')
        check('and it is drawn in millimetres, not pixels',
              w1 and abs(w2 - 2 * w1) <= 3,
              '%d px at 6x, %d px at 12x - it should double' % (w1, w2))
        check('at the scale it is asked for',
              w1 and abs(w1 - FLANK * 6.0) <= 3,
              '%d px for a %g mm tool at 6 px/mm' % (w1, FLANK))

        # and the shank is really put on the canvas, not merely computed. A
        # point 20 mm behind and 20 mm out is well past the 12.6 mm insert,
        # so it is background unless the block is drawn.
        W = H = 500
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
        cr = cairo.Context(surf)
        P.draw_tool(cr, POS, 'ZX', 6.0, 120.0, 60.0, R, ORIENT, 45.0, 60.0,
                    FRONT, BACK, FLANK, 25.0)
        surf.flush()
        data, stride = surf.get_data(), surf.get_stride()
        px = int((POS[2] + 20.0) * 6.0 + 120.0)
        py = int((POS[0] + 20.0) * 6.0 + 60.0)
        check('the shank is drawn, not just computed',
              data[py * stride + px * 4 + 3] > 0,
              'nothing at (20, 20) mm, which is inside the block and outside '
              'the insert')

    # --- the shank: what actually bounds the tool -------------------------
    # Without one the outline closes on a Z-perpendicular cap a flank length
    # back, and both cutting edges are EXTENDED to reach it. The front edge is
    # the steep one, so it climbs radially far faster than it travels in Z and
    # the drawn tool grows without limit. A real tool is bounded by its insert
    # and by the block it is clamped in, neither of which the flank governs.
    check('no shank height, no dimensions', P.shank_dims(0.0) is None)
    for h, l1, edge in P.SHANK_TABLE:
        got = P.shank_dims(h)
        check('a %g mm shank is a %g mm holder carrying a %g mm insert'
              % (h, l1, edge),
              got is not None and abs(got[0] - l1) < 1e-9 and got[1] == edge,
              'got %s' % (got,))
    lens = [P.shank_dims(h)[0] for h in [6.0 + 0.5 * i for i in range(80)]]
    check('holder length never goes backwards as the shank grows',
          all(b >= a - 1e-9 for a, b in zip(lens, lens[1:])),
          'a bigger shank came out with a shorter holder')
    inch = P.shank_dims(25.4)
    check('an inch shank is a little longer than the 25 mm one, not equal to it',
          inch is not None and P.shank_dims(25.0)[0] < inch[0]
          < P.shank_dims(32.0)[0],
          'got %s' % (inch,))
    check('but it carries the same standard insert, not a 12.2 mm one',
          inch is not None and inch[1] == P.shank_dims(25.0)[1])

    SH = 25.0
    edge = P.shank_dims(SH)[1]
    ins = P.tool_silhouette(POS, R, ORIENT, FRONT, BACK, FLANK, shank_h=SH)
    check('a shank height gives a silhouette', ins is not None)
    if ins:
        t_f, t_b, e_b, e_f = ins[0], ins[-3], ins[-2], ins[-1]
        check('the back edge runs exactly one insert edge length',
              abs(math.hypot(e_b[0] - t_b[0], e_b[1] - t_b[1]) - edge) < 1e-9,
              'measured %.4f, wanted %g'
              % (math.hypot(e_b[0] - t_b[0], e_b[1] - t_b[1]), edge))
        check('and so does the front edge',
              abs(math.hypot(e_f[0] - t_f[0], e_f[1] - t_f[1]) - edge) < 1e-9,
              'measured %.4f, wanted %g'
              % (math.hypot(e_f[0] - t_f[0], e_f[1] - t_f[1]), edge))
        rad = max(p[1] for p in ins) - min(p[1] for p in ins)
        old = P.tool_silhouette(POS, R, ORIENT, FRONT, BACK, FLANK)
        old_rad = max(p[1] for p in old) - min(p[1] for p in old)
        check('so the insert is bounded by itself, not by the flank',
              rad < old_rad,
              '%.2f mm radially with a shank, %.2f without - no better'
              % (rad, old_rad))
        check('and no bigger than the edge that draws it',
              rad <= edge * 1.05,
              '%.2f mm radially for a %g mm insert' % (rad, edge))
        far = P.tool_silhouette(POS, R, ORIENT, FRONT, BACK, FLANK * 4, shank_h=SH)
        check('the flank length no longer changes the drawn insert at all',
              far == ins,
              'quadrupling the flank moved it, so it is still the bound')

    sh = P.tool_shank(POS, R, ORIENT, FRONT, BACK, SH)
    check('the shank comes back as its own outline', sh is not None)
    if sh:
        l1 = P.shank_dims(SH)[0]
        dz = max(p[0] for p in sh) - min(p[0] for p in sh)
        dx = max(p[1] for p in sh) - min(p[1] for p in sh)
        check('it is the full holder length in Z', abs(dz - l1) < 1e-9,
              '%.1f mm, wanted %.1f' % (dz, l1))
        check('and the shank height radially', abs(dx - SH) < 1e-9,
              '%.1f mm, wanted %g' % (dx, SH))
        # The corner sits on the INSERT, not on the tip: the insert stands
        # proud of the block it is clamped in. Anchored on the tip, the block's
        # top face lies at the cutting radius and sweeps the whole part behind
        # the tool - 50 collisions on a program with none, and the same 50 for
        # a 12 mm shank as for a 25 mm one.
        near_z = min(p[0] for p in sh)
        near_x = min(p[1] for p in sh)
        check('its corner is behind the insert in Z, not on the tip',
              abs(near_z - max(p[0] for p in ins)) < 1e-9,
              'starts at Z%.4f, the insert ends at Z%.4f'
              % (near_z, max(p[0] for p in ins)))
        check('and outside it radially, so the insert stands proud',
              abs(near_x - max(p[1] for p in ins)) < 1e-9
              and near_x > POS[0] + 1e-9,
              'starts at r%.4f, the insert reaches r%.4f'
              % (near_x, max(p[1] for p in ins)))
        check('lying the way the body does, behind the tip',
              max(p[0] for p in sh) > POS[2]
              and min(p[1] for p in sh) >= POS[0] - 1e-9,
              'the holder is on the cutting side of its own insert')
        stub = P.tool_shank(POS, R, ORIENT, FRONT, BACK, SH, length=SH * P.SHANK_STUB)
        s_dz = max(p[0] for p in stub) - min(p[0] for p in stub)
        check('a stub is drawn shorter than the holder really is',
              s_dz < dz and abs(s_dz - SH * P.SHANK_STUB) < 1e-9,
              '%.1f mm stub against a %.1f mm holder' % (s_dz, dz))
        check('and asking for more than the holder has gives the holder',
              max(p[0] for p in P.tool_shank(POS, R, ORIENT, FRONT, BACK, SH,
                                             length=l1 * 10)) - POS[2]
              <= l1 + max(p[0] for p in sh) - min(p[0] for p in sh) + 1e-9)
    check('no shank height, no shank drawn',
          P.tool_shank(POS, R, ORIENT, FRONT, BACK, 0.0) is None,
          'it invented a holder')
    for o in (6, 8):
        check('orientation %d has no corner to hang a shank on' % o,
              P.tool_shank(POS, R, o, FRONT, BACK, SH) is None)

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('The drawn tool is the tool in the table.')


if __name__ == '__main__':
    main()
