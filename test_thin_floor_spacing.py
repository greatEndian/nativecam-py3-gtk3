#!/usr/bin/env python3
"""Thin protected floor landings are redistributed without exceeding DOC."""
import configparser
import copy
import fcntl
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
from unittest.mock import patch

from lxml import etree
import ncam_preview as P

HERE = Path(__file__).resolve().parent


def pure_checks():
    import lathe_sections as L
    for scale in (1.0, 1 / 25.4):
        for direction in (-1, 1):
            start = 35 * scale
            floor = start + direction * 13.984 * scale
            old = direction * .4980446818 * scale
            step, first = L.spread_thin_floor(start, floor, old, old, .508 * scale, .2 * scale)
            assert abs(step - direction * 13.984 / 28 * scale) < 1e-10
            assert step == first and .2 * scale <= abs(step) <= .508 * scale
            for threshold in (0, .02, .6):
                assert L.spread_thin_floor(start, floor, old, old, .508 * scale,
                                           threshold * scale) == (old, old)
    # A genuinely narrow region still needs its floor; a zero/wrong-way
    # stride cannot be repaired by inventing a new cutting direction.
    for start, floor, step, first, doc, minimum in (
            (10, 9.9, -.5, -.5, .5, .2), (10, 9, 0, 0, .5, .2),
            (10, 9, .5, .5, .5, .2), (10, 9, -.5, -.5, 0, .2)):
        assert L.spread_thin_floor(start, floor, step, first, doc, minimum) == (step, first)
    print('PASS pure spacing: OD/ID signs, both units, threshold bounds and required narrow floors', flush=True)


