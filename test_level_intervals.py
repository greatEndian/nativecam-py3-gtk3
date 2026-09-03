#!/usr/bin/env python3
# coding: utf-8
"""Python predicts the whole interval walk a roughing level takes.

Standalone, like the other test_*.py here - run it directly, no pytest.

A level behind a boss is not one pass. lathe_level_pass runs until the profile
rises above the level, poly_lathe_mill then asks lathe_level_next_start where
the level may resume, and calls again - as many times as the profile allows.
That loop is the reason the blocked gate saw 3373 calls where 30 configurations
hold only 819 levels.

WHAT IS ASSERTED

For every level, the ENTIRE sequence of calls - each interval's start, and
where the sequence ends - is predicted from `lathe_sections.resume_z` and the
previous call's outcome. Not a spot check on one continuation: the whole chain,
and it has to stop where the O-code stopped.

NOTHING IS OBSERVED. Where a pass ends - #<_pl_level_z_end>, the input to the
next resume search - is PREDICTED by `level_stop_z`, not read out of the
record. The record is only what the prediction is judged against.

That was not the first plan. z_end is refined against the stop contour with a
tool-reach clamp (lathe_level_pass.ngc:904) after the plain crossing gives a
first value, and replicating that blind is how a plausible-but-wrong replica
gets built - so the walk was first proved with z_end fed back in from the
record, and the refinement MEASURED: it moves z_end on 0 of 1854 cutting calls
across these five projects. Exact there, so the observation could be dropped.
It is carried in the O-code for cases that do fire, and those are outside this
sweep - the summary line still reports the count so a project that exercises it
shows up as a disagreement rather than as silence.

Nothing in the toolpath reads resume_z or level_stop_z.

THE INSTRUMENT

lib/ in the repo is never touched: the tree is copied to a temp dir, records
are inserted at lathe_level_pass's two blocked returns, at the point it commits
to cutting, and where it exports its cut end. Inertness is proved, not claimed.
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


SUB = 'lathe/lathe_level_pass.ngc'
# WHICH PHASE A CALL BELONGS TO cannot be seen from lathe_level_pass: phase 1
# ends by a branch in its CALLER. poly_lathe_mill emits one header per
# sub-span so each run of calls carries its window index.
MILL = 'lathe/poly_lathe_mill.ngc'
MILL_ANCHOR = '                                o<wh_seg> while [1]\n'
MILL_REC = ('                                (debug, SEGREC w=#<w_idx> '
            'r=#<current_radius>)\n')
ANCHORS = (
    ('\t\to<mc_decide> if [#<mc_wf_state> GT 0]\n',
     '\t\t\t(debug, BLKREC lvl=#<level> wf=#<w_from> wt=#<w_to> blk=1)\n'),
    ('\to<blk> if [[#<found>] AND [[#<z_dir> * [#<zc> - #<w_from>]] GE -0.0001]]\n',
     '\t\t(debug, BLKREC lvl=#<level> wf=#<w_from> wt=#<w_to> blk=1)\n'),
    ('\to<blk> endif\n',
     '\t(debug, BLKREC lvl=#<level> wf=#<w_from> wt=#<w_to> blk=0)\n'),
    ('\t#<_pl_level_z_end> = #<z_end>\n',
     '\t(debug, ZEREC ze=#<_pl_level_z_end> raw=#<z_wend> zc=#<zc>)\n'),
)
RE_ANY = re.compile(
    r'(?:BLKREC lvl=(-?[\d.]+) wf=(-?[\d.]+) wt=(-?[\d.]+) blk=(\d))'
    r'|(?:ZEREC ze=(-?[\d.]+) raw=(-?[\d.]+) zc=(-?[\d.]+))'
    r'|(?:SEGREC w=(-?[\d.]+) r=(-?[\d.]+))')

FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name
          + (('  ' + detail) if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def build_config(instrument):
    root = tempfile.mkdtemp(prefix='intervals_')
    cfg = os.path.join(root, 'ncam_demo')
    shutil.copytree(CFG, cfg, symlinks=True)
    lib = os.path.join(root, 'lib')
    shutil.copytree(os.path.join(HERE, 'lib'), lib)
    if instrument:
        src = os.path.join(lib, SUB)
        text = open(src).read()
        mp = os.path.join(lib, MILL)
        mt = open(mp).read()
        if mt.count(MILL_ANCHOR) != 1:
            raise RuntimeError('the sub-span anchor matched %d times'
                               % mt.count(MILL_ANCHOR))
        open(mp, 'w').write(mt.replace(MILL_ANCHOR, MILL_REC + MILL_ANCHOR))
        for anchor, rec in ANCHORS:
            if text.count(anchor) != 1:
                raise RuntimeError('anchor matched %d times, the instrument '
                                   'needs re-aiming: %r'
                                   % (text.count(anchor), anchor))
            text = text.replace(anchor, anchor + rec)
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


def table(src, base_name, n_name):
    """A Python-emitted (a, b) pair table, or None. THE DEFAULTS BLOCK
    ASSIGNS EVERY GLOBAL FIRST, so the placeholder 0 has to be filtered out
    and the real assignments counted - a plain count is never 1."""
    real = [int(v) for v
            in re.findall(r'#<%s>\s*=\s*(\d+)' % base_name, src) if int(v) > 0]
    n = num(src, r'#<%s>\s*=\s*(\d+)' % n_name)
    if len(real) != 1 or not n:
        return None
    base, n = real[0], int(n)
    vals = {int(m.group(1)): float(m.group(2))
            for m in re.finditer(r'^#(\d+) = ([-\d.]+)$', src, re.M)}
    out = []
    for i in range(n):
        if base + 2 * i + 1 not in vals:
            return None
        out.append((vals[base + 2 * i], vals[base + 2 * i + 1]))
    return out


def records(canon):
    """The instrument's records, in order: ('blk', lvl, wf, wt, blk) and
    ('ze', z_end, z_wend, zc)."""
    out = []
    for m in RE_ANY.finditer(canon):
        g = m.groups()
        if g[0] is not None:
            out.append(('blk', float(g[0]), float(g[1]), float(g[2]),
                        int(g[3])))
        elif g[4] is not None:
            out.append(('ze', float(g[4]), float(g[5]), float(g[6])))
        else:
            out.append(('seg', int(float(g[7]))))
    return out


def passes(recs):
    """One entry per call: (lvl, wf, wt, blocked, z_end, z_wend, zc).

    z_end is None on a blocked call - the subroutine returns before exporting
    it, and poly_lathe_mill correctly searches from w_from in that case."""
    out = []
    phase = 0
    for i, r in enumerate(recs):
        if r[0] == 'seg':
            phase = r[1]
            continue
        if r[0] != 'blk':
            continue
        ze = raw = zc = None
        if not r[4]:
            for nxt in recs[i + 1:]:
                if nxt[0] == 'ze':
                    ze, raw, zc = nxt[1], nxt[2], nxt[3]
                    break
                if nxt[0] == 'blk':
                    break
        out.append((r[1], r[2], r[3], bool(r[4]), ze, raw, zc, phase))
    return out


def groups(ps):
    """Maximal runs of consecutive calls sharing a level and a window end -
    one interval walk of one level in one sub-span."""
    out, cur = [], []
    for p in ps:
        if cur and (abs(p[0] - cur[-1][0]) > 1e-9
                    or abs(p[2] - cur[-1][2]) > 1e-9):
            out.append(cur)
            cur = []
        cur.append(p)
    if cur:
        out.append(cur)
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
    work = tempfile.mkdtemp(prefix='intervals_ngc_')

    probe = generate('testing_15_5.xml', 0, 0, work)
    if probe is not None:
        clean = build_config(False)
        a, b = P.parse_program(probe, clean), P.parse_program(probe, ini)
        check('the instrument changes no motion',
              (not a.error) and (not b.error) and a.flat == b.flat,
              '%s / %s' % (a.error, b.error))

    ran = walks = multi = steps = raw_ok = raw_n = 0
    ctrl = 0
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
                env = table(src, '_pl_res_base', '_pl_res_n')
                flc = table(src, '_pl_flc_base', '_pl_flc_n')
                mc = (num(src, r'#<_pl_multi_cross>\s*=\s*([-\d.]+)', 0.0)
                      or 0) > 0
                oz = num(src, r'#<_pl_rgh_oz>\s*=\s*([-\d.]+)', 0.0) or 0.0
                sect_on = (num(src, r'#<_pl_sectioning>\s*=\s*([-\d.]+)',
                               0.0) or 0) > 0
                mm = num(src, r'#<_mm>\s*=\s*([-\d.]+)', 1.0)
                ps = passes(records(_canon[(ngc, ini)][0]))
                if not ps or env is None or flc is None:
                    continue
                ran += 1
                wrong = []
                for g in groups(ps):
                    walks += 1
                    if len(g) > 1:
                        multi += 1
                    cut_yet = False
                    for i, (lvl, wf, wt, blk, ze, raw, zc, ph) in enumerate(g):
                        steps += 1
                        # where the NEXT search starts: the interval's own
                        # start when this pass was refused, the cut end when
                        # it ran
                        pblk, pze = ls.level_stop_z(flc, lvl, wf, wt, oz,
                                                    mc, mm)
                        if bool(pblk) != blk:
                            wrong.append(('blocked %s vs %s' % (pblk, blk),
                                          lvl, wf))
                            break
                        if not blk and abs(pze - ze) > 0.002:
                            wrong.append(('z_end %.4f vs %.4f' % (pze, ze),
                                          lvl, wf))
                            break
                        # PHASE 1 ABANDONS THE WHOLE LEVEL HERE. Blocked
                        # from the sub-span's own start with nothing cut on
                        # this level yet, poly_lathe_mill's o<p1_none> hands
                        # the radius to phase 2 and breaks out - there is no
                        # resume attempt at all. Only phase 1 does this; a
                        # phase-2 window blocked the same way goes looking.
                        if sect_on and ph < 0 and blk and not cut_yet and i == 0:
                            if i + 1 < len(g):
                                wrong.append(('phase 1 should have stopped',
                                              lvl, wf))
                            break
                        if not blk:
                            cut_yet = True
                        sf = wf if blk else pze
                        found, z = ls.resume_z(env, lvl, sf, wt, mm)
                        nxt = g[i + 1] if i + 1 < len(g) else None
                        if nxt is None:
                            if found:
                                wrong.append(('walk should continue to %.4f'
                                              % z, lvl, wf))
                        elif not found:
                            wrong.append(('walk should stop', lvl, nxt[1]))
                        elif abs(z - nxt[1]) > 0.002:
                            wrong.append(('%.4f vs %.4f' % (z, nxt[1]),
                                          lvl, wf))
                        # NEGATIVE CONTROL: the same question asked from the
                        # window end instead must not keep giving the same
                        # answer, or resume_z is ignoring its arguments
                        if ls.resume_z(env, lvl, wt, wt, mm)[0] != found:
                            ctrl += 1
                        # HOW MUCH OF z_end THE PLAIN CROSSING ALREADY GIVES.
                        # z_end starts as the crossing clamped at the window
                        # end and is then refined against the stop contour
                        # and a tool-reach clamp. This counts where that
                        # refinement actually moved it - the size of what a
                        # Python z_end would still have to reproduce.
                        if not blk and ze is not None:
                            raw_n += 1
                            zd = 1.0 if wf >= wt else -1.0
                            plain = zc if zd * (zc - raw) > 0 else raw
                            raw_ok += abs(ze - plain) < 0.0005
                check('%s: the interval walk goes where Python says' % tag,
                      not wrong, '%d wrong, first 3 %s' % (len(wrong),
                                                           wrong[:3]))

    check('the sweep actually ran', ran >= 25, '%d configurations' % ran)
    check('multi-interval levels are exercised', multi > 0,
          'every level took exactly one interval - the walk is untested')
    check('the control disagrees', ctrl > 0,
          'resume_z answers the same from any search start')
    print('\n%d configurations, %d interval walks, %d of them multi-interval, '
          '%d calls' % (ran, walks, multi, steps))
    if raw_n:
        print('z_end: the plain crossing already gives it on %d of %d cutting '
              'calls - the stop contour and reach clamp move the other %d'
              % (raw_ok, raw_n, raw_n - raw_ok))
    if FAILED:
        print('\nFAILED: %d\n   -  %s' % (len(FAILED), '\n   -  '.join(FAILED)))
        return 1
    print('\nPython predicts every interval the O-code cuts a level in.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
