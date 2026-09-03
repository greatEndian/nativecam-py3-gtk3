#!/usr/bin/env python3
# coding: utf-8
"""Python predicts the windows roughing sweeps, and their radius bands.

Standalone, like the other test_*.py here - run it directly, no pytest.

THE TOP OF THE STACK. Working down, each layer has been proved given the one
above it:

    window   ->  sub-span  ->  interval  ->  level set
    this     ->  084       ->  083       ->  080/081/082

WHAT IS ASSERTED

The whole ordered sequence of windows - index, Z span and radius band - for
every project, sectioning state and direction. The index matters as much as the
span: lathe_level_pass records each window's deepest cut at #2800 + w_idx and
reads its NEIGHBOURS back, so an index is a position along the part.

The Z bounds are predicted too, from the profile's RAW first and last Z: the
back extension is applied and the Z limits then clamped, in that order. Only
the raw pair comes out of the record, and it belongs to the polyline geometry
rather than to the window walk.

WHAT IS NOT PREDICTED HERE

`lvl_start` and `lvl_floor` - what each window does with its ladder. Those are
the ladder layer (analysis/080, 081), and on Natural sectioning they depend on
the phase-1 handover, which is a runtime OUTCOME feeding back into geometry:
poly_lathe_mill reassigns sect_top_r when phase 1 stops on an obstruction. That
feedback is the one thing in the whole roughing stack that is not a
generation-time question, and it is deliberately left standing.

Nothing in the toolpath reads roughing_windows.

THE INSTRUMENT

lib/ in the repo is never touched: the tree is copied to a temp dir, one record
is inserted where the raw profile bounds are read and one per window iteration,
and the scratch config's ncam/lib symlink is repointed at the copy. Inertness
is proved, not claimed.
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

SUB = 'lathe/poly_lathe_mill.ngc'
ANCHORS = (
    # the RAW bounds, read before the extension and the limit clamp so both
    # are Python's to reproduce
    ('        #<l_z> = [#<l_z> + #<_pl_ext_bk_dz>]\n',
     '        (debug, RAWREC ez=#<e_z> lz=#<l_z>)\n', False),
    # one per window, after its span and band are resolved
    ('                #<current_radius> = #<lvl_start>\n',
     '                (debug, WREC w=#<w_idx> wf=#<w_from> wt=#<w_to> '
     'rlo=#<w_rlo> rhi=#<w_rhi>)\n', False),
)
RE_ANY = re.compile(
    r'(?:RAWREC ez=(-?[\d.]+) lz=(-?[\d.]+))'
    r'|(?:WREC w=(-?[\d.]+) wf=(-?[\d.]+) wt=(-?[\d.]+) rlo=(-?[\d.]+) '
    r'rhi=(-?[\d.]+))')

FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name
          + (('  ' + detail) if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def build_config(instrument):
    root = tempfile.mkdtemp(prefix='windows_')
    cfg = os.path.join(root, 'ncam_demo')
    shutil.copytree(CFG, cfg, symlinks=True)
    lib = os.path.join(root, 'lib')
    shutil.copytree(os.path.join(HERE, 'lib'), lib)
    if instrument:
        src = os.path.join(lib, SUB)
        text = open(src).read()
        for anchor, rec, after in ANCHORS:
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


def sections(src):
    """The #3400 window table: (z_from, z_to, r_lo, r_hi) per window, four
    slots each and the first slot of the group unused."""
    n = num(src, r'#<_pl_sect_count>\s*=\s*(\d+)')
    if not n:
        return []
    vals = {int(m.group(1)): float(m.group(2))
            for m in re.finditer(r'^#(\d+) = ([-\d.]+)$', src, re.M)}
    out = []
    for i in range(int(n)):
        slot = ls.SECT_BASE + i * 4
        if slot + 4 not in vals:
            return None
        out.append(tuple(vals[slot + k] for k in (1, 2, 3, 4)))
    return out


def observed(canon):
    """(raw_e_z, raw_l_z, [(w_idx, w_from, w_to, r_lo, r_hi)]) - one window
    per iteration, in the order the O-code took them."""
    raw, wins = None, []
    for m in RE_ANY.finditer(canon):
        g = m.groups()
        if g[0] is not None:
            if raw is None:
                raw = (float(g[0]), float(g[1]))
        else:
            wins.append((int(float(g[2])), float(g[3]), float(g[4]),
                         float(g[5]), float(g[6])))
    return raw, wins


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
    work = tempfile.mkdtemp(prefix='windows_ngc_')

    probe = generate('testing_15_5.xml', 1, 0, work)
    if probe is not None:
        clean = build_config(False)
        a, b = P.parse_program(probe, clean), P.parse_program(probe, ini)
        check('the instrument changes no motion',
              (not a.error) and (not b.error) and a.flat == b.flat,
              '%s / %s' % (a.error, b.error))

    ran = wins = banded = phase1 = ctrl = 0
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
                secs = sections(src)
                if secs is None:
                    continue
                raw, obs = observed(_canon[(ngc, ini)][0])
                if raw is None or not obs:
                    continue
                ran += 1
                wins += len(obs)
                banded += sum(1 for w in obs if w[3] > -999998)
                phase1 += sum(1 for w in obs if w[0] < 0)
                dm = num(src, r'#<_diameter_mode>\s*=\s*([\d.]+)', 2.0)
                ext = num(src, r'#<_pl_ext_bk_dz>\s*=\s*([-\d.]+)', 0.0) or 0.0
                lim = None
                if (num(src, r'#<_pl_lim_on>\s*=\s*([-\d.]+)', 0.0) or 0) > 0:
                    lim = (num(src, r'#<_pl_lim_lo>\s*=\s*([-\d.]+)'),
                           num(src, r'#<_pl_lim_hi>\s*=\s*([-\d.]+)'))
                mode = int(num(src, r'#<_pl_sect_mode>\s*=\s*(\d+)', 0.0) or 0)
                on = (num(src, r'#<_pl_sectioning>\s*=\s*([-\d.]+)', 0.0)
                      or 0) > 0
                mine = ls.roughing_windows(raw[0], raw[1], ext, lim, secs,
                                           mode, on, dm)
                same = len(mine) == len(obs) and all(
                    a_[0] == b_[0]
                    and all(abs(a_[k] - b_[k]) < 0.002 for k in (1, 2, 3, 4))
                    for a_, b_ in zip(mine, obs))
                check('%s: the window sweep is where Python says' % tag, same,
                      'predicted %d, walked %d; first difference %s'
                      % (len(mine), len(obs),
                         next((('%s' % (a_,), '%s' % (b_,))
                               for a_, b_ in zip(mine, obs) if a_ != b_),
                              None)))
                # NEGATIVE CONTROL: the other sectioning mode must not
                # produce the same sweep, or the mode is being ignored
                if ls.roughing_windows(raw[0], raw[1], ext, lim, secs,
                                       1 - mode, on, dm) != mine:
                    ctrl += 1

    check('the sweep actually ran', ran >= 25, '%d configurations' % ran)
    check('banded windows are exercised', banded > 0,
          'no window carried a radius band')
    check('the phase-1 window is exercised', phase1 > 0,
          'no configuration ran a ceiling phase')
    check('the sectioning-mode control disagrees', ctrl > 0,
          'the mode changes nothing about the sweep')
    print('\n%d configurations, %d windows, %d with a radius band, '
          '%d ceiling phases' % (ran, wins, banded, phase1))
    if FAILED:
        print('\nFAILED: %d\n   -  %s' % (len(FAILED), '\n   -  '.join(FAILED)))
        return 1
    print('\nPython predicts every window the O-code sweeps.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
