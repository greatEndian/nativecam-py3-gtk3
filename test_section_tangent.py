#!/usr/bin/env python3
"""Section front follows its entry; back follows the profile tangent."""
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

HERE = Path(__file__).resolve().parent


def extensions(canon, scale):
    position, pending, result = None, None, []
    for line in canon.splitlines():
        marker = re.search(r'COMMENT\("section tangent (front|back)"\)', line)
        if marker:
            pending = marker[1]
        move = re.search(r'STRAIGHT_(FEED|TRAVERSE)\(([^)]*)\)', line)
        if move:
            values = [float(v) for v in move[2].split(',')]
            point = (values[2] * scale, values[0] * scale)
            if pending:
                assert move[1] == 'FEED'
                length = math.dist(position, point)
                if length > 1e-8:       # canon prints coordinates to 4 places
                    result.append(dict(end=pending, a=position, b=point,
                                       length=length))
                pending = None
            position = point
        arc = re.search(r'ARC_FEED\(([^)]*)\)', line)
        if arc:
            values = [float(v) for v in arc[1].split(',')]
            position = (values[0] * scale, values[1] * scale)
    assert pending is None
    return result


def profile_tangent_dot(rows, points, scale):
    """Compare measured extensions with nearby compensated profile segments."""
    points = [(z * scale, r * scale) for z, r in points]
    minimum = 1.0
    for row in rows:
        if row['length'] < .02:  # four-decimal canon quantization dominates
            continue
        dz = row['b'][0] - row['a'][0]
        dr = row['b'][1] - row['a'][1]
        dots = []
        for a, b in zip(points, points[1:]):
            if not any(min(a[0], b[0]) - .004 <= p[0]
                       <= max(a[0], b[0]) + .004 for p in (row['a'], row['b'])):
                continue
            length = math.dist(a, b)
            if length > 1e-8:
                dots.append(abs(dz * (b[0]-a[0]) + dr * (b[1]-a[1]))
                            / (row['length'] * length))
        assert dots and max(dots) > .9999, ('extension left local tangent', row)
        minimum = min(minimum, max(dots))
    return minimum


