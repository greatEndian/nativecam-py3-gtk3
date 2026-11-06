#!/usr/bin/env python3
# coding: utf-8
"""The flat program is the same motion as ncam.ngc, and it loads.

Standalone, like the other test_*.py here - run it directly, no pytest.

ncam.ngc is O-word calls and expressions. The Send dropdown can hand LinuxCNC
the FLAT program instead - the interpreter's own output, every subroutine and
expression already gone - which is what a control that cannot handle O-words
needs. That is only safe if it is the same motion, so this asserts it.

NOT BY COMPARING MOVE LISTS INDEX BY INDEX. flatten_canon drops zero-length
moves, so the two lists are different lengths - 253 against 241 here - and
zipping them reports a 69.89 mm discrepancy that is pure index drift. The
comparison that means something is over quantities that do not care about
ordering or about moves that go nowhere: the number of non-zero feeds, the
total feed length, and the SET of feed endpoints.

Two properties of the flat file are stated in its own header and both were
verified rather than assumed:

- work offsets are NOT baked in, and G54 through G59.3 selections survive.
  Replaying with distinct, nonzero offsets and G55 initially selected must
  give the same physical coordinates, including arcs after a frame change.
- cutter compensation IS applied - the coordinates are tool control points -
  so it must not be run with G41/G42 active as well.
"""
import math
import os
from pathlib import Path
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
FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name
          + (('  ' + detail) if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def stats(tp):
    f = [m for m in tp.moves if m.kind == 'feed']
    nz = [m for m in f
          if math.dist((m.a[0], m.a[2]), (m.b[0], m.b[2])) > 1e-9]
    length = sum(math.dist((m.a[0], m.a[2]), (m.b[0], m.b[2])) for m in f)
    ends = {(round(m.b[2], 4), round(m.b[0], 4)) for m in f}
    return len(nz), length, ends, len([m for m in tp.moves
                                       if m.kind == 'rapid'])


def test_work_coordinates(directory, preview):
    """Replay with G55 remembered and distinct, nonzero work offsets."""
    root = Path(directory)
    var = root / 'work-offsets.var'
    live_var = Path(os.path.dirname(INI)) / preview.ini_value(INI, 'RS274NGC', 'PARAMETER_FILE')
    before = live_var.read_bytes()
    values = dict(line.split() for line in before.decode().splitlines() if line.strip())
    values['5220'] = '2'
    for index in range(1, 10):
        for axis in range(1, 11):
            values[str(5200 + 20 * index + axis)] = '0'
        values[str(5201 + 20 * index)] = str(3 + 14 * (index - 1))
        values[str(5203 + 20 * index)] = str(11 + 26 * (index - 1))
    for key in range(5210, 5220):
        values[str(key)] = '0'
    var.write_text(''.join('%s %s\n' % (k, v) for k, v in sorted(values.items(), key=lambda kv: int(kv[0]))))
    ini = root / 'work-offsets.ini'
    ini.write_text(re.sub(r'(?m)^PARAMETER_FILE\s*=.*$', 'PARAMETER_FILE = ' + str(var),
                         Path(INI).read_text()))

    def canon(name, code):
        path = root / (name + '.ngc')
        path.write_text(code)
        dump = root / (name + '_dump')
        dump.mkdir()
        raw, error = preview._canon_dump(str(path), str(ini), str(dump))
        assert not error and 'STRAIGHT_FEED(' in raw, (name, error)
        return raw

    def machine_moves(raw):
        offset, unit, result = (0, 0, 0), 1, []
        for line in raw.splitlines():
            m = re.search(r'USE_LENGTH_UNITS\(CANON_UNITS_(\w+)\)', line)
            if m:
                new_unit = 25.4 if m[1] == 'INCHES' else 1
                offset = tuple(v * unit / new_unit for v in offset)
                unit = new_unit
            m = re.search(r'SET_G5X_OFFSET\(([^)]*)\)', line)
            if m:
                v = [float(x) for x in m[1].split(',')]
                index, offset = int(v[0]), v[1:4]
            m = re.search(r'(STRAIGHT_FEED|STRAIGHT_TRAVERSE|ARC_FEED)\(([^)]*)\)', line)
            if not m:
                continue
            v = [float(x) for x in m[2].split(',')]
            x, z = (v[1], v[0]) if m[1] == 'ARC_FEED' else (v[0], v[2])
            row = (m[1], index, (x + offset[0]) * unit, (z + offset[2]) * unit)
            if m[1] == 'ARC_FEED':
                row += ((v[3] + offset[0]) * unit, (v[2] + offset[2]) * unit, v[4])
            result.append(row)
        return result

    def replay(name, body, required):
        raw = canon(name, body)
        flat = preview.flatten_canon(raw)
        active = [s.strip() for s in flat.splitlines() if s.strip() and not s.lstrip().startswith('(')]
        first_move = next(i for i, line in enumerate(active) if re.match(r'G[0123]\b', line))
        check('%s selects %s before its first move without manual setup' % (name, required),
              required in active[:first_move])
        a, b = machine_moves(raw), machine_moves(canon(name + '_flat', flat))
        same = len(a) == len(b) and all(
            p[:2] == q[:2] and len(p) == len(q)
            and max(abs(x - y) for x, y in zip(p[2:], q[2:])) < .005
            for p, q in zip(a, b))
        check('%s replays at the same physical coordinates with G55 initially selected' % name,
              same, '%s against %s' % (a[:2], b[:2]))
        return flat

    setup = 'G21 G18 G7 G90 G94 '
    for index in range(1, 10):
        code = 'G%d' % (53 + index) if index <= 6 else 'G59.%d' % (index - 6)
        replay('work_%d' % index, setup + code + '\nG0 X40 Z2\nG1 X30 Z-3 F100\nM2\n', code)
    replay('work_switch_arc', setup + 'G54\nG0 X40 Z2\nG1 X30 Z0 F100\n'
           'G55\nG91 G3 X-10 Z-5 I-5 K0\nG90\nG1 X20 Z-20\n'
           'G54\nG1 X30 Z0\nM2\n', 'G54')
    replay('work_switch_inch', 'G20 G18 G7 G90 G94 G54\n'
           'G0 X2 Z1\nG1 X1 Z0 F4\nG55\nG91 G3 X-0.2 Z-0.1 I-0.1 K0\n'
           'G90 G1 X1 Z-1\nG21 G54\nG1 X30 Z-10\nM2\n', 'G54')
    check('work-coordinate verification leaves the live variable file unchanged', live_var.read_bytes() == before)


def main():
    if not (os.path.isfile(INI) and os.path.isfile(GEN)):
        print('SKIP  demo config or generator not present')
        return
    if not shutil.which('rs274'):
        print('SKIP  rs274 is not installed')
        return
    import ncam_preview as P

    # the action exists, on the class that owns it, and the dropdown wires it
    import ncam                                            # noqa: F401
    from ncam_app_actions import NCamAppActionsMixin as M
    import inspect
    check('the Send dropdown has a flat-G-code action',
          hasattr(M, 'action_send_flat'))
    src = inspect.getsource(M.create_send_mode_menu)
    check('   and the dropdown actually calls it',
          'self.action_send_flat' in src,
          'the action exists but nothing invokes it')
    check('   with its own filename, not ncam.ngc',
          ncam.FLAT_FILE != ncam.GENERATED_FILE,
          'the flat program would overwrite the O-word one')

    d = tempfile.mkdtemp(prefix='flat_')
    try:
        test_work_coordinates(d, P)
        out = os.path.join(d, 'p.ngc')
        subprocess.run([sys.executable, GEN, '--ini', INI, '--project',
                        PROJECT, '--out', out, '--config-copy',
                        '--set', 'polyline:param_n_comp=2'],
                       capture_output=True, text=True)
        if not os.path.isfile(out):
            check('the project generates', False)
            return
        tp = P.parse_program(out, INI)
        check('the original parses and yields a flat listing',
              not tp.error and tp.flat.strip().count('\n') > 50,
              'error %s, %d lines' % (tp.error, tp.flat.count('\n')))
        if tp.error or not tp.flat.strip():
            return

        flat = os.path.join(d, 'ncam-flat.ngc')
        open(flat, 'w').write(tp.flat)
        tp2 = P.parse_program(flat, INI)
        check('the flat program LOADS - the interpreter accepts it',
              not tp2.error, str(tp2.error))
        if tp2.error:
            return

        a, b = stats(tp), stats(tp2)
        check('the same number of cutting moves', a[0] == b[0],
              '%d against %d' % (a[0], b[0]))
        check('the same total feed length', abs(a[1] - b[1]) < 1e-4,
              '%.4f against %.4f mm' % (a[1], b[1]))
        check('the same rapids', a[3] == b[3], '%d against %d' % (a[3], b[3]))
        check('and every feed endpoint is in both',
              a[2] == b[2],
              '%d only in the original, %d only in the flat'
              % (len(a[2] - b[2]), len(b[2] - a[2])))

        # it must be a program, not a listing: the words a control needs
        head = tp.flat[:4000]
        for word, why in (('G18', 'plane'), ('G7', 'diameter mode'),
                          ('M6', 'tool change'), ('M3', 'spindle')):
            check('   the flat program states its %s' % why,
                  word in head, 'no %s in the first 4000 characters' % word)
        check('   and it ends', 'M2' in tp.flat[-2000:],
              'no M2 - the control would run off the end')
    finally:
        shutil.rmtree(d, ignore_errors=True)

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('The flat program loads and is the same motion.')


if __name__ == '__main__':
    main()
