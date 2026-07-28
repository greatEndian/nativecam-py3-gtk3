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

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('All menu layout tests passed.')


if __name__ == '__main__':
    main()
