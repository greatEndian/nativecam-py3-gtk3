#!/usr/bin/env python3
# coding: utf-8
"""Leads do not end in the part, and compensation does not shorten them.

Standalone, like the other test_*.py here - run it directly, no pytest.

greatEndian's criterion, stated 2026-08-04: *"lead in and lead out can not end
in the part or stock therefore we need them, to be like when comp off there is
no play"*. Two separate claims, and this asserts both:

1. NO LEAD MOVE REMOVES MATERIAL. Measured the only way that means anything -
   sweep the real nose circle along the move against the material as it stands
   AT THAT MOMENT in the program, not against the raw bar. Roughing has already
   been past; a lead is clear if it takes nothing off what roughing left.

2. THE LEAD IS THE LENGTH THAT WAS ASKED FOR, in every mode. A lead of 1.000
   must measure 1.000 with compensation on. The regression this file was
   written for is the other half of that: Native inserted a 0.5657 mm move
   between the contour end and the lead-out - G40 jerking the tool out of the
   finished corner because the point it named was not the point the tool was
   standing on - and the retreat then ran 1.5657 mm.

THE THIRD ASSERTION IS THE ONE THAT CAUGHT IT. Native and In CAM reach the same
geometry by different routes: the interpreter compensates one, a Python point
table compensates the other. Where they disagree, one of them is wrong. They
disagreed on the lead-out by exactly the raw orientation vector (0.4, 0.4) -
which is what a missing orientation term looks like, and it was missing from
the exit shift while the entry had had it since c16df1f.
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
PROJECTS = ('testing_15_2.xml', 'testing_13_arcs.xml')
NOSE, ORIENT = 0.4, 2
WP_Z, WP_R = 0.0, 30.0          # stock face at Z0, 60 mm bar
MODES = ((0, 'Off'), (1, 'Native'), (2, 'In CAM'))
FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name
          + (('  ' + detail) if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def lead_report(tp, P):
    """Per pass: the lead moves, whether each cuts, and its length.

    A lead is the first and the last FEED of the pass. Everything between them
    is contour and is supposed to cut - only the ends are being judged here.
    """
    zs = [p for m in tp.moves for p in (m.a[2], m.b[2])]
    z0, z1 = min(zs) - 2, max(zs) + 2
    f = P.StockField(z0, z1, 0.0, WP_R, P.StockField.columns_for(z0, z1, NOSE))
    for i in range(f.n):                      # nothing in front of the face
        if f.z0 + (i + 0.5) * f.dz > WP_Z:
            f.outer[i] = 0.0
    dv = P.nose_offset(ORIENT)

    tags = {}
    for tag, name in ((P.PREFINISH, 'prefinish'), (P.FINISH, 'finish')):
        idx = [k for k, m in enumerate(tp.moves)
               if m.op == 'Lathe Polyline' and tag in m.subs
               and m.kind == 'feed']
        if idx:
            tags[idx[0]] = name + ' lead-in'
            tags[idx[-1]] = name + ' lead-out'

    out = {}
    for k, m in enumerate(tp.moves):
        before = list(f.outer) if k in tags else None
        if m.kind != 'rapid':
            f.cut_move(m.a, m.b, NOSE, dv)
        if before is None:
            continue
        cut = max([before[i] - f.outer[i] for i in range(f.n)] + [0.0])
        out[tags[k]] = {
            'cut': cut,
            'len': ((m.b[2] - m.a[2]) ** 2 + (m.b[0] - m.a[0]) ** 2) ** 0.5,
            'a': (m.a[2], m.a[0]), 'b': (m.b[2], m.b[0])}

    # and the trailing feeds of each pass, so the exit line can be found by
    # POSITION rather than by guessing which move it is - see exit_jerk()
    for tag, name in ((P.PREFINISH, 'prefinish'), (P.FINISH, 'finish')):
        fd = [m for m in tp.moves if m.op == 'Lathe Polyline'
              and tag in m.subs and m.kind == 'feed']
        if fd:
            out[name + ' tail'] = [
                ((m.b[2] - m.a[2]) ** 2 + (m.b[0] - m.a[0]) ** 2) ** 0.5
                for m in fd[-4:]]
    return out


def exit_jerk(rep, off_rep, pass_name):
    """How far cancelling compensation moves the tool, or None.

    The exit line is emitted immediately after G40 and names the point the tool
    is already standing on, so in Off - which has nothing to cancel - it is
    exactly zero length. That is what locates it: find the zero-length move in
    Off's trailing feeds and read the SAME POSITION in the mode being judged.

    Guessing it as "the move before the lead-out" is wrong and was: with a
    lead-out blend radius the move before the lead-out is the ARC, 0.3902 mm on
    testing_13_arcs, and the check then failed on Off itself. A measurement
    that fires on the baseline is not a measurement - the third time that trap
    has been hit in this project.
    """
    tail, off_tail = rep.get(pass_name + ' tail'), off_rep.get(pass_name + ' tail')
    if not tail or not off_tail or len(tail) != len(off_tail):
        return None
    zeros = [i for i, v in enumerate(off_tail) if v < 1e-9]
    if len(zeros) != 1:
        return None
    return tail[zeros[0]]


def main():
    if not (os.path.isfile(INI) and os.path.isfile(GEN)):
        print('SKIP  demo config or generator not present')
        return
    if not shutil.which('rs274'):
        print('SKIP  rs274 is not installed')
        return
    import ncam_preview as P

    d = tempfile.mkdtemp(prefix='leads_')
    try:
        for project in PROJECTS:
            print('--- %s' % project)
            runs = {}
            for mode, label in MODES:
                out = os.path.join(d, '%s_%d.ngc' % (project[:-4], mode))
                subprocess.run([sys.executable, GEN, '--ini', INI, '--project',
                                project, '--out', out, '--config-copy', '--set',
                                'polyline:param_n_comp=%d' % mode],
                               capture_output=True, text=True)
                tp = P.parse_program(out, INI) if os.path.isfile(out) else None
                runs[label] = (lead_report(tp, P)
                               if tp is not None and not tp.error else None)
            check('all three modes generate and run',
                  all(runs.values()),
                  str({k: v is None for k, v in runs.items()}))
            if not all(runs.values()):
                continue

            # 1. the criterion itself
            for label, rep in runs.items():
                dirty = {k: v['cut'] for k, v in rep.items()
                         if not k.endswith(' tail') and v['cut'] > 1e-4}
                check('%-7s no lead move cuts into the material' % label,
                      not dirty,
                      ', '.join('%s takes %.4f mm' % (k, v)
                                for k, v in dirty.items()))

            # 2. the length that was asked for. Off is the reference: it is the
            # mode with no compensation to get wrong, and greatEndian's words
            # are "be like when comp off".
            for label in ('Native', 'In CAM'):
                worst, where = 0.0, ''
                for k, v in runs[label].items():
                    if k.endswith(' tail'):
                        continue
                    want = runs['Off'][k]['len']
                    if abs(v['len'] - want) > worst:
                        worst = abs(v['len'] - want)
                        where = '%s %.4f against %.4f' % (k, v['len'], want)
                check('%-7s leads are the length Off makes them' % label,
                      worst < 1e-3, where)

            # 3. THE ONE THAT CAUGHT THE BUG. G40 fires between the contour and
            # the lead-out; the point named after it must be the point the tool
            # is already standing on, or cancelling compensation is itself a
            # move - out of the corner the pass has just finished.
            for label, rep in runs.items():
                worst, where = 0.0, ''
                for pass_name in ('prefinish', 'finish'):
                    jerk = exit_jerk(rep, runs['Off'], pass_name)
                    if jerk is not None and jerk > worst:
                        worst = jerk
                        where = '%s jerks %.4f mm' % (pass_name, jerk)
                check('%-7s cancelling compensation moves nothing' % label,
                      worst < 1e-4, where)

            # 4. and the two compensated modes must agree, since they are two
            # routes to one geometry
            worst, where = 0.0, ''
            for k in runs['Native']:
                if k.endswith(' tail'):
                    continue
                for end in ('a', 'b'):
                    n, c = runs['Native'][k][end], runs['In CAM'][k][end]
                    gap = ((n[0] - c[0]) ** 2 + (n[1] - c[1]) ** 2) ** 0.5
                    if gap > worst:
                        worst = gap
                        where = ('%s %s: Native Z%.4f r%.4f, In CAM Z%.4f r%.4f'
                                 % (k, end, n[0], n[1], c[0], c[1]))
            check('Native and In CAM place every lead identically',
                  worst < 1e-3, where)
    finally:
        shutil.rmtree(d, ignore_errors=True)

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('Leads clear the material and keep their length under compensation.')


if __name__ == '__main__':
    main()
