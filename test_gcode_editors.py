#!/usr/bin/env python3
"""Real GTK editors preserve custom G-code and included-file selections."""
import argparse
import configparser
from pathlib import Path
import shutil
import sys
import tempfile
import time
import traceback
from unittest.mock import patch

from lxml import etree

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, help='also exercise an existing saved project in memory')
    args = parser.parse_args()
    root = Path(tempfile.mkdtemp(prefix='ncam_gcode_editors_'))
    config = root / 'config'
    shutil.copytree(HERE / 'configs/sim/axis/ncam_demo', config, symlinks=True)
    settings = config / 'ncam/catalogs/ncam.conf'
    prefs = configparser.ConfigParser(interpolation=None)
    prefs.read(settings)
    prefs.set('layout', 'autorefresh', 'False')
    prefs.set('layout', 'dual_view', 'True')
    with settings.open('w') as stream:
        prefs.write(stream)
    sys.argv = ['ncam.py', '-i', str(config / 'lathe-mm.ini'), '-c', 'lathe']
    import ncam
    from ncam import gtk, GLib

    win = gtk.Window()
    app = ncam.NCam(accel_toplevel=win)
    app.pref.autosave = False
    win.add(app)
    win.set_default_size(1200, 950)
    win.show_all()

    def wait(predicate, timeout=5):
        deadline = time.monotonic() + timeout
        while not predicate():
            assert time.monotonic() < deadline, ('GTK editor timed out', root)
            if gtk.events_pending():
                gtk.main_iteration_do(False)
            else:
                time.sleep(.005)

    def settle():
        deadline = time.monotonic() + .15
        wait(lambda: time.monotonic() >= deadline)

    settle()
    project = (app.update_features(etree.parse(str(args.project)).getroot())
               if args.project else etree.Element(ncam.XML_TAG))
    if project.find('.//feature[@type="g-code"]') is None:
        manual = ncam.Feature(src=str(HERE / 'cfg/gcode.cfg'))
        manual.attr.update(id='g-code_900', src='gcode.cfg')
        project.insert(0, manual.to_xml())
    include = project.find('.//feature[@type="incl_gcode"]')
    if include is None:
        item = ncam.Feature(src=str(HERE / 'cfg/i_gcode.cfg'))
        item.attr.update(id='incl_gcode_901', src='i_gcode.cfg')
        include = item.to_xml()
        project.append(include)
    include.find('param[@call="#param_act"]').set('value', '1')
    app.treestore_from_xml(project)
    included = root / 'custom code.ngc'
    included.write_text('(included editor probe)\nG4 P0.002\n')
    other = root / 'other code.ngc'
    other.write_text('(cancelled selection)\n')
    failures = []
    run_dialog = gtk.Dialog.run

    def find(tv, predicate):
        rows = []
        tv.get_model().foreach(lambda model, path, itr: rows.append(path.copy())
                               if predicate(model.get_value(itr, 0)) else None)
        assert rows
        return rows[0]

    def row(kind, name):
        feature_path = find(app.treeview, lambda item: isinstance(item, ncam.Feature) and item.get_type() == kind)
        app.treeview.set_cursor(feature_path)
        app.get_selected_feature(app.treeview)
        tv = app.treeview2 if app.actionDualView.get_active() else app.treeview
        param = app.selected_feature.get_param('param_' + name)
        path = find(tv, lambda item: item is param)
        tv.expand_to_path(path)
        tv.set_cursor(path)
        tv.scroll_to_cell(path, None, True, .5, 0)
        settle()
        return tv, path, param, tv.get_column(1).get_cells()[0]

    def edit(kind, name, initial, replacement, accept=True):
        tv, path, param, renderer = row(kind, name)
        param.attr['value'] = initial
        errors, opened, observed = [], [], []
        # Display text can belong to a different row when editing starts.
        renderer.set_property('text', 'unrelated painted row')

        def run(dialog):
            opened.append(True)
            if isinstance(dialog, gtk.FileChooserDialog):
                def choose():
                    dialog.set_filename(replacement)
                    def respond():
                        if dialog.get_filename() != replacement:
                            return True
                        observed.append(True)
                        dialog.response(gtk.ResponseType.OK if accept else gtk.ResponseType.CANCEL)
                        return False
                    GLib.timeout_add(30, respond)
                    return False
                GLib.timeout_add(30, choose)
            else:
                def type_text():
                    try:
                        buffer = renderer.textedit.get_buffer()
                        assert buffer.get_text(*buffer.get_bounds(), True) == initial, 'editor used painted text instead of content'
                        assert renderer.textedit.get_editable()
                        assert dialog.get_focus() is renderer.textedit, 'G-code editor did not receive keyboard focus'
                        buffer.place_cursor(buffer.get_end_iter())
                        buffer.insert_at_cursor(replacement)
                        observed.append(True)
                    except Exception:
                        errors.append(traceback.format_exc())
                    dialog.response(gtk.ResponseType.OK if accept else gtk.ResponseType.CANCEL)
                    return False
                GLib.timeout_add(30, type_text)
            timeout = GLib.timeout_add_seconds(4, lambda: dialog.response(gtk.ResponseType.CANCEL) or False)
            try:
                return run_dialog(dialog)
            finally:
                GLib.source_remove(timeout)

        def exception(*args):
            errors.append(''.join(traceback.format_exception(*args)))

        with patch.object(gtk.Dialog, 'run', run), patch.object(sys, 'excepthook', exception):
            rect = tv.get_cell_area(path, tv.get_column(1))
            renderer.do_start_editing(None, tv, path.to_string(), rect, rect, gtk.CellRendererState.SELECTED)
            renderer.set_param_value('repaint after activation')
            renderer.set_property('text', 'repaint after activation')
            wait(lambda: not getattr(renderer, '_editor_pending', False))
        assert not errors, '\n'.join(errors)
        assert opened and observed, 'editor did not open'
        expected = (replacement if kind == 'incl_gcode' else initial + replacement) if accept else initial
        assert param.get_value() == expected, (kind, accept, param.get_value(), expected)
        assert gtk.grab_get_current() is None, 'editor retained GTK grab'
        assert app.selected_feature.get_type() == kind
        print('PASS', 'dual' if app.actionDualView.get_active() else 'single', kind,
              'save' if accept else 'cancel', flush=True)
        return expected

    content = 'G4 P0.001\n(manual <probe> & content)\n'
    try:
        for dual in (True, False):
            (app.actionDualView if dual else app.actionSingleView).set_active(True)
            settle()
            for kind, name, initial, replacement, accept in (
                    ('g-code', 'gc', '', content, True),
                    ('g-code', 'gc', content, '(reopened)\n', True),
                    ('g-code', 'gc', content, '(discard)\n', False),
                    ('incl_gcode', 'fname', '', str(included), True),
                    ('incl_gcode', 'fname', str(included), str(other), False)):
                try:
                    edit(kind, name, initial, replacement, accept)
                except Exception:
                    failures.append(traceback.format_exc())
                    print('FAIL', kind, 'save' if accept else 'cancel', failures[-1], flush=True)
                    for dialog in gtk.Window.list_toplevels():
                        if isinstance(dialog, gtk.Dialog):
                            dialog.destroy()
        assert not failures, ('editor regressions', failures, root)
        saved = root / 'project.xml'
        saved.write_bytes(etree.tostring(app.treestore_to_xml()))
        app.treestore_from_xml(app.update_features(etree.parse(str(saved)).getroot()))
        assert row('g-code', 'gc')[2].get_value() == content
        assert row('incl_gcode', 'fname')[2].get_value() == str(included)
        code = app.to_gcode()
        assert 'G4 P0.001' in code and '(manual <probe> & content)' in code
        assert '(included editor probe)' in code and 'G4 P0.002' in code
        assert '(cancelled selection)' not in code
        print('PASS save/reload and generated inline/file G-code', flush=True)
    finally:
        win.destroy()
    print('ARTIFACTS', root, flush=True)
    print('[VERDICT: PASS]')


if __name__ == '__main__':
    main()
