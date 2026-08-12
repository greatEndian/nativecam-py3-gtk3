#!/usr/bin/env python3
# coding: utf-8
"""Slicing a cut into sections changes HOW it is cut, never HOW MUCH.

Standalone, like the other test_*.py here - run it directly, no pytest.

`Z section length` caps how long a single continuous cut may be, for chatter and
rigidity. `build_sections_gcode` is explicit that its pieces "deliberately apply
over the whole radius range", because a cap on cut length only means anything if
it applies at every depth - so MORE PASSES IS THE FEATURE WORKING, not a fault,
and this file deliberately does not assert against it.

What must not change is the metal. The same part with the same allowances has
exactly one correct volume to remove, and the order and length of the cuts that
remove it is a strategy choice. greatEndian, 2026-08-12: with a Z section length
set, roughing "roughs all part long also behind the boss segment".

Measured on testing_15_5 when this was written:

    sec_len  0.0     49 level cuts   1052.6 mm of cut
    sec_len 10.0    202 level cuts   1296.2 mm of cut     <- 23.1% more cutting
    sec_len 20.0    135 level cuts   1263.9 mm of cut     <- 20.1% more

The pass count going 49 -> 202 is right. The 1052.6 -> 1296.2 is not. Note the
excess barely falls when the slicing is halved - 20.1% at sec_len 20 against
23.1% at 10 - so it is not per-piece overhead that more pieces would explain.
Something systematic makes a sliced program cut a fifth further. THIS TEST IS EXPECTED TO FAIL until that is
fixed - it is the acceptance criterion for the fix, written first and on
purpose, so the fix is measured against a number rather than against an opinion.

WHAT THIS MEASURES, EXACTLY - and it is not what the first write-up claimed.
It sums the LENGTH of the level cuts, which is not the same as the metal
removed: in mode 1 every Z slice runs the full ladder, so a pass may traverse a
radius where its own slice has nothing left to take. Length without volume is
still a fault - it is time, and it is the "roughs all part long" that was
reported - but it must not be described as extra metal, and the fix is a
different one depending on which it is. Deciding that needs a volume measure
(the preview's StockField already simulates removal), and until then this file
asserts the number it actually measures.

WHY THE INVARIANT AND NOT THE SYMPTOM. "Does it cut behind the boss" needs a
boss, a direction and a judgement about what "behind" means. "Does it remove the
same metal" needs none of those, holds on every project and every section
length, and would have caught this the day sectioning was built.
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
PROJECT = 'testing_15_5.xml'
FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name
          + (('  ' + detail) if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def run(sec_len):
    """-> (level cut count, total length of cutting moves) or None."""
    import ncam_preview as P
    d = tempfile.mkdtemp(prefix='seclen_')
    try:
        out = os.path.join(d, 'o.ngc')
        cmd = [sys.executable, GEN, '--ini', INI, '--project', PROJECT,
               '--out', out, '--config-copy',
               '--set', 'polyline:param_sectioning=1',
               '--set', 'polyline:param_sec_len=%s' % sec_len]
        subprocess.run(cmd, capture_output=True, text=True)
        if not os.path.isfile(out):
            return None
        tp = P.parse_program(out, INI)
        if tp.error:
            return None
        mv = [m for m in tp.moves if m.op == 'Lathe Polyline'
              and m.kind != 'rapid']
        # a LEVEL cut: a feed at one radius along Z. The lead-ins, ramps and
        # retreats are strategy too and are deliberately left out - what is
        # being compared is the metal the level passes take off.
        lv = [m for m in mv if abs(m.b[0] - m.a[0]) < 1e-6
              and abs(m.b[2] - m.a[2]) > 1e-6]
        return len(lv), sum(abs(m.b[2] - m.a[2]) for m in lv)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main():
    if not (os.path.isfile(INI) and os.path.isfile(GEN)):
        print('SKIP  demo config or generator not present')
        return
    if not shutil.which('rs274'):
        print('SKIP  rs274 is not installed')
        return

    base = run('0.0')
    check('the project generates with sectioning and no section length',
          base is not None)
    if base is None:
        sys.exit(1)
    n0, cut0 = base
    print('      sec_len  0.0   %3d level cuts   %8.1f mm of cut' % (n0, cut0))

    for sec_len in ('10.0', '20.0'):
        r = run(sec_len)
        check('the project generates at a section length of %s' % sec_len,
              r is not None)
        if r is None:
            continue
        n, cut = r
        print('      sec_len %-5s  %3d level cuts   %8.1f mm of cut'
              % (sec_len, n, cut))

        # THE INVARIANT. 2% covers the ends of the extra pieces - a sliced cut
        # has more lead-ins and each starts a hair earlier - without covering
        # anything that could be called a different amount of material.
        drift = abs(cut - cut0) / cut0 if cut0 else 0.0
        check('   sec_len %s does the SAME LENGTH of cutting as no '
              'sectioning' % sec_len, drift < 0.02,
              '%.1f mm against %.1f, %.1f%% more - slicing a cut changes how '
              'it is cut, not how far the tool has to travel cutting'
              % (cut, cut0, 100.0 * drift))

        # and the feature IS doing its job - asserted so a "fix" that simply
        # stops sectioning cannot pass this file
        check('   and it still slices the cut into more, shorter passes',
              n > n0,
              '%d passes against %d - the section length is not slicing at '
              'all' % (n, n0))

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('A section length changes how the cut is made, not how far it cuts.')


if __name__ == '__main__':
    main()
