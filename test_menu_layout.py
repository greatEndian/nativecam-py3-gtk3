#!/usr/bin/env python3
# coding: utf-8
"""Checks the lathe menu/toolbar layout in catalogs/lathe/menu.xml.

Standalone, like the other test_*.py here - run it directly, no pytest.

The toolbar gained dropdowns, which means a toolbar entry can now name a menu
node instead of a feature. Two things then go wrong silently: a <toolmenu>
pointing at an action that does not exist leaves a gap in the toolbar with no
error, and a menuitem whose src no longer resolves gives a button that does
nothing when clicked. Both are checked here against the real catalog file.
"""
import contextlib
import io
import os
import sys

sys.argv = ['ncam.py', '-c', 'lathe']
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import re                                      # noqa: E402
from lxml import etree                          # noqa: E402
import ncam                                     # noqa: E402
from ncam import gtk                            # noqa: E402
from ncam_menu_catalog import NCamMenuCatalogMixin  # noqa: E402

MENU = os.path.join(HERE, 'catalogs', 'lathe', 'menu.xml')
CFG = os.path.join(HERE, 'cfg')
FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name + (('  ' + detail) if detail else ''))
    if not cond:
        FAILED.append(name)


class Stub(NCamMenuCatalogMixin):
    """The real mixin with only what the toolbar path touches."""

    def __init__(self, catalog):
        self.catalog = catalog
        self.nc_toolbar = None
        self.main_box = gtk.Box(orientation=gtk.Orientation.VERTICAL)
        self.added = []

    def add_feature(self, widget, src):
        self.added.append(src)


def _check_popups():
    import shutil
    import tempfile
    ini_src = os.path.join(HERE, 'configs', 'sim', 'axis', 'ncam_demo')
    if not os.path.isdir(ini_src):
        print('SKIP  demo config not present, cannot build a real NCam')
        return
    scratch = tempfile.mkdtemp(prefix='popup_test_')
    dst = os.path.join(scratch, 'ncam_demo')
    shutil.copytree(ini_src, dst, symlinks=True)
    sys.argv = ['ncam.py', '-i', os.path.join(dst, 'lathe-mm.ini'), '-c', 'lathe']
    app = ncam.NCam()

    dead = []
    total = [0]

    def walk(menu):
        for it in menu.get_children():
            sub = it.get_submenu() if hasattr(it, 'get_submenu') else None
            if sub is not None:
                walk(sub)
                continue
            name = it.get_action_name() if hasattr(it, 'get_action_name') else None
            if not name or not name.startswith('app.'):
                continue
            act = app._actions.get(name[4:])
            if act is None:
                dead.append((name, 'no such action'))
                continue
            fired = []
            h = act.connect('activate', lambda *a: fired.append(1))
            was = act.get_enabled()
            act.set_enabled(True)
            it.activate()
            act.set_enabled(was)
            act.disconnect(h)
            total[0] += 1
            if not fired:
                dead.append((name, 'clicked, nothing happened'))

    # This forces every item enabled before clicking it (above), which is the
    # point - a dead button must be caught whether or not it happens to be
    # sensitive right now. The cost is that several callbacks then run with
    # selection state this harness never set up, and raise. Two separate
    # causes, both unreachable by a real user, recorded in analysis/130 rather
    # than silently swallowed:
    #   - action_digits/action_hideField/action_chng_group/action_gcode/
    #     action_revert_type/action_removeItem all read selected_param via
    #     self.treestore.get(self.selected_param, 0), which is None here
    #     because nothing this harness did ever selects a PARAMETER row (the
    #     one real auto-selection on load lands on a top-level feature) - and
    #     in real use these six are only ever *sensitive* once a parameter row
    #     genuinely is selected, which is exactly what sets selected_param.
    #   - action_renameF calls get_toplevel() for a dialog's transient_for,
    #     which is only ever a bare NCam (not a Gtk.Window) because THIS
    #     harness never packs NCam into one - unlike both real entry points,
    #     which pack it into a window before any click is possible (ncam.py's
    #     own __main__ before window.run(), AXIS before the tab is shown).
    # A real regression here is a SEVENTH cause appearing, not a count wiggle
    # among these six - so the gate is "does not grow", not "stays at 22".
    KNOWN_TRACEBACK_CAUSES = 7
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        for menu in (app.pop_up, app.pop_up2):
            walk(menu)
    tb_out = buf.getvalue()
    # every one of these is wrapped by the same ca()-installed <lambda> in
    # ncam_app_actions.py - excluded here, or the seven real causes would
    # always read as eight
    sites = set(re.findall(r'in (action_\w+)\n', tb_out))
    check('every right-click item fires its action', not dead,
          '%d of %d dead: %s' % (len(dead), total[0], dead[:5]))
    check('the popups were actually walked', total[0] > 20,
          'only %d items checked' % total[0])
    check('no-selection click noise does not grow past the known causes',
          len(sites) <= KNOWN_TRACEBACK_CAUSES,
          'saw %d call sites, want <= %d: %s'
          % (len(sites), KNOWN_TRACEBACK_CAUSES, sorted(sites)))
    shutil.rmtree(scratch, ignore_errors=True)


def _check_traceback_capture_control():
    """Negative control for the check above: it must be able to fail.

    Not a rerun of the popup walk - that only proves today's six causes are
    still six, which is the thing already pinned. This proves the CAPTURE
    itself catches a real signal-callback exception, the same mechanism the
    real check depends on, with a throwaway action nothing else touches.
    """
    from gi.repository import Gio

    act = Gio.SimpleAction.new('zzz_menu_layout_control', None)

    def _boom(*_a):
        raise RuntimeError('deliberate test traceback')

    act.connect('activate', _boom)
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        act.activate(None)
    n = buf.getvalue().count('Traceback')
    check('the traceback capture catches a real signal-callback exception',
          n == 1, 'got %d' % n)


