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

        # --- no pass starts in front of the definition's Begin Z -----------
        # greatEndian: the compensated entry is geometrically right against the
        # contour, but on the real part the nose riding onto a first segment
        # that runs FORWARD of the origin leaves a bump at the start. So every
        # pass - roughing, pre-finish and finish, in every mode - begins at the
        # polyline's own Begin Z.
        #
        # Taken from _pl_begin_z, NOT from record 1 of the lathe array: that
        # record is the first ITEM's endpoint, Z+1.0 on this project, and using
        # it silently did nothing.
        import re
        prj = os.path.join(os.path.dirname(INI), 'ncam', 'catalogs', 'lathe',
                           'projects', PROJECT)
        begin_z = 0.0
        if os.path.isfile(prj):
            txt = open(prj, encoding='utf-8').read()
            m = re.search(r'call="#param_b_z"[^>]*?value="([-\d.]+)"', txt)
            if m:
                begin_z = float(m.group(1)) * 25.4
        for mode in (0, 1, 2):
            out = os.path.join(d, 'bz%d.ngc' % mode)
            subprocess.run([sys.executable, GEN, '--ini', INI, '--project',
                            PROJECT, '--out', out, '--config-copy', '--set',
                            'polyline:param_n_comp=%d' % mode],
                           capture_output=True, text=True)
            if not os.path.isfile(out):
                continue
            tp = P.parse_program(out, INI)
            if tp.error:
                continue
            starts = {}
            rgh = [m for m in tp.moves if m.op == 'Lathe Polyline'
                   and not m.subs and m.kind == 'feed'
                   and abs(m.b[0] - m.a[0]) < 1e-6 and m.b[2] < m.a[2] - 1e-6]
            if rgh:
                starts['roughing'] = max(m.a[2] for m in rgh)
            for tag, name in ((P.PREFINISH, 'pre-finish'), (P.FINISH, 'finish')):
                fd = [m for m in tp.moves if m.op == 'Lathe Polyline'
                      and tag in m.subs and m.kind == 'feed']
                if fd:
                    starts[name] = fd[0].b[2]
            # MEASURED ON THE CUT, NOT THE TIP. The tip leads the cutting
            # edge by the orientation term, so a tip at Begin Z puts the cut
            # one term PAST it - which is what an earlier version of this
            # clamp did, and it disagreed with a project that needed no clamp
            # at all. The bound belongs on the edge that removes metal.
            oz = 0.0
            m = re.search(r'#<_pl_rgh_oz> = ([\d.]+)', open(out).read())
            if m:
                oz = float(m.group(1))
            # ROUGHING is bounded on the cut - it enters above the material,
            # so its tip can sit one orientation term in front of the
            # reference. The CONTOUR passes are bounded on the TIP: pulling
            # them back far enough to put their cut on the reference drives
            # the lead-in 0.5039 mm into the part, which breaks the rule that
            # a lead may not end in material. Two different bounds because two
            # different things constrain them, and the test says so.
            # THE TIP, at Begin Z. greatEndian: "when we are at 0.0 Z and X
            # at driven diameter we will be at cutting level already .. we are
            # reaching roughing diameter in the stock". The lead-in descends to
            # the level radius at the tip's own start, so it is the tip that
            # has to be on the reference - bound the CUT there instead and the
            # tool arrives at diameter one orientation term INSIDE the stock,
            # which is the complaint. That version was written, measured and
            # replaced; this assertion is what tells the two apart.
            rc = starts.get('roughing')
            if rc is not None:
                check('mode %d: roughing is at diameter by Begin Z %.4f'
                      % (mode, begin_z), abs(rc - begin_z) < 1e-3,
                      'reaches the cutting radius at %+.4f, which is %.4f mm '
                      'inside the stock' % (rc, begin_z - rc))
            # THE CONTOUR PASSES GET THE SAME STARTING BEHAVIOUR, by extending
            # their first segment to Begin Z rather than by bounding Z alone.
            # A roughing level is a straight line at one radius, so moving its
            # start in Z keeps it on the level; a contour entry moved in Z
            # alone comes OFF the contour and the first cut becomes a diagonal
            # onto it. So this is an equality, and the radius is free to follow
            # the segment - on testing_15_4's chamfer it does, from -0.1172 to
            # exactly 0 with the radius carried back along the chamfer.
            off = {k: v for k, v in starts.items()
                   if k != 'roughing' and abs(v - begin_z) > 1e-3}
            check('mode %d: every contour pass starts AT Begin Z' % mode,
                  not off,
                  ', '.join('%s at %+.4f' % (k, v) for k, v in off.items()))

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
        # --- no level may run beside the pre-finish contour -----------------
        # greatEndian, testing_15_4: the deepest level ran the whole part
        # 0.0160 mm from the pre-finish contour - two passes in the same spot,
        # which is where chatter starts.
        #
        # The cause was the stop table's EXTENSION, not the level's length. It
        # exists to carry a level from the floor allowance it stops on to the
        # pre-finish allowance the table holds - 0.90 to 1.00 mm on every
        # legitimate case across two projects - and unbounded it carried the
        # deepest level 19.4436 mm across a cylinder where that level is below
        # the local roughing floor and has no business cutting.
        #
        # Truncating the level afterwards was tried first (224c0b9) and is
        # wrong: it measures "material removed" as level - contour, which is
        # what is left BELOW the level rather than what it takes, and it cut 10
        # honest passes behind the boss down to 1.299 mm. Reverted.
        chamfer = os.path.join(os.path.dirname(INI), 'ncam', 'catalogs',
                               'lathe', 'projects', 'testing_15_4.xml')
        if os.path.isfile(chamfer):
            o = os.path.join(d, 'beside.ngc')
            subprocess.run([sys.executable, GEN, '--ini', INI, '--project',
                            'testing_15_4.xml', '--out', o, '--config-copy'],
                           capture_output=True, text=True)
            if os.path.isfile(o):
                import re as _re
                vals = {}
                for ln in open(o):
                    m = _re.match(r'#(\d+) = (-?[\d.]+)\s*$', ln.strip())
                    if m and 4400 <= int(m.group(1)) < 4600:
                        vals[int(m.group(1))] = float(m.group(2))
                stop, i = [], 4400
                while i in vals and i + 1 in vals:
                    stop.append((vals[i], vals[i + 1]))
                    i += 2

                def stop_r(z):
                    best = None
                    for (z0, r0), (z1, r1) in zip(stop, stop[1:]):
                        if (min(z0, z1) - 1e-9 <= z <= max(z0, z1) + 1e-9
                                and abs(z1 - z0) > 1e-9):
                            r = r0 + (r1 - r0) * (z - z0) / (z1 - z0)
                            best = r if best is None else max(best, r)
                    return best

                t = P.parse_program(o, INI)
                beside = []
                if stop and not t.error:
                    for m in t.moves:
                        if (m.op != 'Lathe Polyline' or m.subs
                                or m.kind != 'feed'
                                or abs(m.b[0] - m.a[0]) > 1e-6
                                or m.b[2] >= m.a[2] - 1e-6):
                            continue
                        span, close = m.a[2] - m.b[2], 0.0
                        z = m.a[2]
                        while z > m.b[2]:
                            sr = stop_r(z)
                            if sr is not None and 0 <= m.a[0] - sr < 0.10:
                                close += 0.1
                            z -= 0.1
                        if close > 2.0:
                            beside.append((m.a[0], span, close))
                check('no level runs beside the pre-finish contour',
                      not beside,
                      'r%.4f runs %.1f mm of its %.1f within 0.10 mm of it'
                      % (beside[0][0], beside[0][2], beside[0][1])
                      if beside else '')

        # --- a level is lead-in, cut, lead-out - and nothing else -----------
        # greatEndian: "there is movement lead in, then horizontal pass, then
        # next micro lead in, and then lead out, which is wrong - there has to
        # be lead in, horizontal and lead out only".
        #
        # The micro move was a descent onto the pre-finish contour, added when
        # the chamfer level still stopped 0.4190 mm off it. Once the extension
        # was made to carry the level to the feature boundary the descent had
        # nothing left to do, and an 0.081 mm move between the cut and the
        # lead-out is exactly the kind of thing that shakes a machine.
        if os.path.isfile(chamfer):
            o = os.path.join(d, 'shape.ngc')
            subprocess.run([sys.executable, GEN, '--ini', INI, '--project',
                            'testing_15_4.xml', '--out', o, '--config-copy'],
                           capture_output=True, text=True)
            t = P.parse_program(o, INI) if os.path.isfile(o) else None
            extra = []
            if t is not None and not t.error:
                mv = [m for m in t.moves if m.op == 'Lathe Polyline'
                      and not m.subs]
                for i, m in enumerate(mv):
                    if (m.kind != 'feed' or abs(m.b[0] - m.a[0]) > 1e-6
                            or m.b[2] >= m.a[2] - 1e-6):
                        continue
                    # everything between this cut and the next rapid must be
                    # ONE move - the lead-out
                    run = []
                    for n in mv[i + 1:]:
                        if n.kind == 'rapid':
                            break
                        run.append(n)
                    if len(run) > 1:
                        extra.append((m.a[0], len(run),
                                      min(((x.b[2] - x.a[2]) ** 2
                                           + (x.b[0] - x.a[0]) ** 2) ** 0.5
                                          for x in run)))
            check('a level is cut then lead-out, with nothing between',
                  not extra,
                  'r%.4f has %d moves after its cut, the shortest %.3f mm'
                  % extra[0] if extra else '')

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
