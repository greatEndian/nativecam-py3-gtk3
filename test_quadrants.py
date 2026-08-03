#!/usr/bin/env python3
# coding: utf-8
"""Compensation holds for BOTH outside-turning quadrants, in every mode.

Standalone, like the other test_*.py here - run it directly, no pytest.

Outside turning puts the nose centre away from the spindle axis, at +X. Three
orientations do that:

    1  (+X, -Z)   the second quadrant - a left-hand tool, cutting toward +Z
    2  (+X, +Z)   the first quadrant  - a right-hand tool, cutting toward -Z
    7  (+X,  0)   straight out, no Z component

greatEndian asked for all three compensation modes to stay available on the
first and second quadrants rather than the work narrowing to whichever one the
demo tool happens to carry. This checks the geometry for every orientation and
both sides, so a change that only ever gets exercised on orientation 2 cannot
quietly break orientation 1.

WHAT IS PROVED, and why it is worth proving analytically rather than by running
rs274 six times: compensation is correct exactly when the NOSE CIRCLE ends up
tangent to the surface, on the free side. Placing the circle needs the raw
orientation vector - R*sqrt(2) on a corner tool, not R - and the whole point of
the offset rule is that its orientation term cancels the placement so the centre
lands at surface + r * normal whatever the orientation is. That is one identity
and it can be checked to machine precision.

The negative control matters more here than anywhere: a single profile line is
tangent to a circle from BOTH sides, so a proof that does not say which side is
free will pass a wrong answer cheerfully. Every case is therefore also
COMPENSATED TO THE WRONG SIDE and required to come out inside the material -
re-measuring the same circle from the other side would be a tautology.
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import lathe_comp as C                                      # noqa: E402

FAILED = []

# the surfaces an OD profile is actually made of, as (dz, dx) travel directions
# in radius units: a cylinder, a face, and tapers either way
SURFACES = (
    ('cylinder toward -Z', (-1.0, 0.0)),
    ('cylinder toward +Z', (1.0, 0.0)),
    ('face inward', (0.0, -1.0)),
    ('face outward', (0.0, 1.0)),
    ('45 taper down', (-1.0, -1.0)),
    ('45 taper up', (-1.0, 1.0)),
    ('shallow 15 taper', (-3.732, -1.0)),
    ('steep 75 taper', (-1.0, -3.732)),
)

OD_QUADRANTS = (1, 2, 7)
R = 0.4


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name
          + (('  ' + detail) if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def normal(side, dz, dx):
    """The unit normal compensation offsets along, restated independently."""
    n = math.hypot(dz, dx)
    uz, ux = dz / n, dx / n
    return (ux, -uz) if side == C.RIGHT else (-ux, uz)


def nose_centre(surface, off, orient):
    """Where the nose circle actually sits, given a compensated control point.

    control point + R * orientation vector, with the RAW vector - the diagonal
    entries are R*sqrt(2) and normalising them here would hide exactly the
    error this file exists to catch.
    """
    ox, oz = C.nose_offset(orient)
    return (surface[0] + off[0] + R * oz,
            surface[1] + off[1] + R * ox)


def main():
    surface = (0.0, 20.0)

    # --- the identity, for every orientation and both sides ----------------
    worst = 0.0
    for orient in range(1, 10):
        for side in (C.LEFT, C.RIGHT):
            for label, (dz, dx) in SURFACES:
                off = C.offset_vector(side, dz, dx, R, orient)
                cz, cx = nose_centre(surface, off, orient)
                nz, nx = normal(side, dz, dx)
                want = (surface[0] + R * nz, surface[1] + R * nx)
                worst = max(worst, math.hypot(cz - want[0], cx - want[1]))
    check('the nose lands on surface + R * normal for every orientation, '
          'both sides, all %d surfaces' % len(SURFACES),
          worst < 1e-12,
          'worst placement error %.3e mm - the orientation term is not '
          'cancelling' % worst)

    # --- tangency and the free side, on the OD quadrants -------------------
    for orient in OD_QUADRANTS:
        for side in (C.LEFT, C.RIGHT):
            ok_t, ok_free, ok_neg = True, True, True
            for label, (dz, dx) in SURFACES:
                off = C.offset_vector(side, dz, dx, R, orient)
                centre = nose_centre(surface, off, orient)
                nz, nx = normal(side, dz, dx)
                # distance from the nose centre to the surface LINE, signed
                # along the normal: exactly +R when the circle is tangent and
                # standing on the free side
                d = (centre[0] - surface[0]) * nz + (centre[1] - surface[1]) * nx
                if abs(abs(d) - R) > 1e-12:
                    ok_t = False
                if d < 0:
                    ok_free = False
                # THE NEGATIVE CONTROL, and it has to compensate to the
                # WRONG side rather than just re-measure the same circle:
                # offset to the other side, then measure against the normal
                # that is actually correct. The nose must come out on the
                # material side - a gouge - or the side selection is not
                # doing anything and neither is this test.
                other = C.LEFT if side == C.RIGHT else C.RIGHT
                bad = nose_centre(surface,
                                  C.offset_vector(other, dz, dx, R, orient),
                                  orient)
                d_bad = ((bad[0] - surface[0]) * nz
                         + (bad[1] - surface[1]) * nx)
                if d_bad >= 0:
                    ok_neg = False
            q = {1: 'second quadrant', 2: 'first quadrant',
                 7: 'straight out'}[orient]
            check('orientation %d, %s, G%d: the nose is tangent to every '
                  'surface' % (orient, q, side), ok_t)
            check('   and stands on the free side of it', ok_free,
                  'the tool is inside the material')
            check('   while compensating to the wrong side gouges, as it must',
                  ok_neg,
                  'the wrong side is indistinguishable here, so the free-side '
                  'check proves nothing')

    # --- what UNCOMPENSATED costs, per quadrant ---------------------------
    # Off is a real mode, not an absence: it must still be RIGHT on a surface
    # parallel to an axis, and wrong by a knowable amount elsewhere. That is
    # the whole reason compensation is optional.
    for orient in OD_QUADRANTS:
        errs = {}
        for label, (dz, dx) in SURFACES:
            centre = nose_centre(surface, (0.0, 0.0), orient)
            nz, nx = normal(C.RIGHT, dz, dx)
            d = (centre[0] - surface[0]) * nz + (centre[1] - surface[1]) * nx
            errs[label] = abs(abs(d) - R)
        flat = max(errs['cylinder toward -Z'], errs['cylinder toward +Z'],
                   errs['face inward'], errs['face outward'])
        angled = errs['45 taper down']
        q = {1: 'second', 2: 'first', 7: 'straight out'}[orient]
        if orient == 7:
            # straight out has no Z component, so a FACE is the axis-parallel
            # case it gets right and a cylinder is not
            check('orientation 7 uncompensated is exact on a face',
                  errs['face inward'] < 1e-12,
                  '%.4f mm' % errs['face inward'])
        else:
            check('orientation %d (%s quadrant) uncompensated is exact on a '
                  'cylinder and a face' % (orient, q), flat < 1e-12,
                  'worst %.4f mm - comp would not be optional' % flat)
        check('   and out by %.4f mm on a 45 degree taper' % angled,
              angled > 0.1,
              'only %.4f mm, so this profile does not exercise the fault'
              % angled)

    # --- the modes ---------------------------------------------------------
    # In CAM applies the vector above. Native hands the same job to the
    # interpreter through G41.1/G42.1 D- L-, and Step 4's measurement puts the
    # two within 0.0000 mm of each other on three projects. Off applies nothing.
    # What can be asserted here is that the three are DISTINCT and that the
    # mode switch is the only thing between them.
    off_cam = C.offset_vector(C.RIGHT, -1.0, -1.0, R, 2)
    check('In CAM offsets a taper', math.hypot(*off_cam) > 0.1)
    check('Off offsets nothing - a zero radius is the mode switch',
          C.offset_vector(C.RIGHT, -1.0, -1.0, 0.0, 2) == (0.0, 0.0))
    check('and the side is what Native is told, from the same registry',
          C.comp_side('polyline') in (C.LEFT, C.RIGHT)
          and C.comp_side('polyline', flip=True) != C.comp_side('polyline'))

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('Both outside quadrants compensate, and the wrong side is caught.')


if __name__ == '__main__':
    main()
