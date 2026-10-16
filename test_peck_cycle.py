#!/usr/bin/env python3
"""Actual interpreted peck cycle: positions, stops, dwells and retract feeds."""
import copy
import fcntl
import json
import math
from pathlib import Path
import re
import shutil
import sys
import tempfile

from lxml import etree

import ncam_preview as P

HERE = Path(__file__).resolve().parent
MARKER = 'PROBE_PECK'


def groups(tp):
    result, previous = [], False
    for i, move in enumerate(tp.moves):
        active = MARKER in move.subs
        if active:
            if not previous:
                result.append([])
            result[-1].append((i, move))
        previous = active
    return result


def signature(moves):
    return [(m.kind, m.a, m.b, m.feed, m.fmode) for m in moves]


def main():
    root = Path(tempfile.mkdtemp(prefix='ncam_peck_cycle_'))
    config = root / 'config'
    shutil.copytree(HERE / 'configs/sim/axis/ncam_demo', config, symlinks=True)
    ini = config / 'lathe-mm.ini'
    sys.argv = ['ncam.py', '-i', str(ini), '-c', 'lathe']
    import ncam
    app = ncam.NCam()
    saved = etree.parse(str(config / 'ncam/catalogs/lathe/projects/testing_15_9.xml')).getroot()
    xml = app.update_features(copy.deepcopy(saved))
    old_poly = saved.find('.//feature[@type="polyline"]')
    poly = xml.find('.//feature[@type="polyline"]')
    assert float(poly.get('version')) >= 1.80
    for old in old_poly.findall('param'):
        current = poly.find('./param[@call="%s"]' % old.get('call'))
        assert current is not None and current.get('value') == old.get('value')
    for name in ('peck_ret_mode', 'peck_ret_feed'):
        assert poly.find('./param[@call="#param_%s"]' % name).get('value') == '0'
    # Distinct known tool feeds also test the working-feed selector exactly.
    for name, value in [('r_feed', 90), ('f_feed', 30)]:
        node = xml.find('.//feature[@type="tool_change"]/param[@call="#param_%s"]' % name)
        node.set('value', str(value / 25.4))
    print('PASS migration preserves all saved parameters and defaults to working/roughing', flush=True)

    cases = dict(off=dict(peck_len=0, peck_ret=0, peck_dwell=0),
                 idle=dict(peck_len=0, peck_ret_mode=1, peck_ret_feed=1),
                 working={}, finishing_feed=dict(peck_ret_feed=1),
                 rapid=dict(peck_ret_mode=1, hf_feed=500),
                 retract_no_dwell=dict(peck_dwell=0),
                 dwell_only=dict(peck_ret=0), stops_only=dict(peck_ret=0, peck_dwell=0),
                 reverse=dict(dir=1), alternating=dict(dir=2),
                 clamped=dict(peck_ret=100), unsectioned=dict(sectioning=0),
                 no_leads=dict(li_len=0, lo_len=0),
                 contours_off=dict(op=0, pf_on=1, peck_len=0),
                 contours_on=dict(op=0, pf_on=1), feed_per_rev={})
    programs = {}
    for name, changes in cases.items():
        data = copy.deepcopy(xml)
        feature = data.find('.//feature[@type="polyline"]')
        settings = dict(peck_len=2, peck_ret=0.1, peck_dwell=0.4,
                        peck_ret_mode=0, peck_ret_feed=0, op=1, pf_on=0)
        settings.update(changes)
        cases[name] = settings
        if name == 'feed_per_rev':
            data.find('.//feature[@type="tool_change"]/param[@call="#param_feed_mode"]').set('value', '95')
        for key, value in settings.items():
            node = feature.find('./param[@call="#param_%s"]' % key)
            assert node is not None, key
            node.set('value', str(value / 25.4 if node.get('metric_value') is not None else value))
        app.treestore_from_xml(data)
        out = root / (name + '.ngc')
        out.write_text(app.to_gcode())
        programs[name] = out
    # Isolate and instrument only after all NCam initialization/generation.
    library = root / 'library'
    shutil.copytree(HERE / 'lib', library, symlinks=True)
    ini.write_text(re.sub(r'(?m)^SUBROUTINE_PATH\s*=.*$',
                         'SUBROUTINE_PATH = ' + str(library / 'lathe') + ':'
                         + str(library / 'utilities'), ini.read_text()))
    sub = library / 'lathe/lathe_level_pass.ngc'
    source = sub.read_text().replace('\t(CHIP BREAKING.', '\t(begin %s)\n\t(CHIP BREAKING.' % MARKER)
    source = source.replace('\n\t(THIS PASS CUT,', '\n\t(end %s)\n\t(THIS PASS CUT,' % MARKER)
    sub.write_text(source)
    results, traces = {}, {}
    original_dump = P._canon_dump

    def archive_dump(path, ini_path, tmpdir):
        canon, error = original_dump(path, ini_path, tmpdir)
        if canon:
            Path(path).with_suffix('.canon').write_text(canon)
        return canon, error

    P._canon_dump = archive_dump
    with open('/tmp/ncam-rs274.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for name, path in programs.items():
            tp = P.parse_program(str(path), str(ini))
            assert tp.completed and not tp.error, (name, tp.error)
            traces[name] = tp
            settings = cases[name]
            cycles = groups(tp)
            assert cycles, name
            pecks, retreats, waits = 0, 0, 0
            if settings['peck_len']:
                for group in cycles:
                    # First feed reaches the exact pass start, including when
                    # a no-lead approach left a Z positioning clearance.
                    first = group[0][1]
                    start, end = first.b[2], group[-1][1].b[2]
                    sign = 1 if end >= start else -1
                    span = abs(end - start)
                    count = max(0, math.ceil((span - 0.0001) / 2) - 1)
                    expected = [(start, 'feed', 90)]
                    dwell_at = []
                    for k in range(1, count + 1):
                        at = start + sign * 2 * k
                        expected.append((at, 'feed', 90))
                        if settings['peck_ret']:
                            back = at - sign * min(settings['peck_ret'], 2 * k)
                            rapid = settings['peck_ret_mode'] == 1
                            rate = 30 if settings['peck_ret_feed'] else 90
                            expected.append((back, 'rapid' if rapid else 'feed', rate))
                            if settings['peck_dwell']:
                                dwell_at.append((len(expected) - 1, back))
                            expected.append((at, 'feed', 90))
                            retreats += 1
                    expected.append((end, 'feed', 90))
                    if not settings['peck_ret'] and settings['peck_dwell']:
                        dwell_at.append((len(expected) - 1, end))
                    assert len(group) == len(expected), (name, span, len(group), len(expected))
                    for (index, move), (z, kind, rate) in zip(group, expected):
                        assert abs(move.b[2] - z) < 0.0002, (name, z, move)
                        assert move.kind == kind, (name, kind, move)
                        assert abs(move.b[0] - first.b[0]) < 0.0002, (name, move)
                        if kind == 'feed':
                            assert abs(move.feed - rate) < 0.0002, (name, rate, move)
                            if name == 'feed_per_rev':
                                assert move.fmode == 'rev', move
                    actual = [(after, seconds) for after, seconds, _op in tp.dwells
                              if group[0][0] < after <= group[-1][0] + 1]
                    wanted = [(group[offset][0] + 1, 0.4) for offset, _z in dwell_at]
                    assert actual == wanted, (name, actual, wanted)
                    stop_offsets = [1 + k * (3 if settings['peck_ret'] else 1)
                                    for k in range(count)]
                    if not settings['peck_ret'] and settings['peck_dwell']:
                        stop_offsets.append(len(group) - 1)
                    stops = [(after, point) for after, point, _op in tp.peck_stops
                             if group[0][0] < after <= group[-1][0] + 1]
                    expected_stops = [(group[offset][0] + 1, group[offset][1].b)
                                      for offset in stop_offsets]
                    assert stops == expected_stops, (name, stops, expected_stops)
                    waits += len(actual)
                    pecks += count
            results[name] = dict(moves=len(tp.moves), passes=len(cycles),
                                 pecks=pecks, retracts=retreats, peck_dwells=waits)
            print('PASS %s %s' % (name, results[name]), flush=True)

    assert signature(traces['off'].moves) == signature(traces['idle'].moves)
    for name in ('working', 'finishing_feed', 'dwell_only', 'stops_only', 'clamped'):
        assert len(groups(traces[name])) == len(groups(traces['off']))
        for off, on in zip(groups(traces['off']), groups(traces[name])):
            assert off[-1][1].b == on[-1][1].b, name
    assert results['dwell_only']['pecks'] == results['working']['pecks'] > 0
    assert results['working']['peck_dwells'] == results['working']['pecks']
    assert results['dwell_only']['peck_dwells'] == results['dwell_only']['passes']
    assert not traces['off'].peck_stops and not traces['idle'].peck_stops
    # Both pre-finish and finish geometry/feed must be exactly unchanged.
    contour = lambda tp: signature([m for m in tp.moves if any(tag in m.subs for tag in P.PHASES)])
    assert contour(traces['contours_off']) == contour(traces['contours_on'])
    assert contour(traces['contours_on'])
    # Legacy generated programs do not define the two new settings.
    legacy = root / 'legacy.ngc'
    legacy.write_text(re.sub(r'^\s*#<_pl_peck_ret_(?:rapid|feed)>.*\n', '',
                              programs['working'].read_text(), flags=re.M))
    with open('/tmp/ncam-rs274.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        tp = P.parse_program(str(legacy), str(ini))
    assert tp.completed and not tp.error, tp.error
    assert signature(tp.moves) == signature(traces['working'].moves)
    (root / 'results.json').write_text(json.dumps(results, indent=2))
    print('PASS disabled no-op, finishing unchanged, old generated program fallback')
    print('ARTIFACTS', root)


if __name__ == '__main__':
    main()
