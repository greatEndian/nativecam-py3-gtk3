#!/usr/bin/env python3
# coding: utf-8
"""Python predicts the roughing ladder the O-code walks.

Standalone, like the other test_*.py here - run it directly, no pytest.

WHY THIS EXISTS BEFORE ANY .ngc CHANGES

`openPoints` wants the ladder moved into Python: once the levels are known at
generation time, the stop scan's decisions become movable too, `skip_thin`
stops being blind at window boundaries, and the coverage sweep gets something
trustworthy to measure against. Three open points collapse into it.

But replacing a working ladder with a plausible one is exactly how the
anisotropic stock to leave cost four rounds. So `roughing_ladder` is written
first and PROVED against the running O-code, and nothing in the toolpath reads
it yet. This file is that proof.

WHAT IS ASSERTED

Every level the program ACTUALLY CUTS lies on the ladder Python predicts, to
within 0.002 mm, across 5 projects x 2 sectioning states x 3 directions.

The ladder is a SUPERSET and that is expected: the runtime still decides what
each level DOES - skipped as thin, refused as blocked, outside a window's
radius band - and none of those change the level SET. So this proves the
arithmetic, not the skipping.

WHAT IT ALREADY CAUGHT

On its first run, 15 of the 30 configurations had exactly one level off the
ladder, always r20.516 - the first level of the SECOND floor stage on
testing_15_4, _15_5 and _15_6. The replica walked to the first floor stage and
stopped, where poly_lathe_mill re-anchors on each stage in turn: FUP of the
remaining distance over the depth of cut, then an even step to that stage.
Reading the O-code had not shown me that; running the two side by side did.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import lathe_sections as ls  # noqa: E402

INI = os.path.join(HERE, 'configs/sim/axis/ncam_demo/lathe-mm.ini')
GEN = os.path.join(HERE, '.claude/skills/lathe-gcode-verify/scripts/gen_project.py')
PROJECTS = ('testing_15_2.xml', 'testing_15_4.xml', 'testing_15_5.xml',
            'testing_15_6.xml', 'testing_15_9.xml')
FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name
          + (('  ' + detail) if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def num(src, pat, default=None):
    m = re.findall(pat, src)
    return float(m[-1]) if m else default


def compare(project, sect, direction, d, P):
    out = os.path.join(d, '%s_%d_%d.ngc' % (project[:-4], sect, direction))
    subprocess.run([sys.executable, GEN, '--ini', INI, '--project', project,
                    '--out', out, '--config-copy',
                    '--set', 'polyline:param_sectioning=%d' % sect,
                    '--set', 'polyline:param_dir=%d' % direction],
                   capture_output=True, text=True)
    if not os.path.isfile(out):
        return None
    tp = P.parse_program(out, INI)
    if tp.error:                      # includes a run that stopped part way
        return None
    src = open(out).read()
    dm = num(src, r'#<_diameter_mode>\s*=\s*([\d.]+)', 2.0)
    # the radii arrive as globals, already resolved by x_limit_abs and
    # rough_radius_bounds, and are RADII rather than diameters
    sr = num(src, r'#<_pl_rgh_hi_r>\s*=\s*([-\d.]+)')
    fr = num(src, r'#<_pl_rgh_lo_r>\s*=\s*([-\d.]+)')
    doc = num(src, r'#<_rough_cut>\s*=\s*([-\d.]+)')
    if sr is None or fr is None or not doc:
        return None
    fn = int(num(src, r'#<_pl_floor_n>\s*=\s*([\d.]+)', 0.0) or 0)
    vals = {int(m.group(1)): float(m.group(2))
            for m in re.finditer(r'^#(\d+) = ([-\d.]+)$', src, re.M)}
    floors = [vals[3380 + i] for i in range(fn) if 3380 + i in vals]
    cnt = int(num(src, r'#<_pl_sect_count>\s*=\s*([\d.]+)', 0.0) or 0)
    topd = num(src, r'#<_pl_sect_top_dia>\s*=\s*([-\d.]+)')
    lad = ls.roughing_ladder(
        sr, fr,
        num(src, r'#3144\s*=\s*([-\d.]+)', 0.0),
        num(src, r'#3156\s*=\s*\[?([-\d.]+)', 0.0),
        doc,
        (num(src, r'#<_pl_pass_from>\s*=\s*([-\d.]+)', 0.0) or 0) > 0,
        floors,
        (num(src, r'#<_pl_sectioning>\s*=\s*([-\d.]+)', 0.0) or 0) > 0 and cnt > 0,
        (topd / dm) if topd is not None else None,
        int(num(src, r'#<_pl_sect_mode>\s*=\s*([\d.]+)', 0.0) or 0),
        max(cnt, 1))
    pred = set()
    for _w, rs in lad:
        pred.update(rs)
    lv = [m for m in tp.moves
          if m.op == 'Lathe Polyline' and not m.subs and m.kind == 'feed'
          and abs(m.b[0] - m.a[0]) < 1e-6 and abs(m.b[2] - m.a[2]) > 1e-9]
    meas = {round(m.a[0], 4) for m in lv}
    off = sorted(x for x in meas
                 if not any(abs(x - p) < 0.002 for p in pred))
    return len(meas), len(pred), off


def main():
    if not (os.path.isfile(INI) and os.path.isfile(GEN)):
        print('SKIP  demo config or generator not present')
        return
    if not shutil.which('rs274'):
        print('SKIP  rs274 is not installed')
        return
    import ncam_preview as P

    d = tempfile.mkdtemp(prefix='ladpy_')
    ran = 0
    try:
        for project in PROJECTS:
            for sect in (0, 1):
                for direction in (0, 1, 2):
                    r = compare(project, sect, direction, d, P)
                    tag = '%s sect=%d dir=%d' % (project[:-4], sect, direction)
                    check('%s generates and runs' % tag, r is not None)
                    if r is None:
                        continue
                    n_cut, n_pred, off = r
                    ran += 1
                    check('   %s: every cut level is on the Python ladder'
                          % tag, not off,
                          '%d of %d cut levels are not: %s'
                          % (len(off), n_cut,
                             ' '.join('%.4f' % x for x in off[:5])))
        # a sweep that ran nothing proves nothing
        check('the sweep actually ran', ran >= 25, '%d configurations' % ran)
    finally:
        shutil.rmtree(d, ignore_errors=True)

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('Python predicts every level the O-code cuts.')


if __name__ == '__main__':
    main()
