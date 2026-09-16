#!/usr/bin/env python3
# coding: utf-8
"""Hunt the intermittent "Both directions" + Regenerate crash, standalone.

openPoints.md, "BOTH DIRECTIONS" + REGENERATE: greatEndian, 2026-08-26 -
selecting Both directions and regenerating crashes, intermittently. Proven
NOT a generation fault (testing_15_7/8 generate and run clean headless at
param_dir 0/1/2). So it is GUI-side - never a captured traceback before this.

WHAT THIS DOES. Builds a real ncam.NCam() panel (the same object AXIS embeds),
shown in a plain Gtk.Window under Xvfb so gtk.Window.list_toplevels() sees a
visible parent - msg_inv (ncam.py) and mess_dlg skip their dialog entirely with
no visible toplevel, and the prime suspect named in the task prompt is exactly
"a message dialog opened from inside a generation callback", so a headless run
with no window would silently walk past the one thing under suspicion. A
persistent auto-dismiss timeout answers OK to any dialog that appears, so the
loop can run unattended for hundreds of iterations.

Drives the REAL edited-cell code path: Parameter.set_value(new_val, feature),
then NCam.refresh_views()/.action() - the exact tail of ncam_treeview.edited()
- for PARAM_DIR and PARAM_F_DIR on the polyline feature in testing_15_7 and
testing_15_8, cycling 0 -> 2 -> 1 -> 2 as the task prompt specifies, each
change followed by a real action_regen() (the Regenerate button - never
touches linuxcnc.command()). Runs entirely inside one real Gtk.main() so the
preview's worker thread + GLib.idle_add(self._done, ...) actually interleaves
with the next edit, instead of being serialised by a manual pump - timing is
varied by chaining GLib.timeout_add with a randomised delay (0..900 ms) after
each regenerate, so short delays interrupt a still-running preview parse and
long ones let it finish, both asked for by the task prompt.

INSTRUMENTATION. faulthandler (segfault/abort -> Python traceback to the log,
plus a periodic all-thread dump so a hang is not silent), sys.excepthook and
threading.excepthook (both log AND still call the original, so behaviour is
unchanged - this only adds a witness), GLib.log_set_handler on every GTK/GLib
domain for CRITICAL/WARNING/ERROR with a Python stack attached (a GLib
critical carries no Python frame on its own - that is the gap that has hidden
this bug so far). Self-tested against a forced exception in an idle callback,
a forced exception in a thread, and a real GTK critical (destroyed widget)
before any of it is trusted - see selftest() and analysis/291.

Every rs274 invocation the preview's worker thread makes is wrapped in
flock('/tmp/ncam-rs274.lock') at the exact subprocess.run() call, not around
the whole harness - SONNET-LANES.md requires the lock per interpreter run, and
holding it for the whole multi-minute loop would block the GEOMETRY lane for
no reason.

Usage:
    python3 tools/crash_hunt_both_dir.py --selftest
    python3 tools/crash_hunt_both_dir.py --iterations 300 --log /tmp/crash.log
"""
import argparse
import contextlib
import fcntl
import os
import random
import sys
import threading
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, REPO)

RS274_LOCK = '/tmp/ncam-rs274.lock'
DEMO_SRC = os.path.join(REPO, 'configs', 'sim', 'axis', 'ncam_demo')
MAIN_TREE_PROJECTS = ('/home/user/nativeCamDev/configs/sim/axis/ncam_demo'
                       '/ncam/catalogs/lathe/projects')
PROJECTS = ['testing_15_7.xml', 'testing_15_8.xml']

# analysis/211: PreviewPane's ini comes ONLY from os.getenv('INI_FILE_NAME')
# (ncam_preview_ui.py:1206 - `self.ini_file` is never assigned anywhere in
# this project, so that half of the getattr-or-env read is dead code). AXIS
# is unaffected because /usr/bin/linuxcnc:802 exports it; this harness put
# the ini on sys.argv instead and left the env var unset, so PreviewPane's
# ini_path was None for the whole c3c678d run - see build_app() below and
# analysis/29N for the measured before/after.
RS274_RCS = []          # rc of every rs274 invocation since the last .clear()
PREVIEW_COUNTS = {'parsed_ok': 0, 'parsed_fail': 0}

_LOG_FH = None
_STARTED = 0.0


