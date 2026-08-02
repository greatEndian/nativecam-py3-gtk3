#!/usr/bin/env python3
# coding: utf-8
"""Checks lathe_comp is what the four old copies said, before they diverge.

Standalone, like the other test_*.py here - run it directly, no pytest.

The orientation table existed in four places and the comp side rule in five.
That is not a style problem: the OD and ID side rules are INVERTED, so a copy
made from the wrong neighbour is a gouge, and a table transcribed by hand into
G-code is a gouge that no Python test would ever see. This reads the old copies
where they still exist - including the nine-way branch inside the .ngc - and
asserts the single source agrees with every one of them.

It also pins the one asymmetry that was already wrong. tip_comp_vec.ngc scales
the NORMAL by nose_r + extra and the ORIENTATION term by the bare nose_r;
lathe_sections.offset_contour scaled both by nose_r + extra. Those agree only
while extra is 0, which it was at every call site - so the disagreement was
real, latent, and invisible. lathe_comp follows the .ngc, because that is the
rule the interpreter itself uses.
"""
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import lathe_comp as C                                      # noqa: E402

FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name
          + (('  ' + detail) if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def parse_orient_branch(path):
    """{L: (oz, ox)} as tip_comp_vec.ngc actually assigns them."""
    with open(path) as f:
        txt = f.read()
    out = {}
    arms = re.split(r'o<tv_or>\s*(?:if|elseif)\s*\[#<_tip_cam_l>\s*EQ\s*(\d+)\]',
                    txt)
    for i in range(1, len(arms) - 1, 2):
        body = arms[i + 1].split('o<tv_or>')[0]
        oz = re.search(r'#<tv_oz>\s*=\s*\[?(-?\d+)', body)
        ox = re.search(r'#<tv_ox>\s*=\s*\[?(-?\d+)', body)
        if oz and ox:
            out[int(arms[i])] = (int(oz.group(1)), int(ox.group(1)))
    return out


def parse_sides(path, var):
    """[side, ...] in the order the .ngc assigns them: default first."""
    with open(path) as f:
        txt = f.read()
    return [int(v) for v in re.findall(r'#<%s>\s*=\s*(\d+)\b' % var, txt)]


def main():
    # --- the orientation table, against every surviving copy ---------------
    check('the diagonal entries are a raw R*sqrt2 vector, not a unit one',
          all(abs(math.hypot(x, z) - math.sqrt(2)) < 1e-12
              for x, z in C.NOSE_OFFSET[1:5]),
          'normalising them mis-measures every corner tool')
    check('and the axis entries are unit',
          all(abs(math.hypot(x, z) - 1.0) < 1e-12
              for x, z in C.NOSE_OFFSET[5:9]))
    check('orientation 9 has no offset', C.NOSE_OFFSET[9] == (0, 0))

    import lathe_sections as ls
    check('lathe_sections agrees', list(ls.NOSE_OFFSET) == list(C.NOSE_OFFSET),
          '%s' % (ls.NOSE_OFFSET,))

    import ncam_preview as P
    check('ncam_preview agrees, in its own (Z, x) order',
          list(P.NOSE_DIR) == list(C.NOSE_DIR), '%s' % (P.NOSE_DIR,))
    check('   and the two orders really are transposes of one another',
          all(C.NOSE_DIR[i] == (C.NOSE_OFFSET[i][1], C.NOSE_OFFSET[i][0])
              for i in range(1, 10)))

    # ncam_app_actions imports gtk, so its copy is read as TEXT rather than
    # imported - a fourth transcription is exactly the kind that rots unseen
    aa = os.path.join(HERE, 'ncam_app_actions.py')
    with open(aa) as f:
        src = f.read()
    m = re.search(r'LATHE_NOSE_OFFSET\s*=\s*\[(.*?)\]\s*\n\n', src, re.S)
    if m:
        body = m.group(1)
        pairs = [(int(a), int(b)) for a, b in
                 re.findall(r'\(\s*(-?\d+)\s*,\s*(-?\d+)\s*\)', body)]
        check('ncam_app_actions agrees',
              pairs == list(C.NOSE_OFFSET[1:]), '%s' % (pairs,))
    else:
        check('ncam_app_actions still declares a table to check',
              'lathe_comp' in src,
              'neither its own copy nor an import of the shared one')

    ngc = os.path.join(HERE, 'lib/lathe/tip_comp_vec.ngc')
    if os.path.isfile(ngc):
        branch = parse_orient_branch(ngc)
        check('the .ngc nine-way branch parses', len(branch) == 8,
              'got %d arms - the parser, not the table, is what failed'
              % len(branch))
        bad = [n for n, (oz, ox) in branch.items()
               if (ox, oz) != C.NOSE_OFFSET[n]]
        check('and every arm of it agrees', not bad,
              'orientation(s) %s differ' % bad)
    else:
        print('SKIP  tip_comp_vec.ngc is gone - fold its table check into '
              'whatever replaced it')

    # --- the offset vector -------------------------------------------------
    # A wall parallel to Z, cut toward -Z, orientation 2. The whole reason the
    # entry ramp existed: the two terms cancel in X, so the compensated point
    # sits ON the surface and a "+R everywhere" guess is 0.4 mm out.
    oz, ox = C.offset_vector(C.RIGHT, -1.0, 0.0, 0.4, 2)
    check('a Z-parallel wall gets NO radial shift on an orientation-2 tool',
          abs(ox) < 1e-12, 'got %.6f - this is the taper that started it' % ox)
    check('   and is pulled back by the nose radius in Z',
          abs(oz + 0.4) < 1e-12, 'got %.6f' % oz)

    # orientation 9 is the bare normal, which is the easiest case to reason
    # about and the one every intuition is built on
    oz, ox = C.offset_vector(C.RIGHT, -1.0, 0.0, 0.4, 9)
    check('orientation 9 is the plain normal', abs(oz) < 1e-12
          and abs(abs(ox) - 0.4) < 1e-12, '(%.4f, %.4f)' % (oz, ox))

    a = C.offset_vector(C.LEFT, -1.0, 0.0, 0.4, 9)
    b = C.offset_vector(C.RIGHT, -1.0, 0.0, 0.4, 9)
    check('41 and 42 are opposite sides',
          abs(a[0] + b[0]) < 1e-12 and abs(a[1] + b[1]) < 1e-12,
          '%s vs %s' % (a, b))

    check('nothing to compensate gives no offset',
          C.offset_vector(C.RIGHT, 0.0, 0.0, 0.4, 2) == (0.0, 0.0)
          and C.offset_vector(C.RIGHT, -1.0, 0.0, 0.0, 2) == (0.0, 0.0),
          'a caller must be able to apply it unconditionally')

    # THE ASYMMETRY. With an allowance held and a diagonal orientation the two
    # terms scale differently, and scaling both alike is a different answer.
    r, extra = 0.4, 0.5
    got = C.offset_vector(C.RIGHT, -1.0, 0.0, r, 2, extra)
    both = ((r + extra) * 0.0 - (r + extra) * 1,
            (r + extra) * 1.0 - (r + extra) * 1)
    want = (0.0 - r * 1, (r + extra) * 1.0 - r * 1)
    check('the allowance moves the normal but not the nose geometry',
          abs(got[0] - want[0]) < 1e-12 and abs(got[1] - want[1]) < 1e-12,
          'got %s, wanted %s' % (got, want))
    check('   which is a different answer from scaling both alike',
          abs(got[1] - both[1]) > 1e-9,
          'the two rules agree here, so this test proves nothing')

    # --- the lead width ----------------------------------------------------
    check('the lead width is the nose DIAMETER as an X word',
          abs(C.lead_width(0.8) - 1.6) < 1e-12, '%.4f' % C.lead_width(0.8))
    check('   and never negative', C.lead_width(-5.0) == 0.0)

    # --- the comp side registry -------------------------------------------
    ops = (('taper', 'lib/lathe/taper.ngc', 't_side', False),
           ('taper_id', 'lib/lathe/taper_id.ngc', 't_side', False),
           ('boring', 'lib/lathe/boring.ngc', 'b_side', False),
           ('facing', 'lib/lathe/facing.ngc', 'f_side', False),
           ('polyline', 'lib/lathe/lathe_poly_pass.ngc', 'c_side', True))
    for op, path, var, poly in ops:
        full = os.path.join(HERE, path)
        if not os.path.isfile(full):
            print('SKIP  %s is gone' % path)
            continue
        sides = parse_sides(full, var)
        check('%s: the .ngc still states two sides' % op, len(sides) >= 2,
              'found %s' % sides)
        if len(sides) < 2:
            continue
        # the polyline writes its default first and the flip second, like the
        # rest; its bore inversion is a separate expression and not matched
        check('%s: default side %d matches the registry' % (op, sides[0]),
              C.comp_side(op) == sides[0],
              'registry says %s' % C.comp_side(op))
        check('%s: flipped side %d matches' % (op, sides[1]),
              C.comp_side(op, flip=True) == sides[1],
              'registry says %s' % C.comp_side(op, flip=True))

    check('OD and ID really are inverted, which is why this is a table',
          C.comp_side('taper') != C.comp_side('taper_id')
          and C.comp_side('taper') != C.comp_side('boring'),
          'copying one op rule to another would now be silent')
    check('a bore inverts the polyline side',
          C.comp_side('polyline', bore=True) == 83 - C.comp_side('polyline'))
    check('an operation that does not compensate says so',
          C.comp_side('turning') is None and C.comp_side('radius_od') is None,
          'they carry their own G41/G42 and are not in the registry yet')
    check('the registry is the seam for adding them',
          set(C.OPS) == {'taper', 'taper_id', 'boring', 'facing', 'polyline'},
          'a new op is a row, not a refactor')

    check('the free side is the one the material is not on',
          C.free_side(C.LEFT) == 'left' and C.free_side(C.RIGHT) == 'right',
          'a tangency proof without it passes a wrong answer')

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('One table, one offset rule, one side registry.')


if __name__ == '__main__':
    main()
