#!/usr/bin/env python3
# coding: utf-8
"""Python answers the blocked question the same way the O-code does.

Standalone, like the other test_*.py here - run it directly, no pytest.

WHAT IS ASSERTED

For every lathe_level_pass call the sweep makes, `lathe_sections.level_blocked`
returns exactly what the subroutine put in #<_level_blocked>. Same projects,
sectioning states and directions as the ladder gates.

Nothing in the toolpath reads level_blocked. This is the same order the ladder
went in - replica, parallel run, and only then a migration - because replacing
a working decision with a plausible one is how the anisotropic stock to leave
cost four rounds.

WHY IT IS A TABLE WALK AND NOT A GEOMETRY SOLVE

lathe_level_pass has two scans. The one that offsets every segment of the
record array perpendicular by a single allowance, with a corner connector for
the gaps that leaves; and a plain walk of the FLOOR CONTOUR Python already
emits, which is the same contour blended by each surface's own normal with its
corners joined. When that table is present - _pl_flc_n GT 1 - the O-code takes
it and skips the other scan outright. So the decision Python has to reproduce
is a walk of a table Python itself built.

The record-array scan is NOT replicated. `level_blocked` returns None there and
this test counts those calls rather than passing over them - see the summary
line.

THE INSTRUMENT

lib/ in the repo is never touched: the tree is copied to a temp dir, three
`(debug, BLKREC ...)` lines are inserted at the subroutine's own two blocked
returns and at the point it commits to cutting, and the scratch config's
ncam/lib symlink is repointed at the copy. Inertness is proved, not claimed.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import lathe_sections as ls          # noqa: E402
import ncam_preview as P             # noqa: E402

CFG = os.path.join(HERE, 'configs/sim/axis/ncam_demo')
INI = os.path.join(CFG, 'lathe-mm.ini')
GEN = os.path.join(HERE, '.claude/skills/lathe-gcode-verify/scripts/gen_project.py')
PROJECTS = ('testing_15_2.xml', 'testing_15_4.xml', 'testing_15_5.xml',
            'testing_15_6.xml', 'testing_15_9.xml')

SUB = 'lathe/lathe_level_pass.ngc'
BLK1 = '\t\to<mc_decide> if [#<mc_wf_state> GT 0]\n'
BLK2 = '\to<blk> if [[#<found>] AND [[#<z_dir> * [#<zc> - #<w_from>]] GE -0.0001]]\n'
END = '\to<blk> endif\n'
R1 = ('\t\t\t(debug, BLKREC lvl=#<level> wf=#<w_from> wt=#<w_to> blk=1)\n')
R2 = ('\t\t(debug, BLKREC lvl=#<level> wf=#<w_from> wt=#<w_to> blk=1)\n')
R3 = ('\t(debug, BLKREC lvl=#<level> wf=#<w_from> wt=#<w_to> blk=0)\n')
RE_REC = re.compile(r'BLKREC lvl=(-?[\d.]+) wf=(-?[\d.]+) wt=(-?[\d.]+) '
                    r'blk=(\d)')

FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name
          + (('  ' + detail) if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def build_config(instrument):
    root = tempfile.mkdtemp(prefix='level_blocked_')
    cfg = os.path.join(root, 'ncam_demo')
    shutil.copytree(CFG, cfg, symlinks=True)
    lib = os.path.join(root, 'lib')
    shutil.copytree(os.path.join(HERE, 'lib'), lib)
    if instrument:
        src = os.path.join(lib, SUB)
        text = open(src).read()
        for anchor, rec, after in ((BLK1, R1, True), (BLK2, R2, True),
                                   (END, R3, True)):
            if text.count(anchor) != 1:
                raise RuntimeError('anchor matched %d times, the instrument '
                                   'needs re-aiming: %r'
                                   % (text.count(anchor), anchor))
            text = text.replace(anchor, anchor + rec if after else rec + anchor)
        open(src, 'w').write(text)
    os.remove(os.path.join(cfg, 'ncam/lib'))
    os.symlink(lib, os.path.join(cfg, 'ncam/lib'))
    return os.path.join(cfg, 'lathe-mm.ini')


_canon = {}
_orig_dump = P._canon_dump


def _dump(path, ini_path, tmpdir):
    key = (path, ini_path)
    if key not in _canon:
        _canon[key] = _orig_dump(path, ini_path, tmpdir)
    return _canon[key]


P._canon_dump = _dump


def num(src, pat, default=None):
    m = re.findall(pat, src)
    return float(m[-1]) if m else default


def floor_contour(src):
    """The #<_pl_flc_*> table as (z, x) pairs, or None."""
    # THE DEFAULTS BLOCK ASSIGNS EVERY GLOBAL FIRST, _pl_flc_base = 0 among
    # them, so a plain count of assignments is always at least two and the
    # FIRST value read is the placeholder rather than the table. Counting the
    # real ones is what says whether a second polyline rewrote the table.
    real = [int(v) for v
            in re.findall(r'#<_pl_flc_base>\s*=\s*(\d+)', src) if int(v) > 0]
    n = num(src, r'#<_pl_flc_n>\s*=\s*(\d+)')
    if len(real) != 1 or not n:
        return None
    base, n = real[0], int(n)
    vals = {int(m.group(1)): float(m.group(2))
            for m in re.finditer(r'^#(\d+) = ([-\d.]+)$', src, re.M)}
    pts = []
    for i in range(n):
        if base + 2 * i + 1 not in vals:
            return None
        pts.append((vals[base + 2 * i], vals[base + 2 * i + 1]))
    return pts


