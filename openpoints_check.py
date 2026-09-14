#!/usr/bin/env python3
# coding: utf-8
"""openPoints.md decays fast - proven twice in two days. `analysis/190`
(2026-09-13) found six entries already done but still `- [ ]`, one of them
recommended as the next piece of work that same day. One day later,
`analysis/240` found six MORE - the whole "Simulation" preview section -
stale the same way, closed by `24c0b80` with `test_preview_wiring.py`
passing. A reconciliation done by hand decays within a single round of
work; this project's answer to that shape of problem is a checker,
`cam_map.py`'s idiom - each check exists because it would have caught a
staleness this file actually had, proven by a test per check.

    python3 openpoints_check.py     # run the checks against openPoints.md

Exits 1 when there is a HIGH-CONFIDENCE finding (something this file is
fairly sure is wrong) - not on a hint, which needs a human's ten seconds
regardless of exit code.

WHAT THIS DOES NOT DO: decide FOR anyone whether a flagged entry really is
stale. `analysis/190`'s own hardest cases - PARTLY DONE, DECIDED-but-not-yet-
executed, a diagnosis CONFIRMED without the fix being done - all use a
closure word without the entry being closeable, and a checker that ticked on
the word alone would be wrong exactly where care matters most. This prints
evidence; a human (or the same agent, immediately after) reads the entry and
decides.
"""
import glob
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OPENPOINTS = os.path.join(HERE, 'openPoints.md')
ANALYSIS_DIR = os.path.join(HERE, 'analysis')

# Emphatic, ALL-CAPS closure words this file's own convention uses to state a
# verdict - "FIXED 2026-08-24", "DONE 2026-09-02, analysis/072", "CLOSED, not
# a defect". Deliberately word-bounded and case-sensitive: this project's
# closure verdicts are always shouted in caps, and matching lower-case
# "fixed" would also hit ordinary prose ("the bug fixed itself into a
# pattern") that says nothing about entry status.
CLOSURE_WORDS = ('FIXED', 'DONE', 'CLOSED', 'RESOLVED', 'SETTLED', 'RULED',
                  'CONFIRMED')
# "DECIDED" is deliberately NOT in this list. It means a QUESTION was
# answered, not that the underlying work is done - `analysis/240` found a
# real entry, "DECIDED, NOT A CALL ANY MORE - the holder model is BUILT and
# measured", that is correctly still open (a real-machine test is still
# pending) despite using the word as its very first one.

# Words appearing in the 30 characters before a closure word that negate it -
# "NOT FIXED", "never DONE", "cannot be RULED out", "PARTLY DONE". Checked on
# the lower-cased window since the negator itself is not reliably capitalised
# the same way as the closure word it precedes.
NEGATORS = ('not ', 'never ', 'no longer', 'cannot', "isn't", 'nobody has',
            'awaiting', 'is a real one', 'partly')

# A genuine verdict in this file's own convention names ITS OWN evidence
# right next to the word - "FIXED 2026-08-24, `analysis/064`", "DONE
# 2026-09-02, `analysis/072`". A closure word with no date or analysis/NNN
# anywhere near it is far more likely describing a STEP along the way (a
# diagnosis confirmed, a sub-question settled) than the entry's own final
# status - `analysis/240` found exactly this on a real entry, "CONFIRMED by
# greatEndian: it is the tool tip nose radius", with no date or analysis
# reference anywhere close to it. An early-in-the-body cutoff was tried
# first and rejected: the founding case itself, "FIXED 2026-08-24,
# `analysis/064`", sits 842 characters into its entry, well past any
# reasonable "near the title" cutoff - proximity to the word, not to the
# start of the entry, is the real signal.
CLOSURE_EVIDENCE_WINDOW = 100
CLOSURE_EVIDENCE_RE = re.compile(r'\d{4}-\d{2}-\d{2}|analysis/\d+')

STOPWORDS = {
    'a', 'an', 'the', 'on', 'in', 'at', 'of', 'is', 'are', 'to', 'for', 'as',
    'with', 'currently', 'always', 'it', 'and', 'or', 'this', 'that', 'from',
    'by', 'over', 'under', 'not', 'no', 'toggle', 'option', 'slider',
}

# Marker words too generic to search the whole tree for without flooding on
# unrelated hits - found empirically, by running C3 against every entry in
# the real file and reading what came back. Listed rather than silently
# excluded, so a real future collision is at least visible in the code.
TOO_GENERIC = {'point', 'value', 'table', 'window', 'level', 'level',
               'section', 'range', 'contour', 'bound', 'entry'}


