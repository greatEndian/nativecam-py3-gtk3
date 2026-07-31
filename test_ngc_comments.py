#!/usr/bin/env python3
# coding: utf-8
"""Checks every lib/**/*.ngc and cfg/**/*.cfg for the comment rules that make
rs274 stop mid-file with no error message.

Standalone, like the other test_*.py here - run it directly, no pytest.

These two rules are in CLAUDE.md because they have each cost real debugging
time, and both fail the same silent way: the interpreter stops at that line and
everything after it simply never runs. The canon output just ends. There is no
diagnostic, so the symptom is "my change did nothing" or, worse, a program that
looks like it completed because the tail was comments anyway.

  1. NESTED PARENS - `(from (a, b) to (c, d))`. The comment closes at the first
     inner `)`, and the rest of the line becomes garbage G-code.
  2. UNCLOSED COMMENT - a `(` with no `)` on the same line. A bare `(` used as a
     blank separator in a header block does this.

Both were introduced in one sitting while writing tip_comp_vec.ngc and taper.ngc
and killed EVERY mode of the OD taper, native included - so this runs over the
whole tree, not just changed files.

A `;` inside a parenthetical comment is NOT flagged. It looks suspicious, and I
removed one on that suspicion, but this lint found the same pattern in a dozen
long-working subs - facing.ngc, fillet_lead.ngc, lathe_level_pass.ngc - so
LinuxCNC plainly treats it as comment text. A rule that fails on working code is
a worse rule than none.
"""
import glob
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FAILED = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name + (('  ' + detail) if detail else ''))
    if not cond:
        FAILED.append(name)


# A .cfg is an INI file, and only some of its sections are G-code templates.
# Its tool_tip/help/name values are prose shown in the GUI and contain parens
# freely - scanning those reported 60-odd false hits on untouched files, which
# would have made this lint useless noise on day one.
GCODE_SECTIONS = ('[CALL]', '[BEFORE]', '[AFTER]', '[DEFINITIONS]')

# <eval>/<exec>/<subprocess> hold PYTHON, evaluated at generation time and
# replaced before any of this reaches the interpreter. Python nests parens as a
# matter of course, so scanning inside them reported 29 hits on files that have
# always worked.
PY_OPEN = ('<eval>', '<exec>', '<subprocess>')
PY_CLOSE = ('</eval>', '</exec>', '</subprocess>')


def gcode_lines(path):
    """(line number, text) for the lines of this file that become G-code."""
    with open(path, errors='replace') as f:
        lines = f.read().split('\n')
    if path.endswith('.ngc'):
        return list(enumerate(lines, 1))
    out, active, in_py = [], False, False
    for n, line in enumerate(lines, 1):
        st = line.strip()
        if st.startswith('[') and st.endswith(']'):
            active = st in GCODE_SECTIONS
            continue
        opened = any(t in line for t in PY_OPEN)
        closed = any(t in line for t in PY_CLOSE)
        if in_py:
            if closed:
                in_py = False
            continue
        if opened and not closed:
            in_py = True
            continue
        if opened and closed:
            continue          # a one-line <eval>...</eval>
        if active:
            out.append((n, line))
    return out


def scan(path):
    """(nested, unclosed, semicolon) problem lines in one file."""
    nested, unclosed, semi = [], [], []
    for n, line in gcode_lines(path):
        depth = 0
        in_comment = False
        is_nested = False
        for ch in line:
            if ch == ';' and not in_comment:
                # a semicolon outside parens comments out the REST of the line,
                # so parens after it are prose. optimize.ngc has a commented-out
                # formula full of nested parens that is perfectly legal
                break
            if ch == '(':
                depth += 1
                if depth == 2:
                    nested.append((n, line.rstrip()))
                    is_nested = True
                    break
                in_comment = True
            elif ch == ')':
                depth = max(0, depth - 1)
                if depth == 0:
                    in_comment = False
            elif ch == ';' and in_comment:
                semi.append((n, line.rstrip()))
        # a nested line is already reported; the depth it leaves behind is an
        # artefact of stopping at the nest, not a second defect
        if depth > 0 and '(' in line and not is_nested:
            unclosed.append((n, line.rstrip()))
    return nested, unclosed, semi


