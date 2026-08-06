#!/usr/bin/env python3
# coding: utf-8
"""The roughing ladder honours "Space passes from", with Sectioning on.

Standalone, like the other test_*.py here - run it directly, no pytest.

Two anchorings, two different promises, and Sectioning used to break one of
them:

- FINAL CONTOUR takes whole depths of cut measured from the floor outward, so
  the last level lands exactly on the floor and the odd remainder falls on the
  first pass at the stock - through oversize material, where it is harmless.
- STOCK spaces the levels evenly, every step the same and slightly under the
  depth of cut.

With Sectioning on, one ladder was computed for the whole part and then reused
by phase 2, which restarts at the section ceiling with a full step already
spent. It could no longer land on the floor: 17 gaps of 0.5080 and then
**0.2374** - a level sitting just clear of the finished surface and grazing it
for a sliver, which is the exact thing Final contour exists to prevent.

greatEndian: *"there have to be two different ladders.. one from stock and
second for Final Contour"*. Phase 1 sweeps stock -> section ceiling and is
spaced evenly; phase 2 goes ceiling -> floor and is anchored on the part.

A LADDER PER WINDOW WAS TRIED AND IS WRONG - the seven section windows start at
different radii, so their levels miss each other by 0.006 mm. That is why this
asserts on the SET of distinct level radii: two ladders that fail to line up
show up here as extra levels and gaps that are neither a whole step nor the
single remainder.
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
PROJECT = 'testing_15_2.xml'
DOC = 0.508                      # roughing depth of cut, mm
FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name
          + (('  ' + detail) if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def levels(path, P):
    tp = P.parse_program(path, INI)
    if tp.error:
        return None
    mv = [m for m in tp.moves if m.op == 'Lathe Polyline' and not m.subs
          and m.kind == 'feed']
    lv = sorted({round(m.a[0], 4) for m in mv
                 if abs(m.b[0] - m.a[0]) < 1e-6 and m.b[2] < m.a[2] - 1e-6},
                reverse=True)
    return lv


def main():
    if not (os.path.isfile(INI) and os.path.isfile(GEN)):
        print('SKIP  demo config or generator not present')
        return
    if not shutil.which('rs274'):
        print('SKIP  rs274 is not installed')
        return
    import ncam_preview as P

    d = tempfile.mkdtemp(prefix='ladder_')
    try:
        lv = {}
        for v, label in ((1, 'Final contour'), (0, 'Stock')):
            out = os.path.join(d, 'p%d.ngc' % v)
            subprocess.run([sys.executable, GEN, '--ini', INI, '--project',
                            PROJECT, '--out', out, '--config-copy',
                            '--set', 'polyline:param_n_comp=1',
                            '--set', 'polyline:param_pass_from=%d' % v],
                           capture_output=True, text=True)
            lv[label] = levels(out, P) if os.path.isfile(out) else None
        check('both anchorings generate and run', all(lv.values()),
              str({k: v is None for k, v in lv.items()}))
        if not all(lv.values()):
            return

        for label, ladder in lv.items():
            gaps = [round(ladder[i] - ladder[i + 1], 4)
                    for i in range(len(ladder) - 1)]
            print('   %-14s %2d levels, deepest %.4f, gaps %s'
                  % (label, len(ladder), ladder[-1],
                     ' '.join('%.4f' % g for g in gaps)))

            if label == 'Final contour':
                # every gap a whole depth of cut except ONE - the remainder -
                # and that one must not be at the contour end
                odd = [(i, g) for i, g in enumerate(gaps)
                       if abs(g - DOC) > 1e-3]
                check('Final contour: at most one gap is not a whole step',
                      len(odd) <= 1,
                      '%d odd gaps: %s' % (len(odd),
                                           ', '.join('%.4f' % g for _i, g in odd)))
                check('   and the remainder is NOT the last gap', 
                      not odd or odd[0][0] < len(gaps) - 1,
                      'the odd %.4f gap is at the contour end - a level '
                      'grazing the finished surface, which is what this '
                      'anchoring exists to prevent'
                      % (odd[0][1] if odd else 0.0))
            else:
                spread = max(gaps) - min(gaps)
                check('Stock: every gap is the same', spread < 1e-3,
                      'gaps range over %.4f mm' % spread)
                check('   and each is at most the depth of cut',
                      max(gaps) <= DOC + 1e-3,
                      'largest gap %.4f exceeds the %.4f depth of cut'
                      % (max(gaps), DOC))

        # the two anchorings must actually differ, or one of them is not
        # being applied at all
        check('the two anchorings produce different ladders',
              lv['Final contour'] != lv['Stock'],
              'identical - the pass_from setting is doing nothing')

        # --- Skip thin roughing passes -------------------------------------
        # greatEndian: the thin pass at the stock envelope "cuts nothing and
        # created chattering". A level that removes less than the threshold is
        # dropped - at the envelope and anywhere else one appears - but the
        # level ON THE FLOOR never is, because that is the surface roughing
        # has to leave for the pre-finish pass.
        #
        # The guard for that was first written against lvl_floor, which with
        # Sectioning on is the section CEILING - exactly where the envelope
        # pass lands - so it protected the one level the setting exists to
        # remove and nothing was skipped at all. It is step_target now.
        thin = os.path.join(d, 'thin.ngc')
        subprocess.run([sys.executable, GEN, '--ini', INI, '--project',
                        PROJECT, '--out', thin, '--config-copy',
                        '--set', 'polyline:param_n_comp=1',
                        '--set', 'polyline:param_pass_from=1',
                        '--set', 'polyline:param_skip_thin=%g' % (DOC / 2.0)],
                       capture_output=True, text=True)
        tl = levels(thin, P) if os.path.isfile(thin) else None
        check('the project generates with a thin-pass threshold', bool(tl))
        if not tl:
            return
        base = lv['Final contour']
        tgaps = [round(tl[i] - tl[i + 1], 4) for i in range(len(tl) - 1)]
        print('   %-14s %2d levels, deepest %.4f, gaps %s'
              % ('skip thin', len(tl), tl[-1],
                 ' '.join('%.4f' % g for g in tgaps)))
        check('a threshold drops at least one level', len(tl) < len(base),
              '%d levels with the threshold against %d without - nothing was '
              'skipped' % (len(tl), len(base)))
        check('   and every remaining gap is a whole depth of cut',
              all(abs(g - DOC) < 1e-3 for g in tgaps),
              'gaps %s' % ' '.join('%.4f' % g for g in tgaps))
        check('   while the floor itself is never skipped',
              abs(tl[-1] - base[-1]) < 1e-6,
              'the deepest level moved from %.4f to %.4f - roughing is no '
              'longer leaving the pre-finish its stock' % (base[-1], tl[-1]))
    finally:
        shutil.rmtree(d, ignore_errors=True)

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('Both ladders anchor where their setting says they should.')


if __name__ == '__main__':
    main()
