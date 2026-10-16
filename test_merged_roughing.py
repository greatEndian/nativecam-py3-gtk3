#!/usr/bin/env python3
"""Merged roughing dispatch is per operation and resets on every Generate."""
import copy
from pathlib import Path
import re
import shutil
import sys
import tempfile

from lxml import etree

HERE = Path(__file__).resolve().parent


def main():
    root = Path(tempfile.mkdtemp(prefix='merged_operations_'))
    cfg = root / 'config'
    shutil.copytree(HERE / 'configs/sim/axis/ncam_demo', cfg, symlinks=True)
    ini = cfg / 'lathe-mm.ini'
    sys.argv = ['ncam.py', '-i', str(ini), '-c', 'lathe']
    import ncam
    import lathe_sections as L
    import ncam_preview as P

    app = ncam.NCam()
    source = HERE / 'configs/sim/axis/ncam_demo/ncam/catalogs/lathe/projects/testing_15_9.xml'
    xml = app.update_features(etree.fromstring(source.read_bytes()))
    poly = xml.find('.//feature[@type="polyline"]')
    second = copy.deepcopy(poly)
    for i, feature in enumerate(second.iter('feature')):
        feature.set('id', 'merge_second_%d' % i)
    second.find('./param[@call="#param_li_feed"]').set('value', str(1 / 25.4))
    xml.append(second)
    app.treestore_from_xml(xml)
    first = app.to_gcode()
    assert len(L.MERGED_ROUGHING_PLANS) == 2
    assert L.MERGED_ROUGHING_PLANS[0]['leads'] != L.MERGED_ROUGHING_PLANS[1]['leads']
    assert first.count('o<ncam_merge_rough> sub') == 1
    assert re.findall(r'^#<_pl_merge_id>\s*=\s*([12])$', first, re.M) == ['1', '2']
    again = app.to_gcode()
    assert again == first and len(L.MERGED_ROUGHING_PLANS) == 2
    out = root / 'two-operations.ngc'
    out.write_text(first)
    tp = P.parse_program(str(out), str(ini))
    assert tp.error is None and tp.completed and len(tp.moves) > 2700, tp.error
    assert any(m.feed is not None and abs(m.feed - 1) < 1e-6 for m in tp.moves)
    print('PASS  two operation selectors, one dispatcher, captured per-operation feeds')
    print('PASS  repeated Generate is byte-identical, no accumulated plans')

    unmerged = copy.deepcopy(poly)
    for i, feature in enumerate(unmerged.iter('feature')):
        feature.set('id', 'merge_unmerged_%d' % i)
    unmerged.find('./param[@call="#param_min_pass"]').set('value', '0')
    xml.append(unmerged)
    app.treestore_from_xml(xml)
    mixed = app.to_gcode()
    selectors = re.findall(r'^#<_pl_merge_id>\s*=\s*(\d+)$', mixed, re.M)
    assert selectors[-3:] == ['1', '2', '0'], selectors
    assert len(L.MERGED_ROUGHING_PLANS) == 2
    print('PASS  following unmerged operation resets the selector')
    print('Artifacts:', root)
    print('[VERDICT: PASS]')


if __name__ == '__main__':
    main()