def _generate_one():
    """A real generated .ngc, or None when the demo config is absent."""
    import shutil
    import subprocess
    import tempfile
    ini = os.path.join(HERE, 'configs', 'sim', 'axis', 'ncam_demo',
                       'lathe-mm.ini')
    gen = os.path.join(HERE, '.claude', 'skills', 'lathe-gcode-verify',
                       'scripts', 'gen_project.py')
    if not (os.path.isfile(ini) and os.path.isfile(gen)):
        return None
    out = os.path.join(tempfile.mkdtemp(prefix='ngc_lint_'), 'gen.ngc')
    # a project that exercises the flank shadow, so the generated-only
    # comments around the reachable contour are actually emitted
    r = subprocess.run([sys.executable, gen, '--ini', ini, '--project',
                        'testing_15_2.xml', '--out', out, '--config-copy'],
                       capture_output=True, text=True)
    del shutil
    return out if (r.returncode == 0 and os.path.isfile(out)) else None


def main():
    files = []
    for pat in ('lib/**/*.ngc', 'cfg/**/*.cfg'):
        files += glob.glob(os.path.join(HERE, pat), recursive=True)
    files.sort()
    check('there are files to scan at all', len(files) > 20,
          '%d found - a 0 here would make every check below pass vacuously'
          % len(files))

    all_nested, all_unclosed, all_semi = [], [], []
    for p in files:
        nested, unclosed, semi = scan(p)
        rel = os.path.relpath(p, HERE)
        all_nested += [(rel, n, t) for n, t in nested]
        all_unclosed += [(rel, n, t) for n, t in unclosed]
        all_semi += [(rel, n, t) for n, t in semi]

    def report(label, hits):
        check(label, not hits, '%d line(s)' % len(hits))
        for rel, n, t in hits[:12]:
            print('        %s:%d  %s' % (rel, n, t.strip()[:88]))

    report('no comment contains a nested paren', all_nested)
    report('no comment is left unclosed on its line', all_unclosed)
    check('semicolons inside comments are not treated as an error',
          True, '%d present across the tree, all in long-working subs' % len(all_semi))

    # the lint has to be able to fail, or it is decoration
    import tempfile
    with tempfile.NamedTemporaryFile('w', suffix='.ngc', delete=False) as f:
        f.write('(outer (inner) tail)\n(unclosed comment\nG0 X1\n(fine)\n')
        tmp = f.name
    nested, unclosed, _semi = scan(tmp)
    os.unlink(tmp)
    check('the lint detects a planted nested paren', len(nested) == 1, str(nested))
    check('the lint detects a planted unclosed comment', len(unclosed) == 1,
          str(unclosed))
    # and it must not fire on a .cfg tooltip, which is prose and not G-code
    with tempfile.NamedTemporaryFile('w', suffix='.cfg', delete=False) as f:
        f.write('[PARAM_X]\ntool_tip = _("a (parenthetical) aside; and a semicolon")\n'
                '[CALL]\ncontent =\n\t(a clean comment)\n')
        tmp2 = f.name
    n2, u2, _s2 = scan(tmp2)
    os.unlink(tmp2)
    check('the lint ignores cfg prose outside the G-code sections',
          not n2 and not u2, str(n2 + u2))
    # embedded Python is not G-code and nests parens freely
    with tempfile.NamedTemporaryFile('w', suffix='.cfg', delete=False) as f:
        f.write('[AFTER]\ncontent =\n\t<exec>\n\tprint(fn(a, (b, c)))\n\t</exec>\n')
        tmp3 = f.name
    n3, u3, _s3 = scan(tmp3)
    os.unlink(tmp3)
    check('the lint ignores Python inside exec/eval blocks', not n3 and not u3,
          str(n3 + u3))

    # --- the GENERATED file, not just the sources -------------------------
    # Comments composed at generation time from Python strings never appear in
    # lib/ or cfg/, so nothing above can see them. One such string shipped with
    # two unclosed comments and stopped rs274 dead: the file generated fine,
    # rs274 reported no error, and the toolpath simply ended - 220 moves became
    # 14. Linting the output is the only place that catches it.
    gen = _generate_one()
    if gen is None:
        print('SKIP  no demo config to generate from')
    else:
        nested, unclosed, _semi = scan(gen)
        check('the generated G-code has no nested-paren comment', not nested,
              str(nested[:3]))
        check('the generated G-code has no unclosed comment', not unclosed,
              str(unclosed[:3]))

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('Scanned %d files. All G-code comment rules hold.' % len(files))


if __name__ == '__main__':
    main()
