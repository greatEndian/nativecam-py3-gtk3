#!/usr/bin/env python3
"""Coolant/spindle startup waits survive generation, migration and Flat replay."""
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

import ncam_preview as preview

HERE = Path(__file__).resolve().parent


def main():
    root = Path(tempfile.mkdtemp(prefix='ncam_startup_dwells_'))
    config = root / 'config'
    shutil.copytree(HERE / 'configs/sim/axis/ncam_demo', config, symlinks=True)
    settings = config / 'ncam/catalogs/ncam.conf'
    prefs = configparser.ConfigParser(interpolation=None)
    prefs.read(settings)
    prefs.set('layout', 'autorefresh', 'False')
    prefs.set('layout', 'remember_session', 'False')
    with settings.open('w') as stream:
        prefs.write(stream)
    (config / 'lathe_mm.tbl').write_text('T2 P2 D0.8 I15 J75 Q2 ; regression tool\n')
    ini = config / 'lathe-mm.ini'
    sys.argv = ['ncam.py', '-i', str(ini), '-c', 'lathe']
    import ncam
    app = ncam.NCam()
    app.pref.autosave = False

    def feature(source, number=1, **values):
        item = ncam.Feature(src=str(HERE / 'cfg' / source))
        item.attr.update(src=source, id=item.get_type() + '_%03d' % number)
        for key, value in values.items():
            param = item.get_param('param_' + key)
            assert param is not None, 'missing startup setting: ' + key
            param.attr['value'] = str(value / 25.4 if 'metric_value' in param.attr else value)
        return item

    tool = feature('lathe/tool-change.cfg', dnum=2, c_dpt=2,
                   spindle_dwell=1.25, cooling_dwell=2.5)
    calls = [p.attr['call'] for p in tool.param]
    for control in ('spindle_dir', 'cooling'):
        dwell = 'spindle_dwell' if control == 'spindle_dir' else 'cooling_dwell'
        assert calls[calls.index('#param_' + control) + 1] == '#param_' + dwell
        p = tool.get_param('param_' + dwell)
        assert 'metric_value' not in p.attr and float(p.attr['minimum_value']) == 0
    print('PASS startup fields follow their controls and use seconds', flush=True)

    project = etree.Element(ncam.XML_TAG)
    project.append(feature('lathe/material.cfg', od=30, units=21).to_xml())
    project.append(tool.to_xml())
    poly = feature('lathe/polyline.cfg', b_x=30, e_x=20, op=1, pf_on=0,
                   flank=0, n_comp=0, sectioning=0)
    items = poly.to_xml()
    children = items.find('param[@type="items"]')
    children.append(feature('lathe/polyline-to.cfg', 1, type=1, x=25, z=0).to_xml())
    children.append(feature('lathe/polyline-to.cfg', 2, type=1, x=20, z=-10).to_xml())
    project.append(items)
    app.treestore_from_xml(copy.deepcopy(project))
    project = app.treestore_to_xml()

    def generate(name, data):
        app.treestore_from_xml(copy.deepcopy(data))
        path = root / (name + '.ngc')
        def unexpected_dialog(message, *args, **kwargs):
            raise SystemExit('Unexpected generation dialog: ' + message)
        with patch.object(ncam, 'mess_dlg', unexpected_dialog):
            path.write_text(app.to_gcode())
        canon, error = preview._canon_dump(str(path), str(ini), str(root))
        assert not error and 'STRAIGHT_FEED(' in canon, (name, error, root)
        path.with_suffix('.canon').write_text(canon)
        flat = preview.flatten_canon(canon)
        path.with_suffix('.flat.ngc').write_text(flat)
        return canon, flat, path

    def delays(canon):
        return [float(v) for v in re.findall(r'DWELL\(([-0-9.]+)\)', canon) if float(v) > 0]

    def assert_wait(flat, command, seconds):
        lines = [s.strip() for s in flat.splitlines() if s.strip() and not s.lstrip().startswith('(')]
        assert any(a == command and b == 'G4 P%s' % seconds
                   for a, b in zip(lines, lines[1:])), (command, seconds, flat, root)

    with open('/tmp/ncam-rs274.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for cooling, spindle, units in ((8, 3, 21), (7, 4, 21), (8, 4, 20)):
            data = copy.deepcopy(project)
            data[0].find('param[@call="#param_units"]').set('value', str(units))
            data[1].find('param[@call="#param_cooling"]').set('value', str(cooling))
            data[1].find('param[@call="#param_spindle_dir"]').set('value', str(spindle))
            canon, flat, path = generate('on_%s_%s_%s' % (cooling, spindle, units), data)
            assert delays(canon) == [1.25, 2.5], (delays(canon), root)
            assert_wait(flat, 'M%d' % spindle, 1.25)
            assert_wait(flat, 'M%d' % cooling, 2.5)
            replay, error = preview._canon_dump(str(path.with_suffix('.flat.ngc')), str(ini), str(root))
            assert not error and delays(replay) == delays(canon), (error, root)
        print('PASS M3/M4 and M7/M8 immediately followed by their waits in Raw and Flat; G20/G21 unchanged', flush=True)

        zero = copy.deepcopy(project)
        for call in ('spindle_dwell', 'cooling_dwell'):
            zero[1].find('param[@call="#param_%s"]' % call).set('value', '0')
        canon, flat, unused = generate('zero', zero)
        assert delays(canon) == [] and not re.search(r'^\s*G4\b', flat, re.M)
        off = copy.deepcopy(project)
        off[1].find('param[@call="#param_spindle_dir"]').set('value', '5')
        off[1].find('param[@call="#param_cooling"]').set('value', '9')
        canon, unused, unused_path = generate('off', off)
        assert delays(canon) == [], (delays(canon), root)
        print('PASS zero settings, coolant off and spindle off add no waits', flush=True)

        repeated = copy.deepcopy(project)
        again = copy.deepcopy(items)
        again.set('id', 'polyline_002')
        for i, child in enumerate(again.findall('.//feature'), 3):
            child.set('id', child.get('type') + '_%03d' % i)
        repeated.append(again)
        stop = feature('gcode.cfg')
        stop.get_param('param_gc').attr['value'] = 'M9\nM5'
        repeated.append(stop.to_xml())
        again = copy.deepcopy(items)
        again.set('id', 'polyline_003')
        for i, child in enumerate(again.findall('.//feature'), 5):
            child.set('id', child.get('type') + '_%03d' % i)
        repeated.append(again)
        canon, unused, unused_path = generate('restart', repeated)
        assert delays(canon) == [1.25, 2.5, 1.25, 2.5], (delays(canon), root)
        print('PASS already-running equipment has no repeated wait; restart waits again', flush=True)

        # Existing projects have no per-tool dwell fields; retain their preference.
        legacy = copy.deepcopy(project)
        legacy[1].set('version', '1.24')
        for call in ('spindle_dwell', 'cooling_dwell'):
            legacy[1].remove(legacy[1].find('param[@call="#param_%s"]' % call))
        app.pref.ngc_spindle_speedup_time = '0.75'
        migrated = app.update_features(legacy)
        assert float(migrated[1].find('param[@call="#param_spindle_dwell"]').get('value')) == .75
        assert float(migrated[1].find('param[@call="#param_cooling_dwell"]').get('value')) == 0
        canon, unused, unused_path = generate('migrated', migrated)
        assert delays(canon) == [.75], (delays(canon), root)
        saved = etree.fromstring(etree.tostring(project))
        loaded = app.update_features(saved)
        assert loaded[1].find('param[@call="#param_spindle_dwell"]').get('value') == '1.25'
        assert loaded[1].find('param[@call="#param_cooling_dwell"]').get('value') == '2.5'
        print('PASS serialization and old-project migration retain explicit and legacy settings', flush=True)
    print('ARTIFACTS', root, flush=True)
    print('[VERDICT: PASS]')


if __name__ == '__main__':
    main()
