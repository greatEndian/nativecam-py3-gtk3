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

THE NEGATIVE CONTROL is the point of the file, and it runs on EVERY demo project
that can carry it - 21 of them - not on one. A gate validated on a single
geometry is how this one came to be trusted while failing on the next project
along. No generated code is touched: the mutilation is done to the
measurement's input, so it is exact and cannot drift.

WHAT IT MUTILATES, AND WHY IT IS NOT ONE PASS. Until 2026-08-15 it deleted a
single radius, chosen one third of the way down the ladder. That fired on
testing_15_5 and not on testing_15_6, and surveying all 21 runnable demo
projects showed it fired on only 7 of them. Deleting one pass is simply not a
valid mutilation, for two separate reasons:

  A SHALLOW PASS IS OFTEN REDUNDANT. The final roughed surface at any Z is the
  DEEPEST pass covering it. On a monotone profile every pass runs the whole
  length, so only the deepest one shapes the result and deleting a shallower one
  changes nothing at all - measured on testing_10, where removing each of the
  seven outermost radii in turn left the worst standing figure identical to four
  decimals, 0.2505 mm at Z-14.47 every time.

  WHERE IT IS NOT REDUNDANT, IT IS NARROW. A pass is the deepest only in the
  sliver its neighbour below does not reach, and on a rising profile that sliver
  is thin. On testing_15_6 deleting r29.6520 leaves 0.9580 mm standing - nearly
  twice the threshold - across 0.350 mm of Z, which MIN_RUN then discards. The
  band shrinks monotonically down that ladder, 3.75 mm at the top to 0.05 mm at
  the bottom, so removing any of the lower fourteen passes is invisible.

So it does not delete passes at all. IT LEAVES A Z WINDOW UNROUGHED - every
roughing move is trimmed out of a 6 mm slice - which is the failure actually
worth catching, a region of the part no pass reached, and is the shape the
behind-the-boss bug had. It is geometry-independent in a way no choice of radius
was: whatever the ladder looks like, metal that nothing cut stands at stock.

Two selection rules were tried and measured before this one, and both are
recorded because each looked reasonable:

  THE TWO DEEPEST RADII fired on 20 of 21, failing on testing_14_inside. That
  project is BORED - its passes climb r13.36 -> r16.24 - so its final surface is
  the LARGEST radius and the two smallest are the passes furthest from the part.
  Deleting them changes nothing, exactly as deleting a redundant shallow pass
  does.

  THE TWO RADII NEAREST THE TARGET, meant to fix that without guessing the
  direction, was worse: 16 of 21. Being near the target does not mean being the
  surface over any length of it.

WHERE THE WINDOW GOES is itself measured, and needs both halves. It is centred
on the longest stretch where roughing already machines to within one depth of
cut AND where roughing demonstrably cut - the intact surface stands a depth of
cut below the stock. Without the first, a mid-span window lands behind a boss or
on a wall and removing it changes nothing (measured: missed on current_work,
15_2, 15_3, 15_4). Without the second, a stretch where the STOCK already sits
near the target counts as well machined and breaking it removes nothing that was
there - which is how testing_15_3 slipped through. With both, 21 of 21.

Choosing where to break it from the intact program is not circular: the detector
is never asked where to look, only whether it noticed.

