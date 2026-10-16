#!/usr/bin/env python3
"""Configured roughing lead-in must reach the interpreted/simulated motion."""
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

from lxml import etree

import ncam_preview as P
from test_air_leads import Material

HERE = Path(__file__).resolve().parent
ENTRY, EXIT = 'PROBE_ENTRY', 'PROBE_EXIT'


def length(move):
    return math.dist(move.a, move.b)


def lead_cycles(tp, marker):
    groups, previous = [], False
    for index, move in enumerate(tp.moves):
        active = move.op == 'Lathe Polyline' and marker in move.subs
        if active:
            if not previous:
                groups.append([])
            groups[-1].append((index, move))
        previous = active
    return groups


def motion_hash(tp):
    h = hashlib.sha1()
    for m in tp.moves:
        h.update(('%s %.5f %.5f %.5f %.5f %s\n'
                  % (m.kind, m.a[0], m.a[2], m.b[0], m.b[2], m.cat)).encode())
    return h.hexdigest()[:12]


def material_depths(tp):
    moves = [m for m in tp.moves if m.op == 'Lathe Polyline']
    zs = [point[2] for move in moves for point in (move.a, move.b)]
    material = Material(35, 0, min(zs), max(zs))
    rapid, cutting = 0.0, 0.0
    for move in moves:
        if move.kind == 'rapid':
            rapid = max(rapid, material.depth(move))
        elif not move.subs or any(tag in move.subs for tag in (ENTRY, EXIT)):
            cutting = max(cutting, material.depth(move))
        material.cut(move)
    return rapid, cutting


