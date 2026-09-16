#!/usr/bin/env python3
# coding: utf-8
"""Phase 1's own ceiling radius is not re-cut as phase 2 window 0's first
level.

Standalone, like the other test_*.py here - run it directly, no pytest.

THE BUG. `roughing_ladder`'s phase-1 walk ends at `top` (the section
ceiling) - `walk()` appends the level before checking the floor-equality
break, so `top` is p1's own last entry - and every phase-2 window's walk
STARTS at that same `top` (`p2_start = top if top_override is None else
top_override`, fed straight into `lvl_start`). When phase 1 reaches that
ceiling with nothing blocking it - a plain, clean sweep, no boss, no
obstruction - poly_lathe_mill's own `_pl_ph1_front_cut` dedup flag (the one
`analysis/058` added) never gets set, because that flag is only written on
the OBSTRUCTION branch. So window 0 has no way to know phase 1 already cut
that radius, and cuts it again: lead-in, full-length cut, lead-out, retract,
identical to the pass just before it - a whole extra air pass. See
`analysis/210`.

Measured before the fix, on the default (non-NCAM_FLAT) generation path -
the one every user actually gets - `testing_9_6.xml` cut radius X28.262 in
Z0..-49.238 TWICE in a row (moves 13-16 and 17-20 of 182), byte-identical.
Six more projects showed the same shape: testing_9_5, testing_9_6_1,
testing_9_8, testing_10, testing_11, testing_12_0.

THE FIX. `roughing_ladder` now drops the first level of every phase-2
window when it matches phase-1's own last (ceiling) level, within the same
0.002 mm tolerance the function already uses to recognise a truncated
`top_override`. Phase 1 always finishes whatever level it last touches
before handing over (`analysis/058`'s "finish this level before handing
over"), so once phase 1's ladder is non-empty its last radius needs no
second visit from phase 2. This changes ONLY the table `build_level_table_
gcode` emits (and the equivalent `roughing_call_plan` used by the opt-in
flat-rough path) - poly_lathe_mill.ngc is untouched, and the level phase 1
already cut is still cut exactly once, by phase 1.

WHAT IS ASSERTED. For every affected project, no non-degenerate cutting
move (kind 'feed', length > 0.01 mm) appears twice with identical endpoints.
A handful of control projects - already duplicate-free before the fix,
covering the "phase 1 blocked, handed over" case analysis/058 already fixed
- are swept the same way, to prove this fix does not touch what analysis/058
already made correct.

Run with the unfixed `roughing_ladder` (revert the drop in phase-2's walk)
and AFFECTED fails; run with the fix and everything passes - checked by hand
while writing this file, per analysis/210.
"""
import os
import sys
import tempfile
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

INI = os.path.join(HERE, 'configs/sim/axis/ncam_demo/lathe-mm.ini')
GEN = os.path.join(HERE, '.claude/skills/lathe-gcode-verify/scripts/gen_project.py')

# every project the full 46-project sweep found duplicating a full roughing
# pass at the phase-1/phase-2 seam (analysis/210)
AFFECTED = ('testing_9_5.xml', 'testing_9_6.xml', 'testing_9_6_1.xml',
           'testing_9_8.xml', 'testing_10.xml', 'testing_11.xml',
           'testing_12_0.xml')

# already duplicate-free before this fix - the OBSTRUCTION/handover case
# analysis/058 fixed, which this change must leave alone
CONTROL = ('testing_15_5.xml', 'testing_15_6.xml', 'testing_15_blocked.xml')

EPS_LEN = 0.01   # mm - shorter than this is a corner vertex, not a cut

FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name
          + (('  ' + detail) if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def duplicate_cuts(project):
    """[(sig, count)] - every non-degenerate 'feed' move signature that
    appears more than once in this project's generated motion, or None if
    generation failed."""
    import ncam_preview as P
    d = tempfile.mkdtemp(prefix='ceildup_')
    try:
        out = os.path.join(d, 'o.ngc')
        r = subprocess.run([sys.executable, GEN, '--ini', INI, '--project',
                           project, '--out', out, '--config-copy'],
                           capture_output=True, text=True, timeout=300)
        if not os.path.isfile(out):
            print('      NOGEN %s: %s' % (project, (r.stderr or r.stdout)[-200:]))
            return None
        tp = P.parse_program(out, INI)
        if tp.error:
            print('      PARSE ERROR %s: %s' % (project, tp.error))
            return None
        seen = {}
        for m in tp.moves:
            if m.kind != 'feed':
                continue
            length = ((m.b[0] - m.a[0]) ** 2 + (m.b[2] - m.a[2]) ** 2) ** 0.5
            if length < EPS_LEN:
                continue
            key = (m.cat, round(m.a[0], 4), round(m.a[2], 4),
                  round(m.b[0], 4), round(m.b[2], 4))
            seen[key] = seen.get(key, 0) + 1
        return [(k, v) for k, v in seen.items() if v > 1]
    finally:
        import shutil
        shutil.rmtree(d, ignore_errors=True)


def main():
    print('AFFECTED - previously duplicated the phase-1 ceiling level:')
    for pr in AFFECTED:
        dups = duplicate_cuts(pr)
        check('%-24s no duplicate cutting move' % pr,
             dups is not None and len(dups) == 0,
             'still duplicated: %r' % (dups[:3],) if dups else 'NOGEN/parse error')

    print('CONTROL - the analysis/058 handover case, must stay untouched:')
    for pr in CONTROL:
        dups = duplicate_cuts(pr)
        check('%-24s no duplicate cutting move' % pr,
             dups is not None and len(dups) == 0,
             'newly duplicated: %r' % (dups[:3],) if dups else 'NOGEN/parse error')

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('  -', f)
        return 1
    print('ALL PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
