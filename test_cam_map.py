#!/usr/bin/env python3
# coding: utf-8
"""Each of cam_map's checks fails on the bug it exists for.

Standalone, like the other test_*.py here - run it directly, no pytest.

`cam_map.py` passes on the tree as it stands, which says nothing on its own: a
check that cannot fail proves nothing, and this project has been caught by that
before. So each check is driven with a **known-bad** copy of the tree and has to
report the failure.

The bad copies are made in a scratch directory - `cam_map` is pointed at it by
overriding its module-level paths, so nothing here writes to the repository.

WHAT EACH CASE REPRODUCES. Not invented faults: every one is a bug this project
actually had.

  C1  the floor table moved 3300 -> 3380 in Python while poly_lathe_mill kept
      reading 3300. Twice.
  C2  a global read in the O-code with no default, which LinuxCNC refuses at
      LOAD time with "Named parameter not defined".
  C4  a name in an `order =` line with no [PARAM_*] behind it, so the parameter
      never appears in the tree - found by accident on `e_z`, and the checker
      then found five more the same day.
  C6  a subroutine called but not defined on the lib path.
"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name
          + (('  ' + detail) if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def run_against(root):
    """cam_map's checks, run over a copy of the tree. -> {name: ok}"""
    import cam_map
    keep = (cam_map.HERE, cam_map.LIB, cam_map.CFG)
    cam_map.HERE, cam_map.LIB, cam_map.CFG = (
        root, os.path.join(root, 'lib'), os.path.join(root, 'cfg'))
    try:
        return {n: ok for ok, n, _d in cam_map.check_all()}
    finally:
        cam_map.HERE, cam_map.LIB, cam_map.CFG = keep


def copy_tree(dst):
    """A minimal copy: the two directories the checks read, plus the two files."""
    os.makedirs(dst)
    for d in ('lib', 'cfg'):
        shutil.copytree(os.path.join(HERE, d), os.path.join(dst, d),
                        symlinks=True)
    for f in ('lathe_sections.py', 'ncam.py'):
        shutil.copy(os.path.join(HERE, f), os.path.join(dst, f))
    return dst


def edit(path, old, new):
    with open(path) as fh:
        s = fh.read()
    assert s.count(old) >= 1, 'the known-bad edit did not match: %s' % old[:60]
    with open(path, 'w') as fh:
        fh.write(s.replace(old, new, 1))


def main():
    import cam_map

    # the tree as it stands must be clean, or the cases below prove nothing
    base = {n: ok for ok, n, _d in cam_map.check_all()}
    check('the repository passes every check to begin with', all(base.values()),
          ', '.join(n for n, ok in base.items() if not ok))

    names = list(base)
    # 'match lathe_sections', not merely 'literal': two check names contain
    # that word and picking the first selected the wrong one, which passed and
    # made this case look like a checker fault
    win = next(n for n in names if 'match lathe_sections' in n)
    glob = next(n for n in names if 'create_defaults' in n)
    order = next(n for n in names if 'order line' in n)
    subs = next(n for n in names if 'subroutine' in n)
    scratch = next(n for n in names if 'O-code writes' in n)

    tmp = tempfile.mkdtemp(prefix='cam_map_')
    try:
        # C1 - a window moved in Python, the O-code left behind. THE bug.
        root = copy_tree(os.path.join(tmp, 'c1'))
        edit(os.path.join(root, 'lathe_sections.py'),
             'SECT_FLOOR_BASE = 3380', 'SECT_FLOOR_BASE = 3390')
        r = run_against(root)
        check('C1 catches a window moved in Python but not in the O-code',
              not r[win],
              'poly_lathe_mill still reads #3380 and nothing complained')

        # C2 - a global read with no default: LinuxCNC refuses at load
        root = copy_tree(os.path.join(tmp, 'c2'))
        with open(os.path.join(root, 'lib', 'lathe', 'poly_lathe_mill.ngc'),
                  'a') as fh:
            # READ ONLY. Assigning it as well is not the bug - the check
            # deliberately allows a global the O-code sets before use, which
            # is how _pl_ph1_front_cut works - and writing the bad case that
            # way made it look like the check was broken.
            fh.write('\n(a global nothing defines, only read)\n'
                     '#<zzz_local_test> = [#<_pl_zzz_test> + 1]\n')
        r = run_against(root)
        check('C2 catches a global the O-code reads with no default', not r[glob],
              'a #<_pl_*> with no create_defaults entry passed')

        # C1d - a window grown over the O-code's scratch. Found for real: the
        # In-CAM table was capped at 5000 while poly_add_item uses 4984-4999,
        # so it was allowed to grow into slots that subroutine overwrites.
        root = copy_tree(os.path.join(tmp, 'c1d'))
        edit(os.path.join(root, 'lathe_sections.py'),
             'CAM_TOP = 4984', 'CAM_TOP = 5000')
        r = run_against(root)
        check('C1d catches a window reaching over the O-code scratch',
              not r[scratch],
              'a table capped at 5000 may overwrite poly_add_item at 4984')

        # C4 - a name in an order line with nothing behind it
        root = copy_tree(os.path.join(tmp, 'c4'))
        edit(os.path.join(root, 'cfg', 'lathe', 'polyline.cfg'),
             'order = act hx', 'order = act zzz_test hx')
        r = run_against(root)
        check('C4 catches a name in an order line with no parameter',
              not r[order], 'a dangling order name passed')

        # C6 - a subroutine called but never defined
        root = copy_tree(os.path.join(tmp, 'c6'))
        with open(os.path.join(root, 'lib', 'lathe', 'poly_lathe_mill.ngc'),
                  'a') as fh:
            fh.write('\no<zzz_missing_sub> CALL [1]\n')
        r = run_against(root)
        check('C6 catches a subroutine called but not defined', not r[subs],
              'a call to a non-existent subroutine passed')

        # and the cases must be SPECIFIC - a broken window must not also trip
        # the global check, or a failure says nothing about where to look
        root = copy_tree(os.path.join(tmp, 'x'))
        edit(os.path.join(root, 'lathe_sections.py'),
             'SECT_FLOOR_BASE = 3380', 'SECT_FLOOR_BASE = 3390')
        r = run_against(root)
        check('   and a window fault does not trip the other checks',
              r[glob] and r[order] and r[subs],
              'one broken thing failed several checks - the report cannot say '
              'where to look')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('Every check fails on the bug it exists for.')


if __name__ == '__main__':
    main()
