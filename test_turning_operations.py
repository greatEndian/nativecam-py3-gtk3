#!/usr/bin/env python3
"""Real GTK operation menu, toolbar, catalog, and saved-preset behavior."""
import configparser
import copy
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile

from lxml import etree

HERE = Path(__file__).resolve().parent


def main():
    root = Path(tempfile.mkdtemp(prefix='ncam_turning_menu_'))
    cfg = root / 'config'
    shutil.copytree(HERE / 'configs/sim/axis/ncam_demo', cfg, symlinks=True)
    prefs = configparser.ConfigParser(interpolation=None)
    settings = cfg / 'ncam/catalogs/ncam.conf'
    prefs.read(settings)
    prefs.set('layout', 'autorefresh', 'False')
    with settings.open('w') as stream:
        prefs.write(stream)
    sys.argv = ['ncam.py', '-i', str(cfg / 'lathe-mm.ini'), '-c', 'lathe']
    import ncam
    from ncam import gtk, gdk
    local_menu = cfg / 'ncam/catalogs/lathe/menu.xml'
    local_before = local_menu.read_bytes()
    window = gtk.Window()
    app = ncam.NCam(accel_toplevel=window)
    assert local_menu.read_bytes() == local_before, 'existing local menu overwritten'
    window.add(app)
    app.pref.autosave = False
    window.set_default_size(1150, 730)
    window.show_all()

    def pump():
        while gtk.events_pending():
            gtk.main_iteration_do(False)

    pump()
    initial_project = etree.parse(str(cfg / 'ncam/catalogs/lathe/projects/testing_15_9.xml')).getroot()
    app.treestore_from_xml(app.update_features(initial_project))
    baseline_code = app.to_gcode()
    node = app.catalog.find('.//menu[@action="contour"]')
    assert node is not None and node.get('name') == 'Turning', 'operation-based Turning menu missing'
    menu = gtk.Menu()
    app.build_menu_from_node(menu, node)
    items = {m.get_label(): m for m in menu.get_children() if isinstance(m, gtk.MenuItem)}
    wanted = [('Outside roughing', 0, 1), ('Inside roughing', 1, 1),
              ('Outside finishing', 0, 2), ('Inside finishing', 1, 2)]
    results = {}
    app.treestore_from_xml(etree.Element(ncam.XML_TAG))
    for label, side, op in wanted:
        app.iter_selected_type = ncam.tv_select.none
        items[label].activate()
        xml = app.treestore_to_xml()
        poly = xml.findall('./feature')[-1]
        assert poly.get('type') == 'polyline' and poly.get('name') == label
        assert poly.get('src') == 'lathe/polyline.cfg'
        assert items[label].get_always_show_image() and items[label].get_image() is not None
        values = {p.get('call'): p.get('value') for p in poly.findall('param')}
        assert int(values['#param_side']) == side
        assert int(values['#param_op']) == op
        assert int(values['#param_pf_on']) == 0
        start, end = (float(values['#param_'+p]) for p in ('b_x', 'e_x'))
        assert start < end if side else start > end
        assert poly.find('param[@type="items"]') is not None
        results[label] = values
    for label in ('Outside grooving (planned)', 'Inside grooving (planned)', 'Face grooving (planned)'):
        assert not items[label].get_sensitive(), ('unimplemented operation enabled', label)
    saved = app.treestore_to_xml()
    migrated = copy.deepcopy(saved)
    for f in migrated.findall('./feature'):
        f.set('version', '1.0')
        f.find('param[@call="#param_f_off"]').set('value', '.0123')
        f.find('param[@call="#param_op"]').set('value', '0')
        f.find('param[@call="#param_pf_on"]').set('value', '1')
    migrated = app.update_features(migrated)
    for f, original in zip(migrated.findall('./feature'), saved.findall('./feature')):
        assert f.get('name') == original.get('name') and f.get('icon') == original.get('icon')
        assert f.get('catalog_preset') == original.get('catalog_preset')
        assert f.find('param[@call="#param_f_off"]').get('value') == '.0123'
        assert f.find('param[@call="#param_op"]').get('value') == '0'
        assert f.find('param[@call="#param_pf_on"]').get('value') == '1'
    # Direct toolbar shortcuts must carry the same preset as menu/gallery.
    temporary = etree.SubElement(app.catalog.find('toolbar'), 'toolitem', action='profile_rough_od')
    app.get_toolbar_actions()
    app.create_nc_toolbar()
    app.iter_selected_type = ncam.tv_select.none
    app.nc_toolbar.get_children()[-1].emit('clicked')
    assert app.treestore_to_xml().findall('./feature')[-1].get('name') == 'Outside roughing'
    app.catalog.find('toolbar').remove(temporary)
    app.get_toolbar_actions()
    app.create_nc_toolbar()
    chooser = next(b for b in app.nc_toolbar.get_children()
                   if isinstance(b, gtk.MenuToolButton) and b.get_label() == 'Turning')
    count = len(app.treestore_to_xml().findall('./feature'))
    chooser.emit('clicked')
    pump()
    assert chooser.get_menu().get_visible()
    assert len(app.treestore_to_xml().findall('./feature')) == count
    chooser.get_menu().popdown()
    pump()
    def descendants(widget):
        yield widget
        if isinstance(widget, gtk.Container):
            for child in widget.get_children():
                yield from descendants(child)
    arrow = next(w for w in descendants(chooser) if isinstance(w, gtk.ToggleButton))
    arrow.emit('clicked')
    pump()
    assert chooser.get_menu().get_visible(), 'dropdown arrow failed to open menu'
    assert len(app.treestore_to_xml().findall('./feature')) == count
    chooser.get_menu().popdown()
    # Gallery uses the node's preset too, and never inserts planned entries.
    app.update_catalog(node)
    for index, child in enumerate(node):
        if child.get('preset') == 'inside_finishing':
            row = next(itr for itr in app.icon_store if itr[4] == index and itr[1] != 'parent')
            app.add_iconview.select_path(row.path)
            app.iter_selected_type = ncam.tv_select.none
            app.catalog_activate(app.add_iconview)
            assert app.treestore_to_xml().findall('./feature')[-1].get('name') == 'Inside finishing'
            break
    before_planned = etree.tostring(app.treestore_to_xml())
    for index, child in enumerate(node):
        if child.get('action') == 'groove_od':
            app.update_catalog(node)
            row = next(itr for itr in app.icon_store if itr[4] == index and itr[1] != 'parent')
            app.add_iconview.unselect_all()
            app.add_iconview.select_path(row.path)
            app.catalog_activate(app.add_iconview)
            for cell in app.add_iconview.get_cells():
                app.catalog_cell_data(app.add_iconview, cell, app.icon_store, row.iter)
                assert not cell.get_property('sensitive')
            assert etree.tostring(app.treestore_to_xml()) == before_planned
    # Geometry tools are still actual features inserted in the Items group.
    data = copy.deepcopy(saved)
    app.treestore_from_xml(data)
    poly_feature = app.treestore.get_value(app.treestore.get_iter_first(), 0)
    items_param = poly_feature.get_param('param_items')
    match = []
    app.treeview.get_model().foreach(lambda model, path, itr: match.append(path.copy())
                                    if model.get_value(itr, 0) is items_param else None)
    assert match
    app.treeview.expand_to_path(match[0])
    app.treeview.get_selection().select_path(match[0])
    app.get_selected_feature(app.treeview)
    geometry = next(m for m in menu.get_children() if isinstance(m, gtk.MenuItem)
                    and m.get_label() == 'Profile geometry').get_submenu()
    geometry.get_children()[0].activate()
    assert app.treestore_to_xml().find('./feature/param[@type="items"]/feature') is not None
    # A legacy project remains the same generated program; presets are opt-in.
    project = etree.parse(str(cfg / 'ncam/catalogs/lathe/projects/testing_15_9.xml')).getroot()
    app.treestore_from_xml(app.update_features(project))
    code = app.to_gcode()
    results['saved_gcode_hash'] = hashlib.sha256(code.encode()).hexdigest()
    (root / 'saved.ngc').write_text(code)
    assert code == baseline_code, 'menu interaction altered the saved-project G-code'
    # Shared catalog code must also support unchanged mill/plasma definitions.
    for catalog in ('mill', 'plasma'):
        source = (HERE / 'catalogs' / catalog / 'menu.xml').read_text()
        app.catalog = etree.fromstring(source.replace('_(', '').replace(')_', ''))
        app.get_toolbar_actions()
        app.create_nc_toolbar()
        assert app.nc_toolbar.get_n_items() > 0
    # Screenshot the actual Turning menu, independent of the user's live app.
    source = (HERE / 'catalogs/lathe/menu.xml').read_text()
    app.catalog = etree.fromstring(source.replace('_(', '').replace(')_', ''))
    app.get_toolbar_actions()
    app.create_nc_toolbar()
    app.treestore_from_xml(saved)
    window.show_all()
    pump()
    chooser = next(b for b in app.nc_toolbar.get_children()
                   if isinstance(b, gtk.MenuToolButton) and b.get_label() == 'Turning')
    chooser.emit('clicked')
    pump()
    screen = gdk.get_default_root_window()
    shot = gdk.pixbuf_get_from_window(screen, 0, 0, screen.get_width(), screen.get_height())
    shot.savev(str(root / 'turning-menu.png'), 'png', [], [])
    chooser.get_menu().popdown()
    # The documented custom-menu override remains authoritative and untouched.
    custom = cfg / 'ncam/catalogs/lathe/menu-custom.xml'
    custom.write_text(source.replace('name=_("Turning")_', 'name=_("My turning")_'))
    custom_before = custom.read_bytes()
    override = ncam.NCam()
    assert override.catalog.find('.//menu[@action="contour"]').get('name') == 'My turning'
    assert custom.read_bytes() == custom_before and local_menu.read_bytes() == local_before
    (root / 'results.json').write_text(json.dumps(results, indent=2))
    print('ARTIFACTS', root, flush=True)
    print('[VERDICT: PASS]')


if __name__ == '__main__':
    main()
