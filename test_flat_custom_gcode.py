#!/usr/bin/env python3
"""Custom inline/file G-code and per-move feeds survive a real Flat replay."""
import configparser
import copy
import fcntl
from pathlib import Path
import re
import shutil
import sys
import tempfile
from unittest.mock import patch

from lxml import etree

import ncam_preview as P

HERE = Path(__file__).resolve().parent
SETUP = 'G18 G40 G49 G90 G92.1 G94 G54'


def main():
    root = Path(tempfile.mkdtemp(prefix='ncam_flat_custom_'))
    config = root / 'config'
    shutil.copytree(HERE / 'configs/sim/axis/ncam_demo', config, symlinks=True)
    settings = config / 'ncam/catalogs/ncam.conf'
    prefs = configparser.ConfigParser(interpolation=None)
    prefs.read(settings)
    prefs.set('layout', 'autorefresh', 'False')
    with settings.open('w') as stream:
        prefs.write(stream)
    ini = config / 'lathe-mm.ini'
    sys.argv = ['ncam.py', '-i', str(ini), '-c', 'lathe']
    import ncam
    app = ncam.NCam()
    app.pref.autosave = False

    def feature(source, number):
        f = ncam.Feature(src=str(HERE / 'cfg' / source))
        f.attr.update(id=f.get_type() + '_%03d' % number, src=source)
        return f

    inline = feature('gcode.cfg', 1)
    inline.get_param('param_gc').attr['value'] = '''(inline flat probe)
G7 G94 G0 X50 Z2
M0
M1
M7
M64 P2
M65 P2
M62 P3
G1 X40 Z0 F120
M63 P3
G1 Z-1
G3 X30 Z-6 I-5 K0
G4 P0.01
'''
    included = root / 'custom inserted.ngc'
    included.write_text('''(file flat probe)
G95 S600 M3
G1 Z-7 F0.2
G1 Z-8
G96 D1500 S180
G1 Z-9
G97 S600
G94
G1 Z[-9-#1] F#2
G1 Z-12
M67 E1 Q0.25
G1 Z-13
M68 E1 Q0.5
M9
''')
    include = feature('i_gcode.cfg', 1)
    for key, value in (('act', '1'), ('fname', str(included)), ('1', '2'), ('2', '90')):
        include.get_param('param_' + key).attr['value'] = value
    project = etree.Element(ncam.XML_TAG)
    setup = feature('gcode.cfg', 2)
    setup.get_param('param_gc').attr['value'] = SETUP
    project.append(setup.to_xml())
    project.append(inline.to_xml())
    project.append(include.to_xml())
    setup_path = root / 'file setup.ngc'
    setup_path.write_text(SETUP + '\n')
    setup_file = feature('i_gcode.cfg', 2)
    setup_file.get_param('param_fname').attr['value'] = str(setup_path)
    setup_file.get_param('param_act').attr['value'] = '1'
    project.append(setup_file.to_xml())
    original_dump = P._canon_dump

    def generate(name, data):
        app.treestore_from_xml(copy.deepcopy(data))
        path = root / (name + '.ngc')
        path.write_text(app.to_gcode())
        raw = []
        def dump(*args):
            canon, error = original_dump(*args)
            if canon:
                raw.append(canon)
                path.with_suffix('.canon').write_text(canon)
            return canon, error
        with patch.object(P, '_canon_dump', dump):
            tp = P.parse_program(str(path), str(ini))
        assert tp.completed, (name, tp.error, root)
        return tp, raw[0]

    with open('/tmp/ncam-rs274.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        reads, original_open = [], ncam.io.open
        def read_file(path, *args, **kwargs):
            if str(path) == str(setup_path):
                reads.append(str(path))
            return original_open(path, *args, **kwargs)
        with patch.object(ncam.io, 'open', read_file):
            original, canon = generate('original', project)
        assert len(reads) == 1, 'Flat setup must use the same file snapshot as the executed definition'
        assert not original.error, (original.error, root)
        flat = original.flat
        active = [line.strip() for line in flat.splitlines()
                  if line.strip() and not line.lstrip().startswith('(')]
        assert active.count(SETUP) == 2, ('inline/file setup must be executable', root)
        assert 'G-code source:' not in flat
        failures = []
        for token in ('(begin GCode)', '(inline flat probe)', 'M0', 'M1', 'M7',
                      'M64 P2', 'M65 P2', 'M62 P3', 'M63 P3',
                      '(begin Include Gcode)', '(file flat probe)', 'M67 E1 Q0.25', 'M68 E1 Q0.5'):
            if token not in flat:
                failures.append('missing ' + token)
        cuts = [s.strip() for s in flat.splitlines() if re.match(r'^\s*G[123]\b', s)]
        if not cuts or any(not re.search(r'\bF[0-9]', s) for s in cuts):
            failures.append('cutting moves do not state their feedrate')
        assert not failures, (failures, root)
        assert not any('#' in s or 'o<' in s for s in flat.splitlines() if not s.lstrip().startswith('('))
        path = root / 'flat.ngc'
        path.write_text(flat)
        replay_canon, error = original_dump(str(path), str(ini), str(root))
        assert not error, (error, root)
        (root / 'flat.canon').write_text(replay_canon)
        replay = P.parse_program(str(path), str(ini))
        assert not replay.error and replay.completed, (replay.error, root)
        def real(tp):
            return [m for m in tp.moves if m.a != m.b]
        a, b = real(original), real(replay)
        assert len(a) == len(b), (len(a), len(b), root)
        for m, n in zip(a, b):
            assert m.kind == n.kind and m.fmode == n.fmode
            assert max(abs(x-y) for x, y in zip(m.a+m.b, n.a+n.b)) < .001
            if m.kind == 'feed':
                assert abs(m.feed-n.feed) < .0001, (m, n)
                assert abs((m.rpm or 0)-(n.rpm or 0)) < .01, (m, n)
        events = re.compile(r'(?:PROGRAM_STOP|OPTIONAL_PROGRAM_STOP|MIST_ON|MIST_OFF|FLOOD_OFF|'
                            r'(?:SET|CLEAR)_(?:MOTION|AUX)_OUTPUT_(?:BIT|VALUE))\([^)]*\)')
        assert events.findall(canon) == events.findall(replay_canon), 'custom command execution changed'
        print('PASS inline and file comments, stops, coolant, digital/analog outputs', flush=True)
        print('PASS every cutting block carries F; G94/G95 and G96/G97 replay unchanged', flush=True)
        legacy = P.flatten_canon('\n'.join(line for line in canon.splitlines()
                                          if 'COMMENT("ncam custom gcode ' not in line))
        assert '(inline flat probe)' in legacy and '(file flat probe)' in legacy
        commands = lambda s: [line.strip() for line in s.splitlines()
                              if line.strip() and not line.lstrip().startswith('(')]
        assert commands(legacy) == commands(flat), 'legacy custom markers changed execution'
        print('PASS already-generated projects retain custom comments and commands', flush=True)
        off = copy.deepcopy(project)
        for f in off:
            key = 'ena' if f.get('type') == 'g-code' else 'act'
            f.find('param[@call="#param_%s"]' % key).set('value', '0')
        disabled, unused = generate('disabled', off)
        assert '(inline flat probe)' not in disabled.flat and '(file flat probe)' not in disabled.flat
        assert SETUP not in disabled.flat
        assert not events.findall(unused), 'disabled custom code executed'
        print('PASS disabled inline/file contents remain excluded', flush=True)
    print('ARTIFACTS', root, flush=True)
    print('[VERDICT: PASS]')


if __name__ == '__main__':
    main()
