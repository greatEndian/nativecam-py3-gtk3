#!/usr/bin/env python3
"""Real pointer/keyboard dismissal of property lists during playback (X11)."""
import configparser
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

from lxml import etree

HERE = Path(__file__).resolve().parent


def main():
    assert shutil.which('xdotool'), 'xdotool required for actual XTest input'
    root = Path(tempfile.mkdtemp(prefix='ncam_popup_input_'))
    cfg = root / 'config'
    shutil.copytree(HERE / 'configs/sim/axis/ncam_demo', cfg, symlinks=True)
    settings = cfg / 'ncam/catalogs/ncam.conf'
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(settings)
    parser.set('layout', 'autorefresh', 'False')
    parser.set('layout', 'dual_view', 'True')
    with settings.open('w') as stream:
        parser.write(stream)
    sys.argv = ['ncam.py', '-i', str(cfg / 'lathe-mm.ini'), '-c', 'lathe']
    import ncam
    import ncam_preview as P
    from ncam import gtk, gdk, GLib
    from gi.repository import GdkX11  # noqa: F401 - exposes XIDs

    results = []
    def check(name, passed, **data):
        results.append(dict(check=name, passed=bool(passed), **data))
        (root / 'results.json').write_text(json.dumps(results, indent=2))
        print(('PASS ' if passed else 'FAIL ') + name, data, flush=True)
        assert passed, (name, str(root))

    def wait(predicate, timeout=4):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            if gtk.events_pending():
                gtk.main_iteration_do(False)
            else:
                time.sleep(0.005)
        raise AssertionError('GTK timeout: ' + str(root))

    def settle():
        deadline = time.monotonic() + .15
        wait(lambda: time.monotonic() >= deadline)

    def find(tv, predicate):
        found = []
        tv.get_model().foreach(lambda m, p, i: found.append(p.copy())
                               if predicate(m.get_value(i, 0)) else None)
        assert found
        return found[0]

    def children(widget):
        yield widget
        if isinstance(widget, gtk.Container):
            for child in widget.get_children():
                yield from children(child)

    def xinput(*args):
        subprocess.run(['xdotool', *map(str, args)], check=True, timeout=2)

    win = gtk.Window()
    app = ncam.NCam(accel_toplevel=win)
    win.add(app)
    win.set_default_size(757, 876)
    win.show_all()
    app.pref.autosave = False
    app.actionDualView.set_active(True)
    settle()
    app.treestore_from_xml(app.update_features(etree.fromstring(
        (cfg / 'ncam/catalogs/lathe/projects/testing_15_9.xml').read_bytes())))
    path = find(app.treeview, lambda row: row.get_attr('type') == 'polyline')
    app.treeview.set_cursor(path)
    app.get_selected_feature(app.treeview)
    pane = app.preview_pane
    # Playback scheduling is real; no interpreter needed to test input routing.
    tp = P.Toolpath()
    tp.moves = [P.Move('feed', (20, 0, 0), (20, 0, -50), 'Lathe Polyline', 1, P.CUT)]
    tp.min, tp.max, tp.completed = (20, 0, -50), (20, 0, 0), True
    pane._done(tp)

    def case(action, duplicate=False, linked=False):
        tv = app.treeview2
        param = app.selected_feature.get_param('param_pass_from')
        path = find(tv, lambda row: row is param)
        tv.expand_to_path(path)
        tv.scroll_to_cell(path, None, True, .5, 0)
        tv.set_cursor(path)
        settle()
        renderer = tv.get_column(1).get_cells()[0]
        rect = tv.get_cell_area(path, tv.get_column(1))
        old = param.get_ngc_value()
        original_type = param.attr.get('type')
        original_links = param.attr.get('links')
        if linked:
            param.attr.update(type='combo-user', links='min_pass=1')
        pane.speed = .01
        pane.sim_scale.set_value(.13)
        pane._on_play(None)
        forced, completed, editor_widgets = [], [], []
        def inject():
            popup = renderer.list_window
            editor_widgets.append(popup)
            if duplicate:
                renderer.do_start_editing(None, tv, path.to_string(), rect, rect,
                                         gtk.CellRendererState.SELECTED)
            view = next(w for w in children(popup) if isinstance(w, gtk.TreeView))
            if not (root / 'popup.png').exists():
                picture = gdk.pixbuf_get_from_window(win.get_window(), 0, 0,
                                                     win.get_allocated_width(), win.get_allocated_height())
                picture.savev(str(root / 'popup.png'), 'png', [], [])
            if isinstance(popup, gtk.Dialog):
                xinput('windowfocus', popup.get_window().get_xid())
            if action == 'outside':
                x, y = pane.area.get_window().get_origin()[1:]
                xinput('mousemove', x+30, y+30, 'click', 1)
            elif action == 'escape':
                xinput('key', 'Escape')
            elif action == 'keyboard':
                xinput('key', 'Home', 'Down', 'Return')
            elif action == 'mouse':
                bounds = view.get_background_area(gtk.TreePath([0]), view.get_column(0))
                x, y = view.get_bin_window().get_origin()[1:]
                xinput('mousemove', x+30, y+bounds.y+bounds.height//2, 'click', 1)
            elif action == 'parent-close':
                # Same delete-event emitted by the window manager's close button.
                win.emit('delete-event', None)
                win.destroy()
            return False
        def cleanup():
            forced.append(True)
            popup = renderer.list_window
            if isinstance(popup, gtk.Dialog):
                popup.response(gtk.ResponseType.CANCEL)
            else:
                popup.destroy()
            return False
        original = renderer.edit_list
        safety = []
        def edit_list(*args):
            # Start input deadlines when the deferred editor actually opens,
            # after GTK has dispatched the initiating pointer events.
            GLib.timeout_add(120, inject)
            safety.append(GLib.timeout_add(1200, cleanup))
            value = original(*args)
            completed.append(value)
            return value
        renderer.edit_list = edit_list
        original_number = ncam.VKB.run
        linked_edits = []
        def number(vkb, not_allowed):
            linked_edits.append(True)
            check('linked numeric editor opens after list closes', not renderer.list_window.get_visible())
            def respond():
                vkb.entry.set_markup('<b>2.5</b>')
                vkb.ok(None)
                return False
            GLib.timeout_add(40, respond)
            return original_number(vkb, not_allowed)
        # Use the actual cell editor request. A double activation used to queue
        # two modal editors sharing list_window and close-state flags.
        if duplicate:
            for _ in range(2):
                renderer.do_start_editing(None, tv, path.to_string(), rect, rect,
                                         gtk.CellRendererState.SELECTED)
        else:
            x, y = tv.get_bin_window().get_origin()[1:]
            xinput('mousemove', x+rect.x+20, y+rect.y+rect.height//2, 'click', 1)
        try:
            with patch.object(ncam.VKB, 'run', number):
                wait(lambda: bool(completed))
                # The linked number editor runs synchronously in the same
                # deferred commit, before this GTK dispatch returns.
            if not forced:
                GLib.source_remove(safety[0])
            check(action + ' dismisses without forced cleanup', not forced)
            check(action + ' releases popup grab', gtk.grab_get_current() is None)
            if action != 'parent-close':
                settle()
                expected = '1' if action == 'keyboard' else '0' if action == 'mouse' else old
                check(action + ' commits only the selected value', param.get_ngc_value() == expected)
                check(action + ' keeps playback paused in place', not pane.sim_running and pane.sim_t == .13)
                check(action + ' leaves one completed editor', len(completed) == 1)
                check(action + ' restores property selection', tv.get_cursor()[0] == path)
                check(action + ' clears queued/active editor guard', not renderer._editor_pending)
                if linked:
                    check('combo-user keeps its linked numeric edit',
                          linked_edits and float(app.selected_feature.get_param('param_min_pass').get_ngc_value()) == 2.5)
        finally:
            renderer.edit_list = original
            if original_type is not None:
                param.attr['type'] = original_type
            if original_links is None:
                param.attr.pop('links', None)
            else:
                param.attr['links'] = original_links

    try:
        for action in ('outside', 'escape', 'keyboard', 'mouse', 'outside'):
            case(action)
        case('escape', duplicate=True)
        case('keyboard', linked=True)
        case('parent-close')
    finally:
        win.destroy()
    print('ARTIFACTS', root)
    print('[VERDICT: PASS]')


if __name__ == '__main__':
    main()
