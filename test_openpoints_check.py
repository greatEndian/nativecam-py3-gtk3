#!/usr/bin/env python3
# coding: utf-8
"""Each of openpoints_check's checks fails on the bug it exists for.

Standalone, like the other test_*.py here - run it directly, no pytest.

`test_cam_map.py`'s own convention, applied to this checker: a check that
cannot fail proves nothing. Every case here is a REAL bug this project
actually had, read from git history or the live file rather than invented -
`analysis/190` and `analysis/240` are the answer key.

  C1  the front-angle entry, `f610fbd:openPoints.md` (before `ce28d71`'s
      reconciliation): "FIXED 2026-08-24, `analysis/064`" sitting in an
      unticked entry's own body, 842 characters in - the founding case this
      whole checker exists for.
  C1  the negative control: the SAME historical snapshot's genuinely-open
      entries must not fire, and neither must the three real "closure word,
      but not really closed" entries analysis/190 had to reason through by
      hand (PARTLY DONE, DECIDED-not-yet-executed, a diagnosis CONFIRMED).
  C2  a fabricated entry citing an analysis file that does not exist.
  C3  the real, still-open "Simulation" cluster in the CURRENT file -
      `Accuracy` slider now matches `accuracy_divisor` in
      ncam_preview_ui.py, wired by `24c0b80` with `test_preview_wiring.py`
      passing.
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
FAILED = []

import openpoints_check as oc                    # noqa: E402


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name
          + (('  ' + detail) if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def git_show(rev, path):
    return subprocess.check_output(['git', 'show', '%s:%s' % (rev, path)],
                                    cwd=HERE).decode()


def main():
    # ------------------------------------------------------------------
    # C1 - the founding historical case, read from git, not reconstructed
    # ------------------------------------------------------------------
    try:
        stale = git_show('f610fbd', 'openPoints.md')
    except subprocess.CalledProcessError:
        print('SKIP  f610fbd not reachable in this checkout - git history '
              'trimmed?')
        stale = None

    if stale is not None:
        findings, hints, unverified = oc.check_all(stale)
        titles = [t for _l, t, _d in findings]
        check('C1 catches the founding case: FRONT ANGLE, unticked with '
              "FIXED + analysis/064 in its own body",
              any('FRONT ANGLE' in t for t in titles),
              'findings: %s' % titles[:6])

        # NEGATIVE CONTROL, same real snapshot: the three entries
        # analysis/190 had to reason through BY HAND because a naive
        # "contains a closure word" rule would have wrongly flagged them.
        # If C1 fires on any of these, it is not a gate, it is a coin flip
        # that happened to land right on the one case above.
        flagged_lines = set(l for l, _t, _d in findings)
        pd = next((l for l, t, _d in oc.check_all(stale)[0]
                  if 'PARTLY DONE' in t), None)
        check('C1 does not fire on "PARTLY DONE" (analysis/190\'s own '
              'hard case #1)', pd is None, 'got line %s' % pd)

        all_entries = oc.entries(stale)
        # The DECIDED wording is my own analysis/220 phrasing, introduced in
        # ce28d71 (the reconciliation commit) - it does not exist yet at
        # f610fbd, ce28d71's own parent. Read the current file for it
        # instead; the case itself (a real, still-open entry) is live today.
        current_entries = oc.entries(oc._read(oc.OPENPOINTS))
        decided_body = next((b for _s, _i, b in current_entries
                             if 'DECIDED, NOT A CALL ANY MORE' in b), None)
        check('setup: the DECIDED case exists in the current file',
              decided_body is not None)
        if decided_body:
            check('C1 does not fire on "DECIDED, NOT A CALL ANY MORE" '
                  "(analysis/190's hard case #2 - a question answered, not "
                  'work done)',
                  not any(w == 'DECIDED' for w, _ok
                          in oc.c1_closure_words(decided_body)),
                  'DECIDED must not even be in CLOSURE_WORDS')

        confirmed_body = next((b for _s, _i, b in all_entries
                               if 'the remaining reading is COMPENSATION'
                               in b), None)
        check('setup: the bare-CONFIRMED case exists in this snapshot',
              confirmed_body is not None)
        if confirmed_body:
            verified = [w for w, ok in oc.c1_closure_words(confirmed_body)
                        if ok]
            check('C1 does not report a FINDING for the bare "CONFIRMED by '
                  'greatEndian" (no date/analysis/NNN nearby - '
                  "analysis/190's hard case #3)",
                  'CONFIRMED' not in verified, 'verified=%s' % verified)

        # every genuinely-open entry in this historical file, not just the
        # three hard cases, must not appear in `findings` - the broadest
        # negative control this checker can run
        open_titles_flagged = [t for l, t, _d in findings
                               if 'FRONT ANGLE' not in t
                               and 'PHASE-1 HANDOVER' not in t]
        check('C1 flags nothing else in the historical snapshot besides '
              'the two real stale entries', not open_titles_flagged,
              'unexpected: %s' % open_titles_flagged)

    # ------------------------------------------------------------------
    # C2 - a fabricated entry citing a missing analysis file
    # ------------------------------------------------------------------
    fake = ('# Open points\n\n'
            '- [ ] **FIXED 2026-01-01, `analysis/999999`.** A made-up entry '
            'citing an analysis file that cannot exist, to prove C2 fires.\n')
    findings, _hints, _unverified = oc.check_all(fake)
    check('C2 catches a citation to an analysis/NNN with no file on disk',
          any('999999' in d for _l, _t, d in findings),
          'findings: %s' % findings)

    # NEGATIVE CONTROL for C2: the same shape, citing a REAL analysis file.
    # Every real citation in openPoints.md is 3 digits, zero-padded, matching
    # the files on disk (checked: the shortest digit run cited anywhere in
    # the real file is 3) - so the realistic control uses that same shape
    # rather than a bare "analysis/1" nobody would actually write.
    real_num = sorted(
        m.group(1) for f in os.listdir(os.path.join(HERE, 'analysis'))
        for m in [re.match(r'(\d{3})-', f)] if m)[0]
    fake_ok = ('# Open points\n\n'
              '- [ ] **FIXED 2026-01-01, `analysis/%s`.** Cites a real '
              'analysis file, so C2 must stay quiet about the citation '
              '(C1 will still fire - that is a different check).\n'
              % real_num)
    findings, _hints, _unverified = oc.check_all(fake_ok)
    check('C2 does not fire when the cited analysis file exists',
          not any('does not exist' in d for _l, _t, d in findings),
          'findings: %s' % findings)

    # ------------------------------------------------------------------
    # C3 - the real "Simulation" cluster, frozen at the commit before this
    # checker's own fix ticked it (analysis/240) - reading the LIVE file
    # here would make this test decay the exact way openPoints.md itself
    # does the moment the entry it is about gets fixed, which is precisely
    # what happened the first time this was written against oc.check_all()
    # with no argument.
    # ------------------------------------------------------------------
    try:
        pre_fix = git_show('30dc1f4', 'openPoints.md')
    except subprocess.CalledProcessError:
        print('SKIP  30dc1f4 not reachable in this checkout - git history '
              'trimmed?')
        pre_fix = None

    if pre_fix is not None:
        findings, hints, unverified = oc.check_all(pre_fix)
        hint_titles = [t for _l, t, _d in hints]
        check('C3 catches the real, still-open (at 30dc1f4) Accuracy '
              'slider entry (wired by 24c0b80, test_preview_wiring.py '
              'passing)',
              any('Accuracy' in t for t in hint_titles),
              'hints: %s' % hint_titles)

        acc = next((d for _l, t, d in hints if 'Accuracy' in t), '')
        check('C3 names real evidence for it (a file:line in '
              'ncam_preview_ui.py)',
              'ncam_preview_ui.py' in acc, acc)
        check('C3 surfaces its open siblings under the same heading (the '
              'lesson analysis/240 exists to encode - staleness clusters)',
              'other open entr' in acc, acc)

    # NEGATIVE CONTROL for C3: a backtick term with no matching declaration
    # anywhere must not hint
    no_match = ('# Open points\n\n'
               '- [ ] **`Zqxvthklmnop` toggle (not built).**\n')
    _findings, hints, _unverified = oc.check_all(no_match)
    check('C3 stays quiet on a made-up term matching nothing in the tree',
          not hints, 'hints: %s' % hints)

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('Every check fires on the bug it exists for, and only on that.')


if __name__ == '__main__':
    main()
