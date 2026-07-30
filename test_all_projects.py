#!/usr/bin/env python3
# coding: utf-8
"""Loads and generates every saved project, for every machine catalog.

Standalone, like the other test_*.py here - run it directly, no pytest.

This exists because bumping a cfg version is not a no-op on unrelated features.
It moves every feature in every saved project onto the migration path, which may
not have run in months - and that path has already taken down a whole project
load with a KeyError on a nested feature that had no 'expanded' attribute. So
after any cfg version change, every project has to be opened, not just the one
being worked on.

It runs against a COPY of the config: NCam prompts when a system file is newer
than the user's catalog copy, and a headless run has nobody to answer.
"""
import glob
import os
import shutil
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIGS = [('lathe', os.path.join(HERE, 'configs/sim/axis/ncam_demo/lathe-mm.ini'))]
FAILED = []


def run_catalog(machine, ini):
    if not os.path.exists(ini):
        print('SKIP - no ini at %s' % ini)
        return
    scratch = tempfile.mkdtemp(prefix='test_all_projects_')
    dst = os.path.join(scratch, os.path.basename(os.path.dirname(ini)))
    shutil.copytree(os.path.dirname(ini), dst, symlinks=True)
    ini = os.path.join(dst, os.path.basename(ini))

    sys.argv = ['ncam.py', '-i', ini, '-c', machine]
    sys.path.insert(0, HERE)
    import ncam
    from lxml import etree

    app = ncam.NCam()
    base = os.path.join(dst, 'ncam', 'catalogs', machine, 'projects')
    files = sorted(glob.glob(base + '/*.xml') + glob.glob(base + '/examples/*'))
    print('\n%s: %d project(s)' % (machine, len(files)))
    for f in files:
        name = os.path.basename(f)
        try:
            xml = app.update_features(etree.fromstring(open(f).read().encode()))
            app.treestore_from_xml(xml)
            g = app.to_gcode()
            if len(g.splitlines()) < 20:
                raise AssertionError('only %d lines - generation produced nothing'
                                     % len(g.splitlines()))
            print('  ok   %-28s %5d lines' % (name, len(g.splitlines())))
        except Exception as e:
            FAILED.append((name, repr(e)))
            print('  FAIL %-28s %s' % (name, e))
            traceback.print_exc(limit=3)
    shutil.rmtree(scratch, ignore_errors=True)


def main():
    for machine, ini in CONFIGS:
        run_catalog(machine, ini)
    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for n, e in FAILED:
            print('   -', n, e)
        sys.exit(1)
    print('Every saved project loads, migrates and generates.')


if __name__ == '__main__':
    main()