def main():
    root = Path(tempfile.mkdtemp(prefix='roughing_lead_in_'))
    cfg = root / 'config'
    shutil.copytree(HERE / 'configs/sim/axis/ncam_demo', cfg, symlinks=True)
    ini = cfg / 'lathe-mm.ini'
    sys.argv = ['ncam.py', '-i', str(ini), '-c', 'lathe']
    import ncam
    app = ncam.NCam()
    saved = etree.parse(str(cfg / 'ncam/catalogs/lathe/projects/testing_15_9.xml')).getroot()
    xml = app.update_features(copy.deepcopy(saved))
    old_poly = saved.find('.//feature[@type="polyline"]')
    poly = xml.find('.//feature[@type="polyline"]')
    prm = poly.find('./param[@call="#param_li_air"]')
    previous = old_poly.find('./param[@call="#param_li_air"]')
    assert prm is not None and prm.get('value') == (previous.get('value') if previous is not None else '0')
    assert float(poly.get('version')) >= 1.78
    for old in old_poly.findall('param'):
        current = poly.find('./param[@call="%s"]' % old.get('call'))
        assert current is not None and current.get('value') == old.get('value'), old.get('call')
    print('PASS saved project migrates with its saved skip policy and all entered values preserved', flush=True)

    def build(name, **settings):
        data = copy.deepcopy(xml)
        f = data.find('.//feature[@type="polyline"]')
        # Fix the policy test's geometry independently of the operator's
        # currently saved Natural/Artificial and extension choices.
        settings = dict(sectioning=1, sec_len=5, sec_ext_fr=0, sec_ext_bk=0,
                        ret_mode=0, **settings)
        for key, value in settings.items():
            p = f.find('./param[@call="#param_%s"]' % key)
            assert p is not None, key
            p.set('value', str(value / 25.4 if p.get('metric_value') is not None else value))
        app.treestore_from_xml(data)
        out = root / (name + '.ngc')
        out.write_text(app.to_gcode())
        return out

    programs = dict(default=build('default', li_air=0), skip=build('skip', li_air=1),
                    reverse=build('reverse', dir=1, li_air=0), alternating=build('alternating', dir=2, li_air=0),
                    # Zero-length roughing leads have no finishing entry/exit
                    # requirements to mix into this roughing-policy check.
                    zero=build('zero', li_len=0, lo_len=0, op=1, pf_on=0, li_air=0))
    # Zero-length plunges already have a separate clearance finding with the
    # pre-fix subroutine. Check that this policy neither forces a lead there
    # nor worsens that baseline; the 1 mm cases retain the strict clearance gate.
    zero_legacy = root / 'zero-legacy.ngc'
    zero_legacy.write_text(re.sub(r'^\s*#<_pl_li_air>.*\n', '',
                                  programs['zero'].read_text(), flags=re.M))
    programs['zero-legacy'] = zero_legacy
    # Per-operation reset, including a finishing-only following operation.
    mixed = copy.deepcopy(xml)
    f = mixed.find('.//feature[@type="polyline"]')
    f.find('./param[@call="#param_li_air"]').set('value', '1')
    other = copy.deepcopy(poly)
    for index, feature in enumerate(other.iter('feature')):
        feature.set('id', 'lead_following_%d' % index)
    other.find('./param[@call="#param_op"]').set('value', '2')
    other.find('./param[@call="#param_li_air"]').set('value', '0')
    mixed.append(other)
    app.treestore_from_xml(mixed)
    mixed_code = app.to_gcode()
    settings = re.findall(r'^\s*#<_pl_li_air>\s*=\s*([\d.]+)', mixed_code, re.M)
    assert [float(v) for v in settings][-2:] == [1, 0], settings
    print('PASS each operation publishes its lead-in policy, including finishing-only reset', flush=True)

    # Generate first. NCam initialization synchronizes ncam/lib with the repo;
    # the interpreter now uses a separate instrumented library, never that link.
    library = root / 'library'
    shutil.copytree(HERE / 'lib', library, symlinks=True)
    ini.write_text(re.sub(r'(?m)^SUBROUTINE_PATH\s*=.*$',
                         'SUBROUTINE_PATH = ' + str(library / 'lathe') + ':'
                         + str(library / 'utilities'), ini.read_text()))
    sub = library / 'lathe/lathe_level_pass.ngc'
    source = sub.read_text()
    for label, marker in [('lead_ap', ENTRY), ('lead_rt', EXIT)]:
        source = source.replace('\to<%s> if ' % label,
                                '\t(begin %s)\n\to<%s> if ' % (marker, label))
        source = source.replace('\to<%s> endif' % label,
                                '\to<%s> endif\n\t(end %s)' % (label, marker))
    sub.write_text(source)
    results, traces = {}, {}
    with open('/tmp/ncam-rs274.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for name, path in programs.items():
            tp = P.parse_program(str(path), str(ini))
            assert tp.completed and tp.error is None, (name, tp.error)
            traces[name] = tp
            cycles = lead_cycles(tp, ENTRY)
            lengths = [sum(length(move) for _i, move in group if move.kind == 'feed')
                       for group in cycles]
            exits = lead_cycles(tp, EXIT)
            exit_lengths = [sum(length(move) for _i, move in group if move.kind == 'feed')
                            for group in exits]
            is_zero = name.startswith('zero')
            if not is_zero:
                assert len(cycles) == len(exits) and cycles, (name, len(cycles), len(exits))
            else:
                assert cycles, 'zero-length roughing still needs actual passes'
            if name in ('default', 'reverse', 'alternating'):
                assert all(abs(v - 1) < 0.0002 for v in lengths), (name, lengths)
                assert all(abs(v - 1) < 0.0002 for v in exit_lengths), (name, exit_lengths)
                acc, total = P.path_lengths(tp)
                for group in cycles:
                    for index, move in group:
                        if move.kind == 'feed' and length(move) > 0.1:
                            t = ((acc[index-1] if index else 0) + acc[index]) / (2 * total)
                            point, at, kind = P.position_at(tp, t, acc, total)
                            assert at == index and kind == 'feed'
                            assert math.dist(point, tuple((a+b)/2 for a, b in zip(move.a, move.b))) < 1e-8
            elif name == 'skip':
                assert 0 < sum(v > 1e-5 for v in lengths) < results['default']['feed_entries']
                assert motion_hash(tp) != motion_hash(traces['default'])
            else:
                assert not any(v > 1e-5 for v in lengths + exit_lengths)
            rapid, cutting = material_depths(tp)
            results[name] = dict(moves=len(tp.moves), entries=len(cycles),
                                 feed_entries=sum(v > 1e-5 for v in lengths),
                                 rapid_depth_mm=rapid, cutting_depth_mm=cutting)
            (root / 'results.json').write_text(json.dumps(results, indent=2))
            if not is_zero:
                assert rapid < 0.01, (name, 'rapid depth', rapid)
            assert cutting < 0.508 + 0.01, (name, 'cutting depth', cutting)
            print('PASS %s: %d feed entries / %d, %d total moves, rapid %.6f mm, layer %.6f mm'
                  % (name, results[name]['feed_entries'], len(cycles), len(tp.moves), rapid, cutting), flush=True)

        assert results['zero']['rapid_depth_mm'] <= results['zero-legacy']['rapid_depth_mm'] + 1e-4
        print('PASS zero configured length inserts no lead and does not worsen legacy plunge clearance', flush=True)

        # Legacy already-generated files still load and keep their old policy.
        legacy = root / 'legacy.ngc'
        legacy.write_text(re.sub(r'^\s*#<_pl_li_air>.*\n', '', programs['skip'].read_text(), flags=re.M))
        old = P.parse_program(str(legacy), str(ini))
        assert old.completed and old.error is None and old.moves == traces['skip'].moves
        print('PASS legacy file without the new global preserves its previous motion', flush=True)
        def finishing(tp):
            return [m for m in tp.moves if m.op == 'Lathe Polyline' and m.subs
                    and not any(tag in m.subs for tag in (ENTRY, EXIT))]
        assert finishing(traces['default']) and finishing(traces['default']) == finishing(traces['skip'])
        print('PASS lead-in policy changes roughing only; finishing motion is identical', flush=True)
    print('Artifacts:', root)
    print('[VERDICT: PASS]')


if __name__ == '__main__':
    main()
