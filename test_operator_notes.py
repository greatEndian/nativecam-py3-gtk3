#!/usr/bin/env python3
"""Operator notes and setup-only G-code reach the real GUI Flat preview."""
import argparse
import configparser
from pathlib import Path
import shutil
import sys
import tempfile
import time
from unittest.mock import patch

from lxml import etree

HERE = Path(__file__).resolve().parent
SETUP = 'G18 G40 G49 G90 G92.1 G94 G54'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path)
    args = parser.parse_args()
    root = Path(tempfile.mkdtemp(prefix='ncam_operator_notes_'))
    config = root / 'config'
    shutil.copytree(HERE / 'configs/sim/axis/ncam_demo', config, symlinks=True)
    settings = config / 'ncam/catalogs/ncam.conf'
    prefs = configparser.ConfigParser(interpolation=None)
    prefs.read(settings)
    prefs.set('layout', 'autorefresh', 'False')
    prefs.set('layout', 'dual_view', 'True')
    prefs.set('layout', 'remember_session', 'False')
    with settings.open('w') as stream:
        prefs.write(stream)
    sys.argv = ['ncam.py', '-i', str(config / 'lathe-mm.ini'), '-c', 'lathe']
    import ncam
    from ncam import gtk, GLib

    def wait(predicate, timeout=30):
        deadline = time.monotonic() + timeout
        while not predicate():
            assert time.monotonic() < deadline, ('GTK timeout', root)
            if gtk.events_pending():
                gtk.main_iteration_do(False)
            else:
                time.sleep(.005)

    def feature(source, number, **values):
        f = ncam.Feature(src=str(HERE / 'cfg' / source))
        f.attr.update(src=source, id=f.get_type() + '_%03d' % number)
        for key, value in values.items():
            p = f.get_param('param_' + key)
            p.attr['value'] = str(value/25.4 if 'metric_value' in p.attr else value)
        return f

    window = gtk.Window()
    app = ncam.NCam(accel_toplevel=window)
    app.pref.autosave = False
    window.add(app)
    window.set_default_size(1200, 950)
    window.show_all()
    app.preview_pane.widget.set_current_page(0)
    wait(lambda: app.preview_pane.area.get_window() is not None)
    until = time.monotonic() + .2
    wait(lambda: time.monotonic() >= until)
    if args.project:
        project = app.update_features(etree.parse(str(args.project)).getroot())
    else:
        project = etree.Element(ncam.XML_TAG)
        project.append(feature('gcode.cfg', 1).to_xml())
        project.append(feature('lathe/material.cfg', 1, od=50, units=21).to_xml())
        project.append(feature('lathe/tool-change.cfg', 1, dnum=2).to_xml())
        poly = feature('lathe/polyline.cfg', 1, b_x=50, e_x=30)
        app._apply_profile_preset(poly, 'outside_roughing')
        parent = poly.to_xml()
        items = parent.find('param[@type="items"]')
        for i, z in enumerate((0, -5), 1):
            items.append(feature('lathe/polyline-to.cfg', i, type=1, x=30, z=z, m_style=0).to_xml())
        project.append(parent)
    manual = project.find('.//feature[@type="g-code"]')
    manual.find('param[@call="#param_gc"]').set('value', SETUP)
    project.append(feature('lathe/facing.cfg', 1, act=0).to_xml())
    comment = feature('comment.cfg', 1, n='Operator fixture paragraph one\nMount clamp tightly\nReference C:\\parts\\v1\\fixture\nLong note: '
                      + 'verify finish ' * 100 + 'ENDLONG')
    project.append(comment.to_xml())
    app.treestore_from_xml(project)
    assert app.catalog.find('.//menuitem[@action="comment"]').get('src') == 'comment.cfg'
    failures, details = [], {}
    kinds = ('workpiece', 'tool_change', 'polyline', 'facing')
    def inspect(model, path, itr):
        f = model.get_value(itr, 0)
        if isinstance(f, ncam.Feature) and f.get_type() in kinds:
            p = f.get_param('param_operator_notes')
            if p is None:
                failures.append('missing Operator notes on ' + f.get_type())
            else:
                value = f.get_name() + ': inspect finish and setup C:\\parts\\v1\\fixture'
                p.attr['value'] = value
                details[f.get_type()] = value
    app.treestore.foreach(inspect)

    # Edit the shared field using the same popup as an operator, in both layouts.
    if not failures:
        for dual in (True, False):
            (app.actionDualView if dual else app.actionSingleView).set_active(True)
            until = time.monotonic() + .2
            wait(lambda: time.monotonic() >= until)
            paths = []
            app.treeview.get_model().foreach(
                lambda model, path, itr: paths.append(path.copy())
                if isinstance(model.get_value(itr, 0), ncam.Feature)
                and model.get_value(itr, 0).get_type() == 'facing' else None)
            app.treeview.set_cursor(paths[0])
            app.get_selected_feature(app.treeview)
            until = time.monotonic() + .1
            wait(lambda: time.monotonic() >= until)
            tv = app.treeview2 if dual else app.treeview
            param = app.selected_feature.get_param('param_operator_notes')
            paths = []
            tv.get_model().foreach(lambda model, path, itr: paths.append(path.copy())
                                  if model.get_value(itr, 0) is param else None)
            path = paths[0]
            tv.expand_to_path(path)
            tv.set_cursor(path)
            tv.scroll_to_cell(path, None, True, .5, 0)
            until = time.monotonic() + .1
            wait(lambda: time.monotonic() >= until)
            renderer = tv.get_column(1).get_cells()[0]
            initial = param.get_value()
            value = initial + (' / dual edit' if dual else ' / single edit')
            original_run, errors = gtk.Dialog.run, []
            def run(dialog):
                def respond():
                    try:
                        buf = renderer.textedit.get_buffer()
                        assert buf.get_text(*buf.get_bounds(), True) == initial
                        buf.set_text(value)
                    except Exception as error:
                        errors.append(str(error))
                    dialog.response(gtk.ResponseType.OK)
                    return False
                GLib.timeout_add(30, respond)
                return original_run(dialog)
            with patch.object(gtk.Dialog, 'run', run):
                rect = tv.get_cell_area(path, tv.get_column(1))
                renderer.do_start_editing(None, tv, path.to_string(), rect, rect, gtk.CellRendererState.SELECTED)
                wait(lambda: not getattr(renderer, '_editor_pending', False))
            assert not errors and param.get_value() == value
            details['facing'] = value
        print('PASS Operator notes are visible and editable in both property layouts', flush=True)
    pane = app.preview_pane
    generated = Path(ncam.NGC_DIR) / ncam.GENERATED_FILE
    try:
        with patch.object(ncam.linuxcnc, 'command', side_effect=AssertionError('controller command')):
            pane.widget.set_current_page(2)
            button = next(item for item in app.main_toolbar.get_children()
                          if hasattr(item, 'get_action_name') and item.get_action_name() == 'app.Regen')
            button.get_child().clicked()
            wait(lambda: not pane._busy, timeout=90)
            assert pane.toolpath.completed and not pane.toolpath.error, pane.toolpath.error
            flat = pane.flat_buffer.get_text(*pane.flat_buffer.get_bounds(), True)
            assert flat == pane.toolpath.flat
            view = pane.widget.get_nth_page(2).get_child()
            assert view.get_buffer() is pane.flat_buffer and view.get_mapped(), 'the actual Flat view is not visible'
            raw = generated.read_text()
            for value in ('Operator fixture paragraph one', 'Mount clamp tightly', 'ENDLONG'):
                if value not in flat:
                    failures.append('missing from GUI Flat: ' + value)
            commands = [line.strip() for line in flat.splitlines()
                        if line.strip() and not line.lstrip().startswith('(')]
            if SETUP not in commands:
                failures.append('setup G-code is not executable in the Flat program')
            start = flat.index('(begin GCode)')
            end = flat.index('(end GCode)', start)
            if not any(line.strip() == SETUP for line in flat[start:end].splitlines()):
                failures.append('setup block did not stay inside its GCode feature')
            if 'G-code source:' in flat:
                failures.append('custom code still appears as a source annotation')
            for value in details.values():
                if value not in raw or value not in flat:
                    failures.append('operation notes missing from Raw/Flat: ' + value)
            assert not failures, (failures, root)
            at = pane.flat_buffer.get_iter_at_offset(flat.index(SETUP))
            scroll = pane.widget.get_nth_page(2).get_vadjustment()
            mark = pane.flat_buffer.create_mark(None, at, False)
            view.scroll_to_mark(mark, .1, True, 0, .15)
            wait(lambda: scroll.get_value() <= view.get_iter_location(at).y
                 <= scroll.get_value() + scroll.get_page_size(), timeout=5)
            pane.flat_buffer.delete_mark(mark)
            until = time.monotonic() + .3
            wait(lambda: time.monotonic() >= until)
            window.check_resize()
            window.get_window().process_updates(True)
            window.get_display().sync()
            x, y = pane.widget.translate_coordinates(window, 0, 0)
            surface = ncam.gdk.pixbuf_get_from_window(window.get_window(), x, y,
                                                     pane.widget.get_allocated_width(),
                                                     pane.widget.get_allocated_height())
            surface.savev(str(root / 'flat-preview.png'), 'png', [], [])
            print('PASS actual Generate and Flat tab show setup G-code, Comment and four operation note fields', flush=True)

            saved = app.treestore_to_xml()
            poly = saved.find('.//feature[@type="polyline"]')
            poly.set('version', '0.01')
            loaded = app.update_features(etree.fromstring(etree.tostring(saved)))
            for kind, value in details.items():
                fields = loaded.findall('.//feature[@type="%s"]/param[@call="#param_operator_notes"]' % kind)
                assert len(fields) == 1 and fields[0].get('value') == value, kind
            app.treestore_from_xml(loaded)
            print('PASS project serialization and template migration preserve notes without duplicate fields', flush=True)

            # User prose remains data, including template tags and parentheses.
            ncam.OPERATOR_NOTE_EXECUTED = False
            unsafe = 'begin setup (OD) <exec>global OPERATOR_NOTE_EXECUTED; OPERATOR_NOTE_EXECUTED = True</exec>\nG1 X999'
            for f in loaded.findall('feature'):
                if f.get('type') == 'comment':
                    f.find('param[@call="#param_n"]').set('value', unsafe)
            app.treestore_from_xml(loaded)
            code = app.to_gcode()
            assert 'Operator note: begin setup [OD]' in code and 'Operator note: G1 X999' in code
            assert '<exec>global OPERATOR_NOTE_EXECUTED;' in code and not ncam.OPERATOR_NOTE_EXECUTED
            print('PASS operator text is literal and parentheses cannot become executable G-code', flush=True)
    finally:
        window.destroy()
    print('ARTIFACTS', root, flush=True)
    print('[VERDICT: PASS]')


if __name__ == '__main__':
    main()
