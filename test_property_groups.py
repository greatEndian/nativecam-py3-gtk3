#!/usr/bin/env python3
"""Property heading interactions across lathe, mill and plasma in real GTK."""
import argparse
import configparser
import json
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

from lxml import etree

HERE = Path(__file__).resolve().parent
CASES = {
    'lathe': ('material.cfg', 'tool-change.cfg', 'facing.cfg', 'polyline.cfg'),
    'mill': ('material.cfg', 'sel-end-mill.cfg', 'rectangle.cfg', 'polyline.cfg'),
    'plasma': ('material2d.cfg', 'material3d.cfg', 'circle.cfg', 'polyline.cfg'),
}


def child(catalog, root):
    cfg = root / catalog
    shutil.copytree(HERE / 'configs/sim/axis/ncam_demo', cfg, symlinks=True)
    settings = cfg / 'ncam/catalogs/ncam.conf'
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(settings)
    for section in ('layout', 'display'):
        if not parser.has_section(section):
            parser.add_section(section)
    for name, value in (('autorefresh', 'False'), ('dual_view', 'True'),
                        ('subheaders_in_master', 'True')):
        parser.set('layout', name, value)
    parser.set('display', 'tv2_expandable', 'False')
    parser.set('display', 'tv_expandable', 'False')
    with settings.open('w') as output:
        parser.write(output)
    ini = cfg / (catalog + '-mm.ini')
    # Upstream mill/plasma demos name their author's absolute program folder.
    ini.write_text(re.sub(r'(?m)^(\s*PROGRAM_PREFIX\s*=).*$',
                          lambda m: m[1] + ' ' + str(cfg / 'ncam/scripts'), ini.read_text()))
    sys.argv = ['ncam.py', '-i', str(ini), '-c', catalog]
    import ncam
    from ncam import gtk, gdk

    def pump():
        while gtk.events_pending():
            gtk.main_iteration_do(False)

    def find(tv, predicate):
        found = []
        def visit(model, path, itr):
            if predicate(model.get_value(itr, 0)):
                found.append(path.copy())
        tv.get_model().foreach(visit)
        assert found, 'missing row'
        return found[0]

    def heading(tv, call):
        target = app.selected_feature.get_param(call.lstrip('#'))
        return find(tv, lambda row: row is target)

    def click(tv, path):
        if path.get_depth() > 1:
            tv.expand_to_path(gtk.TreePath(path.get_indices()[:-1]))
        tv.scroll_to_cell(path, None, True, 0.5, 0)
        deadline = time.monotonic() + 3
        while True:
            pump()
            rect = tv.get_background_area(path, tv.get_column(0))
            hit = tv.get_path_at_pos(rect.x + 45, int(rect.y + rect.height / 2))
            if hit is not None and hit[0] == path:
                break
            assert time.monotonic() < deadline, ('heading not visible', path.to_string())
            time.sleep(0.01)
        event = gdk.Event.new(gdk.EventType.BUTTON_PRESS)
        event.window, event.button = tv.get_bin_window(), 1
        event.x, event.y = rect.x + 45, rect.y + rect.height / 2
        assert tv.emit('button-press-event', event), 'heading click was not handled'
        pump()

    win = gtk.Window()
    app = ncam.NCam(accel_toplevel=win)
    app.pref.autosave = False
    win.add(app)
    win.set_default_size(1100, 900)
    win.show_all()
    pump()
    xml = etree.Element(ncam.XML_TAG)
    for i, name in enumerate(CASES[catalog]):
        feature = ncam.Feature(src=str(HERE / 'cfg' / catalog / name))
        feature.attr['id'] = catalog + '_groups_%d' % i
        xml.append(feature.to_xml())
    app.treestore_from_xml(xml)
    before = {f.get('id'): {p.get('call'): p.get('value') for p in f.findall('param')}
              for f in xml.findall('feature')}

    def select(index):
        feature_id = catalog + '_groups_%d' % index
        path = find(app.treeview, lambda row: isinstance(row, ncam.Feature)
                    and row.get_attr('id') == feature_id)
        app.treeview.set_cursor(path)
        app.get_selected_feature(app.treeview)
        pump()

    counts = []
    for index, name in enumerate(CASES[catalog]):
        select(index)
        tv = app.treeview2
        rows = []
        def collect(model, path, itr):
            row = model.get_value(itr, 0)
            if row.get_type() in ('header', 'sub-header'):
                rows.append((row.attr['call'], model.iter_has_child(itr)))
        tv.get_model().foreach(collect)
        assert rows and tv.get_show_expanders(), (catalog, name, 'missing headings/arrows')
        assert all(not tv.row_expanded(heading(tv, call)) for call, _ in rows)
        for call, has_children in rows:
            path = heading(tv, call)
            tv.get_column(0).cell_set_cell_data(tv.get_model(), tv.get_model().get_iter(path), False, False)
            attributes = app.name_cell2.get_property('attributes')
            font = ncam.pango.FontDescription()
            attributes.get_iterator().get_font(font)
            assert font.get_weight() >= 700, (name, call, 'not bold')
            if has_children:
                click(tv, path)
                assert tv.row_expanded(path), (name, call, 'did not open')
                click(tv, path)
                assert not tv.row_expanded(path), (name, call, 'did not close')
        tv.collapse_all()
        call = next(call for call, children in rows if children)
        path = heading(tv, call)
        tv.set_cursor(path)
        key = gdk.Event.new(gdk.EventType.KEY_PRESS)
        key.keyval, key.state = gdk.KEY_space, gdk.ModifierType(0)
        assert tv.emit('key-press-event', key)
        assert tv.row_expanded(path), (name, 'Space did not open')
        assert tv.emit('key-press-event', key)
        assert not tv.row_expanded(path), (name, 'Space did not close')
        click(tv, path)
        select((index + 1) % len(CASES[catalog]))
        select(index)
        assert tv.row_expanded(heading(tv, call)), (name, 'lost expansion on feature switch')
        app.get_selected_feature(app.treeview)
        assert tv.row_expanded(heading(tv, call)), (name, 'lost expansion on refilter')
        tv.collapse_all()
        counts.append(len(rows))
        print('PASS %s/%s: %d bold closed headings; click, Space and state restoration'
              % (catalog, name, len(rows)), flush=True)

    # Milling/plasma Closing is a header containing subheaders, not a flat list.
    if catalog in ('mill', 'plasma'):
        select(3)
        tv = app.treeview2
        closing, link = heading(tv, '#param_h7'), heading(tv, '#param_h5')
        click(tv, closing)
        assert not tv.row_expanded(link), 'opening parent expanded its children'
        click(tv, link)
        click(tv, closing)
        app.get_selected_feature(app.treeview)
        assert not tv.row_expanded(heading(tv, '#param_h7')), 'closed parent reopened on refilter'
        click(tv, heading(tv, '#param_h7'))
        assert tv.row_expanded(heading(tv, '#param_h5')), 'nested expansion choice lost'
        tv.collapse_all()
        print('PASS nested Closing/Link preserve independent parent/child choices', flush=True)

    app.actionSingleView.set_active(True)
    pump()
    for index, name in enumerate(CASES[catalog]):
        select(index)
        tv = app.treeview
        feature = app.selected_feature
        param = next(p for p in feature.param if p.get_type() in ('header', 'sub-header'))
        path = heading(tv, param.attr['call'])
        assert tv.get_show_expanders() and not tv.row_expanded(path)
        click(tv, path)
        assert tv.row_expanded(path), (name, 'single view did not open')
        click(tv, path)
        assert not tv.row_expanded(path), (name, 'single view did not close')
    print('PASS %s: all four feature categories work in single view' % catalog, flush=True)

    app.actionDualView.set_active(True)
    pump()
    select(3)
    items = next(p for p in app.selected_feature.param if p.get_type() == 'items')
    path = find(app.treeview, lambda row: row is items)
    assert app._property_group_key(app.treeview, app.master_filter.get_iter(path)) is None
    assert not app.actionSubHdrs.get_enabled(), 'obsolete layout action still enabled'
    print('PASS Items remains a feature container, obsolete layout option disabled', flush=True)
    after_xml = app.treestore_to_xml()
    after = {f.get('id'): {p.get('call'): p.get('value') for p in f.findall('param')}
             for f in after_xml.findall('feature')}
    assert before == after, 'UI interactions changed project values'
    win.destroy()
    pump()
    return dict(catalog=catalog, features=len(CASES[catalog]), headings=sum(counts))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--child', choices=CASES)
    parser.add_argument('--root', type=Path)
    args = parser.parse_args()
    if args.child:
        result = child(args.child, args.root)
        print('RESULT', json.dumps(result))
        return
    root = Path(tempfile.mkdtemp(prefix='ncam_property_groups_'))
    results = []
    for catalog in CASES:
        run = subprocess.run([sys.executable, '-u', __file__, '--child', catalog,
                              '--root', str(root)], capture_output=True, text=True, timeout=60)
        (root / (catalog + '.log')).write_text(run.stdout + run.stderr)
        print(run.stdout, end='', flush=True)
        assert run.returncode == 0, run.stderr
        results.append(json.loads(next(line[7:] for line in run.stdout.splitlines()
                                       if line.startswith('RESULT '))))
    (root / 'results.json').write_text(json.dumps(results, indent=2))
    print('Artifacts:', root)
    print('[VERDICT: PASS]')


if __name__ == '__main__':
    main()
