#!/usr/bin/env python3
"""Section boundaries must not turn a long roughing cut into skipped pieces.

Run directly under Xvfb. Generate into a copied config, trace real rs274
motion, and require one feed across each merged section boundary. Disabling
the merge plan is a negative control; keeping pieces separately measures the
extra approach/retract cycles the merge must remove.
"""
import fcntl
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch

import lathe_sections as L
import ncam_preview as P
from test_air_leads import Material

HERE = Path(__file__).resolve().parent
GEN = HERE / '.claude/skills/lathe-gcode-verify/scripts/gen_project.py'


def table(src, name, base, width):
    count = int(re.findall(r'#<%s>\s*=\s*([\d.]+)' % name, src)[-1])
    vals = {int(m[1]): float(m[2]) for m in
            re.finditer(r'^#(\d+)\s*=\s*([-\d.eE+]+)\s*$', src, re.M)}
    return [tuple(vals[base + i * width + j] for j in range(width))
            for i in range(count)]


def front_shortfalls(tp, stop):
    levels = {}
    for move in tp.moves:
        if (move.op == 'Lathe Polyline' and move.kind == 'feed' and not move.subs
                and abs(move.a[0] - move.b[0]) < 1e-6
                and abs(move.a[2] - move.b[2]) > 1e-5):
            levels.setdefault(round(move.a[0], 4), []).append(
                tuple(sorted((move.a[2], move.b[2]), reverse=True)))
    rows = []
    for radius, spans in sorted(levels.items(), reverse=True):
        spans.sort(reverse=True)
        hi, lo = spans[0]
        if hi < -3:
            continue
        for a, b in spans[1:]:
            if a < lo - 0.002:
                break
            lo = min(lo, b)
        target = next((za + (zb - za) * (radius - ra) / (rb - ra)
                       for (za, ra), (zb, rb) in zip(stop, stop[1:])
                       if ra < radius <= rb), None)
        if target is not None:
            rows.append((radius, lo - target))
    return rows


def rapid_depth(tp):
    moves = [m for m in tp.moves if m.op == 'Lathe Polyline']
    zs = [point[2] for m in moves for point in (m.a, m.b)]
    material = Material(35, 0, min(zs), max(zs))
    worst, cutting_layer = 0.0, 0.0
    for move in moves:
        if move.kind == 'rapid':
            worst = max(worst, material.depth(move))
        elif not move.subs and (abs(move.a[0] - move.b[0]) < 1e-6
                                or (abs(move.a[2] - move.b[2]) < 1e-6
                                    and move.b[0] < move.a[0])):
            # Include the extended horizontal pass: a merge must wait for
            # its shallower neighbors rather than remove multiple layers.
            cutting_layer = max(cutting_layer, material.depth(move))
        material.cut(move)
    return worst, cutting_layer


def unit_checks():
    floor = [(0, 0), (-20, 0)]
    def row(window, radius, start, end):
        return (window, radius, '', [(start, end, True, False)])
    plan = [row(0, 5, 0, -4), row(1, 5, -4, -4.2)]
    tasks, joins, isolated = L.merge_short_calls(plan, floor, 0, 0.5)
    assert joins == 1 and isolated == 0 and len(tasks) == 1
    assert (tasks[0]['a'], tasks[0]['b']) == (0, -4.2)
    assert tasks[0]['owners'] == {0, 1}
    for other in (row(1, 5, -4.1, -4.3), row(1, 4, -4, -4.2)):
        tasks, joins, isolated = L.merge_short_calls([plan[0], other], floor, 0, 0.5)
        assert joins == 0 and isolated == 1 and len(tasks) == 1
    tasks, joins, isolated = L.merge_short_calls([row(0, 5, 0, -0.2)], floor, 0, 0.5)
    assert not tasks and not joins and isolated == 1
    plan = [row(0, 6, 0, -4), row(0, 5, 0, -4),
            row(1, 6, -4, -8), row(1, 5, -4, -4.2)]
    tasks, joins, isolated = L.merge_short_calls(plan, floor, 0, 0.5)
    assert joins == 1
    merged = next(i for i, t in enumerate(tasks) if len(t['owners']) > 1)
    upper_neighbor = next(i for i, t in enumerate(tasks) if t['w'] == 1 and t['r'] == 6)
    assert upper_neighbor < merged, 'clear the upper neighboring layer before extending'
    class Param:
        def get_ngc_value(self):
            return '0.5'
    class Feature:
        def get_param(self, name):
            return Param()
    feature = Feature()
    reset = L.build_short_pass_gcode(feature, 0, 0, 0, 0, 0, 0, None)
    assert '#<_pl_merge_id> = 0' in reset and '#<_pl_short_n> = 0' in reset
    with patch.object(L, 'floor_contour_data', return_value=None):
        assert '#<_pl_merge_id> = 0' in L.build_floor_contour_gcode(feature, 0)
    with patch.object(L, 'floor_contour_data', return_value=L.FLOORC_OVERFLOW):
        assert '#<_pl_merge_id> = 0' in L.build_floor_contour_gcode(feature, 0)
    print('PASS  adjacency, gaps, different levels, isolated short cuts, layer ordering and resets', flush=True)


