#!/usr/bin/env python3
# coding: utf-8
"""Proof harness for the in-process "Restart NativeCAM" rebuild.

Standalone, like the other test_*.py here - run it directly, no pytest.
Needs a display: `xvfb-run -a python3 test_restart_rebuild.py`. Isolate
HOME first (`export HOME=$(mktemp -d)`) - standalone NativeCAM writes to
~/nativecam, which the main tree also uses (see SONNET-PROMPT-RESTART-REBUILD.md).

analysis/280 has the blast-radius table this exercises. Builds one real
ncam.NCam() against a scratch copy of the demo lathe-mm.ini config - the
same pattern test_menu_layout.py::_check_popups and
test_param_bounds_migration.py already use for a real NCam under a fake
DISPLAY - then calls the real _rebuild_panel() (not a stand-in) and measures:

  1. a PARAMETER's cfg display name is picked up on rebuild (via the real
     update_features migration path, fabricated saved-feature xml exactly
     like test_param_bounds_migration.py does)
  2. a menu entry added to a scratch catalogs/lathe/menu.xml is picked up
  3. three consecutive rebuilds of an UNCHANGED catalog add nothing:
     action count, menu item count, toolbar button count, and
     create_actions()'s own call count (proxy for "no new accelerator
     handlers") are all unchanged
  4. an unchanged project survives a rebuild byte-for-byte: feature count,
     every param value, and the generated ncam.ngc sha1 are identical
  5. the process is the same pid throughout, and a regenerate still works
     after a rebuild

The cfg and catalog scratch copies are REAL, independent copies (not the
demo config's usual symlinks back into this worktree's cfg/) - editing them
must never touch a tracked file. See the "materialize" step below.
"""
import contextlib
import hashlib
import io
import os
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from lxml import etree                          # noqa: E402

FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name
          + (('  ' + detail) if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def count_menu_items(widget):
    n = 0
    for child in widget.get_children():
        n += 1
        sub = child.get_submenu() if hasattr(child, 'get_submenu') else None
        if sub is not None:
            n += count_menu_items(sub)
    return n


def sha1_of(path):
    with open(path, 'rb') as f:
        return hashlib.sha1(f.read()).hexdigest()


def main():
    ini_src = os.path.join(HERE, 'configs', 'sim', 'axis', 'ncam_demo')
    if not os.path.isdir(ini_src):
        print('SKIP  demo config not present, cannot build a real NCam')
        return
    if not os.getenv('DISPLAY'):
        print('SKIP  needs a real or Xvfb DISPLAY (run under xvfb-run -a)')
        return

    scratch = tempfile.mkdtemp(prefix='restart_rebuild_')
    dst = os.path.join(scratch, 'ncam_demo')
    shutil.copytree(ini_src, dst, symlinks=True)

    # --- materialize real, independent copies of cfg/ and catalogs/lathe -
    # the demo config normally symlinks ncam/cfg back into THIS worktree's
    # tracked cfg/ (see worker_worktree.py link-sim) - fine for reading, but
    # proof 1 and 2 below EDIT a cfg and a menu.xml, and must never touch a
    # tracked file to do it.
    # The cfg copy itself is made AFTER NCam() starts - see materialize_cfg().
    cfg_link = os.path.join(dst, 'ncam', 'cfg')

    cat_lathe = os.path.join(dst, 'ncam', 'catalogs', 'lathe')
    os.makedirs(cat_lathe, exist_ok=True)
    shutil.copy(os.path.join(HERE, 'catalogs', 'lathe', 'menu.xml'),
                os.path.join(cat_lathe, 'menu.xml'))
    # a real projects/ dir - action_saveCurrent needs somewhere to write
    # current_work.xml, and this also gives a real default_template.xml on
    # the NCAM_DIR-first search path
    shutil.copytree(os.path.join(HERE, 'catalogs', 'lathe', 'projects'),
                     os.path.join(cat_lathe, 'projects'))

    sys.argv = ['ncam.py', '-i', os.path.join(dst, 'lathe-mm.ini'), '-c', 'lathe']
    import ncam                                  # noqa: E402
    from gi.repository import Gtk, GLib          # noqa: E402

    pid0 = os.getpid()

    app = ncam.NCam()

    # NCam's own startup runs update_user_tree (ncam_app_actions.py:115-143),
    # which for lib/graphics/cfg DELETES a real NCAM_DIR/<dir> and replaces it
    # with a symlink to SYS_DIR/<dir> - the TRACKED tree. So a cfg copy made
    # before this point is destroyed and re-pointed at the repo, and PROOF 1's
    # edit below then writes straight into tracked source. Measured: every run
    # left `M cfg/lathe/facing.cfg` in the worktree, and PROOF 1 was not
    # testing an isolated copy at all. _rebuild_panel() does not call
    # update_user_tree, so doing it here holds for the rest of the run.
    if os.path.islink(cfg_link):
        os.remove(cfg_link)
    elif os.path.isdir(cfg_link):
        shutil.rmtree(cfg_link)
    shutil.copytree(os.path.join(HERE, 'cfg'), cfg_link)
    if os.path.realpath(cfg_link).startswith(os.path.realpath(HERE) + os.sep):
        print('FAIL  setup: the scratch cfg still resolves into tracked source')
        sys.exit(1)

    # realize it for real - write_ngc() refuses to run otherwise
    win = Gtk.Window()
    win.add(app)
    win.show_all()
    win.resize(900, 700)
    deadline = [False]
    GLib.timeout_add(1500, lambda: (deadline.__setitem__(0, True), False)[1])
    while not deadline[0]:
        Gtk.main_iteration()
    while Gtk.events_pending():
        Gtk.main_iteration()

    check('the panel actually realized under Xvfb', app.get_realized())

    # ------------------------------------------------------------------
    # PROOF 1 - a PARAMETER's cfg display name is picked up on rebuild.
    # Exercises the real migration path directly (app.update_features),
    # the same technique test_param_bounds_migration.py uses - no need to
    # route it through the live treestore/current-work file at all.
    # ------------------------------------------------------------------
    facing_cfg = os.path.join(cfg_link, 'lathe', 'facing.cfg')
    src_txt = open(facing_cfg).read()
    m = re.search(r'(?m)^version\s*=\s*([\d.]+)', src_txt)
    check('setup: facing.cfg has a version line to bump', m is not None)
    old_version = float(m.group(1)) if m else 1.0
    new_txt = re.sub(r'(?m)^version\s*=\s*[\d.]+',
                      'version = %.2f' % (old_version + 1.0), src_txt, count=1)
    new_txt = re.sub(r'(?m)^(name = _\("Begin diameter"\))',
                      'name = _("Begin diameter EDITED")', new_txt, count=1)
    check('setup: the PARAM_B_X name line was actually matched',
          'Begin diameter EDITED' in new_txt)
    with open(facing_cfg, 'w') as f:
        f.write(new_txt)

    old_project = etree.Element(ncam.XML_TAG)
    old_feature = etree.SubElement(
        old_project, 'feature', type='facing', src='lathe/facing.cfg',
        version='0.01', id='facing_001')
    etree.SubElement(old_feature, 'param', call='#param_b_x', type='float',
                      path='0:0', value='1.0')
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        migrated = app.update_features(old_project)
    p = migrated.find(".//feature[@type='facing']/param[@call='#param_b_x']")
    check('PROOF 1: a parameter display-name cfg edit is picked up on reload',
          p is not None and p.get('name') == 'Begin diameter EDITED',
          'got %r' % (p.get('name') if p is not None else None))
    fnew = migrated.find(".//feature[@type='facing']")
    check('   and the feature version moved to the new cfg\'s',
          fnew is not None and float(fnew.get('version')) == old_version + 1.0,
          'got %r' % (fnew.get('version') if fnew is not None else None))

    # ------------------------------------------------------------------
    # Give the live project one real feature and save it as current work,
    # so load_currentWork() (inside _rebuild_panel) has something to round
    # -trip, and so proof 4 (project survives) has something to compare.
    # ------------------------------------------------------------------
    app.add_feature(None, 'lathe/turning.cfg')
    app.action_saveCurrent()

    xml_before = etree.tostring(app.treestore_to_xml(), pretty_print=True)
    features_before = len(app.treestore_to_xml().findall('.//feature'))
    check('setup: the project has at least one feature to protect',
          features_before >= 1, 'got %d' % features_before)

    ngc_before = app.write_ngc()
    check('setup: ncam.ngc actually got written', ngc_before is not None
          and os.path.isfile(ngc_before))
    sha_before = sha1_of(ngc_before) if ngc_before else None

    # ------------------------------------------------------------------
    # PROOF 3 - three consecutive rebuilds of an UNCHANGED catalog/project
    # duplicate nothing. create_actions() must never be called again (the
    # documented reason: it would add a second accelerator handler for the
    # same keystroke on top of a same-name GSimpleAction replace) - count
    # its calls directly rather than trust widget counts alone.
    # ------------------------------------------------------------------
    create_actions_calls = [0]
    real_create_actions = app.create_actions

    def counted_create_actions():
        create_actions_calls[0] += 1
        return real_create_actions()
    app.create_actions = counted_create_actions

    actions0 = len(app._actions)
    ga0 = len(app.gaction_group.list_actions())
    menu0 = count_menu_items(app.menubar)
    tb0 = len(app.nc_toolbar.get_children())

    snapshots = []
    for i in range(3):
        app._rebuild_panel()
        while Gtk.events_pending():
            Gtk.main_iteration()
        snapshots.append((
            len(app._actions),
            len(app.gaction_group.list_actions()),
            count_menu_items(app.menubar),
            len(app.nc_toolbar.get_children()),
        ))

    check('PROOF 3: create_actions() is never called again by a rebuild',
          create_actions_calls[0] == 0,
          'called %d times' % create_actions_calls[0])
    check('   action count unchanged across 3 rebuilds',
          all(s[0] == actions0 for s in snapshots),
          'baseline %d, saw %s' % (actions0, [s[0] for s in snapshots]))
    check('   GAction name count unchanged across 3 rebuilds',
          all(s[1] == ga0 for s in snapshots),
          'baseline %d, saw %s' % (ga0, [s[1] for s in snapshots]))
    check('   menu item count unchanged across 3 rebuilds',
          all(s[2] == menu0 for s in snapshots),
          'baseline %d, saw %s' % (menu0, [s[2] for s in snapshots]))
    check('   toolbar button count unchanged across 3 rebuilds',
          all(s[3] == tb0 for s in snapshots),
          'baseline %d, saw %s' % (tb0, [s[3] for s in snapshots]))

    # ------------------------------------------------------------------
    # PROOF 4 - the project survives a rebuild of an unchanged tree,
    # exactly (the 3 rebuilds above already happened; check now).
    # ------------------------------------------------------------------
    xml_after = etree.tostring(app.treestore_to_xml(), pretty_print=True)
    features_after = len(app.treestore_to_xml().findall('.//feature'))
    check('PROOF 4: feature count identical after 3 rebuilds',
          features_after == features_before,
          'before %d after %d' % (features_before, features_after))
    check('   every parameter value identical after 3 rebuilds (xml diff)',
          xml_before == xml_after)

    ngc_after = app.write_ngc()
    sha_after = sha1_of(ngc_after) if ngc_after else None
    check('   generated ncam.ngc sha1 identical after 3 rebuilds',
          sha_before is not None and sha_before == sha_after,
          'before %s after %s' % (sha_before, sha_after))

    # ------------------------------------------------------------------
    # PROOF 5 - same pid throughout, and a regenerate still works.
    # ------------------------------------------------------------------
    check('PROOF 5: same pid before and after every rebuild',
          os.getpid() == pid0)
    check('   a regenerate still works after 3 rebuilds',
          ngc_after is not None and os.path.getsize(ngc_after) > 0)

    # ------------------------------------------------------------------
    # PROOF 2 - a menu entry added to a scratch menu.xml is picked up.
    # Edits the MATERIALIZED scratch copy (never the tracked one), adds
    # one <menuitem> under Live Tooling, rebuilds, and checks the item
    # count grows by EXACTLY one and the new item is actually present.
    # ------------------------------------------------------------------
    menu_path = os.path.join(cat_lathe, 'menu.xml')
    menu_txt = open(menu_path).read()
    probe_action = 'RestartRebuildProbe280'
    check('setup: the probe action name is not already in the catalog',
          probe_action not in menu_txt)
    menu_txt2 = menu_txt.replace(
        '<group name="Live Tooling">',
        '<group name="Live Tooling">\n\t\t\t    '
        '<menuitem action="%s" name="Restart Rebuild Probe" '
        'src="lathe/facing.cfg" icon="lathe-facing.png" '
        'tool_tip="analysis/280 proof - safe to remove"/>' % probe_action,
        1)
    check('setup: the probe menuitem was actually inserted',
          menu_txt2 != menu_txt)
    with open(menu_path, 'w') as f:
        f.write(menu_txt2)

    menu_before_edit = count_menu_items(app.menubar)
    app._rebuild_panel()
    while Gtk.events_pending():
        Gtk.main_iteration()
    menu_after_edit = count_menu_items(app.menubar)

    def find_by_label(widget, label):
        # catalog-built menu items (build_menu_from_node) connect "activate"
        # directly to add_feature and carry no Gio action name at all -
        # unlike the static menubar items _create_menu_item builds - so the
        # only thing to search on here is the label text.
        for child in widget.get_children():
            get_label = getattr(child, 'get_label', None)
            if get_label is not None and get_label() == label:
                return True
            sub = child.get_submenu() if hasattr(child, 'get_submenu') else None
            if sub is not None and find_by_label(sub, label):
                return True
        return False

    check('PROOF 2: a scratch catalog edit is picked up - item count +1',
          menu_after_edit == menu_before_edit + 1,
          'before %d after %d' % (menu_before_edit, menu_after_edit))
    check('   and the new item is actually reachable in the rebuilt menu',
          find_by_label(app.menubar, 'Restart Rebuild Probe'))

    win.destroy()
    while Gtk.events_pending():
        Gtk.main_iteration()
    shutil.rmtree(scratch, ignore_errors=True)

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('All restart-rebuild proofs passed.')


if __name__ == '__main__':
    main()
