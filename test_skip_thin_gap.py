#!/usr/bin/env python3
# coding: utf-8
"""Skipping a thin pass may never open a gap larger than the depth of cut.

Standalone, like the other test_*.py here - run it directly, no pytest.

THE BUG THIS EXISTS FOR

`_pl_prev_lvl` does not advance when a level is skipped, so the NEXT level is
two steps from the last one actually cut. With a threshold above the ladder
step that alternates - thin, skip, keep, thin, skip, keep - and every kept level
lands two steps below its predecessor.

Measured on testing_15_2, doc 0.5080, before the fix:

    threshold 0.0000   18 levels, worst gap 0.4992
    threshold 0.2540   18 levels, worst gap 0.4992
    threshold 0.5070   13 levels, worst gap 0.9983   <-- past the doc
    threshold 0.6000   13 levels, worst gap 0.9983
    threshold 0.9000   13 levels, worst gap 0.9983

**A gap past the depth of cut against a part surface is the failure
`test_x_continuity` exists to prevent**, so this is not a tuning nicety.

CLAMPING THE SETTING CANNOT FIX IT. `cfg/lathe/polyline.cfg` has
`minimum_value = 0.0` and no maximum, but the number that matters is the
LADDER STEP, which is worked out at runtime and can be under the depth of cut -
0.4991 here, after the phase-2 spread made the ladder uniform. That is why
0.5070, a threshold BELOW the 0.5080 doc, already halves the ladder: no value
typed into the cfg is safe on every part. The skip itself has to refuse,
because it is the only place that knows both the step and what was last cut.

WHAT IS ASSERTED

1. No threshold opens a gap past the depth of cut - swept from 0 to well above
   the step.
2. The level count does not collapse, which is the same fault seen from the
   other side.
3. The sweep REACHES the dangerous region. A sweep that stopped below the step
   would pass on a broken build, so the thresholds used are pinned to values
   that provably failed before: 0.5070, 0.6000 and 0.9000 all gave 13 levels
   and a 0.9983 gap.
"""
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

INI = os.path.join(HERE, 'configs/sim/axis/ncam_demo/lathe-mm.ini')
GEN = os.path.join(HERE, '.claude/skills/lathe-gcode-verify/scripts/gen_project.py')
DOC = 0.5080
# thresholds that provably broke it before the fix - see the docstring
THRESHOLDS = (0.0, 0.2540, 0.5070, 0.6000, 0.9000)
FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name
          + (('  ' + detail) if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def ladder(project, thin, d):
    import ncam_preview as P
    out = os.path.join(d, '%s_%s.ngc' % (project[:-4], thin))
    cmd = [sys.executable, GEN, '--ini', INI, '--project', project,
           '--out', out, '--config-copy']
    if thin > 0:
        cmd += ['--set', 'polyline:param_skip_thin=%s' % thin]
    subprocess.run(cmd, capture_output=True, text=True)
    if not os.path.isfile(out):
        return None
    tp = P.parse_program(out, INI)
    if tp.error:                       # includes a run that stopped part way
        return None
    lv = [m for m in tp.moves
          if m.op == 'Lathe Polyline' and not m.subs and m.kind == 'feed'
          and abs(m.b[0] - m.a[0]) < 1e-6 and abs(m.b[2] - m.a[2]) > 1e-9]
    rs = sorted({round(m.a[0], 4) for m in lv}, reverse=True)
    gaps = [a - b for a, b in zip(rs, rs[1:])]
    return len(rs), (max(gaps) if gaps else 0.0)


def main():
    if not (os.path.isfile(INI) and os.path.isfile(GEN)):
        print('SKIP  demo config or generator not present')
        return
    if not shutil.which('rs274'):
        print('SKIP  rs274 is not installed')
        return

    d = tempfile.mkdtemp(prefix='thingap_')
    try:
        base = None
        for thin in THRESHOLDS:
            r = ladder('testing_15_2.xml', thin, d)
            check('threshold %.4f generates and runs' % thin, r is not None)
            if r is None:
                continue
            n, gap = r
            print('      thin %.4f  %2d levels, worst gap %.4f' % (thin, n, gap))
            if base is None:
                base = n
            # 1. NO GAP PAST THE DEPTH OF CUT
            check('   %.4f opens no gap past the depth of cut' % thin,
                  gap <= DOC + 1e-3,
                  'worst gap %.4f against a %.4f doc - a skip left the next '
                  'level two steps from the last one cut' % (gap, DOC))
            # 2. AND THE LADDER DOES NOT COLLAPSE
            check('   %.4f keeps the ladder' % thin, n >= base,
                  '%d levels against %d with no skipping' % (n, base))
    finally:
        shutil.rmtree(d, ignore_errors=True)

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('A skipped thin pass never opens a gap past the depth of cut.')


if __name__ == '__main__':
    main()