def main():
    smoke = '--smoke' in sys.argv
    blend_smoke = '--blends' in sys.argv
    edge_smoke = '--edges' in sys.argv
    import lathe_sections as L
    # Analytic horizontal tangent: blend center R+radius; its two lead
    # tangent points lie on opposite sides of that circle.
    for end, sign in ((0, 1), (1, -1)):
        fp = L.tangent_lead_footprint((-1, 0), 1, 45, .2, 1, 1, end)
        assert fp['cz'] == 0 and fp['cr'] == .2
        assert abs(fp['tz'] - sign * math.sqrt(.02)) < 1e-12
        assert abs(fp['tr'] - (.2-sign*math.sqrt(.02))) < 1e-12
        assert abs(math.hypot(fp['tz']-fp['cz'], fp['tr']-fp['cr'])-.2) < 1e-12
    root = Path(tempfile.mkdtemp(prefix='ncam_section_tangent_'))
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
    old = etree.parse(str(
        cfg / 'ncam/catalogs/lathe/projects/testing_15_9.xml')).getroot()
    # Exercise the addition of these fields even after the user saves new
    # values into the live fixture; migration must preserve values that exist.
    old_poly = old.find('.//feature[@type="polyline"]')
    old_poly.set('version', '1.83')
    for p in old_poly.findall('param'):
        if p.get('call') in ('#param_sec_ext_fr', '#param_sec_ext_bk'):
            old_poly.remove(p)
    saved = app.update_features(old)
    for key in ('sec_ext_fr', 'sec_ext_bk'):
        migrated = saved.find('.//feature[@type="polyline"]/param[@call="#param_%s"]' % key)
        assert migrated.get('type') == 'float' and float(migrated.get('value')) == 0
        assert migrated.get('header') == 'h_opt'
    results = {}
    original_dump = P._canon_dump

    def generate(name, front=0, back=0, **overrides):
        data = copy.deepcopy(saved)
        poly = data.find('.//feature[@type="polyline"]')
        values = dict(op=1, pf_on=0, sectioning=1, sec_len=5, dir=0,
                      sec_ext_fr=front, sec_ext_bk=back)
        values.update(overrides)
        units = values.pop('units', 21)
        flat = values.pop('flat', False)
        scalar = values.pop('scalar', False)
        for key, value in values.items():
            param = poly.find('./param[@call="#param_%s"]' % key)
            if param is None:
                assert key in ('sec_ext_fr', 'sec_ext_bk')
                param = etree.SubElement(poly, 'param', call='#param_' + key,
                                         name=key, type='float', metric_value='0')
            param.set('value', str(value / 25.4 if param.get('metric_value') is not None else value))
        data.find('.//feature[@type="workpiece"]/param[@call="#param_units"]').set('value', str(units))
        app.treestore_from_xml(data)
        out = root / (name + '.ngc')
        import lathe_sections as L
        with patch.dict('os.environ', {'NCAM_FLAT': '1' if flat else ''}), \
                patch.object(L, 'LVL_TOP', L.LVL_BASE if scalar else L.LVL_TOP):
            out.write_text(app.to_gcode())
        if flat:
            assert int(re.findall(r'#<_pl_flat_sub>\s*=\s*(\d+)', out.read_text())[-1]) > 0
        raw = []

        def dump(*args):
            canon, error = original_dump(*args)
            if canon:
                raw.append(canon)
                out.with_suffix('.canon').write_text(canon)
            return canon, error

        with patch.object(P, '_canon_dump', dump):
            tp = P.parse_program(str(out), str(ini))
        assert tp.completed and not tp.error, (name, tp.error, root)
        signature = [(m.kind, m.a, m.b, m.feed, m.fmode) for m in tp.moves]
        rows = extensions(raw[0], 25.4 if units == 20 else 1)
        tangent_dot = profile_tangent_dot(
            [r for r in rows if r['end'] == 'back'],
            L.SECTION_TANGENT_PLANS[0]['points'],
            25.4 if units == 20 else 1) if rows else 1.0
        results[name] = dict(moves=len(tp.moves), extensions=rows,
                             profile_dot=tangent_dot,
                             motion_hash=hashlib.sha256(repr(signature).encode()).hexdigest())
        (root / 'results.json').write_text(json.dumps(results, indent=2))
        print(name, len(rows), 'extensions', flush=True)
        return results[name]

    def check(result, front, back):
        rows = result['extensions']
        for side, length in [('front', front), ('back', back)]:
            selected = [r for r in rows if r['end'] == side]
            if length:
                assert selected, ('missing section tangent', side, root)
                assert all(0 < r['length'] <= length + .004 for r in selected)
                if side == 'back':
                    assert any(abs(r['a'][0]-r['b'][0]) > .01
                               and abs(r['a'][1]-r['b'][1]) > .01 for r in selected), 'extension ignored profile slope'
                # Front follows the actual entry, which can be axial when
                # there is no profile-angle ramp. The entry regression checks
                # that direction and requested offset against actual feeds.
            else:
                assert not selected

    with open('/tmp/ncam-rs274.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if edge_smoke:
            generate('zero_allowance_off', f_off=0, pf_off=0)
            check(generate('zero_allowance', front=.7, back=1.3,
                           f_off=0, pf_off=0), .7, 1.3)
            print('ARTIFACTS', root)
            print('[VERDICT: PASS]')
            return
        if blend_smoke:
            generate('zero_blends', li_rad=.1, lo_rad=.1)
            check(generate('blends', front=.7, back=1.3, li_rad=.1, lo_rad=.1), .7, 1.3)
            print('ARTIFACTS', root)
            print('[VERDICT: PASS]')
            return
        zero = generate('zero')
        check(generate('front', front=1), 1, 0)
        check(generate('back', back=1.5), 0, 1.5)
        if smoke:
            print('ARTIFACTS', root)
            print('[VERDICT: PASS]')
            return
        for name, kwargs in [('both', {}), ('reverse', dict(dir=1)),
                             ('alternating', dict(dir=2)), ('inches', dict(units=20)),
                             ('natural', dict(sec_len=0)), ('ordinary', dict(min_pass=0)),
                             ('flat', dict(min_pass=0, flat=True)),
                             ('scalar', dict(min_pass=0, scalar=True)),
                             ('blends', dict(li_rad=.1, lo_rad=.1)),
                             ('no_leads', dict(li_len=0, lo_len=0)),
                             ('zero_allowance', dict(f_off=0, pf_off=0)),
                             ('full', dict(op=0, pf_on=1)),
                             ('pecks', dict(peck_len=2, peck_ret=.1, peck_dwell=.01))]:
            check(generate(name, front=.7, back=1.3, **kwargs), .7, 1.3)
        off = generate('section_off', sectioning=0)
        ignored = generate('section_off_values', front=1, back=2, sectioning=0)
        assert off['motion_hash'] == ignored['motion_hash']
        reset = generate('reset_zero')
        assert reset['motion_hash'] == zero['motion_hash'], 'tangent plan leaked across generations'
    print('ARTIFACTS', root)
    print('[VERDICT: PASS]')


if __name__ == '__main__':
    main()
