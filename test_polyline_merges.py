#!/usr/bin/env python3
"""Merge curves agree with rs274, and start items cannot merge into the tail."""
import configparser
import copy
import math
from pathlib import Path
import shutil
import sys
import tempfile
from unittest.mock import patch

from lxml import etree

import lathe_sections as ls
import test_sections as oracle

HERE = Path(__file__).resolve().parent
POINTS = [(40, 1), (40, -10), (60, -10), (60, -20), (40, -20), (60, -30)]
RAW_GCODE = oracle.gcode_for


def item_call(item):
    p = item.params
    return ('o<poly_add_item> CALL [%s] [%s] [%s / #<_diameter_mode>] '
            '[1] [%s] [%s] [%s] [1] [%s] [0] [0]'
            % (p['param_type'], p['param_z'], p['param_x'], int(p['param_m_style'] == '1'),
               p['param_m_r'], 0, p.get('param_m_b', 0)))


def merged_gcode(feature, mesh=False):
    return RAW_GCODE(feature, mesh).replace('o<poly_create> CALL',
        ls.build_chamfer_gcode(feature) + '\n' + ls.build_radius_flip_gcode(feature) + '\no<poly_create> CALL')


def geometry_checks():
    with patch.object(oracle, 'item_call', item_call), patch.object(oracle, 'gcode_for', merged_gcode):
        cases = [('radius-%d' % i, i, 1, 0, 0) for i in range(1, len(POINTS))]
        cases += [('second-item chamfer', 1, 2, 0, 0), ('chamfer', 2, 2, 0, 0), ('two lengths', 2, 21, 3, 0),
                  ('two lengths flipped', 2, 21, 3, 1), ('angle', 2, 22, 30, 0)]
        for name, index, style, second, flip in cases:
            children = [oracle.line_to(x, z) for x, z in POINTS]
            children[index].params.update(param_m_style=str(style), param_m_r='2',
                                          param_m_b=str(second), param_m_flip=str(flip))
            poly = oracle.Poly(0, 80, children)
            wanted = [(z, r * ls.DIAMETER_MODE) for z, r in oracle.trace(poly, mesh=True)]
            got = ls.resolve_points(poly, trim=False, extend=False)
            assert len(got) == len(wanted), (name, 'different point count', len(got), len(wanted))
            assert all(math.dist(a, b) < .001 for a, b in zip(got, wanted)), (name, got, wanted)
            assert got[-1] == (-30, 60), 'merge moved the back of the profile'
            if index > 1:
                assert got[0] == (1, 40), 'later merge moved the profile start'
            print('PASS  interpreter geometry:', name, flush=True)


def radius_flip_checks():
    children = [oracle.line_to(25, 0), oracle.line_to(25, -25, m_r=5),
                oracle.line_to(50, -25, m_r=5)]
    poly = oracle.Poly(0, 50, children)
    normal = ls.resolve_points(poly, trim=False, extend=False)
    children[1].params['param_m_flip'] = '1'
    flipped = ls.resolve_points(poly, trim=False, extend=False)
    assert normal[0] == (0, 35)
    assert math.dist(flipped[0], (0, 15)) < 1e-8, ('Flip must select the opposite R5 quarter-circle', flipped[0])
    assert any(math.dist(p, (-5, 25)) < 1e-8 for p in flipped) and flipped[-1] == (-25, 50)
    old_gcode = oracle.gcode_for

    def gcode(feature, mesh=False):
        return old_gcode(feature, mesh).replace(
            'o<poly_create> CALL', ls.build_radius_flip_gcode(feature) + '\no<poly_create> CALL')

    def call(item):
        data = copy.deepcopy(item)
        if data.params['param_m_style'] == '1':
            data.params['param_m_flip'] = '0'  # Radius Flip changes the reference, never the sweep.
        return item_call(data)

    with patch.object(oracle, 'gcode_for', gcode), patch.object(oracle, 'item_call', call):
        raw = oracle.machine_records(poly)
        assert math.dist((raw[0]['z'], raw[0]['r']), (0, 7.5)) < .001
        arc = raw[1]
        assert arc['dir'] == 3 and all(abs(arc[k] - v) < .001 for k, v in
                                      [('z', -5), ('r', 12.5), ('cz', -5), ('cr', 7.5)]), arc
        wanted = [(z, 2 * r) for z, r in oracle.trace(poly, mesh=True)]
        assert len(wanted) == len(flipped)
        assert all(math.dist(a, b) < .001 for a, b in zip(wanted, flipped))
    print('PASS  first-corner Flip selects X15 Z0 to X25 Z-5, R5, with a 90-degree sweep', flush=True)


