#!/usr/bin/env python3
# coding: utf-8
"""Isolate parallel worker sessions in this repo with `git worktree`.

See WORKTREES.md for the full writeup - why this exists, what a worktree
does and does not fix, and the honest limits (the sim/rs274 path, the
analysis/NNN numbering, lathe_sections.py as a single-writer file). This
script is deliberately thin: it wraps the `git worktree` commands that
already do the real work, plus the one thing `git worktree add` cannot give
you - the gitignored `ncam/{cfg,lib,graphics}` symlink farm the embedded sim
configs need, which `link-sim` recreates INSIDE the new worktree only.

Commands:
    create <name> [--base BRANCH]   one worktree + one branch, one command
    remove <name> [--keep-branch]   tear both down, one command
    list                            what git worktree already tracks
    link-sim <name> [--demo D ...]  point a worktree's own sim configs at
                                     ITS OWN cfg/lib/graphics (see WORKTREES.md
                                     "What breaks" - this is required before
                                     the sim lane will even load, and it is
                                     NOT verified end to end here: this script
                                     never runs rs274 or ncam.py itself)

Worktrees live OUTSIDE this repo (default: ~/nativecam-worktrees/<name>), so
they never appear in `git status` here and a worker's own `git add -A`
cannot sweep another session's in-flight files into its commit - the two
working directories are physically different, not just different branches.
"""
import argparse
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.abspath(__file__))
DEFAULT_WORKTREE_ROOT = os.path.expanduser('~/nativecam-worktrees')
BRANCH_PREFIX = 'worker/'

# The embedded sim demo directories that carry the gitignored ncam/ symlink
# farm in the MAIN tree today (see WORKTREES.md). A worktree needs the same
# three symlinks recreated, pointed at ITS OWN cfg/lib/graphics.
SIM_DEMOS = [
    'configs/sim/axis/ncam_demo',
]

SYMLINK_TARGETS = ['cfg', 'lib', 'graphics']


def _run(cmd, cwd=None, check=True):
    print('+ %s' % ' '.join(cmd))
    result = subprocess.run(cmd, cwd=cwd)
    if check and result.returncode != 0:
        sys.exit(result.returncode)
    return result.returncode


def _validate_name(name):
    if not name or '/' in name or '..' in name or name.startswith('.'):
        sys.exit('refusing worktree name %r - use a plain directory-safe '
                  'name, no slashes or ".."' % name)


def _worktree_path(name):
    return os.path.join(DEFAULT_WORKTREE_ROOT, name)


def cmd_create(args):
    _validate_name(args.name)
    path = _worktree_path(args.name)
    if os.path.exists(path):
        sys.exit('refusing to create %s - already exists' % path)
    branch = BRANCH_PREFIX + args.name
    os.makedirs(DEFAULT_WORKTREE_ROOT, exist_ok=True)
    _run(['git', 'worktree', 'add', '-b', branch, path, args.base], cwd=REPO)
    print('\nWorktree ready at %s on branch %s' % (path, branch))
    print('It has NO configs/sim/*/ncam_demo/ncam/ directory yet (gitignored,')
    print('not created by `git worktree add`) - run:')
    print('    python3 %s link-sim %s'
          % (os.path.basename(__file__), args.name))
    print('before anything in it tries to load a sim config. See WORKTREES.md.')


def cmd_remove(args):
    _validate_name(args.name)
    path = _worktree_path(args.name)
    branch = BRANCH_PREFIX + args.name
    _run(['git', 'worktree', 'remove', path] + (['--force'] if args.force else []),
        cwd=REPO)
    if not args.keep_branch:
        _run(['git', 'branch', '-D', branch], cwd=REPO, check=False)
    print('\nRemoved %s.' % path)
    if not args.keep_branch:
        print('Deleted branch %s. Merge it first if you wanted its work kept:'
              % branch)
        print('    git merge %s' % branch)


def cmd_list(_args):
    _run(['git', 'worktree', 'list'], cwd=REPO)


def cmd_link_sim(args):
    _validate_name(args.name)
    path = _worktree_path(args.name)
    if not os.path.isdir(path):
        sys.exit('no worktree at %s - run create first' % path)
    demos = args.demo or SIM_DEMOS
    for demo in demos:
        demo_dir = os.path.join(path, demo)
        if not os.path.isdir(demo_dir):
            print('skip %s - no such directory in this worktree' % demo_dir)
            continue
        ncam_dir = os.path.join(demo_dir, 'ncam')
        os.makedirs(ncam_dir, exist_ok=True)
        for target in SYMLINK_TARGETS:
            link = os.path.join(ncam_dir, target)
            dest = os.path.join(path, target)
            if os.path.islink(link) or os.path.exists(link):
                if os.path.islink(link) and os.readlink(link) == dest:
                    print('ok   %s -> %s (already correct)' % (link, dest))
                    continue
                sys.exit('refusing to overwrite existing %s (not the '
                         'expected symlink) - remove it by hand first' % link)
            os.symlink(dest, link)
            print('made %s -> %s' % (link, dest))
    print('\nSymlinks point at THIS worktree\'s own cfg/lib/graphics, not the')
    print('main tree\'s. This has NOT been run through rs274 - see WORKTREES.md.')


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='command', required=True)

    p = sub.add_parser('create', help='create a worktree + branch for one worker')
    p.add_argument('name')
    p.add_argument('--base', default='liveTooling',
                   help='branch/commit to start from (default: liveTooling)')
    p.set_defaults(func=cmd_create)

    p = sub.add_parser('remove', help='remove a worker\'s worktree + branch')
    p.add_argument('name')
    p.add_argument('--keep-branch', action='store_true',
                   help='remove the worktree only, leave the branch (e.g. '
                        'after merging it elsewhere)')
    p.add_argument('--force', action='store_true',
                   help='pass --force to git worktree remove (uncommitted '
                        'changes present) - not the default, on purpose')
    p.set_defaults(func=cmd_remove)

    p = sub.add_parser('list', help='list worktrees (plain git worktree list)')
    p.set_defaults(func=cmd_list)

    p = sub.add_parser('link-sim',
                       help='recreate the ncam/{cfg,lib,graphics} symlink '
                            'farm inside a worktree, pointed at ITS OWN tree')
    p.add_argument('name')
    p.add_argument('--demo', action='append',
                   help='a configs/sim/... demo dir relative to the repo '
                        'root (default: %s)' % ', '.join(SIM_DEMOS))
    p.set_defaults(func=cmd_link_sim)

    args = ap.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
