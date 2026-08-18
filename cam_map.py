#!/usr/bin/env python3
# coding: utf-8
"""What touches what across cfg, Python and O-code — mapped, and checked.

    python3 cam_map.py            # run the static checks, exit 1 on failure
    python3 cam_map.py --map      # write CAM-MAP.md as well

greatEndian, 2026-08-09: *"learn the active CAM framework what touches what and
which change will introduce dependency"*.

WHY THIS EXISTS. `graphify` maps the Python and does it well, but this system's
hard part is not Python: it is the chain from a `.cfg` parameter, through a
Python builder, into a numbered-parameter window, out to an `.ngc` subroutine
that walks it. Nothing could see that chain, so every change was scoped from
memory - and the anisotropic stock to leave took four rounds, each miss a link
in it:

  1. three of four consumers wired; roughing's scan is a scalar and was missed
  2. that scan fixed - and nothing changed, because a SECOND walk sets the cut
     target with multi-crossing on, and it wins
  3. the table built from the reachable contour instead of the raw record
     array, silently costing nine roughing levels
  4. 226 slots needed where 200 were free: a WARNING comment, a silent
     fallback, everything still running

THE MAP IS USEFUL; THE CHECKS ARE THE POINT. Each one is here because it would
have caught a bug this project actually had, and each is proved by a known-bad
case in `test_cam_map.py` - a check that cannot fail proves nothing.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, 'lib')
CFG = os.path.join(HERE, 'cfg')

# Windows whose base is written into the .ngc as a LITERAL rather than reached
# through an emitted `#<_pl_*_base>`. Those are the fragile ones - the floor
# table moved 3300 -> 3380 in Python twice while poly_lathe_mill kept reading
# 3300 - so they are named here and checked against lathe_sections' own
# constants.
LITERAL_WINDOWS = {
    'LVLSPLIT_BASE': 3160,
    'ERAMP_BASE': 3200,
    'SECT_FLOOR_BASE': 3380,
    'SECT_BASE': 3400,
}


# Names in an `order =` line with no [PARAM_*] behind them, found on the first
# run of this checker and left alone: plasma is not the active work and these
# predate it. Listed rather than ignored so a NEW one still fails.
ORDER_KNOWN = (
    set(('cfg/plasma/circle.cfg', n) for n in
        ('s', 'u_s', 'ugc', 'dpt', 'u_dpt', 'ugcd', 'h4', 'fp', 'fc'))
    | {('cfg/mill/sel-reamer.cfg', 'h3'),
       ('cfg/mill/taper-hole.cfg', 'h1'),
       # the section is [PARAM_CUT_TEETH]; the order line still says the old
       # name, so that parameter does not appear in the tree
       ('cfg/mill/sel-thread-mill.cfg', 'teeth')})


def _code(line):
    """The executable part of an .ngc line.

    Both comment forms have to go: `(...)` and a leading `;`. Missing the
    second reported `o<parallel>` as an undefined subroutine on the first run -
    every call to it in lib/ is commented out with a semicolon.
    """
    return line.split('(')[0].split(';')[0]


def _read(path):
    with open(path) as fh:
        return fh.read()


def _walk(root, ext):
    for base, _dirs, files in os.walk(root):
        for f in sorted(files):
            if f.endswith(ext):
                yield os.path.join(base, f)


# --------------------------------------------------------------------------
# extraction
# --------------------------------------------------------------------------

def windows():
    """The parameter-window constants lathe_sections declares, as name -> value."""
    src = _read(os.path.join(HERE, 'lathe_sections.py'))
    out = {}
    for m in re.finditer(r'^([A-Z][A-Z_]*(?:BASE|TOP)) = (\d+)$', src, re.M):
        out[m.group(1)] = int(m.group(2))
    return out


def ngc_literals():
    """Numbered-parameter literals in lib/**.ngc, as (file, line, value).

    Only 3160-4999: below that is the record array, the resume envelope and
    cfg/lathe/polyline.cfg's own CALL scratch at #3141-#3159; above it is
    LinuxCNC's own space.
    """
    out = []
    for path in _walk(LIB, '.ngc'):
        for i, line in enumerate(_read(path).splitlines(), 1):
            code = _code(line)
            for m in re.finditer(r'#\[?\s*(31[6-9]\d|3[2-9]\d\d|4\d\d\d)\b', code):
                out.append((os.path.relpath(path, HERE), i, int(m.group(1))))
    return out


def cfg_scratch():
    """Numbered parameters the .cfg files ASSIGN, as (file, line, value).

    The cfgs stage a feature's CALL arguments in plain numbered parameters -
    `#3141 = #<_pl_rgh_hi_r>` and the rest of #3141-#3159 in
    cfg/lathe/polyline.cfg. That block sits BETWEEN two declared windows, so
    nothing in the overlap check could see it, and a new table placed in "the
    gap at 3140" would have silently overwritten the polyline's own arguments.
    Caught while placing the level-split table; declared here so it cannot
    happen twice.
    """
    out = []
    for path in _walk(CFG, '.cfg'):
        for i, line in enumerate(_read(path).splitlines(), 1):
            m = re.match(r'\s*#(\d{4})\s*=', line)
            if m:
                out.append((os.path.relpath(path, HERE), i, int(m.group(1))))
    return out


def ngc_writes():
    """Numbered parameters lib/**.ngc ASSIGNS, as (file, line, value).

    A window may not extend over one of these. `poly_add_item` uses #4984-#4999
    as scratch on every machine, and CAM_TOP was declared 5000 - so the In-CAM
    table was allowed to grow into slots the O-code would overwrite. It had not
    happened yet, 4890 against 4984, but the declared cap was simply wrong and
    nothing could see it.
    """
    out = []
    for path in _walk(LIB, '.ngc'):
        for i, line in enumerate(_read(path).splitlines(), 1):
            m = re.match(r'\s*#(\d{4})\s*=', _code(line))
            if m:
                out.append((os.path.relpath(path, HERE), i, int(m.group(1))))
    return out


def globals_defined():
    """Global named parameters create_defaults writes, as a set."""
    src = _read(os.path.join(HERE, 'ncam.py'))
    return set(re.findall(r'#<(_[a-z0-9_]+)>\s*=', src))


def globals_read():
    """Global named parameters lib/**.ngc reads, as name -> [files]."""
    out = {}
    for path in _walk(LIB, '.ngc'):
        rel = os.path.relpath(path, HERE)
        for line in _read(path).splitlines():
            code = _code(line)
            for name in re.findall(r'#<(_[a-z0-9_]+)>', code):
                out.setdefault(name, set()).add(rel)
    return {k: sorted(v) for k, v in out.items()}


def cfg_params():
    """Per cfg file: the parameters it defines, and its `order =` names."""
    out = {}
    for path in _walk(CFG, '.cfg'):
        src = _read(path)
        rel = os.path.relpath(path, HERE)
        defined = set(m.group(1).lower()
                      for m in re.finditer(r'^\[PARAM_([A-Z0-9_]+)\]', src, re.M))
        order = []
        m = re.search(r'^order = (.*)$', src, re.M)
        if m:
            order = m.group(1).split()
        out[rel] = {'defined': defined, 'order': order, 'src': src}
    return out


def param_readers():
    """Every `param_x` mentioned anywhere, as name -> [where]."""
    out = {}

    def note(name, where):
        out.setdefault(name, set()).add(where)

    for path in _walk(CFG, '.cfg'):
        rel = os.path.relpath(path, HERE)
        for name in re.findall(r'#(param_[a-z0-9_]+)', _read(path)):
            note(name, rel)
    for f in sorted(os.listdir(HERE)):
        if not f.endswith('.py') or f.startswith('test_'):
            continue
        src = _read(os.path.join(HERE, f))
        for name in re.findall(r"get_param\('(param_[a-z0-9_]+)'\)", src):
            note(name, f)
        for name in re.findall(r"_p\('(param_[a-z0-9_]+)'\)|_off\('(param_[a-z0-9_]+)'\)"
                               r"|_v\('(param_[a-z0-9_]+)'\)", src):
            for g in name:
                if g:
                    note(g, f)
    return {k: sorted(v) for k, v in out.items()}


def subroutines():
    """`o<name> sub` definitions and `o<name> CALL` sites."""
    defined, called = {}, {}
    for path in _walk(LIB, '.ngc'):
        rel = os.path.relpath(path, HERE)
        for line in _read(path).splitlines():
            code = _code(line)
            m = re.search(r'o<([a-z0-9_]+)>\s+sub', code)
            if m:
                defined[m.group(1)] = rel
            for m in re.finditer(r'o<([a-z0-9_]+)>\s+CALL', code):
                called.setdefault(m.group(1), set()).add(rel)
    return defined, {k: sorted(v) for k, v in called.items()}


# --------------------------------------------------------------------------
# checks
# --------------------------------------------------------------------------

def check_all():
    """[(ok, name, detail)] - every static check, in the order they matter."""
    res = []
    win = windows()

    # C1a - the windows themselves must not overlap
    spans = []
    for name, base in sorted(win.items()):
        if not name.endswith('BASE'):
            continue
        top = win.get(name.replace('BASE', 'TOP'))
        if top is None:
            # a base with no top of its own ends at the next base above it
            highs = [v for k, v in win.items() if k.endswith('BASE') and v > base]
            top = min(highs) if highs else base + 1
        spans.append((base, top, name))
    scratch_slots = sorted(set(v for _f, _l, v in cfg_scratch()))
    if scratch_slots:
        spans.append((scratch_slots[0], scratch_slots[-1] + 1, 'cfg CALL scratch'))
    spans.sort()
    bad = [(a, b) for a, b in zip(spans, spans[1:]) if a[1] > b[0]]
    res.append((not bad, 'parameter windows do not overlap',
                '; '.join('%s ends %d but %s starts %d' % (a[2], a[1], b[2], b[0])
                          for a, b in bad)))

    # C1b - every literal in the .ngc is a window base Python still agrees with
    known = set(win.values())
    # above every window is the O-code's own scratch - poly_add_item's
    # #4984-#4999. Those are not table references and must not be read as
    # stray ones; C1d below is what keeps a window from growing into them.
    scratch = max(t for _b, t, _n in spans) if spans else 10000
    stray = []
    for rel, line, val in ngc_literals():
        if val in known or val >= scratch:
            continue
        if any(base <= val < top for base, top, _n in spans):
            continue                       # inside a window, an offset from it
        stray.append('%s:%d reads #%d' % (rel, line, val))
    res.append((not stray,
                'every numbered-parameter literal in lib/ lands in a window '
                'Python declares', '; '.join(stray[:4])))

    # C1c - the literals we deliberately allow still match their constant
    drift = ['%s is %d in Python but lib/ uses %d'
             % (n, win[n], v) for n, v in LITERAL_WINDOWS.items()
             if n in win and win[n] != v]
    res.append((not drift, 'the hard-coded window literals match lathe_sections',
                '; '.join(drift)))

    # C1d - no window may reach over a slot the O-code uses as scratch
    clash = []
    for rel, line, val in ngc_writes():
        for base, top, name in spans:
            if base <= val < top:
                clash.append('%s:%d writes #%d, inside %s' % (rel, line, val, name))
                break
    res.append((not clash,
                'no parameter window reaches over a slot the O-code writes',
                '; '.join(sorted(set(clash))[:4])))

    # C2 - a global read in the .ngc but never defined fails at LOAD time
    defined, read = globals_defined(), globals_read()
    builtin = re.compile(r'^_(mm|metric|rpm|coord_system|off_rot|offsets_|'
                         r'rotated_|tool|feed|speed|diameter_mode|x_|z_|ix_)')
    # a global lib/ ASSIGNS before reading needs no default - _pl_ph1_front_cut
    # and _pl_ph1_z_end are set at the top of poly_lathe_mill and read further
    # down, which is why the program loads today
    assigned = set()
    for path in _walk(LIB, '.ngc'):
        for line in _read(path).splitlines():
            for m in re.finditer(r'#<(_[a-z0-9_]+)>\s*=', _code(line)):
                assigned.add(m.group(1))
    missing = sorted(n for n in read
                     if n not in defined and n not in assigned
                     and not builtin.match(n) and n.startswith('_pl_'))
    res.append((not missing,
                'every #<_pl_*> the O-code reads is defined in create_defaults',
                ', '.join(missing[:6])))

    # C4 - a name in an `order =` line with no [PARAM_*] behind it
    dangling = []
    for rel, info in cfg_params().items():
        for name in info['order']:
            # case-insensitively: probe-stock.cfg's order says H5 where the
            # section is [PARAM_H5], and reading that as a dangling name was
            # this checker's own bug on its first run
            if (name.lower() not in info['defined']
                    and (rel, name) not in ORDER_KNOWN):
                dangling.append('%s: %s' % (rel, name))
    res.append((not dangling, 'every name in an order line has a parameter',
                '; '.join(dangling[:6])))

    # C6 - a subroutine called but not defined anywhere on the lib path
    subs, calls = subroutines()
    unknown = sorted(n for n in calls if n not in subs)
    res.append((not unknown, 'every subroutine called is defined in lib/',
                ', '.join(unknown[:6])))
    return res


def dead_weight():
    """Things defined and never read. Reported, never failed - see --map."""
    readers = param_readers()
    unread = []
    for rel, info in cfg_params().items():
        for name in sorted(info['defined']):
            full = 'param_' + name
            where = [w for w in readers.get(full, []) if w != rel]
            if not where and full not in readers:
                unread.append('%s: %s' % (rel, full))
    defined, read = globals_defined(), globals_read()
    cfg_src = ''.join(_read(p) for p in _walk(CFG, '.cfg'))
    ngl = sorted(n for n in defined
                 if n.startswith('_pl_') and n not in read
                 and ('#<%s>' % n) not in cfg_src)
    return unread, ngl


# --------------------------------------------------------------------------

def write_map(path):
    win = windows()
    subs, calls = subroutines()
    readers = param_readers()
    defined, read = globals_defined(), globals_read()
    unread, ngl = dead_weight()
    L = ['# CAM map — what touches what',
         '',
         'Generated by `cam_map.py --map`. Regenerate after any change to a',
         'parameter, a table window or a subroutine.',
         '',
         '## Parameter windows',
         '',
         '| constant | value |', '|---|---|']
    for k in sorted(win, key=lambda k: (win[k], k)):
        L.append('| `%s` | %d |' % (k, win[k]))
    L += ['', 'Literals the O-code hard-codes, which Python must keep in step:',
          '']
    for rel, line, val in ngc_literals():
        L.append('- `%s:%d` → #%d' % (rel, line, val))
    L += ['', '## Globals', '',
          '%d defined in `create_defaults`, %d read in `lib/`.'
          % (len(defined), len(read)), '']
    for n in sorted(read):
        if n.startswith('_pl_'):
            L.append('- `#<%s>` — read by %s' % (n, ', '.join(read[n])))
    L += ['', '## Parameters', '']
    for name in sorted(readers):
        L.append('- `%s` — %s' % (name, ', '.join(readers[name])))
    L += ['', '## Subroutines', '']
    for n in sorted(subs):
        L.append('- `%s` (%s) — called by %s'
                 % (n, subs[n], ', '.join(calls.get(n, ['nobody'])) or 'nobody'))
    L += ['', '## Defined and never read', '']
    for x in unread:
        L.append('- %s' % x)
    for x in ngl:
        L.append('- `#<%s>`' % x)
    with open(path, 'w') as fh:
        fh.write('\n'.join(L) + '\n')
    return path


def main():
    res = check_all()
    for ok, name, detail in res:
        print(('PASS  ' if ok else 'FAIL  ') + name
              + (('  ' + detail) if detail and not ok else ''))
    if '--map' in sys.argv:
        p = write_map(os.path.join(HERE, 'CAM-MAP.md'))
        unread, ngl = dead_weight()
        print('\nwrote %s  (%d parameters and %d globals defined but never read)'
              % (os.path.relpath(p, HERE), len(unread), len(ngl)))
    bad = [n for ok, n, _d in res if not ok]
    print()
    if bad:
        print('FAILED: %d' % len(bad))
        for n in bad:
            print('   -', n)
        sys.exit(1)
    print('cfg, Python and O-code agree about what touches what.')


if __name__ == '__main__':
    main()
