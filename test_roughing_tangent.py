#!/usr/bin/env python3
"""Roughing tangents work without sectioning and keep finishing independent."""
import configparser
import copy
import fcntl
from pathlib import Path
import shutil
import sys
import tempfile
from unittest.mock import patch

from lxml import etree

import ncam_preview as preview
import lathe_sections
from test_section_tangent import extensions, profile_tangent_dot
from test_air_leads import Material

HERE = Path(__file__).resolve().parent


def main():
    root = Path(tempfile.mkdtemp(prefix='ncam_roughing_tangent_'))
    config = root / 'config'
    shutil.copytree(HERE / 'configs/sim/axis/ncam_demo', config, symlinks=True)
    settings = config / 'ncam/catalogs/ncam.conf'
    prefs = configparser.ConfigParser(interpolation=None)
    prefs.read(settings)
    prefs.set('layout', 'autorefresh', 'False')
    with settings.open('w') as stream:
        prefs.write(stream)
    (config / 'lathe_mm.tbl').write_text('T2 P2 D0.8 I15 J75 Q2 ; regression tool\n')
    ini = config / 'lathe-mm.ini'
    sys.argv = ['ncam.py', '-i', str(ini), '-c', 'lathe']
    import ncam
    app = ncam.NCam()
    app.pref.autosave = False

    def feature(source, number, **values):
        item = ncam.Feature(src=str(HERE / 'cfg/lathe' / source))
        item.attr.update(src='lathe/' + source, id=item.get_type() + '_%03d' % number)
        for key, value in values.items():
            param = item.get_param('param_' + key)
            param.attr['value'] = str(value / 25.4 if 'metric_value' in param.attr else value)
        return item.to_xml()

    project = etree.Element(ncam.XML_TAG)
    project.append(feature('material.cfg', 1, od=50, units=21))
    project.append(feature('tool-change.cfg', 1, dnum=2, c_dpt=.5))
    poly = feature('polyline.cfg', 1, b_x=50, e_x=10, op=0, pf_on=1,
                   f_off=.508, pf_off=.254, n_comp=1, sectioning=0,
                   fr_z_on=1, fr_z=10, fr_z_dat=0,
                   ext_fr=0, ext_bk=0, f_ext_fr=2, f_ext_bk=1,
                   sec_ext_fr=0, sec_ext_bk=0, li_len=0, li_rad=0,
                   lo_len=0, lo_rad=0, min_pass=0, skip_thin=0)
    items = poly.find('param[@type="items"]')
    for i, (x, z, flip) in enumerate(((25, 0, 0), (25, -25, 1), (50, -25, 0)), 1):
        items.append(feature('polyline-to.cfg', i, type=1, x=x, z=z,
                             m_style=1, m_r=5, m_flip=flip))
    project.append(poly)
    original_dump = preview._canon_dump

    def generate(name, front=0, back=0, direction=0, units=21, ramp=False, **values):
        data = copy.deepcopy(project)
        parent = data.find('feature[@type="polyline"]')
        values.update(ext_fr=front, ext_bk=back, dir=direction)
        for key, value in values.items():
            param = parent.find('param[@call="#param_%s"]' % key)
            param.set('value', str(value / 25.4 if param.get('metric_value') is not None else value))
        if ramp:
            children = parent.find('param[@type="items"]')
            for child, (x, z) in zip(children, ((45, 0), (25, -10), (50, -25))):
                for key, value in (('x', x/25.4), ('z', z/25.4), ('m_style', 0)):
                    child.find('param[@call="#param_%s"]' % key).set('value', str(value))
        data.find('feature[@type="workpiece"]/param[@call="#param_units"]').set('value', str(units))
        app.treestore_from_xml(data)
        out = root / (name + '.ngc')
        out.write_text(app.to_gcode())
        canon = []

        def dump(*args):
            raw, error = original_dump(*args)
            if raw:
                canon.append(raw)
                out.with_suffix('.canon').write_text(raw)
            return raw, error

        with patch.object(preview, '_canon_dump', dump):
            path = preview.parse_program(str(out), str(ini))
        assert path.completed and not path.error, (name, path.error, root)
        rows = extensions(canon[0], 25.4 if units == 20 else 1)
        if back:
            profile_tangent_dot([r for r in rows if r['end'] == 'back'],
                                lathe_sections.SECTION_TANGENT_PLANS[0]['points'],
                                25.4 if units == 20 else 1)
        if ramp:
            assert any(abs(r['b'][1] - r['a'][1]) > .02 for r in rows), 'entry tangent ignored the ramp'
        for side, requested in (('front', front), ('back', back)):
            measured = [r for r in rows if r['end'] == side]
            if not requested:
                assert not measured, (name, 'unexpected tangent', side)
            else:
                assert measured, (name, 'missing roughing tangent', side, root)
                assert all(0 < r['length'] <= requested + .004 for r in measured)
                if side == 'front':
                    assert any(abs(r['length'] - requested) < .004 for r in measured)
                    has_leads = any(values.get(k, 0) for k in ('li_len', 'li_rad', 'lo_len', 'lo_rad'))
                    if not ramp and not values.get('sectioning') and not has_leads:
                        assert all(abs(r['length'] - requested) < .004 for r in measured)
                    if direction != 2:
                        assert all((r['b'][0] - r['a'][0]) * (1 if direction else -1) > 0
                                   for r in measured), (name, 'front tangent reversed')
        phases = {
            phase: [(m.a, m.b) for m in path.moves if m.kind == 'feed' and phase in m.subs]
            for phase in (preview.PREFINISH, preview.FINISH)}
        if front and not direction and not ramp and not values.get('sectioning'):
            stock = Material(25, 0, -40, 10, n=40000)
            for move in path.moves:
                if preview.PREFINISH in move.subs or preview.FINISH in move.subs:
                    break
                move = move._replace(a=tuple(v * (25.4 if units == 20 else 1) for v in move.a),
                                     b=tuple(v * (25.4 if units == 20 else 1) for v in move.b))
                if move.kind == 'rapid':
                    assert stock.depth(move) < .01, (name, 'rapid through remaining stock', move)
                elif move.kind == 'feed':
                    stock.cut(move)
        print('PASS', name, len(rows), 'roughing tangents', flush=True)
        return phases

    with open('/tmp/ncam-rs274.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        baseline = generate('disabled')
        assert generate('front-1', front=1) == baseline
        assert generate('front-2', front=2) == baseline
        generate('reverse', front=2, direction=1)
        generate('alternating', front=2, direction=2)
        generate('inches', front=2, units=20)
        generate('back', back=1)
        generate('ramp', front=1, ramp=True)
        generate('leads', front=1, li_len=.5, lo_len=.5, li_rad=.1, lo_rad=.1)
        generate('sectioned', front=1, sectioning=1, sec_len=5)
        assert generate('reset') == baseline
    print('ARTIFACTS', root, flush=True)
    print('[VERDICT: PASS]')


if __name__ == '__main__':
    main()