def chamfer_flip_checks():
    for style, second, depth in [(2, 0, 5), (21, 3, 3), (22, 30, 5 / math.sqrt(3))]:
        children = [oracle.line_to(25, 0), oracle.line_to(25, -25)]
        children[1].params.update(param_m_style=str(style), param_m_r='5',
                                  param_m_b=str(second), param_m_flip='1')
        poly = oracle.Poly(0, 50, children)
        points = ls.resolve_points(poly, trim=False, extend=False)
        assert math.dist(points[0], (0, 15)) < .001, ('chamfer Flip did not select the opposite side', style, points)
        assert math.dist(points[1], (-depth, 25)) < .001, ('chamfer dimensions swapped', style, points)
        with patch.object(oracle, 'item_call', item_call), patch.object(oracle, 'gcode_for', merged_gcode):
            actual = [(r['z'], r['r'] * 2) for r in oracle.machine_records(poly)]
            assert len(actual) == len(points) and all(math.dist(a, b) < .001 for a, b in zip(actual, points)), actual
        print('PASS  chamfer starting-side Flip:', style, flush=True)


def application_checks():
    root = Path(tempfile.mkdtemp(prefix='ncam_merge_regression_'))
    config = root / 'config'
    shutil.copytree(HERE / 'configs/sim/axis/ncam_demo', config, symlinks=True)
    settings = config / 'ncam/catalogs/ncam.conf'
    prefs = configparser.ConfigParser(interpolation=None)
    prefs.read(settings)
    prefs.set('layout', 'autorefresh', 'False')
    with settings.open('w') as output:
        prefs.write(output)
    ini = config / 'lathe-mm.ini'
    # A known small nose isolates merge geometry from the user's tool table.
    (config / 'lathe_mm.tbl').write_text('T1 P1 D0.008 I0 J0 Q9 ; merge regression tool\n')
    sys.argv = ['ncam.py', '-i', str(ini), '-c', 'lathe']
    import ncam
    import ncam_preview
    app = ncam.NCam()
    app.pref.autosave = False

    def feature(source, number):
        f = ncam.Feature(src=str(HERE / 'cfg/lathe' / source))
        f.attr.update(src='lathe/' + source, id=f.get_type() + '_%03d' % number)
        return f

    def put(f, key, value):
        p = f.get_param('param_' + key)
        p.attr['value'] = str(value / 25.4 if 'metric_value' in p.attr else value)

    stock = feature('material.cfg', 1)
    poly = feature('polyline.cfg', 1)
    for key, value in [('b_x', 80), ('e_x', 10), ('op', 1), ('pf_on', 0),
                       ('n_comp', 2), ('f_off', 0), ('f_pass', 1), ('li_len', 0),
                       ('lo_len', 0), ('flank', 0), ('front_flank', 0)]:
        put(poly, key, value)
    project = etree.Element(ncam.XML_TAG)
    project.append(stock.to_xml())
    tool = feature('tool-change.cfg', 1)
    put(tool, 'dnum', 1)
    project.append(tool.to_xml())
    parent = poly.to_xml()
    items = parent.find('param[@type="items"]')
    for index, (x, z) in enumerate(POINTS, 1):
        line = feature('polyline-to.cfg', index)
        for key, value in [('type', 1), ('x', x), ('z', z), ('m_style', 0), ('m_r', 2)]:
            put(line, key, value)
        items.append(line.to_xml())
    project.append(parent)

    paths = {}

    def generate(data, name, phase=None):
        app.treestore_from_xml(copy.deepcopy(data))
        code = app.to_gcode()
        path = root / (name + '.ngc')
        path.write_text(code)
        tp = ncam_preview.parse_program(str(path), str(ini))
        assert tp.completed and not tp.error, tp.error
        paths[name] = tp
        return [(m.kind, m.a, m.b, m.cat) for m in tp.moves if phase is None or phase in m.subs]

    baseline = generate(project, 'baseline')
    for index in (0,):
        modified = copy.deepcopy(project)
        node = modified.find('feature[@type="polyline"]/param[@type="items"]')[index]
        node.find('param[@call="#param_m_style"]').set('value', '1')
        node.find('param[@call="#param_m_r"]').set('value', str(2 / 25.4))
        assert generate(modified, 'ignored-start-%d' % index) == baseline, ('start merge moved path', index)
    broken = copy.deepcopy(project)
    first = broken.find('feature[@type="polyline"]/param[@type="items"]')[0]
    first.find('param[@call="#param_m_style"]').set('value', '1')
    first.set('call', first.get('call').replace(' * [#5000 GE 1]', ''))
    assert generate(broken, 'old-first-item-bug') != baseline, 'negative control did not reproduce the tail shift'
    print('PASS  start-item merge settings cannot move any toolpath point', flush=True)
    for style in (1, 2):
        second_merge = copy.deepcopy(project)
        second = second_merge.find('feature[@type="polyline"]/param[@type="items"]')[1]
        second.find('param[@call="#param_m_style"]').set('value', str(style))
        assert generate(second_merge, 'second-item-%d' % style) != baseline, 'second-item merge was ignored'
    print('PASS  second-item radius and chamfer change the actual cutting path', flush=True)

    # Verify the complete CAM finishing path, not only the analytical points.
    for units in (21, 20):
        scale = 1 if units == 21 else 25.4
        for style in (1, 2):
            modified = copy.deepcopy(project)
            modified.find('feature[@type="workpiece"]/param[@call="#param_units"]').set('value', str(units))
            profile = modified.find('feature[@type="polyline"]')
            profile.find('param[@call="#param_op"]').set('value', '2')
            line = profile.find('param[@type="items"]')[2]
            line.find('param[@call="#param_m_style"]').set('value', str(style))
            moves = generate(modified, 'join-%d-G%d' % (style, units))
            feeds = [((a[2] * scale, a[0] * scale), (b[2] * scale, b[0] * scale))
                     for kind, a, b, _ in moves if kind == 'feed']
            if style == 1:
                inside = [b for _, b in feeds if -9.999 < b[0] < -8.001 and 20.001 < b[1] < 21.999]
                assert len(inside) >= 2, ('radius became a chord', units, inside)
                assert all(abs(math.dist(p, (-8, 22)) - 2) < .008 for p in inside), inside
            else:
                assert any(math.dist(a, (-8, 20)) < .008 and math.dist(b, (-10, 22)) < .008
                           for a, b in feeds), ('missing chamfer feed', units)
            print('PASS  actual CAM join:', style, 'G%d' % units, flush=True)

    # Model the saved project's mixed references and migrate its old templates.
    flipped_project = copy.deepcopy(project)
    profile = flipped_project.find('feature[@type="polyline"]')
    profile.set('version', '1.88')
    for end, value in [('fr', 2), ('bk', 3)]:
        profile.remove(profile.find('param[@call="#param_f_ext_%s"]' % end))
        profile.find('param[@call="#param_ext_%s"]' % end).set('value', str(value / 25.4))
    profile.set('after', profile.get('after').replace(
        '<exec>print(lathe_sections.build_radius_flip_gcode(self))</exec>', ''))
    profile.find('param[@call="#param_b_x"]').set('value', str(50 / 25.4))
    profile.find('param[@call="#param_op"]').set('value', '2')
    items = profile.find('param[@type="items"]')
    for node in list(items)[3:]:
        items.remove(node)
    for index, (node, x, z, option) in enumerate(zip(items, [25, 0, 25], [0, -25, 0], [10, 0, 0])):
        node.set('version', '1.19')
        for key, value in [('x', x / 25.4), ('z', z / 25.4), ('type', option),
                           ('m_style', 1 if index else 0), ('m_r', 5 / 25.4), ('m_flip', int(index == 1))]:
            node.find('param[@call="#param_%s"]' % key).set('value', str(value))
    app.treestore_from_xml(flipped_project)
    flipped_project = app.update_features(app.treestore_to_xml())
    profile = flipped_project.find('feature[@type="polyline"]')
    assert profile.get('version') == '1.91' and 'build_radius_flip_gcode' in profile.get('after')
    for end, value in [('fr', 2), ('bk', 3)]:
        assert abs(float(profile.find('param[@call="#param_f_ext_%s"]' % end).get('value')) * 25.4 - value) < 1e-8
        for prefix in ('ext_', 'f_ext_'):
            profile.find('param[@call="#param_%s%s"]' % (prefix, end)).set('value', '0')
    assert profile.find('param[@type="items"]')[1].find('param[@call="#param_m_flip"]').get('value') == '1'
    for units in (21, 20):
        scale = 1 if units == 21 else 25.4
        for comp in (1, 2):
            modified = copy.deepcopy(flipped_project)
            modified.find('feature[@type="workpiece"]/param[@call="#param_units"]').set('value', str(units))
            modified.find('feature[@type="polyline"]/param[@call="#param_n_comp"]').set('value', str(comp))
            moves = generate(modified, 'flipped-%d-G%d' % (comp, units))
            points = [(p[2] * scale, p[0] * scale) for kind, a, b, _ in moves if kind == 'feed' for p in (a, b)]
            if comp == 1:
                assert min(math.dist(p, (0, 7.5)) for p in points) < .008, ('wrong flipped start', comp, units)
            else:
                # CAM clips the offset nose-centre path to front Z, along the circle.
                assert any(abs(z) < .001 and 7.5 <= r < 8 and abs(math.dist((z, r), (-5, 7.5)) - 5) < .008
                           for z, r in points), ('wrong flipped CAM start', units)
            assert min(math.dist(p, (-5, 12.5)) for p in points) < .008, ('wrong flipped end', comp, units)
            inside = [p for p in points if -4.99 < p[0] < -.01 and 7.51 < p[1] < 12.49]
            assert len(inside) >= 2 and all(abs(math.dist(p, (-5, 7.5)) - 5) < .008 for p in inside), inside
            print('PASS  migrated first-corner Flip: compensation', comp, 'G%d' % units, flush=True)

    # A prefinish allowance shifts the rounded front ahead of Start Z.
    # Projecting its first chord past the next point creates a reversed lead.
    for units in (21, 20):
        scale = 1 if units == 21 else 25.4
        for comp in (1, 2):
            modified = copy.deepcopy(flipped_project)
            modified.find('feature[@type="workpiece"]/param[@call="#param_units"]').set('value', str(units))
            profile = modified.find('feature[@type="polyline"]')
            for key, value in [('op', 1), ('pf_on', 1), ('f_off', .508 / 25.4), ('n_comp', comp)]:
                profile.find('param[@call="#param_%s"]' % key).set('value', str(value))
            # Phase tags identify the actual prefinish pass, independent of leads' inferred categories.
            moves = generate(modified, 'prefinish-entry-%d-G%d' % (comp, units), ncam_preview.PREFINISH)
            feeds = [(a, b) for kind, a, b, _ in moves if kind == 'feed']
            assert len(feeds) > 8
            assert feeds[0][0][0] * scale < 8.5, ('prefinish entry ran beyond the first chord', comp, units)
            assert all(b[2] <= a[2] + .0002 / scale for a, b in feeds[:8]), 'prefinish entry doubles back in Z'
            print('PASS  rounded prefinish entry approaches from +Z:', comp, 'G%d' % units, flush=True)
            profile.find('param[@call="#param_f_dir"]').set('value', '1')
            profile.find('param[@call="#param_zc_ovr"]').set('value', str(1 / 25.4))
            moves = generate(modified, 'prefinish-reverse-%d-G%d' % (comp, units), ncam_preview.PREFINISH)
            a, b = next((a, b) for kind, a, b, _ in moves if kind == 'feed')
            assert (a[2] - b[2]) * scale > .9, 'reverse prefinish approaches from -Z'
            print('PASS  reversed prefinish also approaches from +Z:', comp, 'G%d' % units, flush=True)

    for units in (21, 20):
        scale = 1 if units == 21 else 25.4
        for style, second, depth in [(2, 0, 5), (21, 3, 3), (22, 30, 5 / math.sqrt(3))]:
            for flip in (0, 1):
                modified = copy.deepcopy(flipped_project)
                modified.find('feature[@type="workpiece"]/param[@call="#param_units"]').set('value', str(units))
                profile = modified.find('feature[@type="polyline"]')
                line = profile.find('param[@type="items"]')[1]
                for key, value in [('m_style', style), ('m_flip', flip),
                                   ('m_b', second / 25.4 if style != 22 or units == 21 else second)]:
                    line.find('param[@call="#param_%s"]' % key).set('value', str(value))
                moves = generate(modified, 'chamfer-%d-flip%d-G%d' % (style, flip, units), ncam_preview.FINISH)
                points = [(p[2] * scale, p[0] * scale) for kind, a, b, _ in moves if kind == 'feed' for p in (a, b)]
                assert min(math.dist(p, (0, 7.5 if flip else 17.5)) for p in points) < .02, (style, flip, units)
                assert min(math.dist(p, (-depth, 12.5)) for p in points) < .02, (style, flip, units)
        print('PASS  all chamfer styles select the same starting side in G%d' % units, flush=True)

    def signature(tp, phase):
        return [(m.a, m.b) for m in tp.moves if m.kind == 'feed' and
                (phase in m.subs if phase else not m.subs)]

    for units in (21, 20):
        for comp in (1, 2):
            data = copy.deepcopy(project)
            data.find('feature[@type="workpiece"]/param[@call="#param_units"]').set('value', str(units))
            data.find('feature[@type="workpiece"]/param[@call="#param_od"]').set('value', str(80 / 25.4))
            profile = data.find('feature[@type="polyline"]')
            profile.find('param[@call="#param_op"]').set('value', '0')
            profile.find('param[@call="#param_pf_on"]').set('value', '1')
            profile.find('param[@call="#param_f_off"]').set('value', str(.508 / 25.4))
            profile.find('param[@call="#param_n_comp"]').set('value', str(comp))
            name = 'separate-baseline-%d-G%d' % (comp, units)
            generate(data, name)
            baseline = paths[name]
            for key in ('ext_fr', 'ext_bk', 'f_ext_fr', 'f_ext_bk'):
                modified = copy.deepcopy(data)
                modified.find('feature[@type="polyline"]/param[@call="#param_%s"]' % key).set('value', str(2 / 25.4))
                case = '%s-%d-G%d' % (key, comp, units)
                generate(modified, case)
                rough_changed = signature(paths[case], None) != signature(baseline, None)
                finish_changed = signature(paths[case], ncam_preview.FINISH) != signature(baseline, ncam_preview.FINISH)
                pf_changed = signature(paths[case], ncam_preview.PREFINISH) != signature(baseline, ncam_preview.PREFINISH)
                assert rough_changed == key.startswith('ext_'), ('wrong roughing extension consumer', key, comp, units)
                assert finish_changed == key.startswith('f_ext_'), ('wrong finishing extension consumer', key, comp, units)
                assert pf_changed == finish_changed, ('prefinish does not use finishing extensions', key, comp, units)
            print('PASS  roughing and finishing front/back extensions are independent:', comp, 'G%d' % units, flush=True)

    app.treestore_from_xml(copy.deepcopy(project))
    store = app.treestore
    rows = []
    store.foreach(lambda model, path, itr: rows.append(path.copy())
                  if isinstance(model.get_value(itr, 0), ncam.Feature)
                  and model.get_value(itr, 0).get_type() == 'poly-line-to' else None)
    for index, path in enumerate(rows):
        itr = store.get_iter(path)
        app.refresh_merge_visibility(itr)
        fields = []
        def collect(model, p, i):
            value = model.get_value(i, 0)
            if tuple(p.get_indices()[:len(path)]) == tuple(path.get_indices()):
                if value.get_attr('call') == '#param_h2' or value.get_attr('header') == 'h2':
                    fields.append(model.get_value(i, 2) or model.get_value(i, 3))
        store.foreach(collect)
        assert fields and all(v == (index >= 1) for v in fields), ('merge visibility', index, fields)
        line = store.get_value(itr, 0)
        for style in ('1', '2', '21', '22'):
            line.get_param('param_m_style').attr['value'] = style
            app.refresh_merge_visibility(itr)
            assert line.get_param('param_m_flip').get_grayed() == (index != 1)
    print('PASS  only the first item hides merge controls', flush=True)
    print('ARTIFACTS', root, flush=True)


if __name__ == '__main__':
    chamfer_flip_checks()
    geometry_checks()
    radius_flip_checks()
    application_checks()
    print('[VERDICT: PASS]')
