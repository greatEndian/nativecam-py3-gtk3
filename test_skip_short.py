#!/usr/bin/env python3
# coding: utf-8
"""Checks that a skipped roughing level emits NO motion at all.

Standalone, like the other test_*.py here - run it directly, no pytest.

"Skip short roughing passes" returned out of lathe_level_pass AFTER the
approach and the lead-in had already been written, so a skipped level still
left four moves behind: a retract, two rapids to the lead start, and a FEED
into the workpiece - which then walked away without cutting the pass it had
just entered for. On testing_15_2 that is

    rapid X31.8160 Z-67.5300
    rapid X25.2791 Z-67.5300
    feed  X24.5720 Z-68.2371     <- into the part
    rapid X31.8160 Z-68.2371     <- and out again

A wasted air move would be a nuisance; a feed into the part for no cut is a
mark on the workpiece. The gate now runs before any motion is written.

The trap in testing this: with the option OFF nothing is skipped, so a test
that only ran the default would pass against the broken code. Both states are
generated here, and the OFF one is checked as well - moving the gate moved the
lead-out resolution with it, and that block runs whether or not anything is
skipped.

Verified to fail against the previous lathe_level_pass.ngc: it reports the lone
entry feed above, and the stray rapid that follows it.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '.claude/skills/lathe-gcode-verify/scripts'))

INI = os.path.join(HERE, 'configs/sim/axis/ncam_demo/lathe-mm.ini')
GEN = os.path.join(HERE, '.claude/skills/lathe-gcode-verify/scripts/gen_project.py')
FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name
          + (('  ' + detail) if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def generate(out, skip):
    r = subprocess.run([sys.executable, GEN, '--ini', INI, '--project',
                        'testing_15_2.xml', '--out', out, '--config-copy',
                        '--set', 'polyline:param_skip_short=%d' % skip,
                        '--set', 'tool_change:param_flank_len=16.0'],
                       capture_output=True, text=True)
    return out if (r.returncode == 0 and os.path.isfile(out)) else None


def main():
    if not (os.path.isfile(INI) and os.path.isfile(GEN)):
        print('SKIP  demo config or generator not present')
        return
    if not shutil.which('rs274'):
        print('SKIP  rs274 is not installed')
        return
    import ncam_preview as P

    d = tempfile.mkdtemp(prefix='skip_short_')
    try:
        off = generate(os.path.join(d, 'off.ngc'), 0)
        on = generate(os.path.join(d, 'on.ngc'), 1)
        check('both variants generate', off is not None and on is not None)
        if off is None or on is None:
            return

        # the option has to actually be armed, or everything below is vacuous
        def limit(path):
            with open(path) as f:
                vals = re.findall(r'#<_pl_min_pass>\s*=\s*([-\d.]+)', f.read())
            return float(vals[-1]) if vals else None
        check('with the option off the gate is disarmed', limit(off) == 0.0,
              'limit is %s' % limit(off))
        check('and with it on the gate has a real limit', (limit(on) or 0) > 1.0,
              'limit is %s - nothing would ever be skipped' % limit(on))

        tp_off = P.parse_program(off, INI)
        tp_on = P.parse_program(on, INI)
        check('both programs run clean',
              tp_off.error is None and tp_on.error is None,
              '%s / %s' % (tp_off.error, tp_on.error))

        def rough(tp):
            return [m for m in tp.moves
                    if m.op == 'Lathe Polyline' and not m.subs]
        r_off, r_on = rough(tp_off), rough(tp_on)
        check('turning it on actually skips something',
              len(r_on) < len(r_off),
              '%d roughing moves either way - nothing was skipped, so this '
              'test proves nothing' % len(r_on))

        # THE point: every feed in the roughing phase must belong to a pass
        # that goes somewhere. A skipped level used to leave a lone entry feed
        # bracketed by rapids, cutting into the part and retreating.
        def lone_entries(moves):
            """Feed runs that enter the part but never cut a pass.

            The discriminator is not length - a genuine level pass CAN be
            short, which is the whole reason the option exists. It is that a
            level pass always contains a move along Z at constant diameter,
            the cut itself, and an entry on its own does not: the lead-in is
            angled, so every one of its segments changes X.
            """
            out, i = [], 0
            while i < len(moves):
                if moves[i].kind != 'feed':
                    i += 1
                    continue
                j = i
                while j < len(moves) and moves[j].kind == 'feed':
                    j += 1
                run = moves[i:j]
                cut = [m for m in run
                       if abs(m.b[0] - m.a[0]) < 1e-6
                       and abs(m.b[2] - m.a[2]) > 1e-6]
                if not cut:
                    out.append((run[0].a, run[-1].b, len(run)))
                i = j
            return out

        lone = lone_entries(r_on)
        check('no roughing feed enters the part without cutting a pass',
              not lone,
              '%d lone entry feed(s), first %s' % (len(lone), lone[:1]))

        # and the removal is exactly the entry, not part of a real pass
        off_set = ['%s %.4f %.4f' % (m.kind, m.b[0], m.b[2]) for m in r_off]
        on_set = ['%s %.4f %.4f' % (m.kind, m.b[0], m.b[2]) for m in r_on]
        import difflib
        added = [ln for ln in difflib.unified_diff(off_set, on_set, n=0)
                 if ln.startswith('+') and not ln.startswith('+++')]
        check('skipping only removes moves, it never adds any',
              not added, str(added[:3]))

        # --- the OFF path must be untouched --------------------------------
        # This is the half that a "fix" can quietly break: moving the gate
        # moved the lead-out resolution with it, and that block runs whether
        # or not anything is skipped.
        import parse_rs274 as R
        canon, _e = R.run_rs274(INI, off)
        motion = re.findall(
            r'(?:STRAIGHT_FEED|STRAIGHT_TRAVERSE|ARC_FEED)\([^)]*\)',
            canon or '')
        check('the option off still produces a full toolpath',
              len(motion) > 200, '%d motion calls' % len(motion))
        check('and every roughing level still cuts',
              not lone_entries(r_off),
              'the default path has lone entry feeds of its own')
    finally:
        shutil.rmtree(d, ignore_errors=True)

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('A skipped roughing pass leaves no motion behind.')


if __name__ == '__main__':
    main()
