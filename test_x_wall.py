#!/usr/bin/env python3
# coding: utf-8
"""The perpendicular X wall detour: detection by angle, and the pass shape.

Standalone, like the other test_*.py here - run it directly, no pytest.

greatEndian, 2026-08-26, on testing_15_8: the pre-finish and finish passes met
a perpendicular X wall behind the boss and made the wrong shape - they fed into
the wall, RAPIDED out through metal that was still standing, dived back toward
centre and led out. The wanted shape stops in front of the wall, leads out,
lifts clear in X, comes back down the wall face, and then feeds along Z to take
the strip that stopping short left behind.

THIS IS THE VERIFICATION LOOP THEY ASKED FOR, and its point is that the rules
are checked rather than the coordinates eyeballed: `check_x_wall_moves` states
what the shape must satisfy, and every case below is run through it. Cases that
must FAIL are included too - a validator that cannot fail proves nothing, which
is the trap `test_ladder`'s skip-thin control fell into three days earlier.
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import lathe_sections as L                            # noqa: E402

FAILED = []
TOL, FRONT = 2.0, 0.5


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name
          + (('  ' + detail) if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def wall(dz, dx, z0=-10.0, x0=20.0):
    return [(z0 - 5.0, x0), (z0, x0), (z0 + dz, x0 + dx), (z0 + dz + 5.0, x0 + dx)]


def main():
    # --- 1. detection is an ANGLE, and the boundary is where it says ------
    check('a dead perpendicular wall is detected',
          L.x_wall_indices(wall(0.0, 5.0), TOL) == [1])
    # 2 degrees off X over a 5 mm rise is 0.1747 in Z - seventeen times the
    # 0.0005 the old length test allowed, and still perpendicular to a machinist
    dz2 = 5.0 * math.tan(math.radians(2.0))
    check('   and one exactly at the tolerance still is  dz=%.4f' % dz2,
          L.x_wall_indices(wall(dz2, 5.0), TOL) == [1])
    dz3 = 5.0 * math.tan(math.radians(2.5))
    check('   while one past it is not  dz=%.4f' % dz3,
          L.x_wall_indices(wall(dz3, 5.0), TOL) == [])
    check('   the old length test would have missed the 2 degree wall',
          dz2 > 0.0005,
          'dz %.4f is inside the old 0.0005 window after all' % dz2)
    check('a DESCENDING wall is not one to come at from outside',
          L.x_wall_indices(wall(0.0, -5.0), TOL) == [])
    check('   unless rising_only is off',
          L.x_wall_indices(wall(0.0, -5.0), TOL, rising_only=False) == [1])
    check('a plain taper is not a wall',
          L.x_wall_indices(wall(5.0, 5.0), TOL) == [])
    check('a pure Z move is not a wall',
          L.x_wall_indices([(0.0, 20.0), (-10.0, 20.0)], TOL) == [])
    check('a negative tolerance detects nothing rather than everything',
          L.x_wall_indices(wall(0.0, 5.0), -1.0) == [])

    # --- 2. the shape, both ways round -----------------------------------
    Z_WALL, X_BASE, X_TOP, LEAD = -10.0, 20.0, 25.0, 26.0
    for appr in (1, -1):
        mv = L.x_wall_moves(Z_WALL, X_BASE, X_TOP, appr, FRONT, LEAD)
        bad = L.check_x_wall_moves(mv, Z_WALL, X_BASE, X_TOP, appr, FRONT, LEAD)
        check('the detour satisfies every rule, approach %+d' % appr,
              not bad, '; '.join(bad))
        d = 1 if appr >= 0 else -1
        z_stop = Z_WALL - d * FRONT
        print('      approach %+d: stop Z%.4f, clean-up ends Z%.4f, %.4f past it'
              % (appr, z_stop, mv[4][1], abs(mv[4][1] - z_stop)))
        check('   the stop is on the side the tool came from, approach %+d' % appr,
              d * (Z_WALL - z_stop) > 0)
        check('   and the clean-up is twice the stand-off, approach %+d' % appr,
              abs(abs(mv[4][1] - mv[3][1]) - 2.0 * FRONT) < 1e-9,
              'travelled %.4f' % abs(mv[4][1] - mv[3][1]))
        check('   no rapid happens at the cutting radius, approach %+d' % appr,
              not [1 for k, _z, x in mv if k == 'rapid' and abs(x - X_BASE) < 1e-9])

    # --- 3. the validator must be able to FAIL ---------------------------
    # Each of these is the shape with one rule broken. If any passes, the
    # validator is decoration and every check above is vacuous.
    good = L.x_wall_moves(Z_WALL, X_BASE, X_TOP, 1, FRONT, LEAD)
    broken = {
        'a clean-up of only one stand-off':
            good[:4] + [('feed', Z_WALL - FRONT, X_BASE)],
        'a rapid where the wall face is cut':
            good[:3] + [('rapid', Z_WALL, X_BASE)] + good[4:],
        'a feed used for the lift out':
            good[:1] + [('feed', good[1][1], good[1][2])] + good[2:],
        'a stop that is not short of the wall':
            [('feed', Z_WALL, X_BASE)] + good[1:],
    }
    for name, mv in broken.items():
        bad = L.check_x_wall_moves(mv, Z_WALL, X_BASE, X_TOP, 1, FRONT, LEAD)
        check('the validator rejects %s' % name, bool(bad),
              'it was accepted - the validator proves nothing')
    # and a lead level inside the wall top is refused
    check('the validator rejects a lead level below the wall top',
          bool(L.check_x_wall_moves(
              L.x_wall_moves(Z_WALL, X_BASE, X_TOP, 1, FRONT, X_TOP - 1.0),
              Z_WALL, X_BASE, X_TOP, 1, FRONT, X_TOP - 1.0)))

    # --- 3b. a step shorter than the nose diameter is a corner, not a wall -
    # greatEndian, 2026-08-27: "at boss segment start point of arc it generates
    # infinite long orange stand still line". On testing_15_8 the offset path
    # runs the cylinder into the boss arc through a 0.626 mm EXACTLY
    # perpendicular step - dz is 0.0000, so no angle tolerance separates it
    # from a real wall - and a detour landed in the middle of the arc.
    NOSE_DIA = 0.8
    check('a 0.626 step is rejected at the nose diameter',
          L.x_wall_indices(wall(0.0, 0.626), TOL, NOSE_DIA) == [])
    check('   and the real 19.24 wall beside it is still found',
          L.x_wall_indices(wall(0.0, 19.24), TOL, NOSE_DIA) == [1])
    check('   the boundary is the nose diameter itself',
          L.x_wall_indices(wall(0.0, NOSE_DIA + 0.01), TOL, NOSE_DIA) == [1]
          and L.x_wall_indices(wall(0.0, NOSE_DIA - 0.01), TOL, NOSE_DIA) == [])
    check('   with no minimum, the step reads as a wall - which is the bug',
          L.x_wall_indices(wall(0.0, 0.626), TOL) == [1],
          'the control does not reproduce the fault, so it proves nothing')
    check('a short step does not split the contour either',
          len(L.split_contour_at_walls(
              [(0.0, 20.0), (-10.0, 20.0), (-10.0, 20.626), (-20.0, 20.626)],
              TOL, FRONT, NOSE_DIA)) == 1)

    # --- 4. the split into sub-passes, which is how it is actually built --
    # greatEndian rejected a per-point rapid flag: it would have cost a third
    # slot per point and dropped the finish-contour table from 100 points to
    # 66, and "there could come any files with any number of points". Splitting
    # costs 2 slots per sub-path in a directory and leaves the point stride
    # alone, so no profile gets a smaller ceiling than it has today.
    prof = [(0.0, 20.0), (-10.0, 20.0), (-10.0, 25.0), (-20.0, 25.0)]
    parts = L.split_contour_at_walls(prof, TOL, FRONT)
    check('a wall splits the contour into three sub-paths', len(parts) == 3,
          '%d: %s' % (len(parts), parts))
    if len(parts) == 3:
        a, b, c = parts
        check('   A ends the stand-off short of the wall',
              abs(a[-1][0] - (-10.0 + FRONT)) < 1e-9 and abs(a[-1][1] - 20.0) < 1e-9,
              'A ends at %s' % (a[-1],))
        check('   B leads in at the wall TOP, outside the material',
              abs(b[0][0] - (-10.0)) < 1e-9 and abs(b[0][1] - 25.0) < 1e-9,
              'B starts at %s' % (b[0],))
        check('   B feeds down the face to the corner',
              abs(b[1][0] - (-10.0)) < 1e-9 and abs(b[1][1] - 20.0) < 1e-9,
              'B second point %s' % (b[1],))
        check('   B cleans up twice the stand-off',
              abs(abs(b[2][0] - b[1][0]) - 2.0 * FRONT) < 1e-9,
              'travelled %.4f' % abs(b[2][0] - b[1][0]))
        # MEASURED FROM THE WALL, not as bare magnitudes. Z here is negative,
        # so comparing abs() said -9.0 was nearer the wall than -9.5 when it is
        # a full stand-off further from it. The check was wrong and the
        # geometry was right - the trap CLAUDE.md names about instruments.
        check('   and the clean-up passes the stop rather than touching it',
              abs(b[2][0] - (-10.0)) > abs(a[-1][0] - (-10.0)) + 1e-9,
              'clean-up ends %.4f, stop was %.4f, wall at -10.0000'
              % (b[2][0], a[-1][0]))
        check('   C carries the rest of the contour',
              c[-1] == prof[-1], 'C is %s' % (c,))
        print('      A %s  B %s  C %s' % (a, b, c))

    # --- 4b. the surface into the wall is not always a cylinder ----------
    # greatEndian, 2026-08-27: behind a boss the tool meets the artificial
    # back-angle ramp, and elsewhere an arc or a taper - "movement have to be
    # in all axis together". Holding X at the corner radius is right only on a
    # surface parallel to Z; on a ramp the stop lands off the contour and the
    # clean-up runs through material or through air.
    #
    # A TAPER rising 2.0 over 10.0 into a wall: dx/dz is 0.2, so the stop at
    # 0.5 back must sit at X21.9 and the clean-up at 1.0 back at X21.8 - NOT
    # at the corner's 22.0.
    tap = [(0.0, 20.0), (-10.0, 22.0), (-10.0, 27.0), (-20.0, 27.0)]
    parts = L.split_contour_at_walls(tap, TOL, FRONT, 0.0)
    check('a taper into a wall still splits', len(parts) == 3,
          '%d parts' % len(parts))
    if len(parts) == 3:
        a, b, _c = parts
        print('      taper: A ends %s   B %s' % (a[-1], b))
        check('   the stop follows the taper in X, not the corner radius',
              abs(a[-1][0] + 9.5) < 1e-9 and abs(a[-1][1] - 21.9) < 1e-9,
              'stop is %s, wanted (-9.5, 21.9)' % (a[-1],))
        check('   and the clean-up follows it too',
              abs(b[-1][0] + 9.0) < 1e-9 and abs(b[-1][1] - 21.8) < 1e-9,
              'clean-up ends %s, wanted (-9.0, 21.8)' % (b[-1],))
        check('   the clean-up moves in BOTH axes',
              abs(b[-1][1] - b[-2][1]) > 1e-9,
              'X did not change: %s -> %s' % (b[-2], b[-1]))

    # A RAMP OF SEVERAL SHORT SEGMENTS - an arc, or the back-angle shadow -
    # where the clean-up spans more than one of them and has to keep every
    # vertex between, or it cuts the chord instead of the surface.
    ramp = [(0.0, 20.0), (-9.0, 21.0), (-9.4, 21.2), (-9.8, 21.5),
            (-10.0, 21.8), (-10.0, 27.0), (-20.0, 27.0)]
    parts = L.split_contour_at_walls(ramp, TOL, FRONT, 0.0)
    check('a multi-segment ramp into a wall splits', len(parts) == 3,
          '%d parts' % len(parts))
    if len(parts) == 3:
        a, b, _c = parts
        print('      ramp:  A ends %s   B %s' % (a[-1], b))
        check('   the clean-up keeps the vertices it crosses',
              len(b) >= 4, 'B has only %d points: %s' % (len(b), b))
        zs = [pt[0] for pt in b[1:]]
        check('   and it travels twice the stand-off along Z',
              abs(abs(zs[-1] - zs[0]) - 2.0 * FRONT) < 1e-9,
              'travelled %.4f' % abs(zs[-1] - zs[0]))
        check('   every clean-up point sits on the ramp, none at one radius',
              len({round(pt[1], 6) for pt in b[1:]}) > 1,
              'all at one X: %s' % (b[1:],))

    # --- 4c. a wall running out to the bar starts ON the envelope --------
    # greatEndian, 2026-08-28: the stored path is CONTROL points, shifted in by
    # the tip compensation, so a wall reaching the bar has its top a nose
    # radius inside the envelope - the nose contacts it at exactly one point.
    # "from mathematical point of view we reach this point 100%, but in reality
    # everything have some stiffness and rigidity and everything will somehow
    # bend", and a small sharp tip is left at the outside.
    NOSE, STOCK = 0.4, 35.0
    reach = [(0.0, 20.0), (-10.0, 20.0), (-10.0, STOCK - NOSE), (-20.0, STOCK - NOSE)]
    parts = L.split_contour_at_walls(reach, TOL, FRONT, 0.0, STOCK, NOSE)
    check('a wall reaching the bar splits', len(parts) == 3, '%d' % len(parts))
    if len(parts) == 3:
        top = parts[1][0][1]
        print('      face top %.4f, was %.4f, envelope %.4f, contact %.4f'
              % (top, STOCK - NOSE, STOCK, top + NOSE))
        check('   the face starts ON the envelope, not a nose inside it',
              abs(top - STOCK) < 1e-9,
              'top is %.4f, wanted %.4f' % (top, STOCK))
        check('   so the nose over-travels past the bar instead of touching it',
              top + NOSE > STOCK + 1e-9,
              'contact %.4f only reaches %.4f' % (top + NOSE, STOCK))
    # AND IT MUST NOT LIFT A WALL THAT STOPS INSIDE THE PART. Without this the
    # rule would drag every internal step out to the bar.
    inner = [(0.0, 20.0), (-10.0, 20.0), (-10.0, 25.0), (-20.0, 25.0)]
    parts = L.split_contour_at_walls(inner, TOL, FRONT, 0.0, STOCK, NOSE)
    check('a wall that stops inside the part is NOT lifted to the bar',
          len(parts) == 3 and abs(parts[1][0][1] - 25.0) < 1e-9,
          'top is %s' % (parts[1][0][1] if len(parts) == 3 else parts,))
    check('   and with no stock given nothing is lifted at all',
          abs(L.split_contour_at_walls(reach, TOL, FRONT, 0.0)[1][0][1]
              - (STOCK - NOSE)) < 1e-9)

    # A PROFILE WITHOUT A WALL MUST NOT MOVE AT ALL - that is what makes this
    # safe to switch on, and it is asserted rather than assumed.
    plain = [(0.0, 20.0), (-10.0, 22.0), (-20.0, 22.0)]
    check('a profile with no wall comes back untouched',
          L.split_contour_at_walls(plain, TOL, FRONT) == [plain])
    check('   and so does one with the feature switched off',
          L.split_contour_at_walls(prof, TOL, 0.0) == [prof])
    # a wall as the very first segment has no approach to stop
    check('a wall with no segment before it is left alone',
          L.split_contour_at_walls([(0.0, 20.0), (0.0, 25.0), (-10.0, 25.0)],
                                   TOL, FRONT)
          == [[(0.0, 20.0), (0.0, 25.0), (-10.0, 25.0)]])
    # and one approached radially - no Z travel to shorten
    check('a wall reached without Z travel is left alone',
          len(L.split_contour_at_walls(
              [(0.0, 18.0), (0.0, 20.0), (0.0, 25.0), (-10.0, 25.0)],
              TOL, FRONT)) == 1)

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('The X wall detour is the shape greatEndian specified.')


if __name__ == '__main__':
    main()
