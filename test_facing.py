#!/usr/bin/env python3
# coding: utf-8
"""Validates the facing operation's new properties by tracing real motion.

Standalone, like the other test_*.py here - run it directly, no pytest.

This does not inspect the cfg text and call that a test. It rebuilds what
cfg/lathe/facing.cfg's [CALL] emits, runs it through rs274, and reads the
coordinates back, so what is checked is the toolpath the machine would get.

Needs rs274 and the ncam_demo sim config, same as the lathe-gcode-verify
scripts. Skips with a clear message if rs274 is not on PATH.
"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '.claude', 'skills', 'lathe-gcode-verify', 'scripts'))

INI = os.path.join(HERE, 'configs', 'sim', 'axis', 'ncam_demo', 'lathe-mm.ini')
FAILED = []

STOCK_OD = 60.0
STOCK_ID = 20.0

PREAMBLE = """G21
G18 G40 G49 G90 G92.1 G94 G54 G64 p0.001
G7
#<_diameter_mode>   = 2.0
#<_rough_feed>      = 100.0
#<_finish_feed>     = 60.0
#<_rough_cut>       = 1.0
#<_finish_cut>      = 0.25
#<_z_clear>         = 2.0
#<_x_clear>         = 2.0
#<_x_rapid>         = 5.0
#<_wp_dia_od>       = %(od).4f
#<_wp_dia_id>       = %(id).4f
#<_wp_z>            = 0.0
#<_cooling_mode>    = 9
#<_tool_usage>      = 0
#<_tip_lead_w>      = 0.0
#<_tip_nose_dia>    = 0.0
#<_tip_orient>      = 0.0
#<_tip_comp_d>      = 0.0
#<_tip_comp_l>      = 0.0
#<_flt_ok>          = 0.0
#<_flt_t1z>         = 0.0
#<_flt_t1x>         = 0.0
#<_flt_cz>          = 0.0
#<_flt_cx>          = 0.0
#<_flt_cw>          = 0.0
T3 M6
G43
"""

# The reference-resolution chain exactly as cfg/lathe/facing.cfg [CALL] emits it.
RESOLVE = """o<bxr> if [%(bxr)d EQ 1]
\t#<f_bx> = [#<_wp_dia_od> + %(bx).4f]
o<bxr> elseif [%(bxr)d EQ 2]
\t#<f_bx> = [#<_wp_dia_id> + %(bx).4f]
o<bxr> else
\t#<f_bx> = %(bx).4f
o<bxr> endif
o<exr> if [%(exr)d EQ 1]
\t#<f_ex> = [#<_wp_dia_od> + %(ex).4f]
o<exr> elseif [%(exr)d EQ 2]
\t#<f_ex> = [#<_wp_dia_id> + %(ex).4f]
o<exr> else
\t#<f_ex> = %(ex).4f
o<exr> endif
o<dir> if [%(dir)d EQ 1]
\t#<f_tmp> = #<f_bx>
\t#<f_bx> = #<f_ex>
\t#<f_ex> = #<f_tmp>
o<dir> endif
o<fzr> if [%(fzr)d EQ 1]
\t#<f_fz> = %(fz).4f
o<fzr> else
\t#<f_fz> = [#<_wp_z> + %(fz).4f]
o<fzr> endif
o<facing> CALL [#<f_bx>] [#<f_ex>] [#<f_fz> + %(zd).4f] [#<f_fz>] [%(fin)d] [0] [0] [45] [0] [0] [45] [0] [%(np)d] [0] [%(sl).4f]
M2
"""


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name + (('  ' + detail) if detail else ''))
    if not cond:
        FAILED.append(name)


def run(bxr=0, bx=62.0, exr=0, ex=0.0, direction=0, zd=2.0, fin=1, np_=1, sl=0.0,
        fzr=0, fz=0.0):
    """Emit a harness, trace it, return the list of cutting moves as (z, radius)."""
    from parse_rs274 import run_rs274, parse_canon
    body = PREAMBLE % {'od': STOCK_OD, 'id': STOCK_ID} + RESOLVE % {
        'bxr': bxr, 'bx': bx, 'exr': exr, 'ex': ex, 'dir': direction,
        'zd': zd, 'fin': fin, 'np': np_, 'sl': sl, 'fzr': fzr, 'fz': fz}
    d = tempfile.mkdtemp(prefix='test_facing_')
    path = os.path.join(d, 'case.ngc')
    with open(path, 'w') as f:
        f.write(body)
    canon, _raw = run_rs274(INI, path)
    bad = [ln for ln in canon.splitlines()
           if 'error' in ln.lower() and 'COMMENT(' not in ln and 'error_code' not in ln.lower()]
    if bad:
        raise AssertionError('interpreter error: %s' % bad[0].strip()[:120])
    moves = [(m['kind'], m['z'], m['x']) for m in parse_canon(canon)
             if m['kind'] in ('feed', 'arc', 'rapid')]
    shutil.rmtree(d, ignore_errors=True)
    return moves


def face_span(moves):
    """The longest constant-Z cutting move - the face itself.

    The start point has to come from whatever positioned the tool, rapid
    included: with the leads switched off the face is the first feed in the
    program and nothing cutting precedes it.
    """
    best = None
    for (k0, z0, r0), (k1, z1, r1) in zip(moves, moves[1:]):
        if k1 != 'feed':
            continue
        if abs(z1 - z0) < 1e-6 and (best is None or abs(r1 - r0) > abs(best[1] - best[0])):
            best = (r0, r1)
    return best


def main():
    if shutil.which('rs274') is None:
        print('SKIP - rs274 not on PATH; this test needs the LinuxCNC interpreter')
        return
    if not os.path.exists(INI):
        print('SKIP - demo ini not found at %s' % INI)
        return

    # 1 - a plain value is used as given
    span = face_span(run(bxr=0, bx=62.0, exr=0, ex=0.0))
    check('Value/Value faces from D62 to D0',
          span is not None and abs(span[0] - 31.0) < 1e-3 and abs(span[1]) < 1e-3,
          'span=%s' % (span,))

    # 2 - Stock OD/ID references, with the diameter field acting as the offset
    span = face_span(run(bxr=1, bx=2.0, exr=0, ex=0.0))
    check('Stock OD + 2 begins at D62 with stock D60',
          span is not None and abs(span[0] - 31.0) < 1e-3, 'span=%s' % (span,))

    span = face_span(run(bxr=1, bx=0.0, exr=2, ex=0.0))
    check('Stock OD to Stock ID faces D60 down to the bore D20',
          span is not None and abs(span[0] - 30.0) < 1e-3 and abs(span[1] - 10.0) < 1e-3,
          'span=%s' % (span,))

    span = face_span(run(bxr=1, bx=1.0, exr=2, ex=-4.0))
    check('offsets apply to both ends: OD+1 to ID-4 is D61 to D16',
          span is not None and abs(span[0] - 30.5) < 1e-3 and abs(span[1] - 8.0) < 1e-3,
          'span=%s' % (span,))

    # 3 - Direction swaps the two resolved ends, nothing else
    out_in = face_span(run(bxr=0, bx=62.0, exr=0, ex=20.0, direction=0))
    in_out = face_span(run(bxr=0, bx=62.0, exr=0, ex=20.0, direction=1))
    check('Outside to inside runs D62 -> D20',
          out_in is not None and out_in[0] > out_in[1], 'span=%s' % (out_in,))
    check('Inside to outside runs the same two ends reversed',
          in_out is not None and abs(in_out[0] - out_in[1]) < 1e-3
          and abs(in_out[1] - out_in[0]) < 1e-3, 'span=%s' % (in_out,))

    # 4 - Axial stock to leave is material left ON the face when the operation
    # finishes, so it is the DEEPEST cutting Z that has to move - not just where
    # roughing stops. Checking only the roughing floor is what let this ship
    # doing nothing at all for the common no-roughing-passes case.
    def face_reached(sl, np_=1):
        mv = run(bxr=0, bx=62.0, exr=0, ex=0.0, zd=2.0, fin=1, np_=np_, sl=sl)
        zs = [z for k, z, _r in mv if k in ('feed', 'arc')]
        return min(zs)          # deepest cutting Z = the face actually produced

    check('with no allowance the face is cut to the defined Z',
          abs(face_reached(0.0)) < 1e-3, 'face at Z%.4f' % face_reached(0.0))
    for sl in (0.5, 1.0):
        z = face_reached(sl)
        check('axial stock to leave %.1f leaves the face that far proud' % sl,
              abs(z - sl) < 1e-3, 'face left at Z%.4f, wanted Z%.4f' % (z, sl))

    # the case actually reported: no roughing passes at all. The allowance used
    # to be applied only to the roughing span, so with none it did nothing.
    for sl in (0.0, 0.5):
        z = face_reached(sl, np_=0)
        check('stock to leave %.1f applies with no roughing passes too' % sl,
              abs(z - sl) < 1e-3, 'face left at Z%.4f, wanted Z%.4f' % (z, sl))

    # roughing still stops short of the finish target by the tool change's
    # finish cut depth, on top of whatever is being left on the face
    mv = run(bxr=0, bx=62.0, exr=0, ex=0.0, zd=2.0, fin=1, np_=1, sl=0.5)
    zs = sorted(z for k, z, _r in mv if k in ('feed', 'arc'))
    check('roughing still leaves the finish cut depth above the finish target',
          abs(zs[-1] - (0.5 + 0.25)) < 1e-3, 'roughing stopped at Z%.4f' % zs[-1])

    # 5 - Face Z: an offset from the stock face, or an absolute coordinate
    for fz in (1.5, -2.0):
        z = min(z for k, z, _r in run(fzr=0, fz=fz) if k in ('feed', 'arc'))
        check('face Z offset %+.1f from the stock face lands at Z%+.1f' % (fz, fz),
              abs(z - fz) < 1e-3, 'face at Z%.4f' % z)
    for fz in (3.0, -1.0):
        z = min(z for k, z, _r in run(fzr=1, fz=fz) if k in ('feed', 'arc'))
        check('absolute face Z %+.1f lands at Z%+.1f' % (fz, fz),
              abs(z - fz) < 1e-3, 'face at Z%.4f' % z)

    # the two stack: the face is offset, then the allowance sits above it
    z = min(z for k, z, _r in run(fzr=1, fz=2.0, sl=0.5) if k in ('feed', 'arc'))
    check('face Z and stock to leave combine', abs(z - 2.5) < 1e-3, 'face at Z%.4f' % z)

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('All facing tests passed.')


if __name__ == '__main__':
    main()