def log(msg):
    line = '[%8.3f] %s' % (time.time() - _STARTED, msg)
    print(line, flush=True)
    if _LOG_FH is not None:
        _LOG_FH.write(line + '\n')
        _LOG_FH.flush()
        os.fsync(_LOG_FH.fileno())


# --------------------------------------------------------------------------
# rs274 lock - wraps only the actual subprocess.run() the preview makes
# --------------------------------------------------------------------------
@contextlib.contextmanager
def rs274_lock():
    fd = open(RS274_LOCK, 'w')
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            fd.close()


def patch_rs274_lock(ncam_preview):
    import subprocess
    orig_run = subprocess.run

    def locked_run(cmd, *a, **kw):
        if cmd and isinstance(cmd, (list, tuple)) and cmd[0] == 'rs274':
            log('rs274 run start: %s' % ' '.join(str(c) for c in cmd))
            with rs274_lock():
                res = orig_run(cmd, *a, **kw)
            log('rs274 run done rc=%s' % res.returncode)
            RS274_RCS.append(res.returncode)
            return res
        return orig_run(cmd, *a, **kw)

    ncam_preview.subprocess.run = locked_run


# --------------------------------------------------------------------------
# Instrumentation
# --------------------------------------------------------------------------
def install_instrumentation():
    import faulthandler
    faulthandler.enable(file=_LOG_FH, all_threads=True)
    faulthandler.dump_traceback_later(25, repeat=True, file=_LOG_FH)

    orig_excepthook = sys.excepthook

    def excepthook(etype, value, tb):
        log('MAIN-THREAD EXCEPTION:\n' +
            ''.join(traceback.format_exception(etype, value, tb)))
        orig_excepthook(etype, value, tb)

    sys.excepthook = excepthook

    orig_thread_hook = threading.excepthook

    def thread_hook(args):
        log('THREAD EXCEPTION in %r:\n' % (args.thread,) +
            ''.join(traceback.format_exception(
                args.exc_type, args.exc_value, args.exc_traceback)))
        orig_thread_hook(args)

    threading.excepthook = thread_hook

    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import GLib

    def glib_log_handler(domain, level, message, user_data=None):
        log('GLIB-LOG domain=%r level=%r msg=%s\nPYTHON STACK:\n%s'
            % (domain, level, message,
               ''.join(traceback.format_stack())))

    LEVELS = (GLib.LogLevelFlags.LEVEL_CRITICAL
              | GLib.LogLevelFlags.LEVEL_ERROR
              | GLib.LogLevelFlags.LEVEL_WARNING)
    handler_ids = []
    for domain in (None, '', 'Gtk', 'Gdk', 'GLib', 'GLib-GObject',
                   'Pango', 'GdkPixbuf', 'cairo', 'PyGObject'):
        try:
            hid = GLib.log_set_handler(domain, LEVELS, glib_log_handler)
            handler_ids.append(hid)
        except Exception as e:
            log('could not install log handler for domain %r: %r' % (domain, e))
    return handler_ids


def auto_dismiss_dialogs(gtk):
    """Answer OK to any visible dialog - msg_inv / mess_dlg both use one.

    Registered once as a repeating GLib timeout; it keeps firing even while
    a nested Gtk.Dialog.run() main loop is active, which is exactly the
    reentrancy this harness exists to exercise (see module docstring).
    """
    for w in gtk.Window.list_toplevels():
        try:
            if isinstance(w, gtk.Dialog) and w.get_visible():
                log('AUTO-DISMISS dialog: %r' % _dialog_text(w))
                w.response(gtk.ResponseType.OK)
        except Exception as e:
            log('auto_dismiss_dialogs error on %r: %r' % (w, e))
    return True


def _dialog_text(dlg):
    try:
        return dlg.get_property('text')
    except Exception:
        return repr(dlg)


