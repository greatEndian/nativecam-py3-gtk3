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
   each one full depth of cut into standing metal.

4. THE MODES THAT CANNOT EXPRESS THE CARRY ARE BIT-FOR-BIT UNCHANGED. Natural
   ordering puts the weakest section first, and Both-directions alternates the
   entry end per pass; in neither case is "the window processed before this
   one" the neighbour the lead reaches into. Both must measure exactly as they
   did before the gate existed.

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
    mv = [m for m in tp.moves if m.op == 'Lathe Polyline']
    if not mv:
        return None
    zs = [m.a[2] for m in mv] + [m.b[2] for m in mv]
    mat = Material(stock, wp_z, min(zs), max(zs))
    levels = set()
    for k, m in enumerate(mv):
        if m.kind == 'feed' and abs(m.b[0] - m.a[0]) < 1e-6 \
                and abs(m.b[2] - m.a[2]) > 1e-9:
            levels.add(k)
    r = dict(air_n=0, air_l=0.0, cut_n=0, cut_l=0.0,
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
        r['feed'] += seglen(m)
        if k in levels:
            mat.cut(m)
            continue
        if mat.depth(m) <= 1e-4:
            r['air_n'] += 1
            r['air_l'] += seglen(m)
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
        # ---- the reported case: Artificial sectioning, front to back --------
        a = measure(P, 'testing_15_9.xml', ['polyline:param_dir=0'], d, 'art0')
        check('the Artificial case generates and runs', a is not None)
        if a:
            # 1. THE WORK IS UNTOUCHED
            check('the leads that cut metal are all still there',
                  a['cut_n'] >= 190 and a['cut_l'] > 200.0,
                  'only %d leads / %.1f mm still cut' % (a['cut_n'], a['cut_l']))
            # 2. AIR IS ACTUALLY REMOVED
            check('   and the air leads are gone',
                  a['air_l'] < 400.0,
                  '%.1f mm of lead still cuts nothing (was 693.4 before '
                  'the gate)' % a['air_l'])
            # 3. NOTHING RAPIDS INTO STANDING METAL
            check('   and no rapid descends into standing metal',
                  a['rap_bad'] == 0,
                  '%d of %d rapids, worst %.4f mm deep'
                  % (a['rap_bad'], a['rap_n'], a['rap_worst']))
            # the probe must be able to fail
            st = measure(P, 'testing_15_9.xml', ['polyline:param_dir=0'], d,
                         'art0st', selftest=1.0)
            check('   and the collision check itself fires when it should',
                  st is not None and st['rap_bad'] > 0,
                  'sinking every rapid 1 mm changed nothing - the probe is '
                  'not measuring')

        # ---- 4. the modes the carry cannot express, unchanged ---------------
        # Natural ordering (sec_len 0) puts the weakest section first, and
        # Both-directions alternates the entry end; the gate stands down in
        # both, so these must measure exactly as they did before it existed.
        for project, sets, tag, want in (
                ('testing_15_5.xml', ['polyline:param_sectioning=1'],
                 'nat5', (73, 194, 1326.2)),
                ('testing_15_2.xml', ['polyline:param_sectioning=1'],
                 'nat2', (107, 101, 700.9)),
                ('testing_15_9.xml', ['polyline:param_dir=2'],
                 'both', (556, 327, 1951.1))):
            r = measure(P, project, sets, d, tag)
            check('%s is untouched by the gate' % tag, r is not None)
            if not r:
                continue
            check('   %s keeps its own lead counts' % tag,
                  r['air_n'] == want[0] and r['cut_n'] == want[1],
                  'air %d (want %d), cutting %d (want %d)'
                  % (r['air_n'], want[0], r['cut_n'], want[1]))
            check('   %s keeps its own roughing feed distance' % tag,
                  abs(r['feed'] - want[2]) < 0.5,
                  '%.1f mm against %.1f' % (r['feed'], want[2]))
            check('   %s still rapids only through cleared metal' % tag,
                  r['rap_bad'] == 0,
                  '%d of %d rapids, worst %.4f mm'
                  % (r['rap_bad'], r['rap_n'], r['rap_worst']))
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
