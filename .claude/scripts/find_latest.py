#!/usr/bin/env python3
"""Deterministically find the newest file matching a glob pattern.

Exists because `ls -t` is a common but unreliable way to do this: it sorts by
mtime at *second* resolution and can silently return a stale file when two
candidates share a timestamp, or when a file was deleted/rewritten between
checks (both were hit debugging this project's own linuxcnc.print.*/debug.*
log pairs and photo/ screenshots - see md_files/LEARNINGS-LOG.md).

Usage:
    find_latest.py '/tmp/linuxcnc.print.*'
    find_latest.py 'photo/*'
    find_latest.py 'photo/*' --n 3     # 3 most recent, newest first
"""
import argparse
import glob
import os
import sys


def find_latest(pattern, n=1):
    matches = glob.glob(pattern)
    if not matches:
        return []
    # os.stat().st_mtime_ns for real sub-second precision, not the string
    # sort ls -t effectively does.
    matches.sort(key=lambda p: os.stat(p).st_mtime_ns, reverse=True)
    return matches[:n]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('pattern', help='glob pattern, quote it so the shell does not expand it first')
    ap.add_argument('--n', type=int, default=1, help='how many results, newest first (default 1)')
    args = ap.parse_args()

    results = find_latest(args.pattern, args.n)
    if not results:
        print(f'No files match: {args.pattern}', file=sys.stderr)
        sys.exit(1)
    for r in results:
        print(r)


if __name__ == '__main__':
    main()