# --------------------------------------------------------------------------
# Self-test - validate the instrument before trusting it
# --------------------------------------------------------------------------
def selftest():
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk as gtk
    from gi.repository import GLib

    install_instrumentation()
    log('SELFTEST: begin')

    def boom_idle():
        raise RuntimeError('SELFTEST-MAIN-EXC')

    GLib.idle_add(boom_idle)
    for _ in range(30):
        while gtk.events_pending():
            gtk.main_iteration()
        time.sleep(0.01)

    def boom_thread():
        raise RuntimeError('SELFTEST-THREAD-EXC')

    t = threading.Thread(target=boom_thread)
    t.start()
    t.join()

    b = gtk.Button()
    win = gtk.Window()
    win.add(b)
    win.show_all()
    for _ in range(5):
        while gtk.events_pending():
            gtk.main_iteration()
    b.destroy()
    try:
        b.set_label('x')
    except Exception as e:
        log('SELFTEST: set_label on destroyed widget raised %r (also acceptable)' % e)
    for _ in range(30):
        while gtk.events_pending():
            gtk.main_iteration()
        time.sleep(0.01)
    win.destroy()

    # force a REAL GLib critical through the C API directly - a destroyed
    # GTK widget does not reliably emit one (proven above: it silently
    # no-ops on this pygobject build), so this is the one that actually
    # proves GLib.log_set_handler is wired end to end.
    import ctypes
    import ctypes.util
    libglib = ctypes.CDLL(ctypes.util.find_library('glib-2.0'))
    libglib.g_log.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p]
    G_LOG_LEVEL_CRITICAL = 1 << 3
    libglib.g_log(b'Gtk', G_LOG_LEVEL_CRITICAL, b'SELFTEST-GLIB-CRITICAL')

    log('SELFTEST: end')

    _LOG_FH.flush()
    with open(_LOG_FH.name) as f:
        text = f.read()
    ok = True
    for marker in ('SELFTEST-MAIN-EXC', 'SELFTEST-THREAD-EXC',
                   'SELFTEST-GLIB-CRITICAL'):
        found = marker in text
        print('%-6s marker %s in log' % ('PASS' if found else 'FAIL', marker))
        ok = ok and found
    return ok


# --------------------------------------------------------------------------
# Building and driving the real app
# --------------------------------------------------------------------------
def build_app(scratch_root):
    import shutil
    dst = os.path.join(scratch_root, 'ncam_demo')
    shutil.copytree(DEMO_SRC, dst, symlinks=True)
    ini = os.path.join(dst, 'lathe-mm.ini')

    # Tool tables are gitignored (live GUI state, like the projects), so a
    # fresh worktree has none - copied read-only from the main tree so T2
    # resolves to its real D0.8 Q2 (a DIRECTIONAL insert, per
    # tool-change.cfg's dnum=2 in testing_15_7/8). Without this the nose
    # radius/orientation lookup silently fails and wrong_way_dirs - the
    # exact suspect this hunt is aimed at - can never fire.
    main_demo = '/home/user/nativeCamDev/configs/sim/axis/ncam_demo'
    for tbl in ('lathe_mm.tbl', 'lathe.tbl'):
        src_tbl = os.path.join(main_demo, tbl)
        if os.path.isfile(src_tbl):
            shutil.copy(src_tbl, os.path.join(dst, tbl))
        else:
            log('WARNING: no %s in main tree to copy' % src_tbl)

    sys.argv = ['ncam.py', '-i', ini, '-c', 'lathe']
    # analysis/211: PreviewPane's ini is read ONLY from os.getenv(
    # 'INI_FILE_NAME') at ncam_preview_ui.py:1206 - `self.ini_file` is never
    # assigned anywhere in this project (dead code), so putting the ini on
    # sys.argv (above) is not enough; it never reaches the preview. AXIS never
    # notices because /usr/bin/linuxcnc:802 exports this same variable before
    # the panel is built. Do that here too, so the harness's PreviewPane
    # resolves the same SUBROUTINE_PATH AXIS gets - must be set before
    # ncam.NCam() runs create_preview_pane() (ncam.py:3286, inside __init__).
    os.environ['INI_FILE_NAME'] = ini
    log('exported INI_FILE_NAME=%s' % ini)
    import ncam
    import ncam_preview
    patch_rs274_lock(ncam_preview)

    app = ncam.NCam()
    app.get_realized = lambda: True
    install_preview_logging(app)

    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk as gtk
    win = gtk.Window()
    win.set_default_size(900, 700)
    win.add(app)
    win.show_all()
    for _ in range(10):
        while gtk.events_pending():
            gtk.main_iteration()

    proj_dir = os.path.join(ncam.NCAM_DIR, 'catalogs', 'lathe', 'projects')
    os.makedirs(proj_dir, exist_ok=True)
    for name in PROJECTS:
        src = os.path.join(MAIN_TREE_PROJECTS, name)
        if os.path.isfile(src):
            shutil.copy(src, os.path.join(proj_dir, name))
        else:
            log('WARNING: %s not found in main tree - skipped' % src)

    return ncam, app, win, proj_dir


