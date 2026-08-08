#!/usr/bin/env python3
# coding: utf-8
"""Where a roughing level starts, and how high it retreats.

Standalone, like the other test_*.py here - run it directly, no pytest.

`openPoints` carried this as a gap for four days: *"Nothing asserts the roughing
start or the retreat height directly"*. Both ends of a roughing level have been
changed this session - the start by `analysis/010` (the level fell back to a raw
profile Z and the nose began cutting 0.4 mm past the drawn segment) and again by
the Begin Z clamp - and neither has a test of its own. What covers them today is
`test_rough_comp`'s overcut number, 0.0394 mm, which is an INDIRECT reading: a
start that moves changes it, so does an offset that moves, and one is easily
explained away as the other.

WHAT IS ASSERTED, and why none of it is circular:

1. THE START IS THE POLYLINE'S OWN BEGIN Z. Not "near the front", not "the same
   as last time" - equality with the number the definition carries, which the
   program states in `#<_pl_begin_z>` and the motion must then honour. The
   O-code is explicit that it is an equality and not a one-sided bound (the nose
   shift moves the start PAST the reference, and a "never in front of it" test
   let that through), so both halves are checked: nothing starts in front of it,
   and something starts exactly on it.

2. IT TRACKS. Assertion 1 alone would pass on a program that always started at
   Z0.0 for reasons of its own, because Begin Z is 0 in every saved project.
   So the same project is generated again with Begin Z moved to -5.0 and the
   start has to move with it, exactly. That is the anti-coincidence check and it
   is the one that gives the file teeth.

3. COMPENSATION DOES NOT MOVE IT. Off, Native and In CAM must place the start
   on the same Z. This is the asymmetry `analysis/009` and `analysis/010` both
   found, at the two ends of a contour pass and at the two ends of a level: one
   end carrying the nose while the other did not.

4. NO ROUGHING RAPID REMOVES MATERIAL. That is the retreat height, measured
   rather than read: sweep the real nose circle along every rapid against the
   material AS IT STANDS at that point in the program. A retreat that does not
   clear what is standing ploughs back through it on the return traverse.

5. THE RETURN TRAVERSE CLEARS THE STOCK ENVELOPE. Stronger and simpler than 4
   on OD work - it may not pass over the bar at all - and it states the retreat
   height as a number instead of as an absence of collisions.

The stock is read out of the program (`#<_wp_dia_od>`, `#<_wp_z>`) rather than
hard-coded, so a project whose bar changes does not quietly invalidate 4 and 5.
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
PROJECTS = ('testing_15_2.xml', 'testing_15_4.xml')
MODES = ((0, 'Off'), (1, 'Native'), (2, 'In CAM'))
NOSE, ORIENT = 0.4, 2
SHIFT = -5.0            # a Begin Z nowhere near the 0.0 every project carries
TOL = 1e-4
FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name
          + (('  ' + detail) if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def workpiece(path):
    """(face Z, outer radius) as the program itself states them."""
    z, r = None, None
    for ln in open(path):
        s = ln.strip()
        m = re.match(r'#<_wp_dia_od> = \[([-\d.]+) / 2', s)
        if m:
            r = float(m.group(1)) / 2.0
        m = re.match(r'#<_wp_z>\s*= ([-\d.]+)', s)
        if m:
            z = float(m.group(1))
    return z, r


def begin_z(path):
    """The Begin Z the definition carries, as emitted - the last one wins.

    `create_defaults` writes a 0.0 placeholder at the top of every program so
    the load-time pre-parse finds the name defined; the polyline then assigns
    the real value. Reading the first match gets the placeholder and the test
    passes on a program that ignores Begin Z entirely.
    """
    v = None
    for ln in open(path):
        m = re.match(r'#<_pl_begin_z> = ([-\d.]+)', ln.strip())
        if m:
            v = float(m.group(1))
    return v


def levels(tp, P):
    """The straight Z cuts - one per roughing level, leads excluded.

    A level is a FEED at constant radius that travels in Z. The 45 degree
    lead-in and lead-out that bracket it change both, so they drop out without
    having to be recognised, and the contour passes carry a `subs` tag.
    """
    return [m for m in tp.moves
            if m.op == 'Lathe Polyline' and not m.subs and m.kind == 'feed'
            and abs(m.b[0] - m.a[0]) < 1e-6 and abs(m.b[2] - m.a[2]) > 1e-6]


def rapid_cut(tp, P, wp_z, wp_r):
    """Worst material a roughing RAPID removes, and the field to re-use.

    The field is cut by the feeds as the program runs, so each rapid is judged
    against what is standing at that moment - not against the raw bar, which
    every retreat would clear trivially. A rapid's own sweep is rolled back
    afterwards: it is being measured, not simulated.
    """
    zs = [p for m in tp.moves for p in (m.a[2], m.b[2])]
    z0, z1 = min(zs) - 2, max(zs) + 2
    f = P.StockField(z0, z1, 0.0, wp_r, P.StockField.columns_for(z0, z1, NOSE))
    for i in range(f.n):                        # nothing in front of the face
        if f.z0 + (i + 0.5) * f.dz > wp_z:
            f.outer[i] = 0.0
    dv = P.nose_offset(ORIENT)
    worst, where = 0.0, None
    for m in tp.moves:
        rough = m.op == 'Lathe Polyline' and not m.subs
        if m.kind == 'rapid':
            if not rough:
                continue
            before = list(f.outer)
            f.cut_move(m.a, m.b, NOSE, dv)
            cut = max([before[i] - f.outer[i] for i in range(f.n)] + [0.0])
            f.outer = before
            if cut > worst:
                worst, where = cut, (m.a[2], m.a[0], m.b[2], m.b[0])
        else:
            f.cut_move(m.a, m.b, NOSE, dv)
    return worst, where, f


def traverses(tp):
    """The return rapids: constant radius, real distance in Z."""
    return [m for m in tp.moves
            if m.op == 'Lathe Polyline' and not m.subs and m.kind == 'rapid'
            and abs(m.b[0] - m.a[0]) < 1e-6 and abs(m.b[2] - m.a[2]) > 1.0]


def main():
    if not (os.path.isfile(INI) and os.path.isfile(GEN)):
        print('SKIP  demo config or generator not present')
        return
    if not shutil.which('rs274'):
        print('SKIP  rs274 is not installed')
        return
    import ncam_preview as P

    d = tempfile.mkdtemp(prefix='rough_ends_')
    try:
        def gen(project, mode, b_z=None):
            tag = '%s_%d_%s' % (project[:-4], mode, b_z)
            out = os.path.join(d, tag + '.ngc')
            cmd = [sys.executable, GEN, '--ini', INI, '--project', project,
                   '--out', out, '--config-copy',
                   '--set', 'polyline:param_n_comp=%d' % mode]
            if b_z is not None:
                cmd += ['--set', 'polyline:param_b_z=%s' % b_z]
            subprocess.run(cmd, capture_output=True, text=True)
            if not os.path.isfile(out):
                return None
            tp = P.parse_program(out, INI)
            return None if tp.error else (tp, out)

        # THE METRIC HAS TO BE ALIVE. Assertion 4 reports 0.0000 mm on a healthy
        # program, and a measurement that can only ever say zero says nothing.
        # A rapid driven straight through the bar must be caught by the same
        # code path, so run one before trusting the real answer.
        probe = P.StockField(-10.0, 10.0, 0.0, 30.0, 300)
        probe.cut_move((29.0, 0.0, -8.0), (29.0, 0.0, 8.0), NOSE,
                       P.nose_offset(ORIENT))
        check('the rapid-clearance measurement detects a rapid through stock',
              min(probe.outer) < 29.9,
              'a rapid 1.0 mm inside a 30.0 mm bar registered nothing - '
              'assertion 4 below cannot fail and proves nothing')

        for project in PROJECTS:
            print('--- %s' % project)
            runs = {}
            for mode, label in MODES:
                runs[label] = gen(project, mode)
            check('all three modes generate and run', all(runs.values()),
                  str({k: v is None for k, v in runs.items()}))
            if not all(runs.values()):
                continue

            # 1. THE START IS BEGIN Z - both halves of the equality.
            starts = {}
            for label, (tp, out) in runs.items():
                bz = begin_z(out)
                lv = levels(tp, P)
                check('%-7s the program states a Begin Z and cuts levels'
                      % label, bz is not None and len(lv) > 5,
                      'begin_z=%s, %d levels' % (bz, len(lv)))
                if bz is None or not lv:
                    continue
                st = [m.a[2] for m in lv]
                starts[label] = (bz, max(st))
                ahead = [s for s in st if s > bz + TOL]
                check('%-7s no roughing level starts in front of Begin Z'
                      % label, not ahead,
                      '%d of %d do - frontmost Z%.4f against Begin Z %.4f'
                      % (len(ahead), len(st), max(ahead), bz) if ahead else '')
                on = [s for s in st if abs(s - bz) < TOL]
                check('%-7s and levels start exactly ON it, not merely behind'
                      % label, bool(on),
                      'the frontmost is Z%.4f, %.4f short of Begin Z %.4f - '
                      'a one-sided bound is not the rule'
                      % (max(st), bz - max(st), bz))
                print('      %-7s Begin Z %.4f, %d of %d levels start there'
                      % (label, bz, len(on), len(st)))

            # 2. COMPENSATION DOES NOT MOVE IT.
            if len(starts) == len(MODES):
                spread = (max(v[1] for v in starts.values())
                          - min(v[1] for v in starts.values()))
                check('every mode starts roughing on the same Z',
                      spread < TOL,
                      ' '.join('%s Z%.4f' % (k, v[1])
                               for k, v in starts.items()))

            # 3. NO ROUGHING RAPID REMOVES MATERIAL, and the traverse clears
            #    the bar. Off is enough for the geometry of the retreat - it is
            #    not compensated and the modes have just been shown to agree -
            #    but run all three, since a retreat is cheap to measure and the
            #    two compensated modes reach it by different routes.
            for label, (tp, out) in runs.items():
                wp_z, wp_r = workpiece(out)
                if wp_r is None:
                    check('%-7s the program states its stock' % label, False,
                          'no #<_wp_dia_od> - 3 and 4 cannot be judged')
                    continue
                worst, where, _f = rapid_cut(tp, P, wp_z, wp_r)
                check('%-7s no roughing rapid removes material' % label,
                      worst < 1e-4,
                      'the retreat leaves %.4f mm standing in a rapid\'s way: '
                      'Z%.4f r%.4f -> Z%.4f r%.4f' % ((worst,) + where)
                      if where else '')

                tv = traverses(tp)
                lv = levels(tp, P)
                external = lv and max(m.a[0] for m in lv) <= wp_r + TOL
                if not (tv and external):
                    print('      %-7s %d return traverses, external=%s - '
                          'stock-clearance check does not apply'
                          % (label, len(tv), bool(external)))
                    continue
                low = min(m.a[0] for m in tv)
                check('%-7s every return traverse clears the stock OD' % label,
                      low >= wp_r - TOL,
                      'one runs at r%.4f, %.4f mm INSIDE the r%.4f bar'
                      % (low, wp_r - low, wp_r))
                print('      %-7s retreat height r%.4f, %.4f mm clear of the '
                      'r%.4f bar (%d traverses)'
                      % (label, low, low - wp_r, wp_r, len(tv)))

        # 4. AND IT TRACKS. Everything above would pass on a program that
        #    started at Z0.0 for its own reasons, because Begin Z is 0.0 in
        #    every saved project. Move it and the start has to move exactly
        #    with it. One project, both a compensated and an uncompensated
        #    mode - the point is the number, not the coverage.
        print('--- Begin Z moved to %.1f' % SHIFT)
        for mode, label in ((0, 'Off'), (1, 'Native')):
            base = gen(PROJECTS[0], mode)
            moved = gen(PROJECTS[0], mode, SHIFT)
            if not (base and moved):
                check('%-7s the shifted project generates' % label, False)
                continue
            b_lv, m_lv = levels(base[0], P), levels(moved[0], P)
            if not (b_lv and m_lv):
                check('%-7s both runs cut levels' % label, False)
                continue
            b_st, m_st = max(m.a[2] for m in b_lv), max(m.a[2] for m in m_lv)
            bz = begin_z(moved[1])
            check('%-7s the roughing start follows Begin Z' % label,
                  bz is not None and abs(m_st - bz) < TOL,
                  'Begin Z %.4f but roughing starts at Z%.4f' % (bz or 0, m_st))
            check('%-7s and it actually moved when Begin Z did' % label,
                  abs(m_st - b_st) > 1.0,
                  'Z%.4f both times - the start is not reading Begin Z at all'
                  % b_st)
            print('      %-7s Z%.4f -> Z%.4f, Begin Z %.4f -> %.4f'
                  % (label, b_st, m_st, begin_z(base[1]), bz))
    finally:
        shutil.rmtree(d, ignore_errors=True)

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('Roughing starts on Begin Z and retreats clear of the bar.')


if __name__ == '__main__':
    main()
