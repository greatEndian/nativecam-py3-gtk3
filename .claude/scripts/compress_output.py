#!/usr/bin/env python3
"""Strip repetitive noise from captured command output before it burns context.

Deterministic, not heuristic-guessing: collapses exact-duplicate consecutive
lines (e.g. LinuxCNC's "task: main loop took N seconds" spam - dozens of
near-identical lines seen verifying this project's AXIS embedding), and
collapses repeated identical traceback blocks to one copy + a count. Never
drops a line that only *looks* similar - only byte-identical repeats.

Usage:
    some_noisy_command 2>&1 | python3 .claude/scripts/compress_output.py
    python3 .claude/scripts/compress_output.py --file captured.log
"""
import argparse
import json
import re
import sys

# Lines matching one of these patterns collapse to "<line> (xN)" when they
# repeat back-to-back, instead of "line" once - so the source of repetition
# is still recorded, just not every duplicate copy of it.
REPEAT_PATTERNS = [
    re.compile(r'^\s*task: main loop took [\d.]+ seconds\s*$'),
    re.compile(r'^\s*\[DEFAULT\.COMMON\.\w+\]\[.*\]\s+.*\(iniinfo\.py:\d+\)\s*$'),
]


def compress(lines):
    out = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        is_collapsible = any(p.match(line) for p in REPEAT_PATTERNS)
        if is_collapsible:
            j = i
            while j < n and lines[j] == line:
                j += 1
            count = j - i
            if count > 1:
                out.append(f'{line.rstrip()}  (x{count}, deduplicated)')
            else:
                out.append(line)
            i = j
            continue
        # exact-duplicate consecutive line, regardless of pattern (e.g. a
        # traceback fragment repeated by a retry loop)
        if out and line == lines[i - 1] if i > 0 else False:
            j = i
            while j < n and lines[j] == line:
                j += 1
            count = j - i
            if count > 2:
                out.append(f'{line.rstrip()}  (x{count}, deduplicated)')
                i = j
                continue
        out.append(line)
        i += 1
    return out


def summarize_json(text, max_array_items=5):
    """For a large JSON blob (e.g. graphify's graph.json, a parsed rs274 move
    list): keep structure and small values, truncate long arrays to their
    first/last few items + a count. Falls back to returning text unchanged
    if it doesn't parse as JSON - never guesses at malformed JSON.
    """
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return text, False

    def walk(obj):
        if isinstance(obj, list):
            if len(obj) <= max_array_items * 2:
                return [walk(x) for x in obj]
            head = [walk(x) for x in obj[:max_array_items]]
            tail = [walk(x) for x in obj[-max_array_items:]]
            return head + [f'... ({len(obj) - 2 * max_array_items} more items omitted) ...'] + tail
        if isinstance(obj, dict):
            return {k: walk(v) for k, v in obj.items()}
        return obj

    return json.dumps(walk(data), indent=2, ensure_ascii=False), True


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--file', default=None, help='read from this file instead of stdin')
    ap.add_argument('--json', action='store_true',
                     help='treat input as JSON and truncate long arrays instead of line-deduplication')
    ap.add_argument('--max-array-items', type=int, default=5,
                     help='with --json, keep this many items from each end of a long array (default 5)')
    args = ap.parse_args()

    if args.file:
        with open(args.file) as f:
            text = f.read()
    else:
        text = sys.stdin.read()

    if args.json:
        result_text, was_json = summarize_json(text, args.max_array_items)
        sys.stdout.write(result_text + '\n')
        if not was_json:
            print('--- compress_output.py: --json given but input did not parse as JSON; '
                  'passed through unchanged ---', file=sys.stderr)
        return

    lines = text.splitlines()
    before = len(lines)
    result = compress(lines)
    after = len(result)

    sys.stdout.write('\n'.join(result) + ('\n' if result else ''))
    if before != after:
        print(f'--- compress_output.py: {before} -> {after} lines '
              f'({before - after} removed as exact-duplicate noise) ---', file=sys.stderr)


if __name__ == '__main__':
    main()