def load_project(app, ncam, path):
    from lxml import etree
    xml = etree.fromstring(open(path, 'rb').read())
    xml = app.update_features(xml)
    app.treestore_from_xml(xml)


def find_polyline_feature(app, ncam):
    found = []

    def visit(model, path, itr, data=None):
        obj = model.get_value(itr, 0)
        if isinstance(obj, ncam.Feature) and obj.get_attr('src') == 'lathe/polyline.cfg':
            found.append(obj)
        return False

    app.treestore.foreach(visit)
    return found[0] if found else None


def find_param(feature, call):
    for p in feature.param:
        if p.attr.get('call') == call:
            return p
    return None


def set_param_like_a_real_edit(app, feature, param, value_str):
    """The exact tail of ncam_treeview.edited() for a plain (non-linked) combo."""
    changed = param.set_value(value_str, feature)
    if changed:
        app.refresh_views()
        app.action()
    return changed


def install_preview_logging(app):
    """Log every PreviewPane._done completion - non-blocking, just a witness.

    Wraps the INSTANCE method (shadows the class method via the instance
    dict, same lookup Python uses for `self._done` inside _worker), so the
    normal async interleaving the hunt is testing is untouched - this only
    counts and logs what already happened. Distinct from the synchronous gate
    below: the gate BLOCKS to prove the fix before the long run; this stays
    passive during the run itself, because forcing every iteration to wait
    for its parse to finish would remove the exact overlap (a short delay
    interrupting a still-running parse) the hunt exists to exercise.
    """
    pane = getattr(app, 'preview_pane', None)
    if pane is None:
        log('install_preview_logging: no preview_pane on app - not built?')
        return
    orig_done = pane._done

    def logged_done(tp, checked=False, hits=None):
        orig_done(tp, checked, hits)
        moves = len(tp.moves) if tp is not None and tp.moves else 0
        err = tp.error if tp is not None else 'NO TOOLPATH'
        ok = bool(moves) and not err
        PREVIEW_COUNTS['parsed_ok' if ok else 'parsed_fail'] += 1
        log('PREVIEW DONE: moves=%d error=%r ok=%s (running totals ok=%d fail=%d)'
            % (moves, err, ok, PREVIEW_COUNTS['parsed_ok'],
               PREVIEW_COUNTS['parsed_fail']))

    pane._done = logged_done


def wait_for_preview(app, gtk, timeout_s=30):
    """Pump the GTK loop until the preview's worker thread has landed.

    Only used by the synchronous gate (prove_preview_parses) and available
    for ad-hoc use - the hunt loop itself must NOT call this, see
    install_preview_logging's docstring.
    """
    pane = app.preview_pane
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        while gtk.events_pending():
            gtk.main_iteration()
        if not pane._busy:
            return True
        time.sleep(0.01)
    return False


