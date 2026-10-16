#!/usr/bin/env python3
"""Front section tangents must enter from outside the active roughing layer."""
import configparser
import copy
import fcntl
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import sys
import tempfile
from unittest.mock import patch

from lxml import etree
import ncam_preview as P
from test_section_tangent import extensions

HERE = Path(__file__).resolve().parent


def main():
    controls = '--controls' in sys.argv
    root = Path(tempfile.mkdtemp(prefix='ncam_tangent_entry_'))
    cfg = root / 'config'
    shutil.copytree(HERE / 'configs/sim/axis/ncam_demo', cfg, symlinks=True)
    prefs = configparser.ConfigParser(interpolation=None)
    settings = cfg / 'ncam/catalogs/ncam.conf'
    prefs.read(settings)
    prefs.set('layout', 'autorefresh', 'False')
    with settings.open('w') as stream:
        prefs.write(stream)
    ini = cfg / 'lathe-mm.ini'
    sys.argv = ['ncam.py', '-i', str(ini), '-c', 'lathe']
    import ncam
    app = ncam.NCam()
    saved = app.update_features(etree.parse(str(
        cfg / 'ncam/catalogs/lathe/projects/testing_15_9.xml')).getroot())
    # Copy/instrument only the scratch interpreter library after GTK setup.
    library = root / 'library'
    shutil.copytree(HERE / 'lib', library, symlinks=True)
    ini.write_text(re.sub(r'(?m)^SUBROUTINE_PATH\s*=.*$',
                         'SUBROUTINE_PATH = ' + str(library / 'lathe') + ':'
                         + str(library / 'utilities'), ini.read_text()))
    sub = library / 'lathe/lathe_level_pass.ngc'
    source = sub.read_text().replace(
        '\t(=== WHICH END IS ENTERED,',
        '\t(DEBUG,ENTRY_PROBE level=#<level> zs=#<z_start> apz=#<ap_z> apr=#<ap_x> sfz=#<sf_z> sfr=#<sf_x> on=#<sf_on> w=#<_pl_w_idx>)\n'
        '\t#<entry_probe_wd> = #[2800 + #<_pl_w_idx>]\n'
        '\t(DEBUG,ENTRY_STOCK prev=#<_pl_prev_lvl> wd=#<entry_probe_wd>)\n'
        '\t(=== WHICH END IS ENTERED,')
    sub.write_text(source)
    results = {}
    original_run, original_dump = P.subprocess.run, P._canon_dump
    with open('/tmp/ncam-rs274.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        cases = [('disabled', 0, {}), ('front', .4, {})]
        if controls:
            cases += [('rounded', .4, dict(li_len=1, li_rad=.1, lo_rad=.1)),
                      ('reverse', .4, dict(dir=1)),
                      ('alternating', .4, dict(dir=2)),
                      ('inches', .4, dict(units=20)), ('longer', .8, {})]
        for name, front, changes in cases:
            data = copy.deepcopy(saved)
            poly = data.find('.//feature[@type="polyline"]')
            values = dict(sec_ext_fr=front, sec_ext_bk=0, dir=0,
                          sectioning=1, sec_len=5, li_len=0, li_rad=0)
            values.update(changes)
            units = values.pop('units', 21)
            scale = 25.4 if units == 20 else 1
            data.find('.//feature[@type="workpiece"]/param[@call="#param_units"]').set('value', str(units))
            for key, value in values.items():
                p = poly.find('./param[@call="#param_%s"]' % key)
                p.set('value', str(value/25.4 if p.get('metric_value') is not None else value))
            app.treestore_from_xml(data)
            out = root / (name + '.ngc')
            out.write_text(app.to_gcode())
            debug = []

            def run(*args, **kwargs):
                result = original_run(*args, **kwargs)
                if args[0][0] == 'rs274':
                    debug.append(result.stdout + '\n' + result.stderr)
                return result

            def dump(*args):
                canon, error = original_dump(*args)
                if canon:
                    out.with_suffix('.canon').write_text(canon)
                return canon, error

            with patch.object(P.subprocess, 'run', run), patch.object(P, '_canon_dump', dump):
                tp = P.parse_program(str(out), str(ini))
            assert tp.completed and not tp.error, tp.error
            text = '\n'.join(debug) + out.with_suffix('.canon').read_text()
            out.with_suffix('.debug').write_text(text)
            rows = [dict((k, float(v)) for k, v in re.findall(r'(\w+)=([-\d.]+)', line))
                    for line in text.splitlines() if 'ENTRY_PROBE' in line]
            assert rows, ('no entry diagnostics', root)
            for r in rows:
                for key in ('level', 'zs', 'apz', 'apr', 'sfz', 'sfr'):
                    r[key] *= scale
            active = [r for r in rows if r['on'] > 0]
            actual = [e for e in extensions(out.with_suffix('.canon').read_text(), scale)
                      if e['end'] == 'front']
            assert len(actual) == len(active), ('entry was not traversed', name)
            for p, move in zip(active, actual):
                start, end = (p['sfz'], p['sfr']), (p['apz'], p['apr'])
                gap = min(math.dist(start, move['a']) + math.dist(end, move['b']),
                          math.dist(start, move['b']) + math.dist(end, move['a']))
                assert gap < .006, ('actual feed did not traverse the offset', name, p, move)
            inward = [r for r in active if r['sfr'] < r['level'] - .0001]
            missing, wrong_tangent, short = [], [], []
            for r in rows:
                if r['w'] < 0 or front == 0:
                    continue
                dz, dr = r['apz']-r['zs'], r['apr']-r['level']
                norm = math.hypot(dz, dr)
                unit = (dz/norm, dr/norm) if norm > 1e-5 else (1, 0)
                offset = (r['sfz']-r['apz'], r['sfr']-r['apr'])
                length = math.hypot(*offset)
                if length < 1e-5:
                    missing.append(r)
                elif abs(offset[0]*unit[1]-offset[1]*unit[0]) > .001:
                    wrong_tangent.append(r)
                elif abs(length-front) > .002:
                    short.append(r)
            # Added straight radial cutting feeds are visible green in preview.
            radial = [m for m in tp.moves if m.op == 'Lathe Polyline'
                      and m.kind == 'feed' and not m.subs
                      and abs(m.a[2]-m.b[2]) < 1e-6 and abs(m.a[0]-m.b[0]) > .01]
            results[name] = dict(entries=rows, active=len(active), inward=inward,
                                 actual_front_moves=len(actual),
                                 missing=missing, wrong_tangent=wrong_tangent, short=short,
                                 radial_feed_count=len(radial),
                                 # Boss crown in this saved fixture is Z-32.9
                                 # in compensated coordinates; the rear side
                                 # is deliberately reserved for the next fix.
                                 radial_before_boss=sum(m.b[2]*scale > -32.9 for m in radial),
                                 radial_feeds=[dict(a=tuple(v*scale for v in m.a),
                                                    b=tuple(v*scale for v in m.b)) for m in radial],
                                 motion_hash=hashlib.sha256(repr([
                                     (m.kind, m.a, m.b, m.feed, m.fmode)
                                     for m in tp.moves]).encode()).hexdigest(),
                                 max_radial_feed=max([abs(m.a[0]-m.b[0])*scale for m in radial] or [0]))
            (root / 'results.json').write_text(json.dumps(results, indent=2))
            print(name, 'active', len(active), 'inward', len(inward),
                  'missing', len(missing), 'wrong tangent', len(wrong_tangent),
                  'short', len(short), 'radial feeds', len(radial),
                  'max', results[name]['max_radial_feed'], flush=True)
    print('ARTIFACTS', root, flush=True)
    assert all(not r['inward'] for r in results.values()), 'front tangent starts below active cutting level'
    assert results['front']['active'] > 0, 'all front extensions disappeared'
    assert not results['front']['missing'], 'section front entry offset missing'
    assert not results['front']['wrong_tangent'], 'offset does not continue the actual entry'
    assert not results['front']['short'], 'section entry does not have the requested offset'
    if controls:
        for name in ('longer',):
            assert not results[name]['missing'] and not results[name]['wrong_tangent'] and not results[name]['short'], (name, results[name])
        # The inch fixture has two genuinely uncleared ramp gaps (a .4 mm
        # target is .4005/.4011 mm inside stock in the independent replay).
        # Keep collision clipping there; verify units and direction rather
        # than requiring that blocked travel to be emitted at full length.
        assert not results['inches']['missing'] and not results['inches']['wrong_tangent']
        assert all(math.hypot(r['sfz']-r['apz'], r['sfr']-r['apr']) <= .402
                   for r in results['inches']['entries'])
    assert results['front']['radial_before_boss'] <= results['disabled']['radial_before_boss'], 'extra radial feeds before boss'
    print('[VERDICT: PASS]')


if __name__ == '__main__':
    main()