def main():
    unit_checks()
    root = Path(tempfile.mkdtemp(prefix='section_arc_contact_'))
    cfg = root / 'config'
    shutil.copytree(HERE / 'configs/sim/axis/ncam_demo', cfg, symlinks=True)
    ini = cfg / 'lathe-mm.ini'
    results = {}

    def trace(path):
        tp = P.parse_program(str(path), str(ini))
        assert tp.completed and tp.error is None, tp.error
        return tp

    def generate(label, section=1, minimum=0.5, direction=0, units=21):
        out = root / (label + '.ngc')
        cmd = [sys.executable, str(GEN), '--ini', str(ini), '--project',
               'testing_15_9.xml', '--out', str(out)]
        # Exercise the section-merge regression with cleared-entry skipping
        # enabled, preserving the original optimization's geometry controls.
        for value in ('polyline:param_li_air=1',
                      'polyline:param_sectioning=%d' % section,
                      'polyline:param_min_pass=%g' % minimum,
                      'polyline:param_dir=%d' % direction,
                      'workpiece:param_units=%d' % units):
            cmd += ['--set', value]
        run = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        assert run.returncode == 0, run.stdout + run.stderr
        src = out.read_text()
        tp = trace(out)
        stop = table(src, '_pl_stop_n', L.STOP_BASE, 2)
        # Canon coordinates follow the program units. Compare in mm, including
        # the detector's fixed tolerances and front-of-workpiece cutoff.
        if units == 20:
            tp.moves = [m._replace(a=tuple(v * 25.4 for v in m.a),
                                   b=tuple(v * 25.4 for v in m.b)) for m in tp.moves]
            stop = [(z * 25.4, r * 25.4) for z, r in stop]
        rows = front_shortfalls(tp, stop)
        assert len(rows) >= 25, (label, len(rows))
        if section == 1 and minimum > 0 and units == 21:
            cuts = [m for m in tp.moves if m.op == 'Lathe Polyline'
                    and m.kind == 'feed' and not m.subs
                    and abs(m.a[0] - m.b[0]) < 1e-6]
            assert not [m for m in cuts if 1e-5 < abs(m.a[2] - m.b[2]) < minimum - 0.001], label
            for radius, boundary in ((30.952854, -24.566667), (25.893922, -20.4)):
                joined = [m for m in cuts if abs(m.a[0] - radius) < 0.0001
                          and min(m.a[2], m.b[2]) < boundary - 0.02
                          and max(m.a[2], m.b[2]) > boundary + 0.02]
                assert len(joined) == 1, (label, radius, 'must be one solid feed across join')
        worst = max(short for _radius, short in rows)
        assert worst < 0.002, (label, rows)
        clearance, cutting_layer = rapid_depth(tp) if units == 21 else (None, None)
        results[label] = dict(moves=len(tp.moves), front_levels=len(rows),
                              max_shortfall_mm=worst, rapid_depth_mm=clearance,
                              cutting_layer_depth_mm=cutting_layer)
        (root / 'results.json').write_text(json.dumps(results, indent=2))
        if clearance is not None:
            # The reverse baseline has 0.0042 mm grid discretization on its
            # sloping floor. Restored fragments must not add a layer plunge.
            assert clearance < 0.01, (label, 'rapid depth', clearance)
            assert cutting_layer < 0.508 + 0.01, (label, 'cutting layer depth', cutting_layer)
        print('PASS  %s: %d moves, %d front levels, max shortfall %.6f mm' %
              (label, len(tp.moves), len(rows), worst), flush=True)
        return src, tp

    with open('/tmp/ncam-rs274.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        src, fixed = generate('sectioned')
        assert '(merged 4 short section pieces; filtered 1 isolated short cuts)' in src
        assert len(fixed.moves) < 1609, 'the former standalone pieces must lose their cycles'
        negative = root / 'negative.ngc'
        negative.write_text(re.sub(r'(#<_pl_merge_id>\s*=\s*)[-\d.]+', r'\g<1>0', src))
        old = trace(negative)
        rows = front_shortfalls(old, table(src, '_pl_stop_n', L.STOP_BASE, 2))
        gaps = [short for _radius, short in rows if short > 0.02]
        assert len(gaps) == 2 and max(gaps) > 0.4, gaps
        # Reconstruct the previous keep-as-a-separate-pass policy as a control.
        floor = table(src, '_pl_flc_n', L.FLOORC_BASE, 2)
        resume = table(src, '_pl_res_n', L.RESUME_BASE, 2)
        levels = [float(v) for v in re.findall(
            r'o<lathe_level_pass> CALL \[#<merge_pds>\] \[([-\d.]+)\]', src)]
        vals = {int(m[1]): float(m[2]) for m in
                re.finditer(r'^#(\d+)\s*=\s*([-\d.eE+]+)\s*$', src, re.M)}
        count = int(re.findall(r'#<_pl_sect_count>\s*=\s*(\d+)', src)[-1])
        boundaries = [vals[L.SECT_BASE + i * 4 + j] for i in range(count) for j in (1, 2)]
        oz = float(re.findall(r'#<_pl_rgh_oz>\s*=\s*([-\d.]+)', src)[-1])
        spans = L.continuous_cut_spans(floor, resume, levels, max(boundaries),
                                      min(boundaries), 0.5, [b - oz for b in boundaries], oz)
        assert L.SHORT_BASE + 3 * len(spans) <= L.SHORT_TOP
        keep = ['#<_pl_short_base> = %d' % L.SHORT_BASE,
                '#<_pl_short_n> = %d' % len(spans)]
        for i, row in enumerate(spans):
            keep.extend('#%d = %.8f' % (L.SHORT_BASE + i * 3 + j, value)
                        for j, value in enumerate(row))
        previous = root / 'previous-separate.ngc'
        previous.write_text(re.sub(r'#<_pl_merge_id>\s*=\s*1\b',
                                  '\n'.join(keep) + '\n#<_pl_merge_id> = 0', src))
        separate = trace(previous)
        assert len(separate.moves) - len(fixed.moves) == 20
        print('PASS  four merged pieces remove 20 moves versus separate passes', flush=True)
        print('PASS  disabled merge reproduces original gaps: %s mm' % gaps, flush=True)
        legacy = root / 'legacy.ngc'
        legacy.write_text(re.sub(r'^#<_pl_(?:short_(?:n|base)|merge_\w+|level_ran)>.*\n', '',
                                 negative.read_text(), flags=re.M))
        legacy_tp = trace(legacy)
        assert legacy_tp.moves == old.moves
        print('PASS  legacy generated program without new parameters', flush=True)
        generate('unsectioned', section=0)
        _, unfiltered = generate('unfiltered', minimum=0)
        assert len(fixed.moves) < len(unfiltered.moves), 'genuinely short cut must still skip'
        generate('back-to-front', direction=1)
        generate('both-directions', direction=2)
        generate('inch-program', units=20)
    (root / 'results.json').write_text(json.dumps(results, indent=2))
    print('Artifacts: %s' % root)
    print('[VERDICT: PASS]')


if __name__ == '__main__':
    main()