AND THE LIMITATION THAT SURVEY EXPOSED IS REAL, not a property of the control:
this gate cannot see a single missing pass on most geometry. That is not a
threshold to tune - the metal genuinely is not there to find in the redundant
case, and in the narrow case it is a ridge the width of a nose fillet. It is why
`test_x_continuity` exists and why it, not this file, is what caught the missing
pass behind the boss on testing_15_6. The two gates are complementary and
neither replaces the other.
"""
import glob
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
# IT WAS ARGUED HERE THAT A MISSING PASS IS WIDE - "at least the ladder's own Z
# step, 2.2 mm on these projects, so the two are an order of magnitude apart".
# THAT IS FALSE, and the survey of 2026-08-15 measured it: a pass is the deepest
# only in the sliver the pass below does not reach, so on testing_15_6 the band
# left by removing one runs 3.75 mm at the top of the ladder down to 0.05 mm at
# the bottom. Fourteen of its twenty-six passes leave less than this bound.
#
# The bound stays anyway, because the case it excludes is real and the
# alternative is worse: a nose fillet at a concave corner is genuinely not a
# missing pass, and admitting every 0.05 mm ridge would make the gate fire on
# correct programs. What changed is the honesty about it - this gate does not
# see a single missing pass on most geometry, `test_x_continuity` is what does,
# and the control below no longer pretends otherwise. See the module docstring.
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


class Seg(object):
    """A move stripped to the two things the measurement reads."""
    __slots__ = ('a', 'b')

    def __init__(self, a, b):
        self.a, self.b = a, b


def trim_out(moves, zlo, zhi):
    """The moves with the Z window [zlo, zhi] cut out, endpoints interpolated.

    Removing whole moves would take away cutting outside the window too and
    make the control coarser than the thing it claims to test. Splitting them
    leaves exactly one unroughed slice, which is the failure being modelled: a
    region of the part that no pass reached.
    """
    out = []
    for m in moves:
        z0, z1 = m.a[2], m.b[2]
        if min(z0, z1) >= zhi or max(z0, z1) <= zlo:
            out.append(m)
            continue

        def at(z, m=m, z0=z0, z1=z1):
            if abs(z1 - z0) < 1e-12:
                return m.a
            t = (z - z0) / (z1 - z0)
            return tuple(m.a[i] + (m.b[i] - m.a[i]) * t for i in range(3))

        if min(z0, z1) < zlo:
            out.append(Seg(m.a if z0 < z1 else at(zlo),
                           at(zlo) if z0 < z1 else m.b))
        if max(z0, z1) > zhi:
            out.append(Seg(at(zhi) if z0 < z1 else m.a,
                           m.b if z0 < z1 else at(zhi)))
    return out


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
        def run(project, sec_on, rdir=0):
            out = os.path.join(d, '%s_%d_%d.ngc' % (project[:-4], sec_on, rdir))
            subprocess.run([sys.executable, GEN, '--ini', INI,
                            '--project', project, '--out', out,
                            '--config-copy',
                            '--set', 'polyline:param_n_comp=0',
                            '--set', 'polyline:param_dir=%d' % rdir,
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
            # ALL THREE ROUGHING DIRECTIONS. Back to front has never been asked
            # to leave no metal standing, and before analysis/054 it could not
            # have: it decomposed the part differently - 40 level cuts against
            # 45 - rather than cutting the same ones in reverse order.
            #
            # AND BOTH DIRECTIONS - added 2026-08-18. It had NEVER been
            # generated by this file or any other, which is exactly how it
            # stayed unimplemented while its tooltip promised alternation: on
            # testing_15_6 with Sectioning on it made 28 of front-to-back's 44
            # cuts, all of them the same way round, and left 7.49 mm standing
            # at Z-67 behind the boss - see analysis/060. A direction no gate
            # ever runs is a direction nobody is measuring.
            for sec_on, rdir in ((0, 0), (1, 0), (0, 1), (1, 1),
                                 (0, 2), (1, 2)):
                tag = '%s sect %s %s' % (project[:-4],
                                         'ON ' if sec_on else 'off',
                                         ('f2b', 'b2f', 'alt')[rdir])
                tp = run(project, sec_on, rdir)
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

                if sec_on == 0 and rdir == 0:
                    first[project] = (rough, target, doc)

        # ---------------------------------------------------------- control
        # A check that cannot fire proves nothing, so this deletes the two
        # deepest roughing radii and the same measurement must find the hole.
        # See the module docstring for why it is the deepest two and not one
        # anywhere in the ladder. Nothing generated is touched.
        #
        # RUN ON EVERY DEMO PROJECT THAT CAN CARRY IT. Validating a gate on one
        # geometry is how it came to be trusted while failing on the next
        # project along: the old control passed on testing_15_5 and had never
        # been asked about any other shape.
        def prepare(project):
            """(rough, target, doc) for a project, or (None, why)."""
            tp = run(project, 0)
            if tp is None:
                return None, 'does not generate or rs274 refuses it'
            try:
                f_off, pf_off, doc = project_offsets(project)
            except (KeyError, ValueError):
                return None, 'no polyline offsets in the XML'
            fin, rough = phase(tp, False), phase(tp, True)
            if len(fin) < 5 or not rough:
                return None, ('no polyline roughing and finish pass (%d, %d)'
                              % (len(fin), len(rough)))
            lev = [m for m in rough if abs(m.b[0] - m.a[0]) < 1e-6
                   and abs(m.b[2] - m.a[2]) > 1e-6]
            if len({round(m.a[0], 4) for m in lev}) < 4:
                return None, 'fewer than four roughing levels'
            prog = [(m.a[2], m.a[0]) for m in fin]
            prog.append((fin[-1].b[2], fin[-1].b[0]))
            return (rough, ls.entry_contour(prog, f_off + pf_off, 0), doc), None

        print()
        fired = ran = 0
        for project in sorted(os.path.basename(p) for p in
                              glob.glob(os.path.join(PROJECTS, '*.xml'))):
            got, why = prepare(project)
            if got is None:
                print('      CONTROL %-24s skipped - %s' % (project[:-4], why))
                continue
            rough, target, doc = got
            # WHERE TO BREAK IT: the longest stretch roughing already
            # machines WELL, and where it demonstrably cut. Both halves are
            # needed. Without the first the window lands behind a boss or on a
            # wall and removing it changes nothing (measured: a mid-span window
            # missed on current_work, 15_2, 15_3 and 15_4). Without the second,
            # a stretch where the STOCK already sits near the target counts as
            # well machined, and breaking it removes nothing that was there -
            # which is exactly how testing_15_3 slipped through.
            zs = [q for m in rough for q in (m.a[2], m.b[2])]
            fz0, fz1 = min(zs) - 2.0, max(zs) + 2.0
            top = max(q for m in rough for q in (m.a[0], m.b[0]))
            f0 = P.StockField(fz0, fz1, 0.0, top + doc,
                              P.StockField.columns_for(fz0, fz1, NOSE))
            dv = P.nose_offset(ORIENT)
            for m in rough:
                f0.cut_move(m.a, m.b, NOSE, dv)
            best, cur = (0.0, None), None
            z = max(q[0] for q in target)
            zl = min(q[0] for q in target)
            while z > zl:
                t = radius_at(target, z)
                good = False
                if t is not None and fz0 <= z <= fz1:
                    i = max(0, min(f0.n - 1, int((z - f0.z0) / f0.dz)))
                    good = ((f0.outer[i] - t) <= doc
                            and (top + doc) - f0.outer[i] > doc)
                if good:
                    cur = [z, z] if cur is None else [cur[0], z]
                else:
                    if cur and abs(cur[0] - cur[1]) > best[0]:
                        best = (abs(cur[0] - cur[1]), cur)
                    cur = None
                z -= STEP
            if cur and abs(cur[0] - cur[1]) > best[0]:
                best = (abs(cur[0] - cur[1]), cur)
            if best[1] is None or best[0] < 4 * MIN_RUN:
                print('      CONTROL %-24s skipped - no stretch roughing '
                      'machines cleanly' % project[:-4])
                continue
            W = min(6.0, best[0] * 0.6)
            mid = (best[1][0] + best[1][1]) / 2.0
            zlo, zhi = mid - W / 2.0, mid + W / 2.0
            cut = trim_out(rough, zlo, zhi)
            # WORSE IN EITHER READING. Neither measure is sufficient alone: on
            # current_work the worst excess is 1.7434 intact and after, because
            # the global worst sits on a feature the window never touches while
            # the new metal appears elsewhere; on testing_14_inside a region
            # already stands proud, so the new metal merges into it and the
            # count does not move. The mutilation has to make the report worse,
            # and it may do so either by finding new ground or by leaving more
            # metal.
            w_was, w_now = [-1e9, 0.0], [-1e9, 0.0]
            was = leftovers(rough, target, doc, P, w_was)
            now = leftovers(cut, target, doc, P, w_now)
            ran += 1
            hit = bool(now) and (len(now) > len(was)
                                 or w_now[0] > w_was[0] + 0.5 * doc)
            fired += bool(hit)
            print('      CONTROL %-24s intact %d region(s) worst %.4f, '
                  'Z%.2f..%.2f unroughed -> %d region(s) worst %.4f at Z%.2f'
                  % (project[:-4], len(was), w_was[0], zlo, zhi,
                     len(now), w_now[0], w_now[1]))
            check('CONTROL: %s - an unroughed %.1f mm window is DETECTED'
                  % (project[:-4], W), hit,
                  'worst standing went %.4f -> %.4f, less than the %.4f more '
                  'metal an unroughed window must leave - the measurement '
                  'cannot see metal it was asked to find, so a clean report '
                  'from it on this geometry means nothing'
                  % (w_was[0], w_now[0], 0.5 * doc))
        check('the control ran on several geometries, not one',
              ran >= 10, 'only %d project(s) could carry it' % ran)
        print('      the control fired on %d of the %d projects that carry it'
              % (fired, ran))

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