def main():
    # the catalog uses NativeCAM's own _( )_ gettext markers, which are not
    # valid XML - strip them exactly the way ncam.py does before parsing
    raw = open(MENU).read()
    raw = re.sub(r"_\(", "", raw)
    raw = re.sub(r"\)_", "", raw)
    catalog = etree.fromstring(raw.encode())

    # Preferences.read() normally sets these; it needs a running app, and the
    # toolbar builder only wants the numbers
    ncam.add_menu_icon_size = 24
    ncam.quick_access_icon_size = 30
    # get_pixbuf resolves icons under NCAM_DIR, which NCam.__init__ normally
    # sets from the ini; the repo itself is a valid one for this
    ncam.NCAM_DIR = HERE

    app = Stub(catalog)

    # 1 - every menuitem must point at a cfg that exists, or its button is dead
    missing = []
    for item in catalog.iter('menuitem'):
        src = item.get('src')
        if src and not os.path.exists(os.path.join(CFG, src)):
            missing.append((item.get('action'), src))
    check('every menu entry points at a cfg that exists', not missing, str(missing[:4]))

    # 2 - action names must be unique, or the toolbar lookup picks the wrong one
    actions = [e.get('action') for e in catalog.iter()
               if e.tag in ('menuitem', 'menu', 'group') and e.get('action')]
    dupes = {a for a in actions if actions.count(a) > 1}
    check('action names are unique', not dupes, str(sorted(dupes)))

    # 3 - the toolbar builds, and every entry resolves
    ncam.TB_CATALOG = {}
    app.get_toolbar_actions()
    tb = ncam.TB_CATALOG
    declared = [p for p in catalog.find('toolbar')
                if p.tag in ('toolitem', 'toolmenu', 'separator')]
    check('every toolbar entry resolved to something',
          len(tb) == len(declared),
          '%d resolved of %d declared - a gap means an action name did not match'
          % (len(tb), len(declared)))

    # 4 - the dropdowns specifically
    menus = {k: v for k, v in tb.items() if v != 'separator' and len(v) > 4}
    names = sorted(v[0] for v in menus.values())
    check('both dropdowns are present', len(menus) == 2, 'found %s' % names)

    for v in menus.values():
        node = v[4]
        kids = [c for c in node.iter() if c.tag == 'menuitem']
        check('dropdown %-12s offers entries' % ('"%s"' % v[0]), len(kids) > 0,
              '%d entries' % len(kids))
        check('dropdown %-12s has an icon' % ('"%s"' % v[0]), v[3] is not None)

    # 5 - build the real toolbar and confirm the widget types
    app.create_nc_toolbar()
    kinds = [type(c).__name__ for c in app.nc_toolbar.get_children()]
    check('toolbar contains two MenuToolButtons',
          kinds.count('MenuToolButton') == 2, str(kinds))
    check('toolbar still contains plain ToolButtons',
          kinds.count('ToolButton') >= 4, str(kinds))

    # 6 - a dropdown's menu must actually be populated and wired to add_feature
    for child in app.nc_toolbar.get_children():
        if type(child).__name__ != 'MenuToolButton':
            continue
        m = child.get_menu()
        items = [i for i in m.get_children() if not isinstance(i, gtk.SeparatorMenuItem)]
        check('dropdown menu is populated', len(items) > 0, '%d items' % len(items))
        leaf = next((i for i in items if i.get_submenu() is None), None)
        if leaf is not None:
            before = len(app.added)
            leaf.emit('activate')
            check('clicking a dropdown entry adds a feature',
                  len(app.added) == before + 1, 'added=%s' % app.added[-1:])

    # 7 - the primitives the user asked to gather are all in that dropdown, and
    # no longer loose in the Cutting menu
    prim = next((v[4] for v in menus.values() if 'rimitive' in v[0]), None)
    if prim is not None:
        inside = {i.get('action') for i in prim.iter('menuitem')}
        want = {'turning', 'boring', 'parting', 'taper_oda', 'taper_odl',
                'taper_ida', 'taper_idl', 'radius_od'}
        check('every primitive is in the Primitives dropdown',
              want <= inside, 'missing %s' % sorted(want - inside))

        cutting = catalog.find(".//menu[@action='cutting']")
        loose = {i.get('action') for i in cutting
                 if i.tag == 'menuitem'} & want
        check('no primitive is left loose in the Cutting menu', not loose,
              'still loose: %s' % sorted(loose))

    # 8 - menubar entries must carry text, not just an icon. These used to rely
    # on GTK's stock items for their label; the Py3/GTK3 port replaced
    # create_menu_item() with a hand-built one and the stock lookup went with
    # it, leaving Projects and Edit as rows of unlabelled icons.

    src = open(os.path.join(HERE, 'ncam_app_actions.py')).read()
    import re as _re
    unlabelled = _re.findall(r"ca\(\"(\w+)\",\s*'[\w-]+',\s*None,", src)
    check('every stock-icon action still has a text label', not unlabelled,
          'unlabelled: %s' % unlabelled)

    # 9 - the right-click menus must actually fire their actions.
    # A Gtk.Menu popped up on its own is not in the widget tree, so it cannot
    # walk up to the action group inserted on the NCam widget: every `app.*`
    # item resolves to nothing and clicking does nothing at all. The menubar
    # hid the problem because it IS packed into main_box. This builds a real
    # NCam and activates every popup item.
    _check_popups()
    _check_traceback_capture_control()

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('All menu layout tests passed.')


if __name__ == '__main__':
    main()
