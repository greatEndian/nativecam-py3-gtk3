#!/usr/bin/env python3
# coding: utf-8
"""Roughing leaves no metal standing more than one depth of cut proud.

Standalone, like the other test_*.py here - run it directly, no pytest.

THIS MEASURES THE METAL, NOT THE RECIPE. Every other check on the roughing
ladder inspects the tables that produce it - breakpoints, crossings, the Z each
pass starts at. Those can all read correct while a pass is missing, and during
2026-08-12 they did: the ladder was pronounced right three times from its tables
while greatEndian could see material standing in AXIS. A ladder is only correct
if the metal is gone, so this sweeps the real nose along the roughing moves and
asks what is left.

    after roughing, does the remaining material stand MORE THAN ONE DEPTH OF CUT
    above the surface roughing is meant to leave?

Wherever it does, a pass is missing, and the report names the Z span, the radius
left, the target and the excess.

WHAT IT DELIBERATELY EXCLUDES, and why each one has to be excluded:

  UNREACHABLE MATERIAL. Behind a boss the tool's back angle casts a shadow the
  tool cannot enter; the finish pass skips it and roughing correctly leaves it
  standing. A first attempt at this metric in test_rough_comp compared against
  the FINAL profile and reported 5.0452 mm on the known-good baseline for
  exactly that reason - "a metric that fails the baseline is not a metric". The
  escape is that THE FINISH PASS ITSELF BRIDGES the shadow, crossing it as one
  straight taper, so its programmed path IS the reachable contour. Taking the
  target from that path excludes the shadow at the root, with no window to guess
  at. Measured on testing_15_6: the finish contour crosses Z-35.30 -> -70.40 as
  a single taper where the drawn profile dips away underneath.

  NEAR-VERTICAL SEGMENTS. At an end face or a shoulder there is no single radius
  at that Z, and comparing a swept surface against one of the two reports the
  whole height of the wall. `radius_at` returns None there - the same guard, and
  the same reason, as test_rough_comp's `radius_span`, whose docstring records
  4.7405 mm at Z-69.4 on testing_15_2 in every mode including Off.

  MATERIAL ABOVE THE FIRST PASS. The stock is modelled as sitting one depth of
  cut above the topmost roughing pass. What lies above that is the operator's
  stock setting, not a pass this ladder failed to make, and a field initialised
  to some arbitrary larger radius would report the difference as leftover
  everywhere.

THE TARGET is the programmed contour offset outward by Offset + Pre-finish
offset - the surface the roughing floor and the stop contour are both built on
since 3df0a4c. The programmed contour is taken from an Off-mode run whose finish
pass carries no offset at all, the same non-circular trick test_rough_comp and
test_comp_overlay use.

THE NEGATIVE CONTROL is the point of the file. A leftover check that cannot fire
proves nothing, so one radius of roughing moves is deleted from the parsed
program and the same measurement must then report a leftover at that radius. No
generated code is touched - the suppression is done to the measurement's input,
so it is exact and cannot drift.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

INI = os.path.join(HERE, 'configs/sim/axis/ncam_demo/lathe-mm.ini')
GEN = os.path.join(HERE, '.claude/skills/lathe-gcode-verify/scripts/gen_project.py')
PROJECTS = os.path.join(HERE,
                        'configs/sim/axis/ncam_demo/ncam/catalogs/lathe/projects')
NOSE, ORIENT = 0.4, 2
STEP = 0.05                       # Z sampling for the leftover scan

# A LEFTOVER NARROWER THAN THIS IN Z IS THE NOSE, NOT A MISSING PASS, and the
# bound is the nose radius rather than a round number. Where the profile turns
# up steeply the round nose cannot reach into the corner and leaves a fillet
# standing; on testing_15_5 the shoulder at Z-19.51 rises 0.93 mm in 0.04 mm of
# Z and leaves 0.7219 mm proud - over the one-depth-of-cut threshold, and
# entirely correct, because no ladder of straight cuts can remove it.
# A MISSING PASS IS WIDE: it spans at least the ladder's own Z step, 2.2 mm on
# these projects, so the two are an order of magnitude apart and the bound does
# not have to be delicate. It is asserted below that the control still fires.
MIN_RUN = 1.5 * NOSE
FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name
          + (('  ' + detail) if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def project_offsets(name):
    """(offset per side, pre-finish offset, depth of cut) in mm, from the XML.

    The project stores inches; the demo config is metric. Read by the parameter
    labels rather than assumed, and the caller asserts the resulting target
    really does stand that far off the profile - which is what catches a unit
    error rather than letting it through as a plausible number.
    """
    t = ET.parse(os.path.join(PROJECTS, name))
    got = {}
    for el in t.getroot().iter('param'):
        got.setdefault((el.get('name') or '').strip(), el.get('value'))
    def mm(label):
        return float(got[label]) * 25.4
    return mm('Offset (per side)'), mm('Pre-finish offset (per side)'), mm('Cut depth')


def radius_at(pts, z, flat=0.5):
    """The radius of a (z, radius) polyline at Z, or None where it is not
    single-valued - a wall, a shoulder, a step. See the module docstring."""
    lo = hi = None
    for (z0, r0), (z1, r1) in zip(pts, pts[1:]):
        if min(z0, z1) - 1e-9 <= z <= max(z0, z1) + 1e-9 and abs(z1 - z0) > 1e-9:
            r = r0 + (r1 - r0) * (z - z0) / (z1 - z0)
            lo = r if lo is None else min(lo, r)
            hi = r if hi is None else max(hi, r)
    if lo is None or hi - lo > flat:
        return None
    return hi


def leftovers(rough, target, doc, P, worst_out=None):
    """Contiguous Z runs where the metal left stands more than `doc` proud.

    -> list of (z_from, z_to, worst excess, radius left there, target there)

    `worst_out`, if given, is filled with (excess, z) for the worst point
    ANYWHERE, threshold or not. A clean report means nothing without it: 0.02 mm
    proud and 0.50 mm proud both pass, and only one of them is comfortable.
    """
    if not rough:
        return []
    zs = [p for m in rough for p in (m.a[2], m.b[2])]
    top = max(p for m in rough for p in (m.a[0], m.b[0]))
    z0, z1 = min(zs) - 2.0, max(zs) + 2.0
    # stock one depth of cut above the first pass - see the module docstring
    f = P.StockField(z0, z1, 0.0, top + doc,
                     P.StockField.columns_for(z0, z1, NOSE))
    dv = P.nose_offset(ORIENT)
    for m in rough:
        f.cut_move(m.a, m.b, NOSE, dv)

    runs, cur = [], None
    z = max(p[0] for p in target)
    zlo = min(p[0] for p in target)
    while z > zlo:
        t = radius_at(target, z)
        if t is not None and z0 <= z <= z1:
            i = max(0, min(f.n - 1, int((z - f.z0) / f.dz)))
            excess = f.outer[i] - t          # positive = metal left ABOVE target
            if worst_out is not None and excess > worst_out[0]:
                worst_out[0], worst_out[1] = excess, z
            if excess > doc:
                if cur is None:
                    cur = [z, z, excess, f.outer[i], t]
                else:
                    cur[1] = z
                    if excess > cur[2]:
                        cur[2], cur[3], cur[4] = excess, f.outer[i], t
            elif cur is not None:
                runs.append(cur)
                cur = None
        z -= STEP
    if cur is not None:
        runs.append(cur)
    return [r for r in runs if abs(r[0] - r[1]) >= MIN_RUN]


def main():
    if not (os.path.isfile(INI) and os.path.isfile(GEN)):
        print('SKIP  demo config or generator not present')
        return
    if not shutil.which('rs274'):
        print('SKIP  rs274 is not installed')
        return

    import lathe_sections as ls
    import ncam_preview as P

    d = tempfile.mkdtemp(prefix='leftover_')
    try:
        def run(project, sec_on):
            out = os.path.join(d, '%s_%d.ngc' % (project[:-4], sec_on))
            subprocess.run([sys.executable, GEN, '--ini', INI,
                            '--project', project, '--out', out,
                            '--config-copy',
                            '--set', 'polyline:param_n_comp=0',
                            '--set', 'polyline:param_sectioning=%d' % sec_on],
                           capture_output=True, text=True)
            if not os.path.isfile(out):
                return None
            tp = P.parse_program(out, INI)
            return None if tp.error else tp

        def phase(tp, rough):
            out = []
            for m in tp.moves:
                if m.op != 'Lathe Polyline':
                    continue
                fin = P.FINISH in m.subs or P.PREFINISH in m.subs
                if rough and not fin and m.kind != 'rapid':
                    out.append(m)
                elif not rough and P.FINISH in m.subs and m.kind == 'feed':
                    out.append(m)
            return out

        first = {}
        for project in ('testing_15_5.xml', 'testing_15_6.xml'):
            f_off, pf_off, doc = project_offsets(project)
            print('\n%s   offset %.4f + pre-finish %.4f, depth of cut %.4f'
                  % (project, f_off, pf_off, doc))
            for sec_on in (0, 1):
                tag = '%s sect %s' % (project[:-4], 'ON ' if sec_on else 'off')
                tp = run(project, sec_on)
                check('%s generates and runs' % tag, tp is not None)
                if tp is None:
                    continue

                fin, rough = phase(tp, False), phase(tp, True)
                if len(fin) < 5 or not rough:
                    check('%s has a finish pass and roughing' % tag, False,
                          '%d finish, %d roughing' % (len(fin), len(rough)))
                    continue
                prog = [(m.a[2], m.a[0]) for m in fin]
                prog.append((fin[-1].b[2], fin[-1].b[0]))

                target = ls.entry_contour(prog, f_off + pf_off, 0)
                # the guard that catches a unit error rather than trusting it
                got = radius_at(target, -10.0)
                want = radius_at(prog, -10.0)
                check('   %s the target stands off the profile by %.4f'
                      % (tag, f_off + pf_off),
                      got is not None and want is not None
                      and abs(got - want - (f_off + pf_off)) < 0.03,
                      'measured %s at Z-10'
                      % ('%.4f' % (got - want) if got and want else 'nothing'))

                worst = [-1e9, 0.0]
                runs = leftovers(rough, target, doc, P, worst)
                print('      worst standing %.4f mm at Z%.2f   (threshold %.4f,'
                      ' %d wide region(s))'
                      % (worst[0], worst[1], doc, len(runs)))
                if runs:
                    for zf, zt, ex, left, tgt in runs:
                        print('      LEFT %.4f mm over Z%.2f..%.2f   '
                              'r%.4f standing, target r%.4f'
                              % (ex, zf, zt, left, tgt))
                check('   %s leaves no metal more than one depth of cut proud'
                      % tag, not runs,
                      '%d region(s), worst %.4f mm at Z%.2f'
                      % (len(runs), max(r[2] for r in runs),
                         max(runs, key=lambda r: r[2])[0]) if runs else '')

                if sec_on == 0:
                    first[project] = (rough, target, doc)

        # ---------------------------------------------------------- control
        # A check that cannot fire proves nothing. Delete one radius of
        # roughing from the parsed program and the same measurement must find
        # the hole. Nothing generated is touched, so this is exact.
        print()
        ok = False
        for project, (rough, target, doc) in first.items():
            radii = sorted({round(m.a[0], 4) for m in rough
                            if abs(m.b[0] - m.a[0]) < 1e-6}, reverse=True)
            if len(radii) < 6:
                continue
            victim = radii[len(radii) // 3]
            cut = [m for m in rough if abs(round(m.a[0], 4) - victim) > 1e-9]
            runs = leftovers(cut, target, doc, P)
            print('      CONTROL %s without r%.4f: %d leftover region(s)%s'
                  % (project[:-4], victim, len(runs),
                     ', worst %.4f mm at Z%.2f'
                     % (max(r[2] for r in runs),
                        max(runs, key=lambda r: r[2])[0]) if runs else ''))
            check('CONTROL: deleting the r%.4f pass from %s is DETECTED'
                  % (victim, project[:-4]), bool(runs),
                  'the measurement cannot see a missing pass, so a clean '
                  'report from it means nothing')
            ok = True
        check('the control ran at all', ok)

    finally:
        shutil.rmtree(d, ignore_errors=True)

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('No metal is left standing more than one depth of cut proud.')


if __name__ == '__main__':
    main()
