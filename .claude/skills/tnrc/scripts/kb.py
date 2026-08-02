#!/usr/bin/env python3
# coding: utf-8
"""Query the local knowledge packs. No network, no API, no model.

    kb.py                       list the packs and their sections
    kb.py <terms...>            print every section matching all the terms
    kb.py --pack tnrc <terms>   restrict to one pack
    kb.py --list                section headings only

A pack is a gzipped markdown file in ../knowledge/. Sections are '## ' headed
and are printed whole, because half a rule is worse than none.
"""
import argparse
import gzip
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
KNOWLEDGE = os.path.normpath(os.path.join(HERE, '..', 'knowledge'))


def packs():
    """{name: text} for every pack on disk."""
    out = {}
    if not os.path.isdir(KNOWLEDGE):
        return out
    for fn in sorted(os.listdir(KNOWLEDGE)):
        path = os.path.join(KNOWLEDGE, fn)
        try:
            if fn.endswith('.gz'):
                with gzip.open(path, 'rt', encoding='utf-8') as f:
                    out[fn[:-6] if fn.endswith('.md.gz') else fn] = f.read()
            elif fn.endswith('.md'):
                with open(path, encoding='utf-8') as f:
                    out[fn[:-3]] = f.read()
        except (OSError, EOFError) as e:
            print('kb: cannot read %s: %s' % (fn, e), file=sys.stderr)
    return out


def sections(text):
    """[(heading, body)] - the body includes the heading line."""
    out, cur = [], []
    for line in text.splitlines():
        if line.startswith('## '):
            if cur:
                out.append(('\n'.join(cur)))
            cur = [line]
        elif cur:
            cur.append(line)
    if cur:
        out.append('\n'.join(cur))
    return [(s.splitlines()[0][3:].strip(), s) for s in out]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('terms', nargs='*', help='all must appear in a section')
    ap.add_argument('--pack', help='restrict to one pack by name')
    ap.add_argument('--list', action='store_true', help='headings only')
    args = ap.parse_args()

    found = packs()
    if not found:
        print('kb: no packs in %s' % KNOWLEDGE, file=sys.stderr)
        return 1
    if args.pack:
        if args.pack not in found:
            print('kb: no pack %r - have %s'
                  % (args.pack, ', '.join(sorted(found))), file=sys.stderr)
            return 1
        found = {args.pack: found[args.pack]}

    hits = 0
    for name, text in found.items():
        secs = sections(text)
        if args.list or not args.terms:
            print('%s  (%d sections)' % (name, len(secs)))
            for head, _body in secs:
                print('   ', head)
            hits += len(secs)
            continue
        terms = [t.lower() for t in args.terms]
        for head, body in secs:
            low = body.lower()
            if all(t in low for t in terms):
                print('=' * 72)
                print('%s / %s' % (name, head))
                print('=' * 72)
                print(body)
                print()
                hits += 1
    if args.terms and not args.list and not hits:
        print('kb: nothing matches %s. Widen the terms, or research it and add '
              'a section - see SKILL.md.' % ' '.join(args.terms))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
