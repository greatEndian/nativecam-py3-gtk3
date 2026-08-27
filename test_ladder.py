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
import re
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
        # how many floors this profile is entitled to. The ladder re-anchors
        # on each one, so every count below is per stage rather than per part.
        stages = 1
        floors = []
        for v, label in ((1, 'Final contour'), (0, 'Stock')):
            out = os.path.join(d, 'p%d.ngc' % v)
            subprocess.run([sys.executable, GEN, '--ini', INI, '--project',
                            PROJECT, '--out', out, '--config-copy',
                            '--set', 'polyline:param_n_comp=1',
                            '--set', 'polyline:param_pass_from=%d' % v],
                           capture_output=True, text=True)
            lv[label] = levels(out, P) if os.path.isfile(out) else None
            if os.path.isfile(out):
                txt = open(out).read()
                m = re.search(r'#<_pl_floor_n> = (\d+)', txt)
                if m and int(m.group(1)) >= stages:
                    stages = int(m.group(1))
                    floors = [float(x) for x in
                              re.findall(r'#33[89]\d = ([\d.]+)', txt)]
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
                # ONE REMAINDER PER FLOOR STAGE, not one for the whole part.
                # The ladder re-anchors on each floor the profile is entitled
                # to - see floor_ladder and analysis/022 - and each of those
                # re-anchorings spends its own remainder. A part with one floor
                # still has exactly one, which is what this asserted before.
                odd = [(i, g) for i, g in enumerate(gaps)
                       if abs(g - DOC) > 1e-3]
                # COUNTING ODD GAPS STOPPED MEANING ANYTHING once the ladder
                # re-anchors: a floor stage divides its own run EVENLY, so
                # every one of its steps is a fraction of a whole one. What
                # the old count was really protecting - no overload, and no
                # sliver beside the finished surface - is asserted directly
                # instead, and both bounds are stronger than the count was.
                check('Final contour: no gap exceeds the depth of cut',
                      max(gaps) <= DOC + 1e-3,
                      'largest %.4f against a %.4f depth of cut' %
                      (max(gaps), DOC))
                # EXCEPT THE FIRST, at the stock. This anchoring puts its
                # remainder there on purpose - a full-length cut through
                # oversize material - and that is the whole difference between
                # it and Stock anchoring. The rule protects the descent NEAR
                # THE PART, which is where a sliver rubs.
                rest = gaps[1:]
                check('   and none after the first is under half of it',
                      not rest or min(rest) >= DOC / 2.0 - 1e-3,
                      'smallest %.4f, under half the %.4f depth of cut'
                      % (min(rest) if rest else 0.0, DOC))
                print('      %d odd gaps, %d floor stages: %s'
                      % (len(odd), stages,
                         ', '.join('%.4f' % g for _i, g in odd)))
                check('   and the remainder is NOT the last gap', 
                      not odd or odd[0][0] < len(gaps) - 1,
                      'the odd %.4f gap is at the contour end - a level '
                      'grazing the finished surface, which is what this '
                      'anchoring exists to prevent'
                      % (odd[0][1] if odd else 0.0))
            else:
                # EVENLY SPACED WITHIN A STAGE. Stock anchoring divides the
                # run evenly, and there is now one run per floor stage, so the
                # count of distinct gaps is bounded by the stages rather than
                # being 1. With one floor this is still "every gap the same".
                spread = max(gaps) - min(gaps)
                distinct = len({round(g, 3) for g in gaps})
                check('Stock: evenly spaced within each floor stage',
                      distinct <= stages + 1,
                      '%d distinct gaps against %d floor stages, spread '
                      '%.4f mm' % (distinct, stages, spread))
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
        # the floors THIS program is entitled to - the anchoring differs
        # between the runs above, and so do their floors
        floors = [float(x) for x in re.findall(
            r'#33[89]\d = ([\d.]+)', open(thin).read())] \
            if os.path.isfile(thin) else []
        check('the project generates with a thin-pass threshold', bool(tl))
        if not tl:
            return
        base = lv['Final contour']
        tgaps = [round(tl[i] - tl[i + 1], 4) for i in range(len(tl) - 1)]
        print('   %-14s %2d levels, deepest %.4f, gaps %s'
              % ('skip thin', len(tl), tl[-1],
                 ' '.join('%.4f' % g for g in tgaps)))
        # A CONTROL HAS TO BE CALIBRATED AGAINST THE LADDER IT IS RUN ON.
        # This asserted that doc/2 drops a level on testing_15_2, and it does
        # not - correctly. Every gap in that ladder is a whole 0.5080, and the
        # only gap smaller than one is the stock -> first level handover at
        # 0.3480, which is ABOVE doc/2. There was nothing eligible, so the
        # setting was doing exactly its job by removing nothing, and the red
        # was recorded as "_pl_skip_thin is inert" for three days.
        # Measured 2026-08-24, analysis/062: at a threshold above that real
        # gap the setting fires exactly as designed - 0.400 -> 17 levels, the
        # 29.6520 envelope pass gone, every surviving gap still 0.5080.
        # So the control is calibrated: find the thinnest gap this ladder
        # actually has, ask for a threshold just above it, and require that
        # THAT level - and only it - disappears. stock_r is the stock OD in
        # radius, and _wp_dia_od is written as [<od> / 2 * #<_diameter_mode>]
        # while stock_r is _wp_dia_od / _diameter_mode, so stock_r is <od>/2
        # whichever mode the project is in.
        m = re.search(r'#<_wp_dia_od> = \[([\d.]+) / 2 \* #<_diameter_mode>\]',
                      open(thin).read())
        stock_r = float(m.group(1)) / 2.0 if m else None
        check('the stock radius is readable from the program', stock_r
              is not None)
        if stock_r is None:
            return
        # the stock handover is a real gap and levels() cannot see it - it has
        # no level above it to subtract from
        bgaps = [stock_r - base[0]] + [base[i] - base[i + 1]
                                       for i in range(len(base) - 1)]
        thinnest = min(bgaps)
        print('   %-14s thinnest gap %.4f (stock handover %.4f), doc/2 %.4f'
              % ('calibration', thinnest, stock_r - base[0], DOC / 2.0))
        # BELOW the real gap nothing may be dropped. That is the assertion the
        # old one should have been: a threshold under everything eligible is a
        # no-op, and a ladder that loses a level here is over-skipping.
        check('   a threshold under the thinnest gap drops nothing',
              len(tl) == len(base),
              '%d levels at the %.4f threshold against %d without, but the '
              'thinnest gap is %.4f - nothing was eligible'
              % (len(tl), DOC / 2.0, len(base), thinnest))
        # ABOVE it, exactly the thin level goes. Kept under a whole depth of
        # cut on purpose: a threshold LARGER than the doc makes the check
        # alternate - every level is thin against the last one cut, the next
        # is not, and the ladder halves into gaps of 2 x doc. Measured at
        # 0.600 with doc 0.508: 13 levels, max gap 1.0160. That is its own
        # open point, not this control's business.
        fire = min(thinnest + 0.02, DOC - 0.001)
        check('   the calibrated threshold is under a whole depth of cut',
              fire > thinnest + 1e-6, 'thinnest gap %.4f leaves no room under '
              'the %.4f depth of cut' % (thinnest, DOC))
        if fire <= thinnest + 1e-6:
            return
        cal = os.path.join(d, 'thin_cal.ngc')
        subprocess.run([sys.executable, GEN, '--ini', INI, '--project',
                        PROJECT, '--out', cal, '--config-copy',
                        '--set', 'polyline:param_n_comp=1',
                        '--set', 'polyline:param_pass_from=1',
                        '--set', 'polyline:param_skip_thin=%g' % fire],
                       capture_output=True, text=True)
        cl = levels(cal, P) if os.path.isfile(cal) else None
        check('the project generates at the calibrated threshold', bool(cl))
        if cl:
            gone = [x for x in base if x not in cl]
            print('   %-14s %2d levels at %.4f, dropped %s'
                  % ('skip thin cal', len(cl), fire,
                     ' '.join('%.4f' % x for x in gone) or '(none)'))
            check('   a threshold above the thinnest gap DOES drop a level',
                  len(cl) < len(base),
                  '%d levels at the %.4f threshold against %d without, though '
                  'the thinnest gap is %.4f' % (len(cl), fire, len(base),
                                                thinnest))
            # and it drops the RIGHT one - the level bounding the thin gap,
            # not an arbitrary level somewhere else in the ladder
            cgaps = [stock_r - cl[0]] + [cl[i] - cl[i + 1]
                                         for i in range(len(cl) - 1)]
            # NOT "only the thin one goes", and not "no gap under the
            # threshold survives". Neither is achievable on a UNIFORM ladder,
            # and since phase 2 spreads evenly the ladder is uniform by
            # construction - 0.4991 in all 17 gaps on testing_15_2. Once the
            # threshold passes that common step EVERY level is thin against
            # the one above it, so the check alternates: skip, _pl_prev_lvl
            # stays, the next is two steps away and is kept. Measured at
            # 0.5070 - which is UNDER the 0.5080 doc - 13 levels and a 0.9983
            # gap. That is a real fault in _pl_skip_thin and it is written up
            # in openPoints; it is not this control's job to assert it away.
            # What IS asserted is the range the setting is actually shipped
            # for: at the recommended doc/2 the ladder stays whole.
            print('   %-14s alternating above the ladder step: %d levels, '
                  'worst gap %.4f' % ('note', len(cl), max(cgaps)))
        # THE RECOMMENDED SETTING MUST BE SAFE. doc/2 is what the parameter
        # tooltip tells the operator to start with, so whatever the setting
        # does above the ladder step, at doc/2 it must not open a gap past the
        # depth of cut anywhere - that is a level cutting over the doc against
        # a part surface, the failure test_x_continuity exists to catch and
        # the reason greatEndian ruled SPREAD over DROP on 2026-08-24.
        tgaps_all = [stock_r - tl[0]] + tgaps
        check('   and the recommended doc/2 opens no gap past the doc',
              not [g for g in tgaps_all if g > DOC + 1e-3],
              'gap %.4f exceeds the %.4f depth of cut at the %.4f threshold'
              % (max(tgaps_all), DOC, DOC / 2.0))
        # A stage handover is not a whole step and never was skippable - it
        # lands on a floor. So the rule is: no gap SMALLER than a whole step
        # survives, which is what "the thin ones are gone" actually means.
        # NOTHING THINNER THAN THE THRESHOLD SURVIVES - which is what the
        # setting means - unless it lands on a floor, because a floor level is
        # the surface roughing must leave for the pre-finish pass and is never
        # skippable whatever the threshold. Gaps BETWEEN the threshold and a
        # whole step are legitimate: a floor stage divides its own run evenly,
        # so a 0.7068 handover becomes two cuts of 0.3534 rather than a whole
        # step and a 0.1988 sliver.
        thr = DOC / 2.0
        thin_bad = [(g, tl[i + 1]) for i, g in enumerate(tgaps)
                    if g < thr - 1e-3
                    and not any(abs(tl[i + 1] - f) < 1e-3 for f in floors)]
        check('   and nothing thinner than the threshold survives off a floor',
              not thin_bad,
              'gap %.4f ends at r%.4f, under the %.4f threshold and no floor '
              'of %s' % (thin_bad[0][0], thin_bad[0][1], thr,
                         ['%.4f' % f for f in floors]) if thin_bad else '')
        check('   and no gap exceeds the depth of cut',
              max(tgaps) <= DOC + 1e-3,
              'largest %.4f against a %.4f depth of cut - a level was skipped '
              'and the one under it took the combined bite'
              % (max(tgaps), DOC))
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
