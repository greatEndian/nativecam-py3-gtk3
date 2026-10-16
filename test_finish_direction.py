#!/usr/bin/env python3
"""Reverse finishing is continuous; forward finishing keeps its wall cuts."""
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
    for scale in (1, 1 / 25.4):
        points = [(-scale, 20 * scale), (-2 * scale, 22 * scale),
                  (-6 * scale, 40 * scale)]
        projected = L.project_finish_front(points, 0)
        assert projected[0][0] == 0 and abs(projected[0][1] - 18 * scale) < 1e-12
        assert projected[1:] == points[1:]
        assert L.project_finish_front(list(reversed(points)), 0) == list(reversed(points))
        radial = [(0, 20 * scale), (0, 40 * scale), (-scale, 40 * scale)]
        assert L.project_finish_front(radial, scale) == radial
        assert L.project_finish_front(points, -scale) == points
    counts = [72, 3, 72, 3, 72, 3]
    bases, owner = L.cam_path_layout(counts, split=True)
    intervals = [(b, b+2*n) for b, n in zip(bases, counts)]
    intervals += [(L.CAM_BASE, L.CAM_BASE + 2*len(counts)),
                  (owner, owner+len(counts))]
    for a, b in intervals:
        assert (L.FC_BASE <= a < b <= L.FC_TOP
                or L.CAM_BASE <= a < b <= L.CAM_TOP)
    for i, (a, b) in enumerate(intervals):
        assert all(b <= c or d <= a for c, d in intervals[i+1:])
    assert any(b < L.FC_TOP for b in bases), 'spill bank was not exercised'
    maximum = (L.CAM_TOP - L.CAM_BASE - 2) // 2
    assert L.cam_path_layout([maximum]) == ([L.CAM_BASE+2], 0)
    assert L.cam_path_layout([maximum+1]) is None, 'a contiguous path crossed a bank'
    assert L.cam_path_layout([72]*20, split=True) is None
    print('PASS front projection, radial guards and disjoint CAM bank bounds', flush=True)


def contour_chunks(canon, scale=1.0, phase=P.FINISH):
    """Actual feed vertices between scratch markers, including entry position."""
    chunks, active, position, in_phase = [], None, None, False
    for line in canon.splitlines():
        if 'COMMENT("begin %s")' % phase in line:
            in_phase = True
        elif 'COMMENT("end %s")' % phase in line:
            in_phase = False
        if 'COMMENT("NCAM contour start")' in line and in_phase:
            assert position is not None
            active = [position]
        elif 'COMMENT("NCAM contour end")' in line and in_phase:
            assert active is not None
            chunks.append(active)
            active = None
        match = re.search(r'STRAIGHT_(FEED|TRAVERSE)\(([^)]*)\)', line)
        if match:
            values = [float(v) for v in match[2].split(',')]
            position = (values[2] * scale, values[0] * scale)
            if active is not None and position != active[-1]:
                assert match[1] == 'FEED', 'rapid inserted into finishing contour'
                active.append(position)
    assert chunks and active is None
    return chunks


def same_paths(actual, expected):
    assert len(actual) == len(expected), (len(actual), len(expected))
    for a, b in zip(actual, expected):
        assert len(a) == len(b), ('contour vertex count', len(a), len(b))
        error = max(abs(x-y) for p, q in zip(a, b) for x, y in zip(p, q))
        assert error < .0003, ('finishing geometry changed with direction', error)


