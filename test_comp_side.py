#!/usr/bin/env python3
# coding: utf-8
"""Checks which SIDE each lathe op compensates to, without a free-side flag.

Standalone, like the other test_*.py here - run it directly, no pytest. Needs
rs274 and the demo config; skips cleanly without them.

WHY THIS EXISTS
---------------
facing.ngc compensated to the wrong side. The nose circle sat entirely behind
the finished face and every compensated facing pass cut a full nose DIAMETER too
deep - 2.54 mm with the demo tool. It shipped, and the tangency proof of the day
PASSED it, because that proof takes a --freeside flag and it was given `right`,
which for a face profile written outside-in is the MATERIAL side. One line is
tangent to a circle from both sides, so the flag decides the answer: get it
wrong and a gouging path proves correct.

So this asks a question that has no flag to get wrong:

    the nose CIRCLE must lie wholly on the free side of the wall,
    at least its own radius clear of it

Material side is a fact about the operation - a bore has metal outside it, an OD
turn has metal inside it, a face has the bar behind it - not a convention. And
as a second, independent anchor for facing: compensation must leave the finished
face where the uncompensated program put it. Comp exists to move the TOOL, not
the part.
"""
import math
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '.claude', 'skills', 'lathe-gcode-verify',
                                'scripts'))
INI = os.path.join(HERE, 'configs', 'sim', 'axis', 'ncam_demo', 'lathe-mm.ini')
FAILED = []

HEADER = """G21
G18 G7 G90 G94 G54
#<_diameter_mode> = 2
#<_tbl_scale>     = 1.0
#<_rough_cut>     = 1.0
#<_finish_cut>    = 0.3
#<_rough_feed>    = 200
#<_finish_feed>   = 100
#<_x_clear>       = 2.0
#<_ix_clear>      = 2.0
#<_z_clear>       = 2.0
#<_X_rapid>       = 5.0
#<_z_rapid>       = 5.0
#<_wp_dia_od>     = 60
#<_wp_dia_id>     = 20
#<_wp_z>          = 0
#<_cooling_mode>  = 9
#<_tool_usage>    = 2
#<_tip_nose_dia>  = 0.0
#<_tip_orient>    = 0
#<_tip_comp_d>    = 0
#<_tip_comp_l>    = 0
#<_tip_lead_w>    = 0
#<_tip_cam>       = 0
#<_tip_cam_r>     = 0
#<_tip_cam_l>     = 0
#<_tip_off_z>     = 0
#<_tip_off_x>     = 0
"""

# label, tool, R, Q, CALL line with %s for n_comp, wall a->b in (z, radius),
# where the metal is: 'in' = smaller radius, 'out' = larger, 'behind' = -Z side
CASES = [
    ('OD taper', 2, 0.4, 2,
     'o<taper> CALL [60] [40] [0] [30] [1] [0] [%s]',
     ((0.0, 20.0), (-17.3205, 30.0)), 'in'),
    ('ID taper', 4, 1.27, 4,
     'o<taper_id> CALL [30] [20] [0] [60] [1] [0] [%s]',
     ((0.0, 10.0), (2.8868, 15.0)), 'out'),
    ('boring', 4, 1.27, 4,
     'o<boring> CALL [20] [25] [0] [-20] [1] [0] [%s]',
     ((0.0, 12.5), (-20.0, 12.5)), 'out'),
    ('facing', 3, 1.27, 3,
     'o<facing> CALL [60] [0] [1] [0] [1] [0] [6] [45] [0] [6] [45] [0] [1] [%s] [0]',
     ((0.0, 30.0), (0.0, 0.0)), 'behind'),
]


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name
          + (('  ' + detail) if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def run(d, tool, call, nc):
    from parse_rs274 import run_rs274, parse_canon
    p = os.path.join(d, 'case.ngc')
    with open(p, 'w') as f:
        f.write(HEADER + 'T%d M6\nG43\n' % tool + (call % nc) + '\nM2\n')
    canon, _ = run_rs274(INI, p, None)
    return [m for m in parse_canon(canon) if m['kind'] == 'feed']


def free_clearance(centre, a, b, material):
    """How far the nose centre sits on the FREE side of the wall. Negative
    means it is on the metal side, which is a gouge however deep."""
    cz, cx = centre
    if material == 'behind':
        # a face: metal is at -Z, the tool works from +Z
        return cz - a[0]
    dz, dr = b[0] - a[0], b[1] - a[1]
    n = math.hypot(dz, dr)
    nz, nr = -dr / n, dz / n
    if nr < 0:                       # normal pointing to larger radius
        nz, nr = -nz, -nr
    sd = (cz - a[0]) * nz + (cx - a[1]) * nr
    return sd if material == 'in' else -sd


def main():
    if not os.path.isfile(INI):
        print('SKIP  demo config not present')
        return
    if not shutil.which('rs274'):
        print('SKIP  rs274 is not installed')
        return
    try:
        from check_nose_tangent import calibrate_offset
    except Exception as e:
        print('SKIP  verifier scripts unavailable: %s' % e)
        return

    d = tempfile.mkdtemp(prefix='comp_side_')
    for label, tool, R, Q, call, (a, b), material in CASES:
        off = calibrate_offset(INI, None, R, Q, 42, None)
        moves = run(d, tool, call, 1)          # Native compensation
        if not moves:
            check('%s produces a compensated cut' % label, False,
                  'no feed moves - the harness did not run')
            continue
        m = moves[-1] if material != 'behind' else \
            next((x for x in moves if x['x'] < 5.0), moves[-1])
        centre = (m['z'] + off[0], m['x'] + off[1])
        clear = free_clearance(centre, a, b, material)
        check('%s: the nose sits on the free side of the wall' % label,
              clear >= R - 1e-3,
              'clearance %+.4f, needs %+.4f - the nose is %s the wall by %.3f mm'
              % (clear, R, 'behind' if clear < 0 else 'too close to',
                 abs(R - clear)))

    # facing has a second, independent anchor: compensation moves the TOOL, so
    # the finished FACE must land where the uncompensated program put it
    label, tool, R, Q, call, (a, _b), _mat = CASES[-1]
    zs = {}
    for nc, name in ((0, 'Off'), (1, 'Native'), (2, 'In CAM')):
        moves = run(d, tool, call, nc)
        face = next((x for x in moves if x['x'] < 5.0), None)
        off = calibrate_offset(INI, None, R, Q, 42, None)
        if face is not None:
            # the edge of the nose that touches the face
            zs[name] = face['z'] + off[0] - R
    if len(zs) == 3:
        check('facing leaves the face at the same Z in every comp mode',
              max(abs(v - zs['Off']) for v in zs.values()) < 1e-3,
              'Off %.4f, Native %.4f, In CAM %.4f - compensation moved the PART'
              % (zs['Off'], zs['Native'], zs['In CAM']))

    shutil.rmtree(d, ignore_errors=True)
    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('Every op compensates to the free side.')


if __name__ == '__main__':
    main()
