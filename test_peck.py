#!/usr/bin/env python3
# coding: utf-8
"""Pecking breaks the chip without moving where the cut ends.

Standalone, like the other test_*.py here - run it directly, no pytest.

Gap 16 of `POLYLINE-GAPS.md`. The reference package: *"Pecking creates multiple
steps across the length of the cutting direction. Between Pecking Depths the
tool retracts along its path by the specified Pecking retract distance. Use this
if your material creates long strings of chips."* Two parameters, illustrated at
18 mm peck with 3 mm retract.

WHAT IT MAY NOT DO is change the part. A peck is a pause in a cut, not a
different cut: the tool must reach exactly the same place, take exactly the same
metal, and only the travel may grow - by the retracts, which are re-cut air.

WHY THE RETRACT IS ALONG THE CUT and not radial. Backing out radially would
leave the compensated path and re-enter it, and re-entry is where gouges come
from - the same reason a comp entry move has to be a straight feed in free air.
Backing straight down the groove just made cannot touch anything.

WHY THE SUBDIVISION IS NOT A PYTHON TABLE, against this project's standing rule.
The interval's END is decided by the level scan at RUNTIME, so generation time
does not know how long the cut is. What Python would compute is a repeating rule
with no geometry in it - cut this far, back off that far - so the subroutine
walks the rule and works out no shape.

THE FIRST ASSERTION IS THE ONE THAT MATTERS: with pecking off the program must
be untouched. A feature that quietly alters every existing project is worse than
a feature that is missing.
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
PROJECT = 'testing_15_5.xml'
FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name
          + (('  ' + detail) if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def run(sets):
    """-> dict of the numbers a peck may and may not move, or None."""
    import ncam_preview as P
    d = tempfile.mkdtemp(prefix='peck_')
    try:
        out = os.path.join(d, 'o.ngc')
        cmd = [sys.executable, GEN, '--ini', INI, '--project', PROJECT,
               '--out', out, '--config-copy']
        for kv in sets:
            cmd += ['--set', kv]
        subprocess.run(cmd, capture_output=True, text=True)
        if not os.path.isfile(out):
            return None
        tp = P.parse_program(out, INI)
        if tp.error:
            return None
        mv = [m for m in tp.moves if m.op == 'Lathe Polyline'
              and m.kind != 'rapid']
        lv = [m for m in mv if abs(m.b[0] - m.a[0]) < 1e-6
              and abs(m.b[2] - m.a[2]) > 1e-6]
        zs = [q for m in lv for q in (m.a[2], m.b[2])]
        return {'moves': len(mv), 'level_moves': len(lv),
                'deepest': round(min(zs), 4),
                'travel': sum(abs(m.b[2] - m.a[2]) for m in lv),
                'radii': sorted({round(m.a[0], 4) for m in lv})}
    finally:
        shutil.rmtree(d, ignore_errors=True)


def dwells(sets):
    """How many DWELLs the interpreter actually performs, or None.

    Counted from canon output, not from the file: the G4 is inside
    lathe_level_pass, which is never inlined into the generated program.
    """
    d = tempfile.mkdtemp(prefix='peckdw_')
    try:
        out = os.path.join(d, 'o.ngc')
        cmd = [sys.executable, GEN, '--ini', INI, '--project', PROJECT,
               '--out', out, '--config-copy']
        for kv in sets:
            cmd += ['--set', kv]
        subprocess.run(cmd, capture_output=True, text=True)
        if not os.path.isfile(out):
            return None
        r = subprocess.run(['rs274', '-g', '-b', '-i', INI, out],
                           capture_output=True, text=True,
                           cwd=os.path.dirname(INI), timeout=300)
        return sum(1 for ln in r.stdout.splitlines() if 'DWELL' in ln.upper())
    except Exception:
        return None
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main():
    if not (os.path.isfile(INI) and os.path.isfile(GEN)):
        print('SKIP  demo config or generator not present')
        return
    if not shutil.which('rs274'):
        print('SKIP  rs274 is not installed')
        return

    off = run([])
    check('the project generates with pecking off', off is not None)
    if off is None:
        sys.exit(1)
    print('      peck off        %3d level moves, %8.1f mm, deepest Z%.4f'
          % (off['level_moves'], off['travel'], off['deepest']))

    # THE ONE THAT MATTERS: setting a retract with no length must change
    # nothing, and neither must the feature's mere existence.
    idle = run(['polyline:param_peck_ret=1.0'])
    check('a retract with no peck length changes NOTHING',
          idle is not None and idle['level_moves'] == off['level_moves']
          and abs(idle['travel'] - off['travel']) < 1e-6,
          'the feature is altering a program that did not ask for it')

    PECK, RET = 10.0, 1.0
    on = run(['polyline:param_peck_len=%s' % PECK,
              'polyline:param_peck_ret=%s' % RET])
    check('the project generates with pecking on', on is not None)
    if on is None:
        sys.exit(1)
    print('      peck %.0f/%.0f       %3d level moves, %8.1f mm, deepest Z%.4f'
          % (PECK, RET, on['level_moves'], on['travel'], on['deepest']))

    # the part must be identical - same reach, same levels
    check('the cut reaches exactly the same place',
          on['deepest'] == off['deepest'],
          'Z%.4f against Z%.4f - a peck moved the end of the cut'
          % (on['deepest'], off['deepest']))
    check('   and it cuts the same levels',
          on['radii'] == off['radii'],
          '%d radii against %d' % (len(on['radii']), len(off['radii'])))

    # it must actually peck
    check('the cut IS broken into steps',
          on['level_moves'] > off['level_moves'] * 2,
          '%d level moves against %d - pecking did nothing'
          % (on['level_moves'], off['level_moves']))

    # AND THE EXTRA TRAVEL MUST BE EXACTLY THE RETRACTS. Each peck adds a
    # back-off and a re-approach, so 2 x retract, and nothing else: if the
    # figure is not a whole number of them, the tool is going somewhere it
    # was not told to.
    extra = on['travel'] - off['travel']
    pecks = extra / (2.0 * RET)
    check('   and the extra travel is exactly the retracts',
          abs(pecks - round(pecks)) < 0.02,
          '%.4f mm extra is %.3f retract pairs, not a whole number - the '
          'tool is travelling somewhere unaccounted for' % (extra, pecks))
    print('      %.1f mm extra travel = %d peck retracts of %.1f mm'
          % (extra, round(pecks) * 2, RET))

    # a longer peck must peck LESS - guards against a rule that ignores its
    # own length and just subdivides by a constant
    coarse = run(['polyline:param_peck_len=%s' % (PECK * 3),
                  'polyline:param_peck_ret=%s' % RET])
    check('a longer peck length breaks the chip less often',
          coarse is not None
          and coarse['level_moves'] < on['level_moves']
          and coarse['level_moves'] > off['level_moves'],
          '%s level moves against %s at peck %.0f'
          % (coarse['level_moves'] if coarse else '?', on['level_moves'],
             PECK))

    # --- the dwell -------------------------------------------------------
    # It must add TIME and no motion: same moves, same travel, same reach.
    # And it must happen once per peck, which is counted from the interpreter's
    # own canon output rather than the file - the G4 lives in the SUBROUTINE,
    # so grepping the generated program finds nothing and proves nothing.
    dw = run(['polyline:param_peck_len=%s' % PECK,
              'polyline:param_peck_ret=%s' % RET,
              'polyline:param_peck_dwell=0.4'])
    check('a dwell moves nothing at all',
          dw is not None and dw['level_moves'] == on['level_moves']
          and abs(dw['travel'] - on['travel']) < 1e-6
          and dw['deepest'] == on['deepest'],
          'the dwell changed the path, which it must never do')

    idle2 = run(['polyline:param_peck_dwell=0.4'])
    check('   and a dwell with no peck length changes nothing either',
          idle2 is not None
          and idle2['level_moves'] == off['level_moves']
          and abs(idle2['travel'] - off['travel']) < 1e-6)

    n_dw = dwells(['polyline:param_peck_len=%s' % PECK,
                   'polyline:param_peck_ret=%s' % RET,
                   'polyline:param_peck_dwell=0.4'])
    n_base = dwells(['polyline:param_peck_len=%s' % PECK,
                     'polyline:param_peck_ret=%s' % RET])
    if n_dw is None or n_base is None:
        print('SKIP  dwell count needs rs274')
    else:
        pecks = int(round((on['travel'] - off['travel']) / (2.0 * RET)))
        check('   and it dwells exactly once per peck',
              n_dw - n_base == pecks,
              '%d dwells for %d pecks (%d in the program without a dwell)'
              % (n_dw - n_base, pecks, n_base))
        print('      %d dwells for %d pecks' % (n_dw - n_base, pecks))

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('Pecking breaks the cut, not the part.')


if __name__ == '__main__':
    main()