def _read(path):
    with open(path) as fh:
        return fh.read()


def entries(text):
    """[(state, line0, body)] for every TOP-LEVEL `- [ ]`/`[x]`/`[~]` entry.

    `body` runs from the entry's own line to the line before the next
    top-level entry or the next heading, whichever comes first - nested
    sub-items are part of the parent's body (a stale sub-claim is still a
    stale claim), but a `##` section boundary is never crossed.
    """
    lines = text.split('\n')
    starts = [i for i, ln in enumerate(lines) if re.match(r'^- \[([ x~])\]', ln)]
    out = []
    for si, i in enumerate(starts):
        state = re.match(r'^- \[([ x~])\]', lines[i]).group(1)
        end = starts[si + 1] if si + 1 < len(starts) else len(lines)
        for j in range(i + 1, end):
            if lines[j].startswith('#'):
                end = j
                break
        out.append((state, i, '\n'.join(lines[i:end])))
    return out


def c1_closure_words(body):
    """[(word, has_nearby_evidence)] for every UNNEGATED ALL-CAPS closure
    word in the body. "Nearby evidence" is a date or an analysis/NNN within
    CLOSURE_EVIDENCE_WINDOW characters AFTER the word - see the comment
    above CLOSURE_EVIDENCE_WINDOW for why proximity to the WORD, not to the
    start of the entry, is what distinguishes a real verdict from a step
    along the way.
    """
    hits = []
    for m in re.finditer(r'\b(' + '|'.join(CLOSURE_WORDS) + r')\b', body):
        before = body[max(0, m.start() - 30):m.start()].lower()
        if any(neg in before for neg in NEGATORS):
            continue
        after = body[m.end():m.end() + CLOSURE_EVIDENCE_WINDOW]
        hits.append((m.group(1), bool(CLOSURE_EVIDENCE_RE.search(after))))
    return hits


def c2_missing_analysis(body):
    """An analysis/NNN this entry cites that has no file on disk."""
    missing = []
    for num in set(re.findall(r'analysis/(\d+)', body)):
        if not glob.glob(os.path.join(ANALYSIS_DIR, '%s-*.md' % num)) \
                and not glob.glob(os.path.join(ANALYSIS_DIR, '%s.md' % num)):
            missing.append(num)
    return sorted(missing, key=int)


_SRC_FILES = None


def _source_files():
    """Non-test .py source - excludes test_*.py (a test asserting the very
    fix must not be read as confirming itself) and this checker's own file.
    """
    global _SRC_FILES
    if _SRC_FILES is None:
        _SRC_FILES = sorted(
            f for f in glob.glob(os.path.join(HERE, '*.py'))
            if not os.path.basename(f).startswith('test_')
            and os.path.basename(f) != 'openpoints_check.py')
    return _SRC_FILES


def _grep_identifier(marker):
    """First `def`/assignment site whose identifier contains `marker`, or
    None. A bare mention (the word appearing in a comment or a call site)
    is not enough - this asks for the word to be part of something actually
    DECLARED, which is what "the implementing code now exists" means.
    """
    word = re.compile(r'\b\w*%s\w*\b' % re.escape(marker), re.IGNORECASE)
    decl = re.compile(
        r'(def\s+\w*%s\w*\s*\(|\bself\.\w*%s\w*\s*=|^\s*\w*%s\w*\s*='
        r'|,\s*\w*%s\w*\s*=)' % ((re.escape(marker),) * 4), re.IGNORECASE)
    for path in _source_files():
        for i, line in enumerate(_read(path).splitlines(), 1):
            if re.match(r'^\s*#', line):
                continue
            if word.search(line) and decl.search(line):
                return '%s:%d' % (os.path.relpath(path, HERE), i)
    return None


def c3_symbol_hint(body):
    """A backtick-quoted UI/feature name whose most distinctive word is now
    part of a declared Python identifier - a HINT, not a finding. Word
    overlap is not proof the same feature is wired; it is exactly the class
    of evidence `analysis/240`'s preview case needed a human to confirm in
    ten seconds, which is what this hands over.
    """
    hits = []
    for term in set(re.findall(r'`([A-Za-z][A-Za-z0-9_. ]{2,40})`', body)):
        if '.' in term or '_' in term:
            continue  # already a real dotted/qualified symbol, not UI prose
        words = [w.lower() for w in re.split(r'\s+', term)
                 if w.lower() not in STOPWORDS]
        if not words:
            continue
        marker = max(words, key=len)
        if len(marker) < 6 or marker in TOO_GENERIC:
            continue
        found = _grep_identifier(marker)
        if found:
            hits.append((term, marker, found))
    return hits