def prove_preview_parses(app, ncam_mod, gtk, proj_dir):
    """The acceptance gate for the INI_FILE_NAME fix - run BEFORE the hunt.

    For each of testing_15_7/15_8: load it, regenerate for real
    (action_regen(), the same call the hunt loop makes), wait for the
    preview's worker thread to land, then assert HARD:
      - every rs274 invocation made during that regen exited rc=0
      - the parsed Toolpath has non-zero moves and no .error

    The old harness (c3c678d) asserted neither - `regen_ok` only counted
    Python exceptions escaping action_regen(), so 197/197 rs274 runs died at
    rc=1 with 0 moves and the loop never noticed. This is the fix for that.
    Returns (all_passed: bool, per_project: list of dicts) - never raises;
    the caller decides whether a failure is fatal.
    """
    results = []
    all_passed = True
    for name in PROJECTS:
        path = os.path.join(proj_dir, name)
        if not os.path.isfile(path):
            log('GATE %s: FAIL - project file not found at %s' % (name, path))
            results.append({'project': name, 'passed': False,
                             'reason': 'file not found'})
            all_passed = False
            continue

        load_project(app, ncam_mod, path)
        feat = find_polyline_feature(app, ncam_mod)
        if feat is None:
            log('GATE %s: FAIL - no lathe/polyline.cfg feature found' % name)
            results.append({'project': name, 'passed': False,
                             'reason': 'no polyline feature'})
            all_passed = False
            continue

        RS274_RCS.clear()
        # Do NOT reset .toolpath here - PreviewPane.__init__ seeds it with a
        # real ncam_preview.Toolpath() sentinel, never None (this file's own
        # first attempt at this gate proved that the hard way: setting it to
        # None makes refresh() itself throw on .moves before the worker
        # thread ever starts, so rs274 never runs and the gate hangs on
        # _busy forever). _busy alone is the right completion signal -
        # refresh() sets it True synchronously inside this call, before
        # action_regen() returns, and _done() clears it when the worker
        # thread's result lands via idle_add.
        app.action_regen()
        # SONNET-LANES.md: another lane's rs274 use under the same shared
        # /tmp/ncam-rs274.lock queues this one behind it rather than racing
        # it, and a long GEOMETRY sweep can hold the lock for minutes -
        # measured live during this task: a concurrent
        # test_motion_fingerprint.py run made one gate rs274 call take 112 s
        # against 10.9 s uncontended. 600 s absorbs that instead of misreading
        # contention as a broken fix (analysis/134, analysis/230's false-FAIL
        # shape).
        landed = wait_for_preview(app, gtk, timeout_s=600)

        tp = app.preview_pane.toolpath
        moves = len(tp.moves) if (tp is not None and tp.moves) else 0
        err = tp.error if tp is not None else None
        rcs = list(RS274_RCS)
        rcs_ok = bool(rcs) and all(rc == 0 for rc in rcs)
        passed = landed and rcs_ok and moves > 0 and not err

        log('GATE %s: landed=%s rs274_rcs=%r moves=%d error=%r -> %s'
            % (name, landed, rcs, moves, err, 'PASS' if passed else 'FAIL'))
        results.append({'project': name, 'passed': passed, 'landed': landed,
                         'rs274_rcs': rcs, 'moves': moves, 'error': err})
        all_passed = all_passed and passed

    return all_passed, results


# --------------------------------------------------------------------------
# The hunt loop
# --------------------------------------------------------------------------
DELAYS_MS = [0, 5, 15, 40, 100, 250, 600, 1200, 3000]


def run_hunt(iterations, seed, max_seconds):
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk as gtk
    from gi.repository import GLib

    install_instrumentation()
    GLib.timeout_add(25, lambda: auto_dismiss_dialogs(gtk))

    rng = random.Random(seed)
    import tempfile
    scratch = tempfile.mkdtemp(prefix='crash_hunt_')
    ncam, app, win, proj_dir = build_app(scratch)

    # Acceptance gate for the INI_FILE_NAME fix (analysis/211/29N) - proves
    # the preview now actually parses motion BEFORE spending ~19 minutes on
    # the long run. c3c678d had no such gate: regen_ok=250 there counted only
    # "action_regen() did not raise", and every one of its previews died at
    # rc=1 with 0 moves without the loop ever noticing.
    gate_passed, gate_results = prove_preview_parses(app, ncam, gtk, proj_dir)
    log('GATE RESULT: %s  %r' % ('PASS' if gate_passed else 'FAIL', gate_results))
    state = {
        'i': 0,
        'total': iterations,
        'done': False,
        'crashed': False,
        'regen_ok': 0,
        'regen_fail': 0,
        'dialogs': 0,
        'start': time.time(),
        'gate_passed': gate_passed,
        'gate_results': gate_results,
    }
    if not gate_passed:
        log('GATE FAILED - aborting before the long run. Fix the harness, '
            'do not run 250 iterations on a preview that still parses '
            'nothing.')
        return state

    def load(name):
        p = os.path.join(proj_dir, name)
        load_project(app, ncam, p)
        feat = find_polyline_feature(app, ncam)
        if feat is None:
            log('COULD NOT FIND polyline feature in %s' % name)
        return feat

    active = {'feat': load(PROJECTS[0]), 'proj_idx': 0}
    DIR_SEQ = [0, 2, 1, 2]

    def step():
        i = state['i']
        if i >= state['total'] or (time.time() - state['start']) > max_seconds:
            state['done'] = True
            gtk.main_quit()
            return False

        # every 25 steps, switch project (and let a long settle happen first)
        if i > 0 and i % 25 == 0:
            active['proj_idx'] = (active['proj_idx'] + 1) % len(PROJECTS)
            log('--- switching to %s ---' % PROJECTS[active['proj_idx']])
            active['feat'] = load(PROJECTS[active['proj_idx']])

        feat = active['feat']
        if feat is None:
            state['i'] += 1
            GLib.timeout_add(50, step)
            return False

        which = rng.choice(['dir', 'f_dir', 'both'])
        seq_val = DIR_SEQ[i % len(DIR_SEQ)]
        calls = []
        if which in ('dir', 'both'):
            calls.append('#param_dir')
        if which in ('f_dir', 'both'):
            calls.append('#param_f_dir')

        for call in calls:
            p = find_param(feat, call)
            if p is None:
                log('param %s not found on this feature' % call)
                continue
            set_param_like_a_real_edit(app, feat, p, str(seq_val))

        log('step %d/%d  proj=%s  %s=%d' %
            (i, state['total'], PROJECTS[active['proj_idx']], calls, seq_val))

        try:
            app.action_regen()
            state['regen_ok'] += 1
        except Exception as e:
            state['regen_fail'] += 1
            log('action_regen() RAISED: %r\n%s' % (e, traceback.format_exc()))

        for _ in range(5):
            while gtk.events_pending():
                gtk.main_iteration()

        state['i'] += 1
        delay = rng.choice(DELAYS_MS)
        GLib.timeout_add(delay, step)
        return False

    GLib.timeout_add(50, step)

    try:
        gtk.main()
    except KeyboardInterrupt:
        log('interrupted')

    log('HUNT DONE: iterations=%d regen_ok=%d regen_fail=%d elapsed=%.1fs '
        'preview_parsed_ok=%d preview_parsed_fail=%d' %
        (state['i'], state['regen_ok'], state['regen_fail'],
         time.time() - state['start'],
         PREVIEW_COUNTS['parsed_ok'], PREVIEW_COUNTS['parsed_fail']))
    state['preview_parsed_ok'] = PREVIEW_COUNTS['parsed_ok']
    state['preview_parsed_fail'] = PREVIEW_COUNTS['parsed_fail']
    return state


