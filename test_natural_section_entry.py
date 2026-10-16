#!/usr/bin/env python3
"""Natural roughing: common front datum and no radial feed through cleared stock."""
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
from test_air_leads import Material

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
        '\t(DEBUG,ENTRY_PROBE level=#<level> zs=#<z_start> apz=#<ap_z> apr=#<ap_x> sfz=#<sf_z> sfr=#<sf_x> on=#<sf_on> w=#<_pl_w_idx> air=#<sf_air> pa=#<pa_on> wf=#<w_from> prev=#<_pl_prev_lvl>)\n'
        '\t(DEBUG,ENTRY_FULL valid=#<_pl_st_full_valid> low=#<_pl_st_full_low> high=#<_pl_st_full_high> r=#<_pl_st_full_r>)\n'
                '\t(=== WHICH END IS ENTERED,')
    source = source.replace('\t\tG1 X[#<li_bax> * #<_diameter_mode>] Z#<li_baz>',
                            '\t\t(entry straight probe)\n\t\tG1 X[#<li_bax> * #<_diameter_mode>] Z#<li_baz>')
    source = source.replace('\t(THIS PASS CUT,',
        '\t(DEBUG,CUT_DONE level=#<level> zs=#<z_start> ze=#<z_end_cut>)\n\t(THIS PASS CUT,')
    sub.write_text(source)
    results = {}
    original_run, original_dump = P.subprocess.run, P._canon_dump
    with open('/tmp/ncam-rs274.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        cases = [('disabled', 0, {}), ('front', .2, {})]
        if controls:
            for name, changes in [
                    ('full_retract', dict(ret_mode=0)),
                    ('artificial', dict(sec_len=5)),
                    ('rounded', dict(li_rad=.1, lo_rad=.1)),
                    ('reverse', dict(dir=1)),
                    ('alternating', dict(dir=2)),
                    ('inches', dict(units=20)),
                    ('no_lead', dict(li_len=0)),
                    ('no_global_extension', dict(ext_fr=0)),
                    ('off', dict(sectioning=0))]:
                cases += [(name+'_zero', 0, changes), (name, .2, changes)]
        for name, front, changes in cases:
            data = copy.deepcopy(saved)
            poly = data.find('.//feature[@type="polyline"]')
            values = dict(sec_ext_fr=front, sec_ext_bk=0, dir=0,
                          sectioning=1, sec_len=0, ret_mode=1, li_len=1, li_rad=0,
                          lo_len=1, lo_rad=0)
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
            # Added straight radial cutting feeds are visible green in preview.
            radial = [m for m in tp.moves if m.op == 'Lathe Polyline'
                      and m.kind == 'feed' and not m.subs
                      and abs(m.a[2]-m.b[2]) < 1e-6 and abs(m.a[0]-m.b[0]) > .01]
            material = Material(35, 0, -76, 4, n=40000)
            air_radials, collisions = [], []
            for move in tp.moves:
                physical = move._replace(a=tuple(v*scale for v in move.a),
                                         b=tuple(v*scale for v in move.b))
                depth = material.depth(physical)
                if move.kind == 'rapid' and depth > .01:
                    collisions.append(dict(a=physical.a, b=physical.b, depth=depth))
                if move in radial and depth < .01:
                    air_radials.append(dict(a=physical.a, b=physical.b, depth=depth))
                if move.kind == 'feed':
                    material.cut(physical)
            face_entries = [r for r in rows if r['wf'] >= -1e-6]
            results[name] = dict(entries=rows, air_radials=air_radials,
                                 collisions=collisions, face_entries=face_entries, active=len(active), inward=inward,
                                 actual_front_moves=len(actual),
                                 radial_feed_count=len(radial),
                                 radial_feeds=[dict(a=tuple(v*scale for v in m.a),
                                                    b=tuple(v*scale for v in m.b)) for m in radial],
                                 motion_hash=hashlib.sha256(repr([
                                     (m.kind, m.a, m.b, m.feed, m.fmode)
                                     for m in tp.moves]).encode()).hexdigest(),
                                 max_radial_feed=max([abs(m.a[0]-m.b[0])*scale for m in radial] or [0]))
            (root / 'results.json').write_text(json.dumps(results, indent=2))
            # Independently measure the actually traversed straight leads.
            leads, point, pending = [], None, False
            for line in out.with_suffix('.canon').read_text().splitlines():
                if 'COMMENT("entry straight probe")' in line:
                    pending = True
                match = re.search(r'STRAIGHT_(FEED|TRAVERSE)\(([^)]*)\)', line)
                if match:
                    v = [float(x)*scale for x in match[2].split(',')]
                    target = (v[0], v[2])
                    if pending:
                        assert match[1] == 'FEED' and point is not None
                        leads.append(math.dist(point, target))
                        pending = False
                    point = target
                arc = re.search(r'ARC_FEED\(([^)]*)\)', line)
                if arc:
                    v = [float(x)*scale for x in arc[1].split(',')]
                    point = (v[1], v[0])
            results[name]['lead_lengths'] = leads
            results[name]['cut_ends'] = re.findall(r'MESSAGE\("CUT_DONE ([^"\n]*)', text)
            (root / 'results.json').write_text(json.dumps(results, indent=2))
            print(name, 'entries', len(rows), 'extensions', len(active),
                  'air radial feeds', len(air_radials),
                  'rapid penetrations', len(collisions), flush=True)
    print('ARTIFACTS', root, flush=True)
    for name in ('disabled', 'front'):
        faces = results[name]['face_entries']
        assert faces, name
        assert max(p['zs'] for p in faces) - min(p['zs'] for p in faces) < .0001, (name, 'inconsistent front reference')
        assert results[name]['lead_lengths']
        assert all(abs(length-1) < .001 for length in results[name]['lead_lengths']), 'configured lead lost'
    assert all(abs(p['sfz']-p['apz']-.2) < .0001 for p in results['front']['face_entries'])
    assert not results['front']['air_radials'], 'radial cutting feeds through already-cleared stock'
    for row in results['front']['cut_ends']:
        cut = dict((k, float(v)) for k, v in re.findall(r'(\w+)=([-\d.]+)', row))
        assert min(cut['zs'], cut['ze']) <= 0, ('air-only pass escaped short filter', cut)
    # Compare each changed configuration with its own zero-extension control.
    for name, _, _ in cases:
        if name == 'disabled' or name.endswith('_zero'):
            continue
        baseline = results['disabled' if name == 'front' else name+'_zero']
        current = results[name]
        before = {(tuple(m['a']), tuple(m['b'])) for m in baseline['collisions']}
        after = {(tuple(m['a']), tuple(m['b'])) for m in current['collisions']}
        assert after <= before, (name, 'new rapid collisions', after-before)
        assert current['cut_ends'] == baseline['cut_ends'], (name, 'cut endpoints changed')
    if controls:
        assert results['off']['motion_hash'] == results['off_zero']['motion_hash']
    print('[VERDICT: PASS]')


if __name__ == '__main__':
    main()