def main():
    pure_checks()
    root = Path(tempfile.mkdtemp(prefix='ncam_finish_regression_'))
    cfg = root / 'config'
    shutil.copytree(HERE / 'configs/sim/axis/ncam_demo', cfg, symlinks=True)
    settings = cfg / 'ncam/catalogs/ncam.conf'
    prefs = configparser.ConfigParser(interpolation=None)
    prefs.read(settings)
    prefs.set('layout', 'autorefresh', 'False')
    with settings.open('w') as stream:
        prefs.write(stream)
    library = root / 'lib'
    shutil.copytree(HERE / 'lib', library)
    sub = library / 'lathe/lathe_poly_pass.ngc'
    text = sub.read_text()
    call = '\to<trace_lathe> CALL [#<pds>] [0] [1] [0] [0] [0] [2]'
    assert text.count(call) == 1
    sub.write_text(text.replace(call, '\t(NCAM contour start)\n' + call
                               + '\n\t(NCAM contour end)'))
    ini = cfg / 'lathe-mm.ini'
    sys.argv = ['ncam.py', '-i', str(ini), '-c', 'lathe']
    import ncam
    app = ncam.NCam()
    ini.write_text(re.sub(r'(?m)^SUBROUTINE_PATH\s*=.*$',
                         'SUBROUTINE_PATH = ' + str(library / 'lathe') + ':'
                         + str(library / 'utilities'), ini.read_text()))
    saved = app.update_features(etree.parse(str(
        cfg / 'ncam/catalogs/lathe/projects/testing_15_9.xml')).getroot())
    results = {}
    original_dump = P._canon_dump

    def generate(name, direction, passes=1, units=21, walls=2, comp=2, op=2):
        data = copy.deepcopy(saved)
        poly = data.find('.//feature[@type="polyline"]')
        for key, value in dict(op=op, n_comp=comp, f_dir=direction, f_pass=passes,
                               xw_dir=walls).items():
            poly.find('./param[@call="#param_%s"]' % key).set('value', str(value))
        data.find('.//feature[@type="workpiece"]/param[@call="#param_units"]').set('value', str(units))
        app.treestore_from_xml(data)
        out = root / (name + '.ngc')
        out.write_text(app.to_gcode())
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
        chunks = contour_chunks(raw[0], 25.4 if units == 20 else 1)
        signature = [(m.kind, m.a, m.b, m.feed, m.fmode)
                     for m in tp.moves if m.op == 'Lathe Polyline'
                     and P.FINISH in m.subs]
        results[name] = dict(moves=len(tp.moves), chunks=chunks,
                             finish_hash=hashlib.sha256(repr(signature).encode()).hexdigest())
        results[name]['finish_feed_hash'] = hashlib.sha256(repr(
            [move for move in signature if move[0] == 'feed']).encode()).hexdigest()
        if op == 0:
            results[name]['prefinish_chunks'] = contour_chunks(
                raw[0], 25.4 if units == 20 else 1, P.PREFINISH)
        (root / 'results.json').write_text(json.dumps(results, indent=2))
        print(name, len(chunks), 'contour parts', flush=True)
        return chunks

    with open('/tmp/ncam-rs274.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for suffix, kwargs in [('', {}), ('_inches', dict(units=20))]:
            plain = generate('plain_forward' + suffix, 0, walls=0, **kwargs)
            plain_reverse = generate('plain_reverse' + suffix, 1, walls=0, **kwargs)
            assert len(plain) == len(plain_reverse) == 1
            same_paths(plain_reverse, [list(reversed(plain[0]))])
            forward = generate('forward' + suffix, 0, **kwargs)
            assert len(forward) == 2
            reverse = generate('reverse' + suffix, 1, **kwargs)
            assert len(reverse) == 1, 'reverse finishing still splits at a wall'
            same_paths(reverse, plain_reverse)
            assert results['reverse' + suffix]['finish_hash'] == results['plain_reverse' + suffix]['finish_hash']
            both = generate('both_one' + suffix, 2, **kwargs)
            same_paths(both, forward)
        forward = generate('forward_two', 0, passes=2)
        reverse = generate('reverse_two', 1, passes=2)
        both = generate('both_two', 2, passes=2)
        plain = generate('plain_forward_two', 0, passes=2, walls=0)
        assert (len(forward), len(reverse), len(both), len(plain)) == (4, 2, 3, 2)
        for i in range(2):
            same_paths([reverse[i]], [list(reversed(plain[i]))])
        same_paths(both[:2], forward[:2])
        same_paths(both[2:], reverse[1:])
        for name, direction, passes, parts, pf_parts in (
                ('reverse_full', 1, 1, 1, 1), ('both_full', 2, 2, 3, 2)):
            chunks = generate(name, direction, passes=passes, op=0)
            assert len(chunks) == parts
            assert len(results[name]['prefinish_chunks']) == pf_parts
            reference = 'reverse' if direction == 1 else 'both_two'
            # The initial rapid starts where the preceding operation left
            # the tool. Compare cuts after the approach has positioned it.
            assert results[name]['finish_feed_hash'] == results[reference]['finish_feed_hash']
        for comp in (0, 1):
            a = 'reverse_comp%d_plain' % comp
            b = 'reverse_comp%d_wall' % comp
            plain = generate(a, 1, comp=comp, walls=0)
            reverse = generate(b, 1, comp=comp)
            assert len(plain) == len(reverse) == 1
            assert results[a]['finish_hash'] == results[b]['finish_hash'], 'reverse legacy wall detour remains'
    print('ARTIFACTS', root)
    print('[VERDICT: PASS]')


if __name__ == '__main__':
    main()