def _section_siblings(text):
    """{line0 of a `- [ ]` entry: [line0, ...] of every OTHER unticked
    top-level entry under the same `##` heading}.

    Not a check of its own - a durable record of the actual lesson
    `analysis/240` found: staleness clustered, six entries under one
    heading ("Simulation - paused at your word") stale for the identical
    reason. C1/C2/C3 each look at one entry in isolation and, on that
    section, only ever caught 2 of the 5 open ones on their own evidence.
    Whenever any check fires, the other open entries sharing its heading are
    worth the same ten seconds even with no evidence of their own yet.
    """
    lines = text.split('\n')
    heading_of = {}
    current = None
    open_by_heading = {}
    for i, ln in enumerate(lines):
        if ln.startswith('#'):
            current = ln
            continue
        if re.match(r'^- \[ \]', ln):
            heading_of[i] = current
            open_by_heading.setdefault(current, []).append(i)
    return {i: [j for j in open_by_heading.get(h, []) if j != i]
            for i, h in heading_of.items()}


def check_all(text=None):
    """(findings, hints, unverified) - each a list of (line, title, detail)."""
    text = text if text is not None else _read(OPENPOINTS)
    siblings = _section_siblings(text)
    findings, hints, unverified = [], [], []
    for state, i, body in entries(text):
        if state != ' ':
            continue
        line = i + 1
        title = body.split('\n', 1)[0][:90].lstrip('- [ ]').strip()
        closures = c1_closure_words(body)
        missing = c2_missing_analysis(body)
        verified = sorted(set(w for w, ok in closures if ok))
        bare = sorted(set(w for w, ok in closures if not ok) - set(verified))
        if verified:
            findings.append((line, title,
                             'closure word(s) %s, each naming a date or an '
                             'analysis/NNN close by' % ', '.join(verified)))
        if bare:
            unverified.append((line, title,
                               'closure word(s) %s with no date or '
                               'analysis/NNN nearby - a finding, not grounds '
                               'to tick anything' % ', '.join(bare)))
        if missing:
            findings.append((line, title,
                             'cites analysis/%s, which does not exist on disk'
                             % ', '.join(missing)))
        for term, marker, found in c3_symbol_hint(body):
            detail = ('`%s` (marker "%s") matches a declaration at %s'
                      % (term, marker, found))
            sibs = siblings.get(i, [])
            if sibs:
                detail += ('; %d other open entr%s share its heading, worth '
                          'the same look: line%s %s'
                          % (len(sibs), 'y' if len(sibs) == 1 else 'ies',
                             '' if len(sibs) == 1 else 's',
                             ', '.join(str(j + 1) for j in sibs)))
            hints.append((line, title, detail))
    return findings, hints, unverified


def main():
    findings, hints, unverified = check_all()
    print('%d line%s in openPoints.md' % (
        len(_read(OPENPOINTS).splitlines()), ''))
    print()
    print('HIGH-CONFIDENCE FINDINGS (%d) - own-body evidence already says '
          'this is done, or cites a missing analysis file:' % len(findings))
    for line, title, detail in findings:
        print('  L%-5d %s' % (line, title))
        print('         %s' % detail)
    print()
    print('UNVERIFIED CLOSURE CLAIMS (%d) - a closure word with nothing '
          'behind it; per analysis/190 this is a FINDING, not grounds to '
          'tick anything:' % len(unverified))
    for line, title, detail in unverified:
        print('  L%-5d %s' % (line, title))
        print('         %s' % detail)
    print()
    print('HINTS (%d) - a named UI/feature term now matches a real code '
          'declaration; word overlap only, confirm before acting:'
          % len(hints))
    for line, title, detail in hints:
        print('  L%-5d %s' % (line, title))
        print('         %s' % detail)
    print()
    if findings:
        print('FINDINGS: %d entr%s worth a human look before the next '
              'reconciliation.' % (len(findings), 'y' if len(findings) == 1
                                    else 'ies'))
        sys.exit(1)
    print('No high-confidence staleness found.')


if __name__ == '__main__':
    main()
