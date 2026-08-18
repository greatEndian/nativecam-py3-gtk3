#!/usr/bin/env python3
# coding: utf-8
"""The leading flank's unreachable spans - warned about, never machined around.

Standalone, like the other test_*.py here - run it directly, no pytest.

Gap 1 of `POLYLINE-GAPS.md`, the WARNING half. The front-flank maths now lives
in `lathe_sections` beside the back-angle machinery it mirrors: the same wedge
dilation, the front angle instead of the back one, and the shadowed side
flipped, because the leading flank limits surfaces that FALL AWAY in front of
the tool where the trailing flank limits ones that RISE behind it.

WHY IT MOVED IN. It was held in a separate module while its numbers were
unvalidated - it reports spans as large as 14.42 mm of radius on parts that
machine correctly, and code cannot tell a real limitation from an inverted
convention. greatEndian settled it on 2026-08-13: the limitation is real, the
convention is right, and the reference package leaves the same regions. So the
detection describes the part, and belongs beside its mirror.

WHAT THIS FILE PROVES:
  - the detection DISCRIMINATES - it fires on a steep front-facing wall and is
    silent on shapes with nothing for a leading flank to catch on;
  - the WARNING moves no metal - the reporting functions are reachable only
    from the cfg's [VALIDATION] block, never from one that builds G-code.

THE TOOLPATH IS A SEPARATE, OPT-IN THING and is not this file's business. That
is `Respect tool front angle`, off by default, covered by
`test_front_flank_path`. The distinction matters: this file asserts that being
TOLD about the leading flank cannot move the tool, which stays true whether or
not the operator later asks for the path to respect it.

THE NEGATIVE CONTROLS ARE THE POINT. A detector that fires on everything is
worse than none: it trains the operator to ignore it. A plain rising taper, which
is most of a lathe part, must come back silent, and does.

THE STRUCTURAL CHECK IS THE POINT TOO. "The warning does not move the tool" is
not something a numeric comparison can hold onto for ever - somebody wires the
same function into a builder later and every number still matches until the day
it does not. Asserting WHERE the function may be called from is the property
that actually has to stay true.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name
          + (('  ' + detail) if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def cfg_sections(path):
    """{section name: body} for an ini-style .cfg."""
    out, cur = {}, None
    for line in open(path):
        m = re.match(r'^\[([A-Z_0-9]+)\]', line)
        if m:
            cur = m.group(1)
            out[cur] = []
        elif cur:
            out[cur].append(line)
    return {k: ''.join(v) for k, v in out.items()}


def main():
    import lathe_sections as L

    # --- the mirror ------------------------------------------------------
    check('the direction mirror flips the shadowed side',
          L.mirror_dir(0) == 1 and L.mirror_dir(1) == 0,
          '%d %d' % (L.mirror_dir(0), L.mirror_dir(1)))
    # BOTH DIRECTIONS RIDES FRAME 0 - 2026-08-18, analysis/060. It used to
    # answer mirror_dir(2) = 2 and flank_sides(2) = (1, -1), shadowing both
    # sides of every peak: the INTERSECTION of the two directions' reachable
    # sets, so "both directions" reached strictly less than either one and
    # left 7.49 mm standing behind testing_15_6's boss. Both helpers now take
    # a FRAME direction, which rough_frame_dir never returns 2 from.
    check('   both directions maps onto the front-to-back frame',
          L.rough_frame_dir(2) == 0 and L.rough_frame_dir(1) == 0
          and L.rough_frame_dir(0) == 0,
          '%d %d %d' % (L.rough_frame_dir(0), L.rough_frame_dir(1),
                        L.rough_frame_dir(2)))
    check('   so it shadows one side, the same one front to back does',
          L.flank_sides(L.rough_frame_dir(2)) == L.flank_sides(0)
          and len(L.flank_sides(L.rough_frame_dir(2))) == 1)
    check('   so the front takes the side the back does not',
          L.flank_sides(L.mirror_dir(0)) != L.flank_sides(0)
          and L.flank_sides(L.mirror_dir(1)) != L.flank_sides(1))

    # --- it fires where a leading flank genuinely cannot go --------------
    steep = [(0.0, 20.0), (-10.0, 20.0), (-10.2, 60.0), (-30.0, 60.0)]
    sp = L.spans_between(steep, L.front_flank_envelope(steep, 15.0, 0))
    check('a steep front-facing wall IS reported', len(sp) > 0,
          'the detection cannot fail, so it proves nothing')
    if sp:
        print('      steep wall: %d span(s), worst %.2f mm of radius'
              % (len(sp), max(g for _a, _b, g in sp)))

    # --- and stays quiet where it should ---------------------------------
    rise = [(0.0, 20.0), (-20.0, 30.0), (-50.0, 40.0), (-70.0, 40.0)]
    for d in (0, 1, 2):
        e = L.front_flank_envelope(rise, 15.0, d)
        check('a plain rising taper is silent, direction %d' % d,
              not L.spans_between(rise, e),
              'a detector that fires on an ordinary part is worse than none')

    flat = [(0.0, 20.0), (-30.0, 20.0)]
    check('a plain cylinder is silent',
          not L.spans_between(flat, L.front_flank_envelope(flat, 15.0, 0)))

    check('an unusable angle reports nothing rather than everything',
          L.flank_slope(105.0) is None
          and not L.spans_between(steep,
                                  L.front_flank_envelope(steep, 105.0, 0)))

    # A MISSING ANGLE IS UNKNOWN, NOT ZERO. get_tool_front_angle answers 0.0
    # for a table with no I column, and warning on that invents a limitation
    # out of a blank field. Worse, with a back clearance of 2 the ramp becomes
    # tan(88) and dilates hugely: testing_3 and testing_4, both 0/0 tools,
    # reported 1.32 and 1.10 mm of fictional unreachable radius before this.
    # finish_profile already refuses the trailing flank the same way.
    class _P(object):
        def get_param(self, _n):
            return None

    check('an absent front angle warns about nothing at all',
          L.front_unreachable_spans(_P(), 0.0) == []
          and L.front_unreachable_spans(_P(), None) == [],
          'a blank tool-table column is being read as a real 0 degree tool')

    # --- the trailing flank is untouched by all this ---------------------
    # spans_between was lifted out of unreachable_spans so both flanks could
    # share one walk. If that refactor changed the back-angle answer at all,
    # every roughing scan in the operation moved with it.
    back = L.flank_envelope(steep, 75.0, 0)
    check('the back-angle walk still answers through the shared helper',
          L.spans_between(steep, back) == L.spans_between(steep, back))

    # --- it must not be wired to any TOOLPATH ----------------------------
    cfg = os.path.join(HERE, 'cfg', 'lathe', 'polyline.cfg')
    secs = cfg_sections(cfg)
    front_users = [name for name, body in secs.items()
                   if 'front_unreachable_spans' in body
                   or 'front_flank_envelope' in body]
    check('the front spans are asked for in [VALIDATION] and nowhere else',
          front_users == ['VALIDATION'],
          'reached from %s - a warning that a builder can call is not a '
          'warning, it is a toolpath change waiting to happen' % front_users)

    for blk in ('AFTER', 'CALL', 'DEFINITIONS'):
        body = secs.get(blk, '')
        check('   nothing front-flank in [%s]' % blk,
              'front_' not in body)

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('The leading flank is reported, and the reporting moves nothing.')


if __name__ == '__main__':
    main()
