#!/usr/bin/env python3
# coding: utf-8
"""Checks the tool flank shadow in lathe_sections.py.

Standalone, like the other test_*.py here - run it directly, no pytest. Pure
geometry, so it needs no rs274 and runs instantly.

The property under test is the one photo/spaceBehindIssue_0.png shows going
wrong: behind a raised boss the reachable floor is not the profile, it is a
ramp leaving the boss corner at the tool's flank angle. Getting the sign or the
trig wrong here does not crash anything - it silently either gouges the boss or
leaves a step of uncut material - so every case checks a computed number, not
just that a list came back.
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


def at(env, z):
    """Envelope diameter at a Z. Interpolates on a Z-sorted copy: the envelope
    comes back in profile order, which may be descending, and _interpolate_x
    assumes otherwise."""
    e = sorted(env)
    for (z0, x0), (z1, x1) in zip(e, e[1:]):
        if z0 - 1e-9 <= z <= z1 + 1e-9:
            if abs(z1 - z0) < 1e-9:
                return max(x0, x1)
            return x0 + (x1 - x0) * (z - z0) / (z1 - z0)
    return e[-1][1] if z > e[-1][0] else e[0][1]


def main():
    # --- the angles the tool table actually carries -------------------------
    # every demo tool's I/J bisect to its CL angle; that is the consistency
    # check that says the two flanks and the orientation are one set
    for i, j, cl in ((105, 165, 135), (15, 75, 45), (285, 345, 315), (195, 255, 225)):
        check('I%d J%d bisects to CL %d' % (i, j, cl), abs((i + j) / 2.0 - cl) < 1e-9)

    # --- the limiting flank -------------------------------------------------
    # BACK is the trailing flank and the one that fouls a wall already driven
    # past, so it is the column this uses. T2 is J75.
    # BACK is measured off the perpendicular, so the ramp is at 90 - BACK from
    # the Z axis: a J75 insert ramps at 15 degrees and needs a LONG projection
    check('a J75 insert ramps at 15 deg',
          abs(ls.flank_slope(75.0) - math.tan(math.radians(15.0))) < 1e-9)
    check('a J45 insert ramps at 45 deg',
          abs(ls.flank_slope(45.0) - 1.0) < 1e-9)
    check('a flank at or past the perpendicular constrains nothing',
          ls.flank_slope(90.0) is None and ls.flank_slope(0.0) is None)

    # which side is shadowed follows the roughing direction
    check('front to back shadows what is behind, the +Z side',
          ls.flank_sides(0) == (1,))
    check('back to front mirrors it', ls.flank_sides(1) == (-1,))
    check('both directions takes both faces', set(ls.flank_sides(2)) == {1, -1})

    # --- the shape itself ---------------------------------------------------
    # a boss at r20 from Z0 to Z-10, then a valley floor at r10 out to Z-40
    prof = [(0.0, 20.0), (-10.0, 20.0), (-10.0, 10.0), (-40.0, 10.0)]

    # prof is in DIAMETERS, so a D20 boss over a D10 floor is 5 mm of radius.
    # A 45 degree flank rises 1 mm of radius per 1 mm of Z, so it takes 5 mm to
    # come back down to the floor - not 10.
    env = ls.flank_envelope(prof, 45.0)
    check('at the boss the envelope is the boss', abs(at(env, -10.0) - 20.0) < 0.05,
          'r%.3f' % at(env, -10.0))
    for dz, want in ((2.0, 16.0), (5.0, 10.0), (8.0, 10.0), (15.0, 10.0)):
        got = at(env, -10.0 - dz)
        check('%4.1f mm behind the boss the 45 deg flank allows r%.1f' % (dz, want),
              abs(got - want) < 0.06, 'got r%.3f' % got)

    # never below the true profile, anywhere
    below = [(z, r) for z, r in env
             if (ls._outer_x(prof, z) or 0) - r > 1e-6]
    check('the envelope never dips below the profile', not below, str(below[:3]))

    # --- the angle actually changes the ramp --------------------------------
    # a steeper flank gets closer to the boss: 75 degrees rises at tan(75), so
    # it recovers the floor in 10/tan(75) = 2.68 mm instead of 10
    env75 = ls.flank_envelope(prof, 75.0)
    reach = 5.0 / math.tan(math.radians(90.0 - 75.0))
    check('a 75 deg flank recovers the floor in %.2f mm' % reach,
          abs(at(env75, -10.0 - reach) - 10.0) < 0.06,
          'r%.3f at Z%.3f' % (at(env75, -10.0 - reach), -10.0 - reach))
    check('the steeper flank is never more restrictive than the shallow one',
          all(at(env75, z) <= at(env, z) + 1e-6 for z, _ in env75))

    # --- a vertical flank constrains nothing --------------------------------
    envv = ls.flank_envelope(prof, 90.0)
    check('a vertical flank leaves the profile alone', envv == prof, str(envv[:3]))

    # --- both sides bind at once, which is why travel direction drops out ---
    # a valley between two bosses: each wall casts its own ramp inward
    vee = [(0.0, 20.0), (-10.0, 20.0), (-10.0, 8.0), (-30.0, 8.0),
           (-30.0, 20.0), (-40.0, 20.0)]
    envb = ls.flank_envelope(vee, 45.0)
    # 4 mm past a 12 mm wall on a 1:1 flank the tool is still 12 - 4 = 8 above
    # the floor, i.e. r16 - that is the whole point of the shadow
    check('the near wall ramps in at the flank angle',
          abs(at(envb, -14.0) - 12.0) < 0.06, 'D%.3f' % at(envb, -14.0))
    # only the back flank binds, so the far wall - which the tool drives away
    # from, not past - casts no shadow of its own
    check('the far wall casts no shadow, only the near one does',
          abs(at(envb, -26.0) - 8.0) < 0.06, 'r%.3f at Z-26' % at(envb, -26.0))
    check('6 mm past the near wall the floor is reached',
          abs(at(envb, -16.0) - 8.0) < 0.06, 'D%.3f' % at(envb, -16.0))

    # a narrow valley cannot be reached to the bottom at all
    narrow = [(0.0, 20.0), (-10.0, 20.0), (-10.0, 8.0), (-14.0, 8.0),
              (-14.0, 20.0), (-24.0, 20.0)]
    envn = ls.flank_envelope(narrow, 45.0)
    check('a valley narrower than the shadow cannot be bottomed out',
          at(envn, -12.0) > 8.0 + 0.5,
          'deepest reachable D%.3f against a true floor of D8' % at(envn, -12.0))

    # the result is breakpoints, not a sampled curve - it has to fit in a
    # record array, and every point costs eight numbered parameters
    check('the envelope stays compact', len(env) <= 8, '%d points' % len(env))

    # --- degenerate input is handled, not crashed ---------------------------
    check('an empty profile returns empty', ls.flank_envelope([], 45.0) == [])
    check('a single point is returned unchanged',
          ls.flank_envelope([(0.0, 10.0)], 45.0) == [(0.0, 10.0)])

    # --- the emitted ramp must measure the tool's own back angle ------------
    # points are diameters and a flank slope is rise-in-radius per unit Z; if
    # that is not accounted for the ramp comes out at half the angle, which is
    # exactly what testing_15_0 showed - a 75 degree tool ramping at 61.8
    for ang in (75.0, 60.0, 45.0, 30.0):
        e = sorted(ls.flank_envelope([(0.0, 40.0), (-10.0, 40.0),
                                      (-10.0, 22.0), (-90.0, 22.0)], ang))
        got = None
        for (z0, r0), (z1, r1) in zip(e, e[1:]):
            if abs(z1 - z0) > 1e-9 and abs(r1 - r0) > 1e-9:
                got = math.degrees(math.atan(abs((r1 - r0) / 2.0 / (z1 - z0))))
        want = 90.0 - ang
        check('a J%.0f insert ramps at %.0f deg from Z' % (ang, want),
              got is not None and abs(got - want) < 0.01,
              'measured %.2f deg' % got if got else 'no ramp found')

    # --- the reported part: a boss with plain ground either side ------------
    # Front to back over a D50 boss spanning Z-20..-50 in D40 stock. Only the
    # ground the tool has already driven past is shadowed; the approach side is
    # ordinary roughing, because there the tip is the highest touching point.
    boss = [(0.0, 40.0), (-20.0, 40.0), (-20.0, 50.0), (-50.0, 50.0),
            (-50.0, 40.0), (-80.0, 40.0)]
    eb = ls.flank_envelope(boss, 75.0, 0)
    check('the approach side Z0..-20 is left as plain roughing',
          all(abs(at(eb, z) - 40.0) < 0.01 for z in (-2.0, -10.0, -19.0)),
          'D%.2f at Z-10' % at(eb, -10.0))
    check('the boss itself is held at its own diameter',
          all(abs(at(eb, z) - 50.0) < 0.01 for z in (-25.0, -35.0, -49.0)),
          'D%.2f at Z-35' % at(eb, -35.0))
    check('the far side is shadowed, reaching the floor at Z-68.66',
          abs(at(eb, -60.0) - 44.64) < 0.05 and abs(at(eb, -70.0) - 40.0) < 0.01,
          'D%.2f at Z-60, D%.2f at Z-70' % (at(eb, -60.0), at(eb, -70.0)))
    # a wall gives one Z two diameters; seeding from the foot put the envelope
    # INSIDE the boss, which gouges rather than merely under-cuts
    check('the envelope never sits inside the boss',
          not [z for z, x in eb if (ls._outer_x(boss, z) or 0) - x > 1e-6])
    # and back to front mirrors which side is left alone
    er = ls.flank_envelope(boss, 75.0, 1)
    check('back to front shadows the other side instead',
          abs(at(er, -10.0) - 44.64) < 0.05 and abs(at(er, -60.0) - 40.0) < 0.01,
          'D%.2f at Z-10, D%.2f at Z-60' % (at(er, -10.0), at(er, -60.0)))

    # --- a boss TOP is shadowed too, by whatever stands taller beside it ----
    # ground D40, a D50 boss at Z-20..-50, then a D70 wall at Z-60. The boss
    # top is a lower surface like any other: the wall shadows it when the wall
    # is on the side the tool has already driven past, and not otherwise. This
    # needs no separate rule - it is the same wedge, which is the point.
    stepped = [(0.0, 40.0), (-20.0, 40.0), (-20.0, 50.0), (-50.0, 50.0),
               (-50.0, 40.0), (-60.0, 40.0), (-60.0, 70.0), (-90.0, 70.0)]
    ef = ls.flank_envelope(stepped, 75.0, 0)
    check('front to back, the boss top is reached before the tall wall',
          all(abs(at(ef, z) - 50.0) < 0.05 for z in (-25.0, -35.0, -45.0)),
          'D%.2f at Z-35' % at(ef, -35.0))
    er2 = ls.flank_envelope(stepped, 75.0, 1)
    check('back to front, the tall wall shadows the boss top',
          at(er2, -45.0) > 50.0 + 1.0 and abs(at(er2, -21.0) - 50.0) < 0.2,
          'D%.2f at Z-45, D%.2f at Z-21' % (at(er2, -45.0), at(er2, -21.0)))
    check('and that shadow never sits inside either feature',
          not [z for z, x in er2 if (ls._outer_x(stepped, z) or 0) - x > 1e-6])

    # --- a real insert's flank is not infinite ------------------------------
    # the shadow may only reach flank_len * cos(ramp) in Z; past that the body
    # has stepped back and the wall no longer touches it
    bl = [(0.0, 40.0), (-20.0, 40.0), (-20.0, 50.0), (-50.0, 50.0),
          (-50.0, 40.0), (-80.0, 40.0)]
    inf = ls.flank_envelope(bl, 75.0, 0, 0.0)
    check('0 means infinite, exactly as before the field existed',
          ls.flank_envelope(bl, 75.0, 0) == inf)
    # the full ramp is 18.66 mm of Z, so a 20 mm flank - 19.3 mm of reach -
    # covers it and must change nothing
    check('a flank longer than the ramp changes nothing',
          ls.flank_envelope(bl, 75.0, 0, 20.0) == inf)
    for L in (5.0, 2.0):
        reach = L * math.cos(math.radians(15.0))
        e = ls.flank_envelope(bl, 75.0, 0, L)
        check('a %.0f mm flank releases the shadow %.2f mm past the wall' % (L, reach),
              abs(at(e, -50.0 - reach - 0.01) - 40.0) < 0.05,
              'D%.2f just past the limit' % at(e, -50.0 - reach - 0.01))
        check('and still shadows inside that reach',
              at(e, -50.0 - reach + 0.5) > 45.0,
              'D%.2f inside it' % at(e, -50.0 - reach + 0.5))

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('All flank envelope tests passed.')


if __name__ == '__main__':
    main()
