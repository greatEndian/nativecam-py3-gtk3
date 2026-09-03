#!/usr/bin/env python3
# coding: utf-8
"""Python predicts how a roughing level is broken into sub-spans.

Standalone, like the other test_*.py here - run it directly, no pytest.

THE LAYER ABOVE THE INTERVAL WALK. `test_level_intervals` proves that once a
sub-span's start is known, every interval inside it is predicted. This proves
where those sub-spans are.

Walked back to front, a level a peak certainly blocks must not be swept as one
span from the window start - it would lead in through the peak. poly_lathe_mill
breaks the sweep at every split point the level sits below, taking them from
the back out of the #3160 table Python emits, until a sub-span reaches the
window's own front.

WHAT IS ASSERTED

For every level of every window, the whole ordered decomposition - each
sub-span's start and end, and how many there are - matches what the O-code
walked. `sg_use`, the decision to read the table at all, is predicted too and
checked against the recorded value rather than taken from it.

WHAT COMES OUT OF THE RECORD, AND WHY

`w_idx`, `w_from` and `w_to` - the window itself. That is the NEXT layer up
(poly_lathe_mill's o<wh_w> loop) and is deliberately not replicated here; the
sub-span walk is judged given its window, exactly as the interval walk was
judged given its sub-span.

Nothing in the toolpath reads sub_spans.

THE INSTRUMENT

lib/ in the repo is never touched. Two files are instrumented in a temp copy:
poly_lathe_mill emits one header per level, and lathe_level_pass emits one
record per interval - the observed sub-spans are the runs of those records.
Inertness is proved, not claimed.
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
            'testing_15_6.xml', 'testing_15_9.xml',
            'testing_15_blocked.xml')

ANCHORS = {
    'lathe/poly_lathe_mill.ngc': (
        ('                                o<wh_seg> while [1]\n',
         '                                (debug, SGREC w=#<w_idx> '
         'lvl=#<current_radius> wf=#<w_from> wt=#<w_to> zd=#<z_dirw> '
         'use=#<sg_use>)\n', False),
    ),
    'lathe/lathe_level_pass.ngc': (
        ('\t\to<mc_decide> if [#<mc_wf_state> GT 0]\n',
         '\t\t\t(debug, IVREC wf=#<w_from> wt=#<w_to>)\n', True),
        ('\to<blk> if [[#<found>] AND [[#<z_dir> * [#<zc> - #<w_from>]] GE -0.0001]]\n',
         '\t\t(debug, IVREC wf=#<w_from> wt=#<w_to>)\n', True),
        ('\to<blk> endif\n',
         '\t(debug, IVREC wf=#<w_from> wt=#<w_to>)\n', True),
    ),
}
RE_ANY = re.compile(
    r'(?:SGREC w=(-?[\d.]+) lvl=(-?[\d.]+) wf=(-?[\d.]+) wt=(-?[\d.]+) '
    r'zd=(-?[\d.]+) use=(-?[\d.]+))'
    r'|(?:IVREC wf=(-?[\d.]+) wt=(-?[\d.]+))')

FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name
          + (('  ' + detail) if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def build_config(instrument):
    root = tempfile.mkdtemp(prefix='sub_spans_')
    cfg = os.path.join(root, 'ncam_demo')
    shutil.copytree(CFG, cfg, symlinks=True)
    lib = os.path.join(root, 'lib')
    shutil.copytree(os.path.join(HERE, 'lib'), lib)
    if instrument:
        for name, specs in ANCHORS.items():
            src = os.path.join(lib, name)
            text = open(src).read()
            for anchor, rec, after in specs:
                if text.count(anchor) != 1:
                    raise RuntimeError('anchor matched %d times in %s, the '
                                       'instrument needs re-aiming: %r'
                                       % (text.count(anchor), name, anchor))
                text = text.replace(
                    anchor, anchor + rec if after else rec + anchor)
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


def table(src, base, n_name):
    """A Python-emitted pair table at a FIXED base address. The defaults block
    assigns the count first, so the LAST assignment is the real one."""
    n = num(src, r'#<%s>\s*=\s*(\d+)' % n_name)
    if not n:
        return []
    vals = {int(m.group(1)): float(m.group(2))
            for m in re.finditer(r'^#(\d+) = ([-\d.]+)$', src, re.M)}
    out = []
    for i in range(int(n)):
        if base + 2 * i + 1 not in vals:
            return None
        out.append((vals[base + 2 * i], vals[base + 2 * i + 1]))
    return out


def levels(canon):
    """[(w_idx, level, w_from, w_to, z_dirw, sg_use, [(from, to), ...])] -
    one entry per level, with the sub-spans the O-code actually walked."""
    out = []
    for m in RE_ANY.finditer(canon):
        g = m.groups()
        if g[0] is not None:
            out.append([int(float(g[0])), float(g[1]), float(g[2]),
                        float(g[3]), float(g[4]), int(float(g[5])), []])
        elif out:
            wf, wt = float(g[6]), float(g[7])
            spans = out[-1][6]
            # a new sub-span starts where the window end moves; further
            # records at the same end are the interval walk inside it
            if not spans or abs(spans[-1][1] - wt) > 1e-9:
                spans.append((wf, wt))
    return out


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
    work = tempfile.mkdtemp(prefix='sub_spans_ngc_')

    probe = generate('testing_15_5.xml', 0, 0, work)
    if probe is not None:
        clean = build_config(False)
        a, b = P.parse_program(probe, clean), P.parse_program(probe, ini)
        check('the instrument changes no motion',
              (not a.error) and (not b.error) and a.flat == b.flat,
              '%s / %s' % (a.error, b.error))

    ran = lv = split_lv = ctrl = 0
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
                tbl = table(src, ls.LVLSPLIT_BASE, '_pl_p1s_n')
                if tbl is None:
                    continue
                dm = num(src, r'#<_diameter_mode>\s*=\s*([\d.]+)', 2.0)
                # THE DIRECTION IS THE cfg PARAMETER, not a global read out of
                # the program. #<_pl_cut_rev> is a RUNTIME value - set inside
                # poly_lathe_mill from rough_dir, and for Both directions
                # flipped after every pass that emitted motion
                # (lathe_level_pass.ngc:1785) - so the source only ever shows
                # the defaults block's 0.0. Reading it there made sg_use False
                # everywhere and failed all seven back-to-front configurations.
                # AND THE TABLE ITSELF IS CLEARED unless the direction is back
                # to front (poly_lathe_mill.ngc:1320), which is why Both
                # directions takes one span despite its flag alternating.
                rev = direction == 1
                if not rev:
                    tbl = []
                sect_on = (num(src, r'#<_pl_sectioning>\s*=\s*([-\d.]+)', 0.0)
                           or 0) > 0
                recs = levels(_canon[(ngc, ini)][0])
                if not recs:
                    continue
                ran += 1
                wrong = []
                for w_idx, level, wf, wt, zd, use, spans in recs:
                    if not spans:
                        continue
                    lv += 1
                    if len(spans) > 1:
                        split_lv += 1
                    mine_use = bool(rev and tbl
                                    and ((not sect_on) or w_idx < 0))
                    if mine_use != bool(use):
                        wrong.append(('sg_use %s vs %s' % (mine_use, use),
                                      level))
                        continue
                    mine = ls.sub_spans(tbl, level, wf, wt, zd, dm, mine_use)
                    if len(mine) != len(spans) or any(
                            abs(a_[0] - b_[0]) > 0.002
                            or abs(a_[1] - b_[1]) > 0.002
                            for a_, b_ in zip(mine, spans)):
                        wrong.append((level, mine, spans))
                    # NEGATIVE CONTROL: with the table refused, a level that
                    # really was split must come back as a single span
                    if len(ls.sub_spans(tbl, level, wf, wt, zd, dm, False)) \
                            != len(spans):
                        ctrl += 1
                check('%s: the sub-span split is where Python says' % tag,
                      not wrong, '%d wrong, first %s' % (len(wrong),
                                                         wrong[:1]))

    check('the sweep actually ran', ran >= 25, '%d configurations' % ran)
    check('split levels are exercised', split_lv > 0,
          'every level was one span - the split is untested')
    check('the no-table control disagrees', ctrl > 0,
          'refusing the split table changes nothing')
    print('\n%d configurations, %d levels, %d of them split into sub-spans'
          % (ran, lv, split_lv))
    if FAILED:
        print('\nFAILED: %d\n   -  %s' % (len(FAILED), '\n   -  '.join(FAILED)))
        return 1
    print('\nPython predicts the sub-spans the O-code sweeps each level in.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