def generate(project, sect, direction, work):
    out = os.path.join(work, '%s_%d_%d.ngc' % (project[:-4], sect, direction))
    subprocess.run([sys.executable, GEN, '--ini', INI, '--project', project,
                    '--out', out, '--config-copy',
                    '--set', 'polyline:param_sectioning=%d' % sect,
                    '--set', 'polyline:param_dir=%d' % direction],
                   capture_output=True, text=True)
    return out if os.path.isfile(out) else None


def main():
    if not (os.path.isfile(INI) and os.path.isfile(GEN)):
        print('SKIP - the demo lathe config is not present')
        return 0
    ini = build_config(True)
    work = tempfile.mkdtemp(prefix='level_blocked_ngc_')

    # VALIDATE THE INSTRUMENT BEFORE TRUSTING IT
    probe = generate('testing_15_5.xml', 0, 0, work)
    if probe is not None:
        clean = build_config(False)
        a, b = P.parse_program(probe, clean), P.parse_program(probe, ini)
        check('the instrument changes no motion',
              (not a.error) and (not b.error) and a.flat == b.flat,
              '%s / %s' % (a.error, b.error))
        check('the instrument actually recorded something',
              bool(RE_REC.search(_canon[(probe, ini)][0])))

    ran = calls = agree = uncovered = 0
    blocked = ctrl_diff = mc_calls = 0
    for project in PROJECTS:
        for sect in (0, 1):
            for direction in (0, 1, 2):
                tag = '%s sect=%d dir=%d' % (project[:-4], sect, direction)
                ngc = generate(project, sect, direction, work)
                if ngc is None:
                    continue
                tp = P.parse_program(ngc, ini)
                if tp.error:
                    continue
                src = open(ngc).read()
                flc = floor_contour(src)
                mc = (num(src, r'#<_pl_multi_cross>\s*=\s*([-\d.]+)', 0.0)
                      or 0) > 0
                mm = num(src, r'#<_mm>\s*=\s*([-\d.]+)', 1.0)
                recs = [(float(a_), float(b_), float(c_), int(d_))
                        for a_, b_, c_, d_
                        in RE_REC.findall(_canon[(ngc, ini)][0])]
                if not recs:
                    continue
                ran += 1
                wrong, cov = [], 0
                for lvl, wf, wt, blk in recs:
                    calls += 1
                    blocked += blk
                    mine = ls.level_blocked(flc or (), lvl, wf, wt, mc, mm)
                    if mine is None:
                        uncovered += 1
                        continue
                    cov += 1
                    if mc:
                        mc_calls += 1
                    # NEGATIVE CONTROL. The same call with the window read
                    # back to front - which reverses z_dir and moves the
                    # start to the other end - must not keep answering the
                    # same thing, or the comparison has no teeth and a
                    # function that ignored its arguments would pass.
                    if bool(ls.level_blocked(flc, lvl, wt, wf, mc, mm)) != \
                            bool(blk):
                        ctrl_diff += 1
                    if bool(mine) == bool(blk):
                        agree += 1
                    else:
                        wrong.append((lvl, wf, wt, blk, mine))
                # a config whose calls all fell through to the un-replicated
                # scan would otherwise pass this vacuously - the first run of
                # this test did exactly that, 30 green configs over 0 answers
                check('%s: Python answers blocked as the O-code does' % tag,
                      (not wrong) and cov == len(recs),
                      '%d of %d disagree %s, %d of %d covered'
                      % (len(wrong), len(recs), wrong[:1], cov, len(recs)))

    check('the sweep actually ran', ran >= 25, '%d configurations' % ran)
    # an all-clear over calls that never block would prove nothing
    check('the blocked branch is exercised at all', blocked > 0,
          '%d blocked of %d calls' % (blocked, calls))
    check('every call is covered by the replica', uncovered == 0,
          '%d calls fell to the record-array scan' % uncovered)
    check('the reversed-window control disagrees', ctrl_diff > 0.05 * calls,
          'only %d of %d calls answer differently reversed'
          % (ctrl_diff, calls))
    check('the multi-crossing branch is exercised', mc_calls > 0,
          'every call took the single-crossing branch')
    print('\n%d configurations, %d calls, %d agree, %d blocked, %d uncovered'
          % (ran, calls, agree, blocked, uncovered))
    print('%d calls on the multi-crossing branch, control disagrees on %d'
          % (mc_calls, ctrl_diff))
    if FAILED:
        print('\nFAILED: %d\n   -  %s' % (len(FAILED), '\n   -  '.join(FAILED)))
        return 1
    print('\nPython answers the blocked question the same way the O-code does.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
