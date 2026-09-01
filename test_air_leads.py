#!/usr/bin/env python3
# coding: utf-8
"""An entry lead into metal that is already gone is not emitted as a cut.

Standalone, like the other test_*.py here - run it directly, no pytest.

THE BUG THIS EXISTS FOR

With Artificial sectioning the roughing ladder is computed ONCE and shared by
every section window, so section N and section N-1 cut at exactly the same
radii. Every pass in section N whose level section N-1 already reached was
therefore leading in - a 45 degree straight lead AND a profile-angle ramp -
through a column that was already fully cleared. greatEndian, 2026-08-31, on
the 10th section of testing_15_9: *"could have skipped artificial lead in from
1-3 passes and only 4th in the part contact it should has it"*.

Measured before the fix, on testing_15_9 front-to-back: 689 lead and ramp moves
totalling 693.4 mm cut nothing at all - 35.5% of the whole roughing feed
distance.

WHAT IS ASSERTED

1. THE WORK IS UNTOUCHED. The leads that DO cut are still there, to the
   millimetre. This is the assertion that stops the gate being widened into
   something that drops real approach moves: the fix must remove air and only
   air.

2. AIR IS ACTUALLY REMOVED. On the Artificial case the air lead distance is far
   below what it was. Stated as a bound rather than an equality so a later
   change to the ladder does not fail this for the wrong reason.

3. NOTHING RAPIDS INTO STANDING METAL. The point of the whole exercise: with
   the lead gone the pass falls onto the no-lead path, which stands off in Z
   and descends radially. That descent must happen in cleared material. This is
   the assertion that caught two real regressions while the fix was being
   built - Natural sectioning at 0.4962 mm and Both-directions at 0.5059 mm,
   each one full depth of cut into standing metal - both caused by a first
   version that carried ONE value meaning "the window processed before this
   one".

4. EVERY MODE IS COVERED, AND NATURAL HAS NOTHING TO TAKE. The gate asks the
   windows an entry lead actually CROSSES what they have already cut, so the
   order windows are visited in stops mattering: Natural's weakest-section-first
   and Both-directions' alternating entry end are both handled by the same
   lookup. Natural then turns out to have had almost no air entry leads in the
   first place - 10.0 mm on testing_15_5 and 7.9 mm on testing_15_2 - because
   its windows carry a RADIUS BAND and so partition the ladder between them
   instead of each re-walking all of it. That is asserted here so the absence of
   a saving there is a recorded fact rather than a suspicion.

NOT CIRCULAR

The material state is rebuilt from the rs274 canon output in time order - every
cutting move lowers the surface it passes under - and each move is sampled
ALONG its length against that state. Nothing is compared against the table the
gate itself reads. A self-test lowers every rapid by 1 mm and requires the
collision check to fire, so a probe that has stopped measuring cannot pass.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

INI = os.path.join(HERE, 'configs/sim/axis/ncam_demo/lathe-mm.ini')
GEN = os.path.join(HERE, '.claude/skills/lathe-gcode-verify/scripts/gen_project.py')
FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name
          + (('  ' + detail) if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def seglen(m):
    return ((m.b[2] - m.a[2]) ** 2 + (m.b[0] - m.a[0]) ** 2) ** 0.5


class Material(object):
    """Outer radius of the remaining stock, on a Z grid, in time order.

    Bounded at the stock face: filling the grid across the whole Z range put
    phantom material in FRONT of the part, and the first run of this probe then
    reported a rapid 0.7 mm clear of the face as a 14.8 mm collision.
    """

    def __init__(self, stock, wp_z, zlo, zhi, n=8000):
        self.n, self.zlo = n, zlo
        self.step = (zhi - zlo) / float(n) if zhi > zlo else 1.0
        self.rad = [stock if (zlo + i * self.step) <= wp_z + 1e-9 else -1e9
                    for i in range(n + 1)]

    def _bin(self, z):
        return max(0, min(self.n, int(round((z - self.zlo) / self.step))))

    def cut(self, m):
        z0, x0, z1, x1 = m.a[2], m.a[0], m.b[2], m.b[0]
        i0, i1 = self._bin(z0), self._bin(z1)
        if i0 > i1:
            i0, i1, z0, z1, x0, x1 = i1, i0, z1, z0, x1, x0
        for i in range(i0, i1 + 1):
            z = self.zlo + i * self.step
            xv = x0 if abs(z1 - z0) < 1e-12 else x0 + (x1 - x0) * ((z - z0) / (z1 - z0))
            if xv < self.rad[i]:
                self.rad[i] = xv

    def depth(self, m, ns=60, off=0.0):
        """How far below the current surface this move reaches, sampled along."""
        z0, x0, z1, x1 = m.a[2], m.a[0] - off, m.b[2], m.b[0] - off
        w = 0.0
        for s in range(ns + 1):
            t = s / float(ns)
            z, xv = z0 + (z1 - z0) * t, x0 + (x1 - x0) * t
            w = max(w, self.rad[self._bin(z)] - xv)
        return w


def measure(P, project, sets, d, tag, selftest=0.0):
    out = os.path.join(d, tag + '.ngc')
    cmd = [sys.executable, GEN, '--ini', INI, '--project', project,
           '--out', out, '--config-copy']
    for kv in sets:
        cmd += ['--set', kv]
    subprocess.run(cmd, capture_output=True, text=True)
    if not os.path.isfile(out):
        return None
    tp = P.parse_program(out, INI)
    if tp.error:
        return None
    src = open(out).read()
    try:
        stock = float(re.findall(
            r'#<_wp_dia_od>\s*=\s*\[\s*([\d.]+)\s*/\s*2', src)[-1]) / 2.0
        wp_z = float(re.findall(r'#<_wp_z>\s*=\s*([-\d.]+)', src)[-1])
    except IndexError:
        return None
    # THE MATERIAL STATE TAKES EVERY CUT - roughing and the finish passes
    # alike - because the metal a finish pass removes is gone whether or not
    # this report counts its moves. Filtering the finish out of the MODEL made
    # a legitimate rapid over finish-cleared ground read as a 0.2842 mm
    # collision. Only the REPORTING below is roughing-only, via m.subs.
    mv = [m for m in tp.moves if m.op == 'Lathe Polyline']
    if not mv:
        return None
    zs = [m.a[2] for m in mv] + [m.b[2] for m in mv]
    mat = Material(stock, wp_z, min(zs), max(zs))
    levels = set()
    for k, m in enumerate(mv):
        if m.kind == 'feed' and not m.subs \
                and abs(m.b[0] - m.a[0]) < 1e-6 \
                and abs(m.b[2] - m.a[2]) > 1e-9:
            levels.add(k)
    r = dict(air_n=0, air_l=0.0, cut_n=0, cut_l=0.0, ent_n=0, ent_l=0.0,
             rap_n=0, rap_bad=0, rap_worst=0.0, feed=0.0)
    for k, m in enumerate(mv):
        if m.kind == 'rapid':
            w = mat.depth(m, off=selftest)
            r['rap_n'] += 1
            if w > 1e-3:
                r['rap_bad'] += 1
                r['rap_worst'] = max(r['rap_worst'], w)
            mat.cut(m)
            continue
        if m.kind != 'feed':
            continue
        # The finish passes still CUT - they shape the material state - but
        # they are not roughing and their long contour moves are not leads. A
        # 35.0032 mm finish move classified as a "lead-out" is what made the
        # first lead-out measurement unusable.
        if m.subs:
            mat.cut(m)
            continue
        r['feed'] += seglen(m)
        if k in levels:
            mat.cut(m)
            continue
        if mat.depth(m) <= 1e-4:
            r['air_n'] += 1
            r['air_l'] += seglen(m)
            # ENTRY or RETREAT. A lead emitted just BEFORE a level cut is the
            # entry; one after it is the retreat, and only entries are gated -
            # a retreat leaves the cut this pass has just made, which is a
            # different question. Validated against the state before any gate
            # existed, where it reported 408 air entry moves; 389 of those are
            # what the gate removes, leaving the 19 asserted below.
            if any(t in levels for t in range(k + 1, min(k + 4, len(mv)))):
                r['ent_n'] += 1
                r['ent_l'] += seglen(m)
        else:
            r['cut_n'] += 1
            r['cut_l'] += seglen(m)
        mat.cut(m)
    return r


def main():
    if not (os.path.isfile(INI) and os.path.isfile(GEN)):
        print('SKIP  demo config or generator not present')
        return
    if not shutil.which('rs274'):
        print('SKIP  rs274 is not installed')
        return
    import ncam_preview as P

    d = tempfile.mkdtemp(prefix='airlead_')
    try:
        # ---- every mode, by the numbers it actually produces ---------------
        # air ENTRY leads are what the gate targets. Before any gate existed
        # the Artificial front-to-back case carried 408 of them / 419.4 mm.
        # All distances here are ROUGHING ONLY - the finish passes still shape
        # the material state but are not roughing motion, and counting them
        # inflated every figure in analysis/066 and 067.
        cases = (
            ('artificial front to back', 'testing_15_9.xml',
             ['polyline:param_dir=0'], 'art0',
             dict(ent_n=19, cut_n=54, feed=1352.9, rap=0)),
            ('artificial back to front', 'testing_15_9.xml',
             ['polyline:param_dir=1'], 'art1',
             dict(ent_n=0, cut_n=309, feed=1319.0, rap=80)),
            ('both directions', 'testing_15_9.xml',
             ['polyline:param_dir=2'], 'both',
             dict(ent_n=10, cut_n=183, feed=1445.8, rap=0)),
            ('natural, testing_15_5', 'testing_15_5.xml',
             ['polyline:param_sectioning=1'], 'nat5',
             dict(ent_n=20, cut_n=57, feed=1144.4, rap=0)),
            ('natural, testing_15_2', 'testing_15_2.xml',
             ['polyline:param_sectioning=1'], 'nat2',
             dict(ent_n=16, cut_n=35, feed=530.0, rap=0)),
        )
        for name, project, sets, tag, want in cases:
            r = measure(P, project, sets, d, tag)
            check('%s generates and runs' % name, r is not None)
            if not r:
                continue

            # 1. THE WORK IS UNTOUCHED
            check('   %s keeps every lead that cuts metal' % name,
                  r['cut_n'] == want['cut_n'],
                  '%d leads still cut, want %d' % (r['cut_n'], want['cut_n']))

            # 2. AIR IS ACTUALLY REMOVED
            check('   %s has no air entry leads left to speak of' % name,
                  r['ent_n'] <= want['ent_n'],
                  '%d air entry leads / %.1f mm, want at most %d'
                  % (r['ent_n'], r['ent_l'], want['ent_n']))

            check('   %s cuts the distance it is meant to' % name,
                  abs(r['feed'] - want['feed']) < 0.5,
                  'roughing feed %.1f mm against %.1f'
                  % (r['feed'], want['feed']))

            # 3. NOTHING RAPIDS INTO STANDING METAL
            # art1 carries a handful of hits at 0.0042 mm - grid
            # discretisation on a sloped floor, present identically before any
            # of this work (64 at 0.0041) and four orders of magnitude below a
            # depth of cut. THE DEPTH IS THE BOUND THAT MATTERS; the count
            # drifts with the geometry (60 before the ramp-orientation gate, 76
            # after, at the same 0.0042) so it is given room while the depth
            # stays hard. A real collision is orders of magnitude deeper and
            # still fails.
            check('   %s rapids only through cleared metal' % name,
                  r['rap_bad'] <= want['rap'] and r['rap_worst'] < 0.01,
                  '%d of %d rapids, worst %.4f mm deep'
                  % (r['rap_bad'], r['rap_n'], r['rap_worst']))

        # ---- the lead-out setting, off and on ------------------------------
        # _pl_lo_air is greatEndian's per-project choice and 0 is the original
        # behaviour, so OFF must match the numbers above exactly and ON must
        # remove air without removing work. The pair is asserted together
        # because "the leads that cut are identical either way" is the whole
        # proof that nothing goes unremoved.
        pairs = (
            ('front to back', 'testing_15_9.xml', ['polyline:param_dir=0'],
             'lo0', 1352.9, 1103.9),
            ('both directions', 'testing_15_9.xml', ['polyline:param_dir=2'],
             'lo2', 1445.8, 1324.8),
            ('natural 15_5', 'testing_15_5.xml',
             ['polyline:param_sectioning=1'], 'lo5', 1144.4, 1103.4),
        )
        for name, project, sets, tag, f_off, f_on in pairs:
            a = measure(P, project, sets, d, tag + 'off')
            b = measure(P, project, sets + ['polyline:param_lo_air=1'], d,
                        tag + 'on')
            check('%s: lead-out setting runs both ways' % name,
                  a is not None and b is not None)
            if not (a and b):
                continue
            check('   %s off is the original motion' % name,
                  abs(a['feed'] - f_off) < 0.5,
                  '%.1f mm against %.1f' % (a['feed'], f_off))
            check('   %s on removes the air lead-outs' % name,
                  abs(b['feed'] - f_on) < 0.5,
                  '%.1f mm against %.1f' % (b['feed'], f_on))
            check('   %s on removes NO work' % name,
                  b['cut_n'] == a['cut_n'],
                  'leads that cut: %d on against %d off'
                  % (b['cut_n'], a['cut_n']))
            check('   %s on still rapids only through cleared metal' % name,
                  b['rap_bad'] == 0,
                  '%d of %d rapids, worst %.4f mm'
                  % (b['rap_bad'], b['rap_n'], b['rap_worst']))

        # THE LEAD-OUT SETTING MUST NOT TOUCH BACK TO FRONT. Every pass there
        # is reversed, so the setting has nothing it may act on. Applied to
        # reversed passes before it was bounded to forward ones, it took the
        # feed to 1110.6 mm and put 2 rapids 7.5622 mm into standing metal.
        # 1319.0 is that direction's feed AFTER the ramp-orientation gate,
        # which legitimately removed 18 ramps (40.6 mm) from it - see
        # test_ramp_orient. This asserts lo_air changes nothing FURTHER.
        rb = measure(P, 'testing_15_9.xml',
                     ['polyline:param_dir=1', 'polyline:param_lo_air=1'],
                     d, 'lo1on')
        check('back to front keeps every retreat, setting or not',
              rb is not None and abs(rb['feed'] - 1319.0) < 0.5,
              'roughing feed %.1f, want 1319.0' % (rb['feed'] if rb else -1))
        check('   and back to front gains no rapid into standing metal',
              rb is not None and rb['rap_worst'] < 0.01,
              'worst %.4f mm' % (rb['rap_worst'] if rb else -1))

        # ---- the probe must be able to fail --------------------------------
        st = measure(P, 'testing_15_9.xml', ['polyline:param_dir=0'], d,
                     'selftest', selftest=1.0)
        check('the collision check itself fires when it should',
              st is not None and st['rap_bad'] > 0,
              'sinking every rapid 1 mm changed nothing - the probe is not '
              'measuring')

    finally:
        shutil.rmtree(d, ignore_errors=True)

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('Entry leads are emitted only where there is metal to enter.')


if __name__ == '__main__':
    main()
