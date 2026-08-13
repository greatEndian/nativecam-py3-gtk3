#!/usr/bin/env python3
# coding: utf-8
"""The leading flank's unreachable spans - detection only, no toolpath.

Standalone, like the other test_*.py here - run it directly, no pytest.

Gap 1 of `POLYLINE-GAPS.md`, the WARNING half. `lathe_front_flank` mirrors the
back-angle machinery: same wedge dilation, front angle instead of back, and the
shadowed side flipped, because the leading flank limits surfaces that FALL AWAY
in front of the tool where the trailing flank limits ones that RISE behind it.

WHAT THIS FILE CAN AND CANNOT PROVE. It proves the detection DISCRIMINATES -
fires on a steep front-facing wall, silent on shapes with nothing for a leading
flank to catch on - and that it moves no metal, because nothing imports the
module into a toolpath. It does NOT prove the numbers are physically right on a
real insert: that needs the angle convention and the side mirror checked against
a tool in a hand, and until that is done the module must not be wired to a
warning. See analysis/040 for the survey and the reason.

THE NEGATIVE CONTROLS ARE THE POINT. A detector that fires on everything is
worse than none - it trains the operator to ignore it. So a plain rising taper,
which is most of a lathe part, must come back silent, and it does.
"""
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


def main():
    import lathe_sections as L
    import lathe_front_flank as F

    # --- the mirror ------------------------------------------------------
    check('the direction mirror flips the shadowed side',
          F.mirror_dir(0) == 1 and F.mirror_dir(1) == 0,
          '%d %d' % (F.mirror_dir(0), F.mirror_dir(1)))
    check('   and both-directions stays both',
          F.mirror_dir(2) == 2)
    check('   so the front takes the side the back does not',
          L.flank_sides(F.mirror_dir(0)) != L.flank_sides(0)
          and set(L.flank_sides(F.mirror_dir(2))) == set(L.flank_sides(2)))

    # --- it fires where a leading flank genuinely cannot go --------------
    steep = [(0.0, 20.0), (-10.0, 20.0), (-10.2, 60.0), (-30.0, 60.0)]
    env = F.front_envelope(steep, 15.0, 0)
    sp = F.spans_between(steep, env)
    check('a steep front-facing wall IS reported', len(sp) > 0,
          'the detection cannot fail, so it proves nothing')
    if sp:
        print('      steep wall: %d span(s), worst %.2f mm of radius'
              % (len(sp), max(g for _a, _b, g in sp)))

    # --- and stays quiet where it should ---------------------------------
    rise = [(0.0, 20.0), (-20.0, 30.0), (-50.0, 40.0), (-70.0, 40.0)]
    for d in (0, 1, 2):
        e = F.front_envelope(rise, 15.0, d)
        check('a plain rising taper is silent, direction %d' % d,
              not F.spans_between(rise, e),
              'a detector that fires on an ordinary part is worse than none')

    flat = [(0.0, 20.0), (-30.0, 20.0)]
    check('a plain cylinder is silent',
          not F.spans_between(flat, F.front_envelope(flat, 15.0, 0)))

    # an angle the wedge maths cannot use must degrade to silence, not to a
    # false alarm - flank_slope returns None at or past 90 degrees
    check('an unusable angle reports nothing rather than everything',
          L.flank_slope(105.0) is None
          and not F.spans_between(steep, F.front_envelope(steep, 105.0, 0)))

    # --- it must not be wired to anything --------------------------------
    import subprocess
    r = subprocess.run(['grep', '-rl', 'lathe_front_flank', '--include=*.py',
                        '--include=*.cfg', '--include=*.ngc', HERE],
                       capture_output=True, text=True)
    users = [os.path.basename(x) for x in r.stdout.split()
             if os.path.basename(x) not in ('lathe_front_flank.py',
                                            'test_front_flank.py')]
    check('nothing imports it, so no toolpath can have moved', not users,
          'imported by %s - this is detection only until the convention is '
          'checked against a real insert' % users)

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('The leading-flank detection discriminates, and moves nothing.')


if __name__ == '__main__':
    main()