def main():
    pure_checks()
    root = Path(tempfile.mkdtemp(prefix='ncam_thin_floor_'))
    cfg = root / 'config'
    shutil.copytree(HERE / 'configs/sim/axis/ncam_demo', cfg, symlinks=True)
    settings = cfg / 'ncam/catalogs/ncam.conf'
    prefs = configparser.ConfigParser(interpolation=None)
    prefs.read(settings)
    prefs.set('layout', 'autorefresh', 'False')
    with settings.open('w') as stream:
        prefs.write(stream)
    sys.argv = ['ncam.py', '-i', str(cfg / 'lathe-mm.ini'), '-c', 'lathe']
    import ncam
    import lathe_sections as L
    app = ncam.NCam()
    saved = app.update_features(etree.parse(str(cfg / 'ncam/catalogs/lathe/projects/testing_15_9.xml')).getroot())
    library = root / 'lib'
    shutil.copytree(HERE / 'lib', library)
    sub = library / 'lathe/lathe_level_pass.ngc'
    s = sub.read_text()
    marker = '\t(CHIP BREAKING.'
    assert s.count(marker) == 1
    s = s.replace(marker, '\t(debug, FLOORPASS w=#<_pl_w_idx> r=#<level> za=#<em_z0> zb=#<em_z1>)\n' + marker)
    sub.write_text(s)
    ini = cfg / 'lathe-mm.ini'
    ini.write_text(re.sub(r'(?m)^SUBROUTINE_PATH\s*=.*$',
                         'SUBROUTINE_PATH = ' + str(library / 'lathe') + ':' + str(library / 'utilities'),
                         ini.read_text()))
    results = {}
    original_dump = P._canon_dump
    def generate(name, threshold=.2, anchor=1, direction=0, units=21, minimum=.5,
                 table=True, section=1, section_length=None, flat=False, redistribute=True):
        data = copy.deepcopy(saved)
        poly = data.find('.//feature[@type="polyline"]')
        values = dict(pass_from=anchor, skip_thin=threshold, min_pass=minimum,
                      dir=direction, sectioning=section, peck_len=0)
        if section_length is not None:
            values['sec_len'] = section_length
        for key, value in values.items():
            param = poly.find('./param[@call="#param_%s"]' % key)
            param.set('value', str(value / 25.4 if param.get('metric_value') is not None else value))
        data.find('.//feature[@type="workpiece"]/param[@call="#param_units"]').set('value', str(units))
        app.treestore_from_xml(data)
        out = root / (name + '.ngc')
        normalizer = L.spread_thin_floor if redistribute else lambda *args: (args[2], args[3])
        with patch.object(L, 'LVL_TOP', L.LVL_TOP if table else L.LVL_BASE), \
                patch.object(L, 'spread_thin_floor', normalizer), \
                patch.dict('os.environ', {'NCAM_FLAT': '1' if flat else ''}):
            out.write_text(app.to_gcode())
        if flat:
            assert int(re.findall(r'#<_pl_flat_sub>\s*=\s*(\d+)', out.read_text())[-1]) > 0
        canon_text = []
        def dump(*args):
            canon, error = original_dump(*args)
            if canon:
                out.with_suffix('.canon').write_text(canon)
                canon_text.append(canon)
            return canon, error
        with patch.object(P, '_canon_dump', dump):
            tp = P.parse_program(str(out), str(ini))
        assert tp.completed and not tp.error, (name, tp.error, root)
        scale = 25.4 if units == 20 else 1
        rows = []
        for line in canon_text[0].splitlines():
            if 'FLOORPASS' in line:
                row = {k: float(v) for k, v in re.findall(r'(w|r|za|zb)=(-?[\d.]+)', line)}
                if row:
                    rows.append({k: v if k == 'w' else v * scale for k, v in row.items()})
        assert rows
        # Window numbering reverses with travel direction. Identify the
        # physical front section by its Z span, not by window index zero.
        front_rows = [r for r in rows if max(r['za'], r['zb']) > -.5]
        radii = list(dict.fromkeys(round(r['r'], 5) for r in front_rows))
        gaps = [abs(a-b) for a, b in zip([35]+radii, radii)]
        signature = [(m.kind, tuple(round(v * scale, 6) for v in m.a),
                      tuple(round(v * scale, 6) for v in m.b), m.feed, m.fmode)
                     for m in tp.moves]
        result = dict(moves=len(tp.moves), front_radii=radii, gaps_mm=gaps,
                      min_gap_mm=min(gaps) if gaps else None,
                      max_gap_mm=max(gaps) if gaps else None,
                      front_passes=len(front_rows),
                      motion_hash=hashlib.sha256(repr(signature).encode()).hexdigest(),
                      rows=rows)
        results[name] = result
        (root / 'results.json').write_text(json.dumps(results, indent=2))
        print(name, 'moves', result['moves'], 'front gaps', result['min_gap_mm'], result['max_gap_mm'], flush=True)
        return result

    def floor_is_clean(result):
        radii = result['front_radii']
        assert any(abs(r-21.016) < .0003 for r in radii), 'required floor was dropped'
        assert min(result['gaps_mm']) >= .2-.0003, ('thin floor survived', result['gaps_mm'], root)
        assert max(result['gaps_mm']) <= .508+.0003, ('overloaded cut', result['gaps_mm'], root)
        assert result['front_passes'] == len(radii), ('duplicate floor pass', result['front_passes'], len(radii), root)

    with open('/tmp/ncam-rs274.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        off = generate('final_off', threshold=0)
        fixed = generate('final_on')
        floor_is_clean(fixed)
        assert len(fixed['front_radii']) == 28
        assert len(off['front_radii']) == 29 and min(off['gaps_mm']) < .04
        low = generate('final_below', threshold=.02)
        assert low['motion_hash'] == off['motion_hash'], 'below-thin threshold changed motion'
        stock_off = generate('stock_off', threshold=0, anchor=0)
        stock_on = generate('stock_on', anchor=0)
        assert stock_off['motion_hash'] == stock_on['motion_hash'], 'Stock spacing changed'
        for name, kwargs in [('reverse', dict(direction=1)), ('alternating', dict(direction=2)),
                             ('inches', dict(units=20)), ('unmerged', dict(minimum=0)),
                             ('scalar_fallback', dict(minimum=0, table=False)),
                             ('flat', dict(minimum=0, flat=True))]:
            floor_is_clean(generate(name, **kwargs))
        # Sectioning is a boolean. Natural means enabled with zero section
        # length; any positive length selects artificial sectioning.
        for name, kwargs in [('unsectioned', dict(section=0)),
                             ('natural', dict(section=1, section_length=0))]:
            a = generate(name + '_before', redistribute=False, **kwargs)
            b = generate(name + '_after', **kwargs)
            assert a['motion_hash'] == b['motion_hash'], ('unrelated spacing changed', name)
    print('ARTIFACTS', root)
    print('[VERDICT: PASS]')


if __name__ == '__main__':
    main()