def run_gate_only(scratch=None):
    """Run just the two-project gate and return (passed, results) - for a
    standalone before/after measurement, separate from the long hunt."""
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk as gtk
    from gi.repository import GLib

    install_instrumentation()
    # Same as run_hunt(): must be armed BEFORE build_app(), because
    # NCam.__init__() (ncam.py:3296, create_M_file) opens a synchronous
    # gtk.MessageDialog.run() of its own on a fresh NCAM_DIR (no M123 file
    # yet to skip it) - with nothing answering it the gate hangs forever.
    # Caught by this gate's own first run: 25s watchdog dumps piled up at
    # ncam.py:656 mess_dlg -> ncam.py:3296 NCam.__init__, never reaching
    # prove_preview_parses at all.
    GLib.timeout_add(25, lambda: auto_dismiss_dialogs(gtk))
    import tempfile
    scratch = scratch or tempfile.mkdtemp(prefix='crash_hunt_gate_')
    ncam, app, win, proj_dir = build_app(scratch)
    return prove_preview_parses(app, ncam, gtk, proj_dir)


def main():
    global _LOG_FH, _STARTED
    ap = argparse.ArgumentParser()
    ap.add_argument('--selftest', action='store_true')
    ap.add_argument('--gate-only', action='store_true',
                     help='run only the testing_15_7/15_8 preview-parses '
                          'gate and exit - no long hunt')
    ap.add_argument('--iterations', type=int, default=300)
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--max-seconds', type=int, default=1200)
    ap.add_argument('--log', default=None)
    args = ap.parse_args()

    _STARTED = time.time()
    logpath = args.log or os.path.join(
        '/tmp', 'crash_hunt_%d.log' % os.getpid())
    _LOG_FH = open(logpath, 'a')
    log('log file: %s' % logpath)
    log('argv: %r' % sys.argv)

    if args.selftest:
        ok = selftest()
        print()
        print('INSTRUMENT VALIDATION:', 'PASS' if ok else 'FAIL')
        sys.exit(0 if ok else 1)

    if args.gate_only:
        passed, results = run_gate_only()
        print()
        print('GATE:', 'PASS' if passed else 'FAIL')
        print('log file:', logpath)
        sys.exit(0 if passed else 1)

    state = run_hunt(args.iterations, args.seed, args.max_seconds)
    print()
    print('log file: %s' % logpath)
    if not state.get('gate_passed', False):
        print('GATE FAILED - hunt was NOT run. See log for details.')
        sys.exit(1)
    sys.exit(0)


if __name__ == '__main__':
    main()
