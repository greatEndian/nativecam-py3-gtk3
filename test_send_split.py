#!/usr/bin/env python3
# coding: utf-8
"""Checks that Regenerate and Send are really two separate actions.

Standalone, like the other test_*.py here - run it directly, no pytest.

One gear button used to generate the G-code AND push it into LinuxCNC in a
single press, so there was no way to rebuild without taking over the machine's
loaded program. The split is only worth anything if each half genuinely does
its half and nothing more, and that is exactly the kind of thing that reads
correctly and behaves wrongly:

  - Regenerate must never reach linuxcnc.command(). If it does, it is still the
    old button wearing a new label, and pressing it while a program runs would
    interrupt the machine.
  - Send must NOT regenerate in the default mode, or the radio is decoration.
  - Send MUST regenerate in the other mode, or the radio is decoration the
    other way round.
  - Auto-refresh must still do both, because every tree edit calls it.

Nothing here talks to a real LinuxCNC: send_to_linuxcnc is replaced with a
recorder, which is also what makes "Regenerate never sends" checkable at all.
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
INI = os.path.join(HERE, 'configs', 'sim', 'axis', 'ncam_demo', 'lathe-mm.ini')

FAILED = []


def check(name, cond, detail=''):
    # detail only on failure: these details are worded as explanations of what
    # went wrong, and printing them beside PASS reads as if the test failed
    print(('PASS  ' if cond else 'FAIL  ') + name
          + (('  ' + detail) if detail and not cond else ''))
    if not cond:
        FAILED.append(name)


def build_app():
    """A real NCam against a scratch copy of the demo config."""
    import shutil
    scratch = tempfile.mkdtemp(prefix='send_split_')
    dst = os.path.join(scratch, 'ncam_demo')
    shutil.copytree(os.path.dirname(INI), dst, symlinks=True)
    ini = os.path.join(dst, os.path.basename(INI))

    sys.argv = ['ncam.py', '-i', ini, '-c', 'lathe']
    sys.path.insert(0, HERE)
    import ncam
    app = ncam.NCam()
    return ncam, app


def main():
    if not os.path.isfile(INI):
        print('SKIP  demo config not present at %s' % INI)
        return
    ncam, app = build_app()
    # write_ngc refuses to generate before the panel is realized, which never
    # happens in a headless run. That guard is about GUI lifecycle, not about
    # the Regenerate/Send split under test here.
    app.get_realized = lambda: True

    # --- the two actions exist, and the old combined one is gone ------------
    acts = app._actions
    check('a Regenerate action exists', 'Regen' in acts)
    check('a Send action exists', 'Send' in acts)
    check('the old combined Build action is gone', 'Build' not in acts,
          'still present - the split is additive, not a split')
    for n in ('Regen', 'Send'):
        if n in acts:
            check('%s has a text label' % n, bool(getattr(acts[n], '_label', None)))

    # --- the toolbar carries both, and Send has the radio dropdown ----------
    kinds = [type(c).__name__ for c in app.main_toolbar.get_children()]
    check('the toolbar has a MenuToolButton for Send',
          kinds.count('MenuToolButton') == 1, str(kinds[:4]))
    btn = next((c for c in app.main_toolbar.get_children()
                if type(c).__name__ == 'MenuToolButton'), None)
    if btn is not None:
        items = [i for i in btn.get_menu().get_children()]
        check('the Send dropdown offers exactly two radio choices',
              len(items) == 2 and all(type(i).__name__ == 'RadioMenuItem'
                                      for i in items),
              str([type(i).__name__ for i in items]))

    # both radio copies - toolbar and Utilities menu - must be tracked, or
    # choosing in one leaves the other showing the wrong mode
    check('every radio copy is tracked for syncing',
          len(getattr(app, 'send_mode_groups', [])) >= 2,
          '%d group(s)' % len(getattr(app, 'send_mode_groups', [])))

    # --- behaviour: replace the LinuxCNC half with a recorder ---------------
    sent = []
    app.send_to_linuxcnc = lambda fname=None: sent.append(fname) or True

    ngc = os.path.join(ncam.NGC_DIR, ncam.GENERATED_FILE)
    if os.path.isfile(ngc):
        os.unlink(ngc)

    # Regenerate: writes, never sends
    app.action_regen()
    check('Regenerate writes the G-code file', os.path.isfile(ngc))
    check('Regenerate does NOT send to LinuxCNC', not sent,
          'sent %d time(s) - it is still the old combined button' % len(sent))

    # Send, default mode: sends, does not regenerate
    with open(ngc, 'w') as f:
        f.write('(sentinel - must survive a plain Send)\n')
    app.send_regenerates = False
    del sent[:]
    app.action_send()
    check('Send loads the file', len(sent) == 1, 'sent %d time(s)' % len(sent))
    check('Send does NOT regenerate in the default mode',
          open(ngc).read().startswith('(sentinel'),
          'the sentinel was overwritten, so Send regenerated anyway')

    # Send, regenerate mode: regenerates first
    app.send_regenerates = True
    del sent[:]
    app.action_send()
    check('Send DOES regenerate in the other mode',
          not open(ngc).read().startswith('(sentinel'),
          'the sentinel survived, so the radio changes nothing')
    check('and still loads it', len(sent) == 1)

    # Auto-refresh must keep doing both - every tree edit calls it
    with open(ngc, 'w') as f:
        f.write('(sentinel)\n')
    del sent[:]
    app.autorefresh_call()
    check('Auto-refresh still generates', not open(ngc).read().startswith('(sentinel'))
    check('Auto-refresh still sends', len(sent) == 1)

    # --- the recorder has to be able to catch a send, or the two "does NOT
    # send" checks above would pass no matter what the code did
    del sent[:]
    app.send_to_linuxcnc('probe')
    check('the recorder detects a send when one happens', sent == ['probe'])

    print()
    if FAILED:
        print('FAILED: %d' % len(FAILED))
        for f in FAILED:
            print('   -', f)
        sys.exit(1)
    print('Regenerate and Send are properly separated.')


if __name__ == '__main__':
    main()
