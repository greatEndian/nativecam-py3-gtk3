#!/usr/bin/env python3
# coding: utf-8
# ------------------------------------------------------------------
# --  NO USER SETTINGS IN THIS FILE -- EDIT PREFERENCES INSTEAD  ---
# ------------------------------------------------------------------

APP_COPYRIGHT = '''Copyright © 2017 Fernand Veilleux : fernveilleux@gmail.com
Copyright © 2012 Nick Drobchenko aka Nick from cnc-club.ru
Copyright © 2026 greatEndian (Python 3 / GTK3 Port)'''
APP_AUTHORS = ['Fernand Veilleux (original author)',
               'Nick Drobchenko (initiator)',
               'Meison Kim', 'Alexander Wigen', 'Konstantin Navrockiy', 'Mit Zot',
               'Dewey Garrett', 'Karl Jacobs', 'Philip Mullen',
               'greatEndian (Python 3 / GTK3 port, Side Drill)']

APP_VERSION = "2.0b"

import sys
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk as gtk
from gi.repository import Gdk as gdk
from gi.repository import Pango as pango
from gi.repository import GdkPixbuf
from gi.repository import GLib
from gi.repository import Gio
from lxml import etree
from gi.repository import GObject as gobject
from gi.repository import Gdk
import configparser as ConfigParser
import re, os
import getopt
import shutil
import hashlib
import subprocess
import webbrowser
import io
from io import StringIO
import gettext
import time
import locale
import platform
import pref_edit
import tkinter as Tkinter
import math
import contextlib
import warnings

# check for X11 vs Wayland for XEMBED compatibility
try:
    _display = Gdk.Display.get_default()
    if _display and not _display.get_name().lower().startswith('x11') and not _display.get_name().lower().startswith('display'):
        # Some envs use ':0' which is X11. Wayland usually says 'wayland-0'
        if 'wayland' in _display.get_name().lower():
            print("Warning: NativeCAM embedding (XEMBED) requires X11. Wayland detected ('%s')." % _display.get_name())
except Exception:
    pass

# PyGObject warns on every Gtk.Action / GAction bridge / ImageMenuItem call.
warnings.filterwarnings(
    'ignore', category=DeprecationWarning,
    message=r'.*Gtk\..* is deprecated')

SYS_DIR = os.path.dirname(os.path.realpath(__file__))

locale.setlocale(locale.LC_ALL, '')
decimal_point = locale.localeconv()["decimal_point"]

# if False, NO_ICON_FILE will be used
DEFAULT_USE_NO_ICON = True
NO_ICON_FILE = 'no-icon.png'

# info at http://www.pygtk.org/pygtk2reference/pango-markup-language.html
# when grayed, uses these format
gray_header_fmt_str = '<span foreground="gray" style="oblique">%s...</span>'
gray_sub_header_fmt_str = '<span foreground="gray" style="oblique">%s...</span>'
gray_sub_header_fmt_str2 = '<span foreground="gray" style="oblique" weight="bold">%s</span>'
gray_feature_fmt_str = '<span foreground="gray" weight="bold">%s</span>'
gray_items_fmt_str = '<span foreground="gray" style="oblique" weight="bold">%s</span>'
gray_val = '<span foreground="gray">%s</span>'
# when NOT grayed
header_fmt_str = '<i>%s...</i>'
sub_header_fmt_str = '<i>%s...</i>'
sub_header_fmt_str2 = '<b><i>%s</i></b>'
feature_fmt_str = '<b>%s</b>'
items_fmt_str = '<span foreground="blue" style="oblique"><b>%s</b></span>'

UNDO_MAX_LEN = 200
gmoccapy_time_out = 0.0

# use or test translation file
APP_NAME = 'nativecam'
nativecam_locale = os.getenv('NATIVECAM_LOCALE')
if nativecam_locale is not None :
    translate_test = True
else :
    translate_test = False
    nativecam_locale = '/usr/share/locale'
gettext.bindtextdomain(APP_NAME, nativecam_locale)
gettext.textdomain(APP_NAME)
try :
    lang = gettext.translation(APP_NAME, nativecam_locale, fallback = True)
    lang.install()
    _ = lang.gettext
except Exception:
    gettext.install(APP_NAME, None)

APP_TITLE = _("NativeCAM for LinuxCNC")
APP_COMMENTS = _('A GUI to help create LinuxCNC NGC files.')
APP_LICENCE = _('''This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.\n
It is recommended you use the deb package
''')

VALID_CATALOGS = ['mill', 'plasma', 'lathe']
DEFAULT_CATALOG = "mill"

# directories
CFG_DIR = 'cfg'
PROJECTS_DIR = 'projects'
LIB_DIR = 'lib'
NGC_DIR = 'scripts'
EXAMPLES_DIR = 'examples'
CATALOGS_DIR = 'catalogs'
GRAPHICS_DIR = 'graphics'
DEFAULTS_DIR = 'defaults'
CUSTOM_DIR = 'my-stuff'

# files
DEFAULT_TEMPLATE = 'default_template.xml'
USER_DEFAULT_FILE = 'custom_defaults.conf'
EXCL_MSG_FILE = 'excluded_msg.conf'
CURRENT_WORK = "current_work.xml"
PREFERENCES_FILE = "default.conf"
CONFIG_FILE = 'ncam.conf'
TOOLBAR_FNAME = "toolbar.conf"
TOOLBAR_CUSTOM_FNAME = "toolbar-custom.conf"
GENERATED_FILE = "ncam.ngc"

CURRENT_PROJECT = ''

DEFAULT_EDITOR = 'gedit'

SUPPORTED_DATA_TYPES = ['sub-header', 'header', 'bool', 'boolean', 'int', 'gc-lines',
                        'tool', 'gcode', 'text', 'list', 'float', 'string', 'engrave',
                        'combo', 'combo-user', 'items', 'filename', 'prjname']
NUMBER_TYPES = ['float', 'int']
NO_ICON_TYPES = ['sub-header', 'header']
GROUP_HEADER_TYPES = ['items', 'sub-header', 'header']

XML_TAG = "lcnc-ncam"

HOME_PAGE = 'https://github.com/greatEndian/nativecam-py3-gtk3'
DONATE_URL = 'https://github.com/sponsors/greatEndian'

class tv_select :  # 'enum' items
    none, feature, items, header, param = list(range(5))

class search_warning :
    none, print_only, dialog = list(range(3))

#global variables
INCLUDE = []
DEFINITIONS = []
PIXBUF_DICT = {}
USER_VALUES = {}
USER_SUBROUTINES = []
TB_CATALOG = {}

# Units the generated PROGRAM is written in, as opposed to machine_metric,
# which is the machine's own units from the ini's TRAJ/LINEAR_UNITS. They are
# the same until a Workpiece asks otherwise, which is what lets an inch program
# come off a metric machine. Every float is stored in inches internally (see
# Parameter.set_value), so this is the single flag deciding the way out.
program_metric = True

# What a value read straight from the tool table must be multiplied by to reach
# program units. #5410 and friends are NOT converted by G20/G21 - verified with
# rs274 against a metric config, where a D0.8 tool reads 0.800000 under both -
# so every dimensional tool-table read has to scale itself. 1.0 whenever the
# program and the machine agree, which is every existing project.
TBL_SCALE = 1.0

# Lathe tool-tip compensation global-default overrides, mirrored from the
# preferences by Preferences.read() so a cfg <exec> can reach them - it runs
# against ncam's module namespace and cannot see the Preferences instance.
TIP_NOSE_DIA = 0.0
TIP_ORIENT = 0

# Whether to warn in the tree when the drawn contour cannot all be reached with
# the loaded tool. On by default - a part that will not come out to drawing is
# worth saying out loud - but switchable, because on some jobs the leftover
# metal is expected and the message is then just noise.
WARN_UNREACHABLE = True

# Decimal places for a value emitted in inches. Six is the metric convention
# and gives 0.001 mm there, but the same six in inches is only 0.025 mm, and
# the roughing loop steps level by level so that error accumulates - measured
# as 0.05 mm of drift across one test part before this was raised.
NGC_INCH_DIGITS = 8
EXCL_MESSAGES = {}
GLOBAL_PREF = None
UNIQUE_ID = 9
# True only when running `python3 ncam.py` (standalone dialog). GladeVCP embeds NCam and owns gtk.main();
# calling gtk.main_quit() from a handler there tears down GTK while the X embed is still dying → Gdk warnings.
NCAM_STANDALONE = False


def get_int(s10) :
    index = s10.find('.')
    if index > -1 :
        s10 = s10[:index]
    try :
        return int(s10)
    except ValueError:
        return 0

def get_float(s10) :
    try :
        return float(s10)
    except ValueError:
        try :
            return locale.atof(s10)
        except ValueError:
            return 0.0

def get_string(float_val, digits, localized = True):
    fmt = '%' + '0.%sf' % digits
    if localized :
        return (locale.format_string(fmt, float_val))
    else :
        return (fmt % float_val)

def search_path(warn, f, *argsl) :
    if f == "" :
        return None

    if os.path.isfile(f) :
        return f

    src = NCAM_DIR
    i = 0
    j = argsl.__len__()
    while i < j :
        src = os.path.join(src, argsl[i])
        i += 1
    src = os.path.abspath(os.path.join(src, f))
    if os.path.isfile(src) :
        return src

    for pa in [GRAPHICS_DIR, CFG_DIR, CATALOGS_DIR, LIB_DIR, PROJECTS_DIR] :
        src = os.path.join(pa, f)
        if os.path.isfile(src) :
            return src
    src = os.path.join(os.getcwd(), f)
    if os.path.isfile(src) :
        return src

    if warn > search_warning.none:
        print(_("Can not find file %(filename)s") % {"filename":f})

    if warn == search_warning.dialog :
        mess_dlg(_("Can not find file %(filename)s") % {"filename":f})
    return None

# The accent colour the shipped icon set is drawn in, and the window of hues
# around it that counts as "the accent". Everything else in an icon - the reds,
# yellows and blues - sits far outside this window and is never touched.
ICON_BASE_RGB = (68, 230, 68)
ICON_HUE_LO, ICON_HUE_HI = 100 / 360.0, 140 / 360.0
# None = leave the icons as drawn. Set from the display/icon_colour preference
# or the View > Icon Colour dialog.
ICON_ACCENT_RGB = None


def accent_from_pref(text):
    """Parse a display/icon_colour preference into an rgb tuple, or None.

    None means "leave the icons as drawn", and is also what anything
    unparseable gives - a malformed preference must not stop the program
    starting, and a silently as-drawn icon set is an obvious enough symptom.
    """
    if not text:
        return None
    try:
        parts = [int(v.strip()) for v in str(text).split(',')]
    except (TypeError, ValueError):
        return None
    if len(parts) != 3 or any(v < 0 or v > 255 for v in parts):
        return None
    return tuple(parts)


def set_icon_accent(rgb):
    """Choose the accent colour icons are recoloured to, or None for as-drawn.

    Clears the pixbuf cache so the next get_pixbuf reloads from disk and
    recolours from the original - recolouring is never applied on top of an
    already-recoloured icon, so repeated changes cannot drift.
    """
    global ICON_ACCENT_RGB
    if rgb is not None and tuple(rgb) == ICON_BASE_RGB:
        rgb = None
    ICON_ACCENT_RGB = tuple(rgb) if rgb is not None else None
    PIXBUF_DICT.clear()


def recolour_pixbuf(pix_buf, rgb):
    """Return a copy of pix_buf with its accent hue moved to rgb.

    Hue is replaced outright; saturation and value are scaled by whatever it
    takes to map the base accent exactly onto the target, so every shaded and
    anti-aliased variant of the accent moves with it and the icon keeps its
    original edges.
    """
    import colorsys
    th, ts, tv = colorsys.rgb_to_hsv(rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0)
    bh, bs, bv = colorsys.rgb_to_hsv(ICON_BASE_RGB[0] / 255.0,
                                     ICON_BASE_RGB[1] / 255.0,
                                     ICON_BASE_RGB[2] / 255.0)
    s_ratio = (ts / bs) if bs > 0.001 else 1.0
    v_ratio = (tv / bv) if bv > 0.001 else 1.0

    pix_buf = pix_buf.copy()
    n = pix_buf.get_n_channels()
    if n < 3:
        return pix_buf
    stride = pix_buf.get_rowstride()
    w, h = pix_buf.get_width(), pix_buf.get_height()
    data = bytearray(pix_buf.get_pixels())

    for y in range(h):
        row = y * stride
        for x in range(w):
            i = row + x * n
            r, g, b = data[i], data[i + 1], data[i + 2]
            if n > 3 and data[i + 3] < 20:
                continue
            mx, mn = max(r, g, b), min(r, g, b)
            if mx == 0 or (mx - mn) / mx < 0.12:
                continue
            ph, ps, pv = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
            if not (ICON_HUE_LO <= ph <= ICON_HUE_HI):
                continue
            nr, ng, nb = colorsys.hsv_to_rgb(th, min(1.0, ps * s_ratio),
                                             min(1.0, pv * v_ratio))
            data[i] = int(round(nr * 255))
            data[i + 1] = int(round(ng * 255))
            data[i + 2] = int(round(nb * 255))

    return GdkPixbuf.Pixbuf.new_from_bytes(
        GLib.Bytes.new(bytes(data)), pix_buf.get_colorspace(),
        pix_buf.get_has_alpha(), pix_buf.get_bits_per_sample(), w, h, stride)


def get_pixbuf(icon, size) :
    if size < 16 :
        size = 16
    if ((icon is None) or (icon.strip() == "")) :
        if DEFAULT_USE_NO_ICON:
            return None
        else :
            icon = NO_ICON_FILE

    icon_id = icon + str(size)

    if (icon_id) in PIXBUF_DICT :
        return PIXBUF_DICT[icon_id]

    icon_fname = search_path(search_warning.none, icon, GRAPHICS_DIR)
    if icon_fname is not None :
        try :
            pix_buf = GdkPixbuf.Pixbuf.new_from_file_at_size(icon_fname, size, size)
            if ICON_ACCENT_RGB is not None :
                try :
                    pix_buf = recolour_pixbuf(pix_buf, ICON_ACCENT_RGB)
                except Exception :
                    pass
            PIXBUF_DICT[icon_id] = pix_buf
            return pix_buf
        except GLib.Error as err :
            print(err)
            PIXBUF_DICT[icon_id] = None
    return None

def translate(fstring):
    # translate the glade file when testing translation
    txt2 = fstring.split('\n')
    fstring = ''
    for line in txt2 :
        inx = line.find('translatable="yes">')
        if inx > -1 :
            inx2 = line.find('</')
            txt = line[inx + 19:inx2]
            line = re.sub(r'%s' % txt, '%s' % _(txt), line)
        fstring += (line + '\n')
    return fstring

def mess_dlg(mess, title = "NativeCAM", parent=None):
    if parent is None:
        active = [w for w in gtk.Window.list_toplevels() if w.get_visible()]
        parent = active[0] if active else None
    dlg = gtk.MessageDialog(transient_for = parent,
        modal = True,
        destroy_with_parent = True,
        message_type = gtk.MessageType.WARNING,
        buttons = gtk.ButtonsType.OK,
        text = '%s' % mess)
    dlg.set_title(title)
    dlg.set_keep_above(True)
    dlg.run()
    dlg.destroy()

def mess_yesno(mess, title = "", parent=None):
    return mess_with_buttons(mess, ('gtk-yes', gtk.ResponseType.YES,
                             'gtk-no', gtk.ResponseType.NO), title, parent=parent) == gtk.ResponseType.YES

def mess_with_buttons(mess, buttons, title = "", parent=None):
    if parent is None:
        active = [w for w in gtk.Window.list_toplevels() if w.get_visible()]
        parent = active[0] if active else None
    mwb = gtk.Dialog(transient_for = parent,
                     buttons = buttons,
                     flags = gtk.DialogFlags.MODAL | gtk.DialogFlags.DESTROY_WITH_PARENT,
          )
    mwb.set_title(title)
    finbox = mwb.get_content_area()
    l = gtk.Label(label=mess)
    finbox.pack_start(l, True, True, 0)
    mwb.set_keep_above(True)
    mwb.show_all()
    response = mwb.run()
    mwb.hide()
    mwb.destroy()
    return response

class copymode:  # 'enum' items
    one_at_a_time, yes_to_all, no_to_all = list(range(3))

def copy_dir_recursive(fromdir, todir,
                       update_ct = 0,
                       mode = copymode.one_at_a_time,
                       overwrite = False,
                       verbose = False) :
    if not os.path.isdir(todir) :
        os.makedirs(todir, 0o755)

    for p in os.listdir(fromdir) :
        frompath = os.path.join(fromdir, p)
        topath = os.path.join(todir, p)
        if os.path.isdir(frompath) :
            mode, update_ct = copy_dir_recursive(frompath, topath,
                                      update_ct = update_ct,
                                      mode = mode,
                                      overwrite = overwrite,
                                      verbose = verbose)
            continue

        # copy files
        if not os.path.isfile(topath) or overwrite :
            shutil.copy(frompath, topath)
            update_ct += 1
            continue
        else :  # local file exists and not overwrite
            with open(frompath, 'rb') as f1, open(topath, 'rb') as f2:
                from_digest = hashlib.md5(f1.read()).digest()
                to_digest = hashlib.md5(f2.read()).digest()
            if from_digest == to_digest :
                # files are same
                if verbose :
                    print("NOT copying %s to %s" % (p, todir))
            else :  # files are different
                if (os.path.getctime(frompath) < os.path.getctime(topath)) :
                    # different and local file most recent
                    if verbose :
                        print(_('Keeping modified local file %(filename)s') % {"filename":p})
                    pass
                else :  # different and system file is most recent
                    if mode == copymode.yes_to_all :
                        if verbose :
                            print("copying %s to %s" % (p, todir))
                        shutil.copy(frompath, topath)
                        update_ct += 1
                        continue
                    if mode == copymode.no_to_all :
                        os.utime(topath, None)  # touch it
                        continue

                    buttons = ('gtk-yes', gtk.ResponseType.YES,
                             'gtk-no', gtk.ResponseType.NO,
                             'gtk-refresh', gtk.ResponseType.ACCEPT,
                             'gtk-cancel', gtk.ResponseType.NONE)
                    msg = (_('\nAn updated system file is available:\n\n%(frompath)s\n\n'
                        'YES     -> Use new system file\n'
                        'NO      -> Keep local file\n'
                        'Refresh -> Accept all new system files (don\'t ask again)\n'
                        'Cancel  -> Keep all local files (don\'t ask again)\n') \
                        % {'frompath':frompath})
                    ans = mess_with_buttons(msg, buttons,
                                            title = _("NEW file version available"))

                    # set copymode
                    if ans == gtk.ResponseType.YES :
                        pass
                    elif ans == gtk.ResponseType.ACCEPT :
                        mode = copymode.yes_to_all
                    elif ans == gtk.ResponseType.NONE :
                        mode = copymode.no_to_all
                    elif ans == gtk.ResponseType.NO :
                        pass
                    else :
                        ans = gtk.gtk.ResponseType.NO  # anything else (window close etc)

                    # copy or touch
                    if ans == gtk.ResponseType.YES or mode == copymode.yes_to_all :
                        if verbose:
                            print("copying %s to %s" % (p, todir))
                        shutil.copy(frompath, topath)
                        update_ct += 1

                    if ans == gtk.ResponseType.NO or mode == copymode.no_to_all :
                        os.utime(topath, None)  # touch it (update timestamp)

    return mode, update_ct

def err_exit(errtxt):
    print(errtxt)
    mess_dlg(errtxt)
    sys.exit(1)

if platform.system() != 'Windows' :
    try :
        import linuxcnc
    except ImportError as detail :
        err_exit(_('NativeCAM failed to import the linuxcnc module. Is LinuxCNC installed or are you running this script inside a LinuxCNC environment?\n\nDetails: %s') % detail)

# One hidden Tk for Tcl "send" to Axis. A fresh Tk() on every auto-refresh makes Tk set
# XSetErrorHandler while GDK may have an error trap pushed → Gdk-WARNING (GladeVCP + GTK3).
_tk_axis_send_root = None

def _tk_axis_remote_open(fname):
    global _tk_axis_send_root
    if _tk_axis_send_root is None:
        _tk_axis_send_root = Tkinter.Tk()
        _tk_axis_send_root.withdraw()
    _tk_axis_send_root.tk.call("send", "axis", ("remote", "open_file_name", fname))

def require_ini_items(fname, ini_instance):
    global NCAM_DIR, NGC_DIR

    val = ini_instance.find('DISPLAY', 'NCAM_DIR')
    if val is None :
        err_exit(_('Ini file <%(inifilename)s>\n'
                    'must have entry for [DISPLAY]NCAM_DIR')
                % {'inifilename':fname})

    val = os.path.expanduser(val)
    if os.path.isabs(val) :
        NCAM_DIR = val
    else :
        NCAM_DIR = (os.path.realpath(os.path.dirname(fname) + '/' + val))

    val = ini_instance.find('DISPLAY', 'PROGRAM_PREFIX')
    if val is None :
        msg = _("There is no PROGRAM_PREFIX in ini file\n"
            "Edit to add in DISPLAY section\n\n"
            "PROGRAM_PREFIX = abs or relative path to scripts directory\n"
            "i.e. PROGRAM_PREFIX = ./scripts or ~/ncam/scripts")
        err_exit(msg)
    else :
        if ':' in val :
            val = val.split(':')[0]

    val = os.path.expanduser(val)
    if os.path.isabs(val) :
        NGC_DIR = val
    else :
        NGC_DIR = (os.path.realpath(os.path.dirname(fname) + '/' + val))

def require_ncam_lib(fname, ini_instance):
    # presumes already checked:[DISPLAY]NCAM_DIR
    # ini file must specify a [RS274NGC]SUBROUTINE_PATH that
    # includes NCAM_DIR + LIB_DIR (typ: [DISPLAY]NCAM_DIR/lib)
    require_lib = os.path.realpath(os.path.join(NCAM_DIR, LIB_DIR))
    found_lib_dir = False
    try :
        subroutine_path = ini_instance.find('RS274NGC', 'SUBROUTINE_PATH')
        if subroutine_path is None :
            err_exit(_('Required lib missing:\n\n'
                       '[RS274NGC]SUBROUTINE_PATH'))

        print("[RS274NGC]SUBROUTINE_PATH = %s\n  Real paths:" % subroutine_path)

        for i, d in enumerate(subroutine_path.split(":")):
            d = os.path.expanduser(d)
            if os.path.isabs(d) :
                thedir = d
            else :
                thedir = os.path.join(os.path.realpath(os.path.dirname(fname)), d)
            if os.path.isdir(thedir) :
                real_dir = os.path.realpath(thedir)
                print("   %s" % real_dir)
                if not found_lib_dir :
                    # Use os.path.samefile or string startswith on real paths
                    if os.path.exists(require_lib):
                        found_lib_dir = os.path.samefile(real_dir, require_lib) or real_dir.startswith(require_lib)
                    else:
                        found_lib_dir = real_dir.startswith(require_lib)

        print("")

        if not found_lib_dir :
            err_exit (_('\nThe required NativeCAM lib directory :\n<%(lib)s>\n\n'
                      'is not in [RS274NGC]SUBROUTINE_PATH:\n'
                      '<%(path)s>\n\nEdit ini and correct\n'
                    % {'lib':require_lib, 'path':subroutine_path}))

    except Exception as detail :
        err_exit(_('Required NativeCAM lib\n%(err_details)s') % {'err_details':detail})

def get_short_id():
    global UNIQUE_ID
    UNIQUE_ID += 1
    return str(UNIQUE_ID)

def create_M_file() :
    p = os.path.join(NCAM_DIR, NGC_DIR, 'M123')
    with open(p, 'w') as f :
        f.write("#!/usr/bin/env python\n# coding: utf-8\n")
        f.write("import os\nimport gi\ngi.require_version('Gtk', '3.0')\nfrom gi.repository import Gtk as gtk, GdkPixbuf\n\n")
        f.write("fname = '%s'\n" % os.path.join(NCAM_DIR, CATALOGS_DIR, 'no_skip_dlg.conf'))
        f.write("if os.path.isfile(fname) :\n    exit(0)\n\n")
        f.write("msg = '%s'\n" % _('Stop LinuxCNC program,&#10;toggle the shown button,&#10;then restart'))
        f.write("msg1 = '%s'\n" % _('Skip block not active'))
        f.write("icon_fname = '%s'\n\n" % os.path.join(NCAM_DIR, GRAPHICS_DIR, 'skip_block.png'))
        f.write("active = [w for w in gtk.Window.list_toplevels() if w.get_visible()]\n")
        f.write("parent_win = active[0] if active else None\n")
        f.write("dlg = gtk.MessageDialog(transient_for = parent_win, flags = gtk.DialogFlags.MODAL | gtk.DialogFlags.DESTROY_WITH_PARENT, type = gtk.MessageType.WARNING, buttons = gtk.ButtonsType.NONE, message_format = msg1)\n\n")
        f.write("dlg.set_title('NativeCAM')\ndlg.format_secondary_markup(msg)\n\n")
        f.write("img = gtk.Image()\n")
        f.write("img.set_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_size(icon_fname, 80, 80))\n")
        f.write("dlg.get_message_area().pack_start(img, True, True, 0)\n\n")
        f.write("cb = gtk.CheckButton(label = \"%s\")\n" % _("Do not show again"))
        f.write("dlg.get_content_area().pack_start(cb, True, True, 0)\n")
        f.write("dlg.add_button(\"gtk-ok\", gtk.ResponseType.OK).grab_focus()\n\n")
        f.write("dlg.set_keep_above(True)\ndlg.show_all()\ndlg.run()\n")
        f.write("if cb.get_active() :\n    open(fname, 'w').close()\n")
        f.write("exit(0)\n")

    os.chmod(p, 0o755)
    mess_dlg(_('LinuxCNC needs to be restarted now'))

class Tools(object):

    def __init__(self):
        self.table_fname = None
        self.list = ''
        self.orientation = 0

    def set_file(self, tool_table_file):
        fn = search_path(search_warning.dialog, tool_table_file)
        if fn is not None :
            self.table_fname = fn
            self.load_table()

    def load_table(self, *arg):
        self.table = None
        self.table = []
        if self.table_fname is not None :
            with open(self.table_fname) as f:
                tbl = f.read().split("\n")
            for s in tbl :
                s = s.strip()
                if ";" in s:
                    tnumber = '0'
                    torient = '0'
                    tdia = '0'
                    tfront = '0'
                    tback = '0'
                    txoff = '0'
                    tzoff = '0'
                    s = s.split(";")
                    tdesc = s[1][0:]
                    s = s[0][0:]
                    s1 = s.split(" ")
                    for s2 in s1 :
                        if (len(s2) > 1) :
                            if (s2[0] == 'T') :
                                tnumber = s2[1:]
                            elif (s2[0] == 'Q') :
                                torient = s2[1:]
                            elif (s2[0] == 'D') :
                                tdia = s2[1:]
                            elif (s2[0] == 'I') :
                                tfront = s2[1:]
                            elif (s2[0] == 'J') :
                                tback = s2[1:]
                            elif (s2[0] == 'X') :
                                txoff = s2[1:]
                            elif (s2[0] == 'Z') :
                                tzoff = s2[1:]
                    if tnumber != '0' :
                        if tdesc == '' :
                            tdesc = _('no description')

                        is_live = ('live' in tdesc.lower() or 'mill' in tdesc.lower())
                        # Grooving/parting insert width. The LinuxCNC tool table has no
                        # column for it, so it is read from the description the same way
                        # is_live is - a W token followed by a number, e.g. ";groove W3.0".
                        # The token must stand alone: preceded by start-of-string or
                        # whitespace and followed by whitespace or end-of-string, so an
                        # ISO holder code such as "SCLCR W1234-A" is rejected rather than
                        # read as a 1234 mm insert.
                        m_w = re.search(r'(?:^|\s)[Ww]([0-9]+(?:\.[0-9]+)?)(?=\s|$)', tdesc)
                        twidth = m_w.group(1) if m_w else '0'
                        # front/back angle (I/J), X/Z offsets and width appended after
                        # is_live so existing tool[3]=orient tool[4]=dia tool[5]=is_live
                        # indices stay valid
                        self.table.append([int(tnumber), tnumber, tdesc, torient, tdia, is_live,
                                           tfront, tback, txoff, tzoff, twidth])
        self.table.append ([0, '0', _('None'), '0', '0', False, '0', '0', '0', '0', '0'])
        self.table.sort()

        self.list = ''
        for tool in self.table :
            self.list += tool[1] + ' - ' + tool[2] + '=' + tool[1] + ':'
        self.list = self.list.rstrip(':')

    def get_text(self, tn):
        for tool in self.table :
            if tool[1] == tn :
                return tool[1] + ' - ' + tool[2]
        return '0 - ' + _('None')

    def save_tool_orient(self, tn):
        self.saved_tool = tn
        if tn == 0 :
            self.orientation = 0
        else :
            for tool in self.table :
                if tool[0] == tn :
                    self.orientation = get_int(tool[3])

    def is_live_tool(self, tn):
        for tool in self.table:
            if tool[0] == tn or tool[1] == str(tn):
                return tool[5]
        return False

    def get_tool_diameter(self, tn):
        for tool in self.table:
            if tool[0] == tn or tool[1] == str(tn):
                return get_float(tool[4])
        return 0.0

    def get_tool_nose_radius(self, tn):
        return self.get_tool_diameter(tn) / 2.0

    def get_tool_front_angle(self, tn):
        for tool in self.table:
            if tool[0] == tn or tool[1] == str(tn):
                return get_float(tool[6])
        return 0.0

    def get_tool_back_angle(self, tn):
        for tool in self.table:
            if tool[0] == tn or tool[1] == str(tn):
                return get_float(tool[7])
        return 0.0

    def get_tool_width(self, tn):
        # Grooving/parting insert width, from the W token in the tool description.
        # 0 means the token is absent - callers must treat that as "unknown" and
        # refuse to generate a groove rather than assuming a width.
        for tool in self.table:
            if tool[0] == tn or tool[1] == str(tn):
                return get_float(tool[10])
        return 0.0

    def get_tool_orient(self):
        return self.orientation

    def get_back_angle(self):
        """Back angle of the last tool selected in a Tool Change.

        The flank shadow needs it at generation time, where the polyline has no
        idea which tool it will run under - the Tool Change feature does, and it
        already tells TOOL_TABLE via save_tool_orient.
        """
        return self.get_tool_back_angle(getattr(self, 'saved_tool', 0))

    def save_flank_len(self, value):
        """Remember the flank length of the tool loaded from here on.

        It is a property of the INSERT, not of the cut, so it is set on the
        Tool Change and read by whatever comes after - the same route the tool
        number takes. There is no tool-table column for it: LinuxCNC's table
        carries D, I, J and Q but nothing about how far the body extends.
        """
        self.saved_flank_len = max(get_float(value), 0.0)

    def get_flank_len(self):
        """Flank length of the last tool change, 0 when none was given.

        0 means "treat the flank as unbounded", which is the conservative
        answer and what the shadow did before the field existed.
        """
        return getattr(self, 'saved_flank_len', 0.0)


def tip_comp_inputs():
    """(nose radius, orientation) as the generated G-code will resolve them.

    Compensating in CAM has to offset the path at generation time, so it needs
    the same two numbers lib/lathe/tip_comp_dia.ngc resolves at runtime, by the
    same rules - the tool table's own D/#5410 and Q/#5413 when it carries them,
    otherwise the preference overrides. Diverging here would offset the path by
    one radius while the machine believes another.

    D is scaled by TBL_SCALE: tool-table reads are NOT converted by G20/G21, so
    an inch program reading a metric table needs it, exactly as the .ngc does.

    Returns (0.0, 0) when neither source knows, which callers must refuse on
    rather than treat as "no compensation needed".
    """
    tn = getattr(TOOL_TABLE, 'saved_tool', 0)
    nose_r = TOOL_TABLE.get_tool_nose_radius(tn) * TBL_SCALE
    if nose_r <= 0.0:
        nose_r = TIP_NOSE_DIA / 2.0
    orient = TOOL_TABLE.get_tool_orient()
    if orient <= 0:
        orient = TIP_ORIENT
    return nose_r, orient


def tool_wedge():
    """(centre-line angle, included angle) of the loaded tool, in degrees.

    Read from the tool table's I and J - the front and back angles of the two
    cutting edges, measured from Z+ - rather than from the orientation number,
    which only knows nine directions and nothing at all about how wide the
    insert is.

        centre line = (I + J) / 2      included angle = |J - I|

    Verified against the demo table: every insert comes out at 60 degrees
    included, the parting blade at 0, and the centre lines match the CL values
    written in that table's own comments. (T6 and T7 are the exception - their
    comments read CL0 and CL90 where the arithmetic gives 90 and 0. The
    arithmetic agrees with LinuxCNC's orientation table, so those two comments
    are simply swapped.)

    Returns (None, None) when the tool table carries no angles, so callers can
    fall back rather than draw a tool that is 0 degrees wide.
    """
    tn = getattr(TOOL_TABLE, 'saved_tool', 0)
    front = TOOL_TABLE.get_tool_front_angle(tn)
    back = TOOL_TABLE.get_tool_back_angle(tn)
    if front == 0.0 and back == 0.0:
        return None, None
    return (front + back) / 2.0, abs(back - front)


class VKB(object):

    def __init__(self, toplevel, tooltip, min_value, max_value, data_type, convertible) :
        self.dlg = gtk.Dialog(parent=toplevel, flags=gtk.DialogFlags.DESTROY_WITH_PARENT)
        self.dlg.set_decorated(False)
        self.dlg.set_border_width(3)
        self.dlg.set_property("skip-taskbar-hint", True)

        lbl = gtk.Label(label='')
        lbl.set_line_wrap(True)
        self.dlg.get_content_area().pack_start(lbl, False, False, 0)
        lbl.set_markup(tooltip)

        self.entry = gtk.Label(label='')
        self.entry.set_halign(gtk.Align.END)
        self.entry.set_valign(gtk.Align.CENTER)
        self.entry.set_property('ellipsize', pango.EllipsizeMode.START)
        self.min_value = min_value
        self.max_value = max_value
        self.data_type = data_type
        self.convertible_units = convertible

        box = gtk.EventBox()

        box.add(self.entry)
        frame = gtk.Frame()
        frame.add(box)
        frame.set_hexpand(True)
        frame.set_vexpand(True)

        tbl = gtk.Grid(column_homogeneous=True, row_homogeneous=True)
        tbl.attach(frame, 0, 0, 5, 1)

        self.dlg.get_content_area().pack_start(tbl, True, True, 0)

        btn = gtk.Button(label=_('BS'))
        btn.connect("clicked", self.input, 'BS')
        btn.set_can_focus(False)
        tbl.attach(btn, 4, 2, 1, 1)

        i = 0
        for lbl in ['F2', 'Pi', '()', '=', 'C'] :
            btn = gtk.Button(label=lbl)
            btn.connect("clicked", self.input, lbl)
            btn.set_can_focus(False)
            tbl.attach(btn, i, 1, 1, 1)
            i = i + 1

        i = 2
        for lbl in ['/', '*', '-', '+'] :
            btn = gtk.Button(label=lbl)
            btn.connect("clicked", self.input, lbl)
            btn.set_can_focus(False)
            tbl.attach(btn, 3, i, 1, 1)
            i = i + 1

        k = 10
        for i in range(2, 5) :
            k = k - 3
            for j in range(0, 3):
                lbl = str(k + j)
                btn = gtk.Button(label=lbl)
                btn.connect("clicked", self.input, lbl)
                btn.set_can_focus(False)
                tbl.attach(btn, j, i, 1, 1)

        if (self.min_value < 0.0) :
            btn = gtk.Button(label='+/-')
            btn.connect("clicked", self.input, '+/-')
            btn.set_can_focus(False)
            tbl.attach(btn, 2, 5, 1, 1)
            last_col = 2
        else :
            last_col = 3

        if self.data_type == 'float' :  # and get_int(self.digits) > 0 :
            btn = gtk.Button(label=decimal_point)
            btn.connect("clicked", self.input, decimal_point)
            btn.set_can_focus(False)
            tbl.attach(btn, last_col - 1, 5, 1, 1)
            last_col = last_col - 1

        btn = gtk.Button(label='0')
        btn.connect("clicked", self.input, '0')
        btn.set_can_focus(False)
        tbl.attach(btn, 0, 5, last_col, 1)

        btn = gtk.Button()
        img = gtk.Image()
        btn = gtk.Button(label="Esc")
        btn.connect("clicked", self.cancel)
        btn.set_can_focus(False)
        tbl.attach(btn, 4, 3, 1, 1)
        
        if self.convertible_units :
            btn = gtk.Button()
            img = gtk.Image()
            img.set_from_pixbuf(get_pixbuf('mm2in.png', treeview_icon_size))
            btn.set_image(img)
            btn.connect("clicked", self.input, 'CV')
            btn.set_can_focus(False)
            tbl.attach(btn, 4, 4, 1, 1)

        self.OKbtn = gtk.Button(label="OK")
        self.OKbtn.connect("clicked", self.ok)
        self.OKbtn.set_can_focus(False)
        if self.convertible_units :
            tbl.attach(self.OKbtn, 4, 5, 1, 1)
        else :
            tbl.attach(self.OKbtn, 4, 4, 1, 2)

        self.dlg.connect('key-press-event', self.key_press_event)
        self.focus_id = self.dlg.connect('focus-out-event', self.focus_out)
        self.dlg.set_keep_above(True)

    def __enter__(self):
        self.not_allowed_msg = _("Not allowed - F2 edit")
        self.err_msg = _("Error - F2 edit")
        return self

    def initvalue(self, value, saved, initialize):
        self.entry.set_markup('<b>%s</b>' % value)
        self.save_edit = saved
        self.initialize = initialize

    def run(self, not_allowed):

        def show_error(errm) :
            self.entry.set_markup('<b>%s</b>' % errm)
            self.initialize = True

        self.opened_paren = 0
        while True :
            self.convert_units = False
            self.OKbtn.grab_focus()
            response = self.dlg.run()
            if response == gtk.ResponseType.OK:
                if self.entry.get_text() in ['', self.not_allowed_msg, self.err_msg] :
                    self.entry.set_markup('<b>0</b>')
                is_good, rval = self.compute(self.entry.get_text())
                if not is_good :
                    show_error(self.err_msg)
                elif self.data_type == 'int' :
                    val = int(rval)
                    a_min = int(self.min_value)
                    a_max = int(self.max_value)

                    if val > a_max :
                        val = a_max
                    elif val < a_min :
                        val = a_min

                    if not_allowed is not None :
                        for na in not_allowed.split(':') :
                            if get_int(na) == val :
                                is_good = False
                                show_error(self.not_allowed_msg)
                                break
                    if is_good :
                        return response, str(val)
                else:
                    if self.convert_units :
                        if default_metric :
                            rval = rval * 25.4
                        else :
                            rval = rval / 25.4

                    if rval > self.max_value :
                        rval = self.max_value
                    elif rval < self.min_value :
                        rval = self.min_value

                    if not_allowed is not None :
                        for na in not_allowed.split(':') :
                            if get_float(na) == rval :
                                is_good = False
                                show_error(self.not_allowed_msg)
                                break
                    if is_good :
                        return response, str(rval)
            else :
                return response, None

    def input(self, btn, data):
        if self.initialize :
            lbl = '0'
            self.initialize = False
            self.opened_paren = 0
        else :
            lbl = self.entry.get_text()
            if lbl in ['0.0', '0.00', '0.000', '0.0000', '0.00000', '0.000000'] :
                lbl = '0'

        if data == 'C' :
            self.entry.set_markup('<b>0</b>')
            self.opened_paren = 0

        elif data == '=' :
            is_good, rval = self.compute(self.entry.get_text())
            if not is_good :
                self.show_error(_("Error - F2 to edit"))
            elif self.data_type == 'int' :
                self.entry.set_markup('<b>%d</b>' % int(rval))
            else :
                self.entry.set_markup('<b>%s</b>' % locale.format_string('%0.6f', rval))

        elif data == 'F2' :
            self.entry.set_markup('<b>%s</b>' % self.save_edit)

        elif data == 'BS' :
            if (len(lbl) == 1) or lbl == 'Pi':
                self.input(None, 'C')
                return
            elif lbl[-1] == 'i' :
                self.entry.set_markup('<b>%s</b>' % lbl[0:-2])
            elif lbl[-1] == ')' :
                self.opened_paren += self.opened_paren
                self.entry.set_markup('<b>%s</b>' % lbl[0:-1])
            elif lbl[-1] == '(' :
                self.entry.set_markup('<b>%s</b>' % lbl[0:-1])
                self.opened_paren -= 1
            else :
                self.entry.set_markup('<b>%s</b>' % lbl[0:-1])

        elif data == 'CV' :
            self.convert_units = True
            self.dlg.response(gtk.ResponseType.OK)

        elif data == '+/-' :
            if lbl == '0' :
                self.entry.set_markup('<b>-</b>')
            elif lbl.find('-') == 0 :
                self.entry.set_markup('<b>%s</b>' % lbl[1:])
            else :
                self.entry.set_markup('<b>-%s</b>' % lbl)

        elif data == 'Pi' :
            if lbl == '0' :
                self.entry.set_markup('<b>%s</b>' % data)
            elif lbl[-1] in ['+', '-', '*', '/', '('] :
                self.entry.set_markup('<b>%s%s</b>' % (lbl, data))

        elif data in ['*', '/', '+'] :
            if lbl != '0' and not lbl[-1] in ['+', '-', '*', '/', '('] :
                self.entry.set_markup('<b>%s%s</b>' % (lbl, data))

        elif data == '()' :
            if lbl == '0' :
                self.entry.set_markup('<b>(</b>')
                self.opened_paren = 1
            elif lbl[-1] in ['+', '-', '*', '/', '('] :
                self.entry.set_markup('<b>%s(</b>' % lbl)
                self.opened_paren += 1
            elif lbl[-1] not in ['+', '-', '*', '/', '('] :
                if self.opened_paren > 0 :
                    self.entry.set_markup('<b>%s)</b>' % lbl)
                    self.opened_paren -= 1

        elif data == decimal_point :
            if lbl == '0' :
                self.entry.set_markup('<b>0%s</b>' % data)
            elif lbl[-1] in ['+', '-', '*', '/', '('] :
                self.entry.set_markup('<b>%s0%s</b>' % (lbl, data))
            elif lbl[-1] >= '0' and lbl[-1] <= '9' :
                j = len(lbl)
                i = 0
                while (i < j) :
                    car = lbl[-i]
                    i += 1
                    if car == decimal_point :
                        return
                    if car in ['+', '-', '*', '/', '('] :
                        self.entry.set_markup('<b>%s%s</b>' % (lbl, data))
                        return
                self.entry.set_markup('<b>%s%s</b>' % (lbl, data))

        else :
            if lbl == '0' :  # numbers and minus sign
                self.entry.set_markup('<b>%s</b>' % data)
            elif lbl[-1] not in [')', 'i'] :
                self.entry.set_markup('<b>%s%s</b>' % (lbl, data))

    def key_press_event(self, win, event):
        key_press_const = getattr(gdk, "KEY_PRESS", getattr(getattr(gdk, "EventType", object), "KEY_PRESS", None))
        if key_press_const is not None and event.type == key_press_const:
            k_name = gdk.keyval_name(event.keyval)
#            print(k_name)
            if ((k_name >= 'KP_0' and k_name <= 'KP_9') or \
                    (k_name >= '0' and k_name <= '9')) :
                self.input(None, k_name[-1])
            elif k_name in ['KP_Decimal', 'period', 'comma', 'KP_Separator'] :
                if (self.data_type == 'float'):
                    self.input(None, decimal_point)
            elif k_name in ['KP_Divide', 'slash'] :
                self.input(None, '/')
            elif k_name in ['KP_Multiply', 'asterisk'] :
                self.input(None, '*')
            elif k_name in ['parenleft', 'parenright'] :
                self.input(None, '()')
            elif k_name == 'F2' :
                self.input(None, 'F2')
            elif k_name in ['C', 'c'] :
                self.input(None, 'C')
            elif k_name == 'equal' :
                self.input(None, '=')
            elif k_name in ['KP_Subtract', 'minus'] :
                self.input(None, '-')
            elif k_name in ['KP_Add', 'plus'] :
                self.input(None, '+')
            elif k_name == 'BackSpace' :
                self.input(None, 'BS')
            elif k_name in ['KP_Enter', 'Return', 'space']:
                self.dlg.response(gtk.ResponseType.OK)

    def ok(self, btn):
        self.is_closing = True
        self.convert_units = False
        self.dlg.response(gtk.ResponseType.OK)

    def cancel(self, btn):
        self.is_closing = True
        self.dlg.response(gtk.ResponseType.CANCEL)

    def focus_out(self, widget, event):
        if getattr(self, 'is_closing', False): return
        self.is_closing = True
        if vkb_cancel_on_out:
            self.dlg.response(gtk.ResponseType.CANCEL)
        else :
            self.dlg.response(gtk.ResponseType.OK)

    def compute(self, input_string):
        while input_string.count('(') > input_string.count(')') :
            input_string = input_string + ')'
        self.opened_paren = 0
        self.save_edit = input_string

        for i in('-', '+', '/', '*', '(', ')'):
            input_string = input_string.replace(i, " %s " % i)
        input_string = input_string.replace('Pi', str(math.pi))

        qualified = ''
        for i in input_string.split():
            try:
                i = str(locale.atof(i))
                qualified = qualified + str(float(i))
            except ValueError:
                qualified = qualified + i

        try :
            return True, eval(qualified)
        except Exception:
            return False, 0.0

    def __exit__(self, type, value, traceback):
        self.is_closing = True
        self.dlg.destroy() 
        self.dlg = None


class CellRendererMx(gtk.CellRendererText):

    def __init__(self, treeview) :
        gtk.CellRendererText.__init__(self)
        self.set_property('xpad', 2)
        self.set_property("wrap-mode", 2)
        self.set_property("editable", True)

        self.max_value = 999999.9
        self.min_value = -999999.9
        self.data_type = 'string'
        self.tv = treeview
        self.options = ''
        self.param_value = ''
        self.combo_values = []
        self.tooltip = ''
        self.preedit = None
        self.edited = None
        self.refresh_fn = None
        self.inputKey = ''
        self.tool_list = []
        self.not_allowed = None
        self.convertible_units = False
        self.convert_units = False
        self.save_edit = ''
        self.opened_paren = 0

    def set_convertible_units(self, value):
        self.convertible_units = value

    def set_tooltip(self, value):
        self.tooltip = value

    def set_max_value(self, value):
        self.max_value = value

    def set_param_value(self, value):
        self.param_value = value

    def set_not_allowed(self, value):
        self.not_allowed = value

    def set_min_value(self, value):
        self.min_value = value

    def set_data_type(self, value):
        self.data_type = value

    def set_edit_datatype(self, value):
        self.editdata_type = value

    def set_refresh_fn(self, value):
        self.refresh_fn = value

    def set_Input(self, value):
        self.inputKey = value

    def set_fileinfo(self, patrn, mime_type, filter_name):
        self.pattern = patrn
        self.mime_type = mime_type
        self.filter_name = filter_name

    def set_toolinfo(self, toollist):
        self.tool_list = toollist

    def set_options(self, value):
        self.options = value.replace('&#176;', '°')

    def set_digits(self, value):
        self.digits = value

    def set_preediting(self, value):
        self.preedit = value

    def get_treeview(self):
        return self.tv

    def do_get_size(self, widget, cell_area):
        return (gtk.CellRendererText.do_get_size(self, widget, cell_area))

    def edit_number(self, time_out = 0.05) :

        with VKB(self.tv.get_toplevel(), self.tooltip, self.min_value, self.max_value,
                 self.editdata_type, self.convertible_units) as vkb :

            status, tree_x, tree_y = self.tv.get_bin_window().get_origin()
            tree_w, tree_h = self.tv.get_allocated_width(), self.tv.get_allocated_height()

            vkb.dlg.set_size_request(vkb_width, vkb_height)
            vkb.dlg.resize(vkb_width, vkb_height)

            x = tree_w - vkb_width
            if x > self.cell_area.x :
                x = self.cell_area.x
            y = tree_y + self.cell_area.y + self.cell_area.height
            vkb.dlg.move(tree_x + x + 2, y)

            initialize = self.inputKey == ''
            if not initialize :
                if ((self.data_type == 'int') and \
                        (decimal_point in self.inputKey)) or \
                        (self.inputKey == 'BS') :
                    vkb.initvalue('0', self.param_value, initialize)
                else :
                    vkb.initvalue(self.inputKey, self.param_value, initialize)

                self.inputKey = ''
            else :
                vkb.initvalue(self.param_value, self.param_value, initialize)

            vkb.dlg.show_all()
            return vkb.run(self.not_allowed)

    def edit_list(self, time_out = 0.05):
        # must reset here: set True once this popup closes, and never reset
        # since, so every popup after the first silently ignored its own
        # focus-out-event and could only be dismissed by clicking a row -
        # clicking away instead left the modal .run() loop blocked forever
        self.lst_is_closing = False
        self.list_window = gtk.Dialog(parent=self.tv.get_toplevel(), flags=gtk.DialogFlags.DESTROY_WITH_PARENT)
        self.list_window.set_border_width(0)
        self.list_window.set_decorated(False)
        self.list_window.set_property("skip-taskbar-hint", True)
        
        sw = gtk.ScrolledWindow()
        sw.set_shadow_type(gtk.ShadowType.ETCHED_IN)
        sw.set_policy(gtk.PolicyType.NEVER, gtk.PolicyType.AUTOMATIC)
        
        self.list_window.get_content_area().pack_start(sw, True, True, 0)

        self.list_window.realize()
        self.list_window.resize(1, 1)
        lw, base_height = self.list_window.get_size()

        ls = gtk.ListStore(str, str)
        active_row = 0
        count = 0
        for option in self.options.split(":") :
            opt = option.split('=')
            ls.append([opt[0], opt[1]])
            if (opt[1] == self.param_value) :
                active_row = count
            count += 1

        ls_view = gtk.TreeView(ls)
        ls_view.set_headers_visible(False)
        tvcolumn = gtk.TreeViewColumn('Column 0')
        ls_view.append_column(tvcolumn)
        rdr = gtk.CellRendererText()
        row_height = self.cell_area.height - 4
        rdr.set_fixed_size(self.cell_area.width, row_height)
        tvcolumn.pack_start(rdr, True)
        tvcolumn.add_attribute(rdr, 'text', 0)
        tvcolumn.set_min_width(self.cell_area.width - 2)
        self.list_window.connect('focus-out-event', self.list_out)
        ls_view.connect('button-release-event', self.list_btn_released)
        ls_view.connect('key-press-event', self.list_keypress)
        sw.add(ls_view)

        lw_height = base_height + 4 + self.cell_area.height * min(count, 10)
        status, tree_x, tree_y = self.tv.get_bin_window().get_origin()
        tree_w, tree_h = self.tv.get_allocated_width(), self.tv.get_allocated_height()
        y = tree_y + min(self.cell_area.y, tree_h - lw_height)

        self.list_window.move(tree_x + self.cell_area.x - 5, y - 2)
        self.list_window.resize(tree_w - self.cell_area.x + 5, lw_height)
        position = int(sw.get_vadjustment().get_upper() * active_row / count)
        sw.get_vadjustment().set_value(position)

        self.list_window.show_all()
        ls_view.set_cursor(active_row)
        ls_view.grab_focus()

        response = self.list_window.run()

        if response == gtk.ResponseType.OK:
            model, ls_itr = ls_view.get_selection().get_selected()
            if ls_itr is not None:
                new_val = model.get_value(ls_itr, 1)
            else:
                new_val = self.param_value
        else:
            new_val = self.param_value

        self.lst_is_closing = True
        self.list_window.destroy()

        return response, new_val

    def edit_string(self, time_out = 0.05):
        # same reset as edit_list's lst_is_closing - without it, every
        # popup after the first ignores its own focus-out-event forever
        self.str_is_closing = False
        self.stringedit_window = gtk.Dialog(parent=self.tv.get_toplevel(), flags=gtk.DialogFlags.DESTROY_WITH_PARENT)
        self.stringedit_window.hide()
        self.stringedit_window.set_decorated(False)
        self.stringedit_window.set_border_width(0)
        self.stringedit_window.set_property("skip-taskbar-hint", True)

        self.stringedit_entry = gtk.Entry()
        self.stringedit_window.get_content_area().add(self.stringedit_entry)
        self.stringedit_entry.set_editable(True)

        self.stringedit_entry.connect('key-press-event', self.string_edit_keyhandler)

        # position the popup on the edited cell
        status, tree_x, tree_y = self.tv.get_bin_window().get_origin()
        (tree_w, tree_h) = self.tv.get_window().get_geometry()[2:4]
        x = tree_x + self.cell_area.x
        y = tree_y + self.cell_area.y
        self.stringedit_window.move(x - 4, y - 2)
        self.stringedit_window.resize(tree_w - self.cell_area.x + 4, self.cell_area.height)
        self.stringedit_window.show_all()
        self.stringedit_entry.grab_focus()
        self.stringedit_entry.connect('focus-out-event', self.string_edit_focus_out)

        if self.inputKey != 'BS' :
            self.stringedit_entry.set_text(self.param_value)
        self.inputKey = ''
        response = self.stringedit_window.run()
        if response == gtk.ResponseType.OK:
            new_val = self.stringedit_entry.get_text()
        else:
            new_val = self.param_value

        self.str_is_closing = True
        self.stringedit_window.destroy()
        return response, new_val

    def list_keypress(self, widget, event) :
        keyname = gdk.keyval_name(event.keyval)
        if keyname in ["Return", "KP_Enter", "space"] :
            self.list_window.response(gtk.ResponseType.OK)

    def list_out(self, widget, event):
        if getattr(self, 'lst_is_closing', False): return
        self.lst_is_closing = True
        self.list_window.response(gtk.ResponseType.CANCEL)

    def list_btn_released(self, widget, event):
        self.list_window.response(gtk.ResponseType.OK)

    def do_start_editing(self, event, treeview, path, background_area, \
                        cell_area, flags):

        if not self.get_property('editable'):
            self.inputKey = ''
            return None

        if self.preedit is None :
            self.inputKey = ''
            return None
        else :
            self.preedit(self, treeview, path)

        if self.editdata_type in GROUP_HEADER_TYPES or self.editdata_type == 'grayed' :
            self.inputKey = ''
            return None

        if self.editdata_type == 'prjname' :
            self.inputKey = ''
            return None


        self.cell_area = gdk.Rectangle()
        self.cell_area.x = cell_area.x
        self.cell_area.y = cell_area.y
        self.cell_area.width = cell_area.width
        self.cell_area.height = cell_area.height

        def defer_number():
            response, result = self.edit_number()
            if response == gtk.ResponseType.OK :
                self.edited(self, path, result)
            return False

        def defer_bool():
            if self.param_value == '0' :
                self.edited(self, path, '1')
            else :
                self.edited(self, path, '0')
            return False

        def defer_list():
            response, result = self.edit_list()
            if response == gtk.ResponseType.OK :
                self.edited(self, path, result)
            return False

        def defer_string():
            response, result = self.edit_string()
            if response == gtk.ResponseType.OK :
                self.edited(self, path, result)
            return False

        def defer_filename():
            filechooserdialog = gtk.FileChooserDialog(_("Open"), None,
                     gtk.FileChooserAction.OPEN,
                     ('gtk-cancel', gtk.ResponseType.CANCEL,
                     'gtk-ok', gtk.ResponseType.OK))
            try:
                filt = gtk.FileFilter()
                filt.set_name(self.filter_name)

                for option in self.mime_type.split(":") :
                    filt.add_mime_type(option)

                for option in self.pattern.split(":") :
                    filt.add_pattern(option)

                filechooserdialog.add_filter(filt)
                filechooserdialog.set_transient_for(treeview.get_toplevel())
                filechooserdialog.set_destroy_with_parent(True)
                filechooserdialog.set_keep_above(True)

                filt = gtk.FileFilter()
                filt.set_name(_("All files"))
                filt.add_pattern("*")
                filechooserdialog.add_filter(filt)

                if os.path.exists(self.param_value):
                    filechooserdialog.set_filename(self.param_value)
                else :
                    filechooserdialog.set_current_folder(os.getcwd())

                response = filechooserdialog.run()
                if response == gtk.ResponseType.OK:
                    result = filechooserdialog.get_filename()
                    self.edited(self, path, result)
            finally:
                filechooserdialog.destroy()
            return False

        def defer_text():
            # same reset as edit_list's lst_is_closing - without it, every
            # popup after the first ignores its own focus-out-event forever
            self.txt_is_closing = False
            self.selection = treeview.get_selection()
            self.treestore, self.treeiter = self.selection.get_selected()

            self.textedit_window = gtk.Dialog(parent=treeview.get_toplevel(), flags=gtk.DialogFlags.DESTROY_WITH_PARENT)
            self.textedit_window.set_decorated(False)
            self.textedit_window.set_property("skip-taskbar-hint", True)

            self.textedit = gtk.TextView()
            self.textedit.set_editable(True)
            self.textbuffer = self.textedit.get_buffer()
            self.textedit.set_wrap_mode(gtk.WRAP_WORD)
            self.textbuffer.set_property('text', self.get_property('text'))

            self.textedit_window.connect('key-press-event', self.text_edit_keyhandler)
            self.textedit_window.connect('focus-out-event', self.text_edit_focus_out, path)

            scrolled_window = gtk.ScrolledWindow()
            scrolled_window.set_policy(gtk.PolicyType.AUTOMATIC, gtk.PolicyType.AUTOMATIC)

            scrolled_window.add(self.textedit)
            self.textedit_window.get_content_area().add(scrolled_window)
            self.textedit_window.realize()

            status, tree_x, tree_y = treeview.get_bin_window().get_origin()
            y = tree_y + self.cell_area.y
            tree_w = treeview.get_allocated_width()

            self.textedit_window.move(tree_x, y + self.cell_area.height)
            self.textedit_window.resize(tree_w, self.cell_area.height + 60)
            self.textedit_window.show_all()

            response = self.textedit_window.run()
            if response == gtk.ResponseType.OK:
                (iter_first, iter_last) = self.textbuffer.get_bounds()
                text = self.textbuffer.get_text(iter_first, iter_last)
                self.edited(self, path, text)
                
            self.txt_is_closing = True
            self.textedit_window.destroy()
            if self.refresh_fn:
                self.refresh_fn(self.tv)
            return False

        if self.editdata_type in NUMBER_TYPES :
            GLib.idle_add(defer_number)
            return None

        elif self.editdata_type in ['bool', 'boolean']:
            if self.inputKey :
                self.inputKey = ''
                return None
            GLib.idle_add(defer_bool)
            return None

        elif self.editdata_type in ['combo-user', 'combo', 'tool']:
            self.inputKey = ''
            GLib.idle_add(defer_list)
            return None

        elif self.editdata_type in ['string', 'gcode'] :
            GLib.idle_add(defer_string)
            return None

        elif self.editdata_type == 'filename':
            if self.inputKey :
                self.inputKey = ''
            GLib.idle_add(defer_filename)
            return None

        else :  
            GLib.idle_add(defer_text)
            return None


    def do_render(self, cr, widget, background_area, cell_area, flags):
        if self.data_type in ['bool', 'boolean'] :
             cell_area.width = 30
             chk = gtk.CellRendererToggle()
             chk.set_active(self.param_value == '1')
             chk.render(cr, widget, background_area, cell_area, flags)
        else :
             gtk.CellRendererText.do_render(self, cr, widget, background_area, cell_area, flags)

    def string_edit_focus_out(self, widget, event):
        if getattr(self, 'str_is_closing', False): return
        self.str_is_closing = True
        self.stringedit_window.response(gtk.ResponseType.OK)

    def string_edit_keyhandler(self, widget, event):
        keyname = gdk.keyval_name(event.keyval)
        if keyname in ['Return', 'KP_Enter']:
            self.stringedit_window.response(gtk.ResponseType.OK)

    def text_edit_focus_out(self, widget, event, path):
        if getattr(self, 'txt_is_closing', False): return
        self.txt_is_closing = True
        self.textedit_window.response(gtk.ResponseType.OK)

    def text_edit_keyhandler(self, widget, event):
        keyname = gdk.keyval_name(event.keyval)
        if gdk.keyval_name(event.keyval) in ['Return', 'KP_Enter'] :
            if event.state & (gdk.ModifierType.SHIFT_MASK | gdk.ModifierType.CONTROL_MASK) :
                pass
            else :
                event.keyval = 0
                self.textedit_window.response(gtk.ResponseType.OK)

gobject.type_register(CellRendererMx)

class Parameter(object) :
    def __init__(self, ini = None, ini_id = None, xml = None) :
        self.attr = {}
        if ini is not None :
            self.from_ini(ini, ini_id)
        elif xml is not None :
            self.from_xml(xml)

    def __repr__(self) :
        return etree.tostring(self.to_xml(), pretty_print = True, encoding='unicode')

    def __delattr__(self, *args, **kwargs):
        return object.__delattr__(self, *args, **kwargs)

    def from_ini(self, ini, ini_id) :
        self.attr = {}
        ini = dict(ini)
        for i in ini :
            self.attr[i] = ini[i]
        if "type" not in self.attr or self.attr["type"] not in SUPPORTED_DATA_TYPES :
            self.attr["type"] = 'string'

        if "call" not in self.attr :
            self.attr["call"] = "#" + ini_id

    def from_xml(self, xml) :
        for i in list(xml.keys()) :
            self.attr[i] = xml.get(i)

    def to_xml(self) :
        xml = etree.Element("param")
        for i in self.attr :
            xml.set(i, str(self.attr[i]))
        return xml

    def get_icon(self, icon_size) :
        icon = self.get_attr("icon")
        return get_pixbuf(icon, icon_size)

    def get_value(self, editor = False) :
        if self.get_type() == 'float' :
            if default_metric and "metric_value" in self.attr :
                return get_string(get_float(self.attr["value"]) * 25.4, 6, editor)
            else :
                return get_string(get_float(self.attr["value"]), 6, editor)
        else :
            return self.attr["value"] if "value" in self.attr else ""

    def get_ngc_value(self):
        if self.get_type() == 'gcode' :
            val = self.attr["value"] if "value" in self.attr else ""
            if val == '' :
                return '0'
            else :
                return val
        if self.get_type() == 'float' :
            # program_metric, not machine_metric: the value goes into the file,
            # so it must be in the units the file declares in its G20/G21.
            # An inch program needs more decimal places for the same resolution
            # - 6 of them is 0.001 mm in metric but 0.025 mm in inches, and the
            # roughing loop accumulates that error one level at a time.
            if program_metric and "metric_value" in self.attr :
                return get_string(get_float(self.attr["value"]) * 25.4, 6, False)
            else :
                return get_string(get_float(self.attr["value"]), NGC_INCH_DIGITS, False)
        else :
            return self.attr["value"] if "value" in self.attr else ""

    def set_value(self, new_val, parent) :
        done = False
        cancel = False
        if 'on_change' in self.attr :
            exec(self.attr['on_change'])
        if cancel :
            return False
        if not done :
            if self.get_type() == "float" :
                factor = 25.4 if (default_metric and "metric_value" in self.attr) else 1
                new_val = get_string(get_float(new_val) / factor, 10, False)
                old_val = get_string(get_float(self.attr["value"]), 10, False)
            else :
                old_val = self.attr["value"]
            if new_val == old_val :
                return False
            else :
                self.attr["value"] = new_val
        if 'value_changed' in self.attr :
            exec(self.attr['value_changed'])
        return True

    def get_display_string(self) :
        if self.get_type() == "float" :
            if default_metric and "metric_value" in self.attr :
                return get_string(get_float(self.attr["value"]) * 25.4, self.get_digits())
            else :
                return get_string(get_float(self.attr["value"]), self.get_digits())
        else :
            return self.attr["value"] if "value" in self.attr else ""

    def set_hidden(self, hide):
        if hide :
            self.attr['hidden'] = '2'
        elif self.get_hidden() :
            self.attr['hidden'] = '0'
            return 1
        return 0

    def get_grayed(self):
        return (self.attr["grayed"] == '1') if "grayed" in self.attr else False

    def set_grayed(self, value):
        if value :
            self.attr["grayed"] = '1'
        else :
            self.attr["grayed"] = '0'

    def change_group(self):
        t = self.get_type()
        if t in ['sub-header', 'header'] :
            if t == 'sub-header' :
                if 'header' in self.attr :
                    return False
                self.set_type('header')
            else :
                self.set_type('sub-header')
            return True
        return False

    def get_hidden(self):
        return ('hidden' in self.attr) and (self.attr['hidden'] == '2')

    def get_name(self) :
        return _(self.attr["name"]) if "name" in self.attr else ""

    def get_options(self):
        return _(self.attr["options"]) if "options" in self.attr else ""

    def get_type(self):
        return self.attr["type"]

    def set_type(self, new_type):
        self.attr['old_type'] = self.attr['type']
        self.attr['type'] = new_type
        if new_type == 'gcode' and default_metric and "metric_value" in self.attr :
            self.attr["value"] = self.attr["metric_value"]

    def revert_type(self):
        if 'old_type' in self.attr :
            if self.attr['old_type'] == 'float' :
                val = get_float(self.attr['value'])
                if val < get_float(self.get_min_value()) :
                    val = get_float(self.get_min_value())
                if val > get_float(self.get_max_value()) :
                    val = get_float(self.get_max_value())
                self.attr['value'] = str(val)
                self.attr['type'] = 'float'
            elif self.attr['old_type'] == 'int' :
                val = get_int(self.attr['value'])
                if val < get_int(self.get_min_value()) :
                    val = get_int(self.get_min_value())
                if val > get_int(self.get_max_value()) :
                    val = get_int(self.get_max_value())
                self.attr['value'] = str(val)
                self.attr['type'] = 'int'

    def get_tooltip(self):
        return _(self.attr["tool_tip"]) if "tool_tip" in self.attr else self.get_name()

    def get_attr(self, name) :
        return self.attr[name] if name in self.attr else None

    def get_digits(self):
        if self.get_type() == 'int' :
            return '0'
        else :
            return self.attr["digits"] if "digits" in self.attr else default_digits

    def set_digits(self, new_digits) :
        self.attr["digits"] = new_digits

    def get_min_value(self):
        min_v = self.attr["minimum_value"] if "minimum_value" in self.attr \
                        else "-999999.9"
        if self.get_type() == 'float' and default_metric and 'metric_value' in self.attr :
            return str(get_float(min_v) * 25.4)
        else :
            return min_v

    def get_max_value(self):
        max_v = self.attr["maximum_value"] if "maximum_value" in self.attr \
                        else "999999.9"
        if self.get_type() == 'float' and default_metric and 'metric_value' in self.attr :
            return str(get_float(max_v) * 25.4)
        else :
            return max_v

class Feature(object):
    def __init__(self, src = None, xml = None) :
        self.attr = {}
        self.param = []
        if src is not None :
            self.from_src(src)
        elif xml is not None :
            self.from_xml(xml)

    def __repr__(self) :
        return etree.tostring(self.to_xml(), pretty_print = True, encoding='unicode')

    def get_grayed(self):
        return (self.attr["grayed"] == '1') if "grayed" in self.attr else False

    def get_icon(self, icon_size) :
        return get_pixbuf(self.get_attr("icon"), icon_size)

    def get_value(self):
        return self.attr["value"] if "value" in self.attr else ""

    def get_version(self):
        return get_float(self.attr["version"]) if "version" in self.attr else 0.0

    def get_display_string(self):
        return self.get_value()

    def set_value(self, new_val):
        self.attr["value"] = new_val

    def get_type(self):
        return self.attr["type"] if "type" in self.attr else "string"

    def get_tooltip(self):
        s = _(self.attr["tool_tip"]) if "tool_tip" in self.attr else \
            _(self.attr["help"]) if "help" in self.attr else None
        return s.replace('&#176;', '°')

    def get_attr(self, attr) :
        return self.attr[attr] if attr in self.attr else None

    def get_param(self, param_id):
        for p in self.param :
            if 'call' in p.attr and p.attr['call'] == "#%s" % param_id :
                return p
        return None

    def get_name(self):
        return _(self.attr["name"]) if "name" in self.attr else _("unname")

    def from_src(self, src) :
        src_config = ConfigParser.ConfigParser()
        with io.open(src) as a_f:
            uf = a_f.read()
        f = str(uf)

        # remove _(" and ")
        f = re.sub(r"_\(\"", "", f)
        f = re.sub(r"\"\)", "", f)

        # add "." in the begining of multiline parameters to save indents
        f = re.sub(r"(?m)^(\ |\t)", r"\1.", f)
        src_config.read_string(f)
        # remove "." in the begining of multiline parameters to save indents
        conf = {}
        for section in src_config.sections() :
            conf[section] = {}
            for item in src_config.options(section) :
                s = src_config.get(section, item, raw = True)
                s = re.sub(r"(?m)^\.", "", " " + s)[1:]
                conf[section][item] = s
        self.attr = conf["SUBROUTINE"]

        ftype = self.attr["type"]
        if ftype is None :
            raise Exception(_('Type not defined for\n%s') % src)

        # get order
        if "order" not in self.attr :
            self.attr["order"] = []
        else :
            self.attr["order"] = self.attr["order"].upper().split()
        self.attr["order"] = [s if s[:6] == "PARAM_" else "PARAM_" + s \
                              for s in self.attr["order"]]

        self.attr['hidden_count'] = '0'
        # get params
        self.param = []
        parameters = self.attr["order"] + [p for p in conf if \
                    (p[:6] == "PARAM_" and p not in self.attr["order"])]
        for s in parameters :
            if s in conf :
                pn = s.lower()
                p = Parameter(ini = conf[s], ini_id = pn)

                p_id = "%s:%s" % (ftype, pn)
                if (p_id + '--type') in USER_VALUES :
                    p.set_type(USER_VALUES[p_id + '--type'])

                # set hidden as per user preferences
                if (p_id + '--hidden') in USER_VALUES :
                    p.set_hidden(True)
                    self.hide_field()

                if (p_id + '--grayed') in USER_VALUES :
                    p.attr["grayed"] = USER_VALUES[p_id + '--grayed']

                if (p_id + '--name') in USER_VALUES :
                    p.attr["name"] = USER_VALUES[p_id + '--name']

                if (p_id + '--value') in USER_VALUES :
                    p.attr["value"] = USER_VALUES[p_id + '--value']

                self.param.append(p)

        self.attr["id"] = ftype + '_000'

        # get gcode parameters
        for l in ["DEFINITIONS", "BEFORE", "CALL", "AFTER", "VALIDATION", "INIT"] :
            if l in conf and "content" in conf[l] :
                self.attr[l.lower()] = re.sub(r"(?m)\r?\n\r?\.", "\n",
                                              conf[l]["content"])
            else :
                self.attr[l.lower()] = ""

        parent = self
        exec(self.attr['init'])

    def from_xml(self, xml) :
        self.attr = {}
        for i in xml.keys() :
            self.attr[i] = xml.get(i)

        self.param = []
        for p in xml :
            self.param.append(Parameter(xml = p))

    def to_xml(self) :
        xml = etree.Element("feature")
        for i in self.attr :
            xml.set(i, str(self.attr[i]))

        for p in self.param :
            xml.append(p.to_xml())
        return xml

    def get_id(self, xml) :
        num = 1
        if xml is not None :
            # get smallest free name
            l = xml.findall(".//feature[@type='%s']" % self.attr["type"])
            num = max([get_int(i.get("id")[-3: ]) for i in l] + [0]) + 1
        self.attr["id"] = self.attr["type"] + "_%03d" % num

    def get_definitions(self) :
        s = self.attr["definitions"] if "definitions" in self.attr else ''
        if s != '' :
            s = self.process(s)
        return s

    def include(self, srce) :
        src = search_path(search_warning.dialog, srce, LIB_DIR)
        if src is not None:
            with io.open(src) as f:
                return f.read()
        return ''

    def include_once(self, src) :
        if src not in INCLUDE :
            INCLUDE.append(src)
            return self.include(src)
        return ""

    def replace_params(self, s):
        for p in self.param :
            if "call" in p.attr and "value" in p.attr :
                if p.attr['type'] == 'text' :
                    note_lines = p.get_value().split('\n')
                    lines = ''
                    for line in note_lines :
                        lines = lines + '( ' + line + ' )\n'
                    s = re.sub(r"%s([^A-Za-z0-9_]|$)" %
                        (re.escape(p.attr["call"])), r"%s\1" %
                        lines, s)
                elif p.attr['type'] == 'gc-lines' :
                    note_lines = p.get_value().split('\n')
                    lines = '\n'
                    for line in note_lines :
                        lines = lines + '\t' + line + '\n'
                    s = re.sub(r"%s([^A-Za-z0-9_]|$)" %
                        (re.escape(p.attr["call"])), r"%s\1" %
                        lines, s)

                else :
                    s = re.sub(r"%s([^A-Za-z0-9_]|$)" %
                       (re.escape(p.attr["call"])), r"%s\1" %
                       p.get_ngc_value(), s)
        return s

    def process(self, s, line_leader = '') :

        def eval_callback(m) :
            try :
                return str(eval(m.group(2), globals(), {"self":self}))
            except Exception:
                return ''

        def exec_callback(m) :
            s = m.group(2)

            # strip starting spaces
            s = s.replace("\t", " ")
            i = 1e10
            for l in s.split("\n") :
                if l.strip() != "" :
                    i = min(i, len(l) - len(l.lstrip()))
            if i < 1e10 :
                res = ""
                for l in s.split("\n") :
                    res += l[i:] + "\n"
                s = res

            old_stdout = sys.stdout
            redirected_output = StringIO()
            sys.stdout = redirected_output
            try :
                exec(s, globals(), {"self":self})
                out = redirected_output.getvalue()
            except Exception:
                out = ''
            finally :
                sys.stdout = old_stdout
            return out

        def subprocess_callback(m) :
            s = m.group(2)

            # strip starting spaces
            s = s.replace("\t", "  ")
            i = 1e10
            for l in s.split("\n") :
                if l.strip() != "" :
                    i = min(i, len(l) - len(l.lstrip()))
            if i < 1e10 :
                res = ""
                for l in s.split("\n") :
                    res += l[i:] + "\n"
                s = res
            try :
                output = subprocess.check_output([s], shell = True, stderr = subprocess.STDOUT)
                return output.decode('utf-8')
            except subprocess.CalledProcessError as e:
                msg = _('Error with subprocess: returncode = %(errcode)s\n'
                         'output = %(output)s\n'
                         'e= %(e)s\n') \
                         % {'errcode':e.returncode, 'output':e.output, 'e':e}
                print(msg)
                mess_dlg(msg)
                return ''

        def import_callback(m) :
            fname = m.group(2)
            fname = search_path(search_warning.dialog, fname, PROJECTS_DIR)
            if fname is not None :
                with open(fname) as f:
                    return str(f.read())

        s = self.replace_params(s)

        s = re.sub(r"#sub_name", "%s" % self.attr['name'], s)
        s = re.sub(r"%SYS_DIR%", "%s" % SYS_DIR, s)
        f_id = self.get_attr("id")
        s = re.sub(r"#self_id", "%s" % f_id, s)

        s = re.sub(r"(?i)(<import>(.*?)</import>)", import_callback, s)
        s = re.sub(r"(?i)(<eval>(.*?)</eval>)", eval_callback, s)
        s = re.sub(r"(?ims)(<exec>(.*?)</exec>)", exec_callback, s)
        s = re.sub(r"(?ims)(<subprocess>(.*?)</subprocess>)",
                   subprocess_callback, s)

        if "#ID" in s :
            if 'short_id' not in self.attr :
                self.attr['short_id'] = get_short_id()
            s = re.sub(r"#ID", "%s" % self.attr['short_id'], s)

        s = s.lstrip('\n').rstrip('\n\t')
        if s == '' :
            return ''
        if line_leader :
            result_s = '\n'
            for line in s.split('\n') :
                result_s += line_leader + line + '\n'
            return result_s + '\n'
        else :
            return '\n' + s + '\n\n'

    def getindent(self) :
        count = get_int(self.attr['indent']) if 'indent' in self.attr else 0
        return('\t' * count)

    def hide_field(self):
        if 'hidden_count' not in self.attr :
            self.attr['hidden_count'] = '1'
        else :
            self.attr['hidden_count'] = str(get_int(self.attr['hidden_count']) + 1)

    def show_all_fields(self):
        result = 0
        for p in self.param :
            result += p.set_hidden(False)
        self.attr['hidden_count'] = '0'
        return result > 0

    def has_hidden_fields(self):
        if 'hidden_count' in self.attr :
            return get_int(self.attr['hidden_count']) > 0
        else :
            return False

    def msg_inv(self, msg, msgid):
        msg = msg.replace('&#176;', '°')
        print('\n%(feature_name)s : %(msg)s' % {'feature_name':self.get_name(), 'msg':msg})

        if (("ALL:msgid-0" in EXCL_MESSAGES) or
                ("%s:msgid-0" % (self.get_type()) in EXCL_MESSAGES) or
                (("%s:msgid-%d" % (self.get_type(), msgid)) in EXCL_MESSAGES)) :
            return

        # create dialog with image and checkbox
        active = [w for w in gtk.Window.list_toplevels() if w.get_visible()]
        parent_win = active[0] if active else None
        dlg = gtk.MessageDialog(transient_for = parent_win,
            flags = gtk.DialogFlags.MODAL | gtk.DialogFlags.DESTROY_WITH_PARENT,
            type = gtk.MessageType.WARNING,
            buttons = gtk.ButtonsType.NONE,
            message_format = self.get_name())
        dlg.set_title('NativeCAM')
        dlg.format_secondary_text(msg)
        img = gtk.Image()
        img.set_from_pixbuf(self.get_icon(add_dlg_icon_size))
        dlg.set_image(img)
        cb = gtk.CheckButton(label = _("Do not show again"))
        dlg.get_content_area().pack_start(cb, True, True, 0)
        dlg.add_button('gtk-ok', gtk.ResponseType.OK).grab_focus()

        dlg.set_keep_above(True)
        dlg.show_all()
        dlg.run()
        if cb.get_active() :
            GLOBAL_PREF.add_excluded_msg(self.get_type(), msgid)
        dlg.destroy()

    def check_hash(self, s, default = 0):
        try :
            return (0 + eval(s.strip('[]')))
        except Exception:
            print(_('%(feature_name)s : can not evaluate %(value)s') % \
                  {'feature_name':self.get_name(), 'value':s})
            return default

    def validate(self):
        VALIDATED = True
        s = self.attr["validation"]
        s = self.replace_params(s)
        s = re.sub(r"#", r"""#""", s)
        exec(s)
        if not VALIDATED :
            print('%s failed validation\n' % self.get_name())
        return True

class Preferences(object):

    def __init__(self):
        global default_metric
        default_metric = None
        self.pref_file = None
        self.cfg_file = None
        self.ngc_init_str = None
#        self.cat_name = None
        self.has_Z_axis = True

    def read(self, cat_name, read_all = True):
        global default_digits, default_metric, add_menu_icon_size, \
            add_dlg_icon_size, quick_access_icon_size, menu_icon_size, \
            treeview_icon_size, vkb_width, vkb_height, vkb_cancel_on_out, \
            toolbar_icon_size, gmoccapy_time_out

        def read_float(cf, section, key, default):
            try :
                return cf.getfloat(section, key)
            except Exception:
                return default

        def read_boolean(cf, section, key, default):
            try :
                return cf.getboolean(section, key)
            except Exception:
                return default

        def read_sbool(cf, section, key, default):
            if read_boolean(cf, section, key, default):
                return '1'
            else :
                return '0'

        def read_str(cf, section, key, default):
            try :
                val = cf.get(section, key).strip()
                if val is None :
                    return default
                else :
                    return val
            except Exception:
                return default

        def read_int(cf, section, key, default):
            return int(round(read_float(cf, section, key, default), 0))

        if cat_name is not None :
            self.cat_name = cat_name

        config = ConfigParser.ConfigParser()

        if read_all :
            self.cfg_file = os.path.join(NCAM_DIR, CATALOGS_DIR, CONFIG_FILE)
            self.pref_file = os.path.join(NCAM_DIR, CATALOGS_DIR, self.cat_name, PREFERENCES_FILE)

            config.read(self.cfg_file)

            self.w_adj_value = read_int(config, 'display', 'width', 550)
            self.col_width_adj_value = read_int(config, 'display', 'name_col_width', 160)
            self.tv_w_adj_value = read_int(config, 'display', 'master_tv_width', 175)
            self.restore_expand_state = read_boolean(config, 'display', 'restore_expand_state', True)
            # empty means "as drawn"; otherwise "r,g,b" naming the accent
            # colour every icon's accent hue is mapped onto - see
            # set_icon_accent / recolour_pixbuf
            self.icon_colour = read_str(config, 'display', 'icon_colour', '')
            self.tv2_expandable = read_boolean(config, 'display', 'tv2_expandable', False)
            self.tv_expandable = read_boolean(config, 'display', 'tv_expandable', False)
            self.use_dual_views = read_boolean(config, 'layout', 'dual_view', True)
            self.side_by_side = read_boolean(config, 'layout', 'side_by_side', True)
            self.sub_hdrs_in_tv1 = read_boolean(config, 'layout', 'subheaders_in_master', False)
            self.hide_value_column = read_boolean(config, 'layout', 'hide_value_column', False)
            self.autorefresh = read_boolean(config, 'layout', 'autorefresh', False)
            # does the Send button regenerate before loading? Default False -
            # "send" honestly means "load what is on disk", and Regenerate is
            # its own button now
            self.send_regenerates = read_boolean(config, 'layout', 'send_regenerates', False)
            global WARN_UNREACHABLE
            WARN_UNREACHABLE = read_boolean(config, 'layout',
                                            'warn_unreachable', True)
            self.warn_unreachable = WARN_UNREACHABLE
            treeview_icon_size = read_int(config, 'icons_size', 'treeview', 28)
            add_menu_icon_size = read_int(config, 'icons_size', 'add_menu', 24)
            menu_icon_size = read_int(config, 'icons_size', 'menu', 4)
            toolbar_icon_size = read_int(config, 'icons_size', 'toolbar', 5)
            add_dlg_icon_size = read_int(config, 'icons_size', 'add_dlg', 70)
            quick_access_icon_size = read_int(config, 'icons_size', 'ncam_toolbar', 30)
            vkb_width = read_int(config, 'virtual_kb', 'minimum_width', 260)
            vkb_height = read_int(config, 'virtual_kb', 'height', 260)
            vkb_cancel_on_out = read_boolean(config, 'virtual_kb', 'cancel_on_focus_out', True)
            self.name_ellipsis = read_int(config, 'display', 'name-ellipsis', 2)

            # point the icon loader at the saved accent before anything asks
            # for a pixbuf, so the first tree/menu build already has it
            set_icon_accent(accent_from_pref(self.icon_colour))

        config.read(self.pref_file)

        if self.ngc_init_str is None :
            # No path-control word here on purpose. It used to be a hard-coded
            # 'G64 p0.001' that silently won for the whole file, so the Tool
            # Change feature's own G61/G61.1/G64/G64 P-Q- setting could only
            # ever be a correction to it rather than the thing in charge.
            # Leaving it out means LinuxCNC's own default applies until a
            # feature says otherwise, and a machine that really does want one
            # at start-up can still set RS274NGC_STARTUP_CODE in its ini or
            # the init string in Preferences.
            if self.cat_name in ['mill', 'plasma'] :
                self.ngc_init_str = 'G17 G40 G49 G90 G92.1 G94 G54'
            elif self.cat_name == 'lathe' :
                self.ngc_init_str = 'G18 G40 G49 G90 G92.1 G94 G54'

        self.timeout_value = read_int(config, 'general', 'time_out', 0.300) * 1000
        self.autosave = read_boolean(config, 'general', 'autosave', False)
        default_digits = read_str(config, 'general', 'digits', '3')

        if no_ini :
            default_metric = read_int(config, 'general', 'default_metric', 1) == 1

        self.ngc_show_final_cut = read_sbool(config, 'general', 'show_final_cut', True)
        self.ngc_show_bottom_cut = read_sbool(config, 'general', 'show_bottom_cut', True)
        self.ngc_init_str = read_str(config, 'ngc', 'init_str', self.ngc_init_str)
        self.ngc_post_amble = read_str(config, 'ngc', 'post_amble', " ")
        self.use_pct = read_boolean(config, 'ngc', 'use_pct_signs', False)
        self.ngc_spindle_speedup_time = read_str(config, 'ngc', 'spindle_acc_time', '0.0')
        self.spindle_all_time = read_sbool(config, 'ngc', 'spindle_all_time', True)

        self.ngc_off_rot_coord_system = read_int(config, 'ngc', 'off_rot_coord_system', 2)
        gmoccapy_time_out = read_float(config, 'general', 'gmoccapy_time_out', 0.15)

        self.ngc_probe_func = read_str(config, 'probe', 'probe_func', "4")
        self.probe_tool_len_comp = read_sbool(config, 'probe', 'probe_tool_len_comp', True)
        if default_metric :
            self.ngc_probe_feed = read_str(config, 'probe_mm', 'probe_feed', '200')
            self.ngc_probe_latch = read_str(config, 'probe_mm', 'probe_latch', '-1')
            self.ngc_probe_latch_feed = read_str(config, 'probe_mm', 'probe_latch_feed', '50')
            self.ngc_probe_tip_dia = read_str(config, 'probe_mm', 'probe_tip_dia', '3.0')
            self.ngc_probe_safe = read_str(config, 'probe_mm', 'probe_safe', '5.0')
            self.ngc_probe_height = read_str(config, 'probe_mm', 'probe_height', '0')

            self.drill_center_depth = read_str(config, 'drill_mm', 'center_drill_depth', '-3.0')
        else :
            self.ngc_probe_feed = read_str(config, 'probe', 'probe_feed', '8.0')
            self.ngc_probe_latch = read_str(config, 'probe', 'probe_latch', '-0.05')
            self.ngc_probe_latch_feed = read_str(config, 'probe', 'probe_latch_feed', '2')
            self.ngc_probe_tip_dia = read_str(config, 'probe', 'probe_tip_dia', '0.125')
            self.ngc_probe_safe = read_str(config, 'probe', 'probe_safe', '0.2')
            self.ngc_probe_height = read_str(config, 'probe', 'probe_height', '0')

            self.drill_center_depth = read_str(config, 'drill', 'center_drill_depth', '-0.125')

        self.pocket_mode = read_str(config, 'pocket', 'mode', '0')

        self.opt_eng1 = read_str(config, 'optimizing', 'engagement1', '0.20')
        self.opt_eng2 = read_str(config, 'optimizing', 'engagement2', '0.30')
        self.opt_eng3 = read_str(config, 'optimizing', 'engagement3', '0.80')

        self.opt_ff1 = read_str(config, 'optimizing', 'feedfactor1', '1.60')
        self.opt_ff2 = read_str(config, 'optimizing', 'feedfactor2', '1.40')
        self.opt_ff3 = read_str(config, 'optimizing', 'feedfactor3', '1.25')
        self.opt_ff4 = read_str(config, 'optimizing', 'feedfactor4', '1.00')
        self.opt_ff0 = read_str(config, 'optimizing', 'feedfactor0', '1.00')

        self.opt_sf1 = read_str(config, 'optimizing', 'speedfactor1', '1.25')
        self.opt_sf2 = read_str(config, 'optimizing', 'speedfactor2', '1.25')
        self.opt_sf3 = read_str(config, 'optimizing', 'speedfactor3', '1.25')
        self.opt_sf4 = read_str(config, 'optimizing', 'speedfactor4', '1.00')
        self.opt_sf0 = read_str(config, 'optimizing', 'speedfactor0', '1.00')

        # lathe tool-tip compensation global-default override (0 = use the tool table's
        # own D/#5410 nose diameter and Q/#5413 orientation)
        self.tip_nose_dia = read_str(config, 'lathe', 'tip_nose_dia', '0.0')
        self.tip_orient = read_str(config, 'lathe', 'tip_orient', '0')
        # also as module globals: compensating in CAM needs these at generation
        # time, in a cfg <exec> that can only reach ncam's module namespace
        global TIP_NOSE_DIA, TIP_ORIENT
        TIP_NOSE_DIA = get_float(self.tip_nose_dia)
        TIP_ORIENT = get_int(self.tip_orient)

        self.plasma_test_mode = read_sbool(config, 'plasma', 'test_mode', True)

        self.read_user_values()
        self.read_excluded_msgs()
        self.create_defaults()

    def read_user_values(self):
        global USER_VALUES, USER_SUBROUTINES

        USER_VALUES = {}
        fname = os.path.join(NCAM_DIR, CATALOGS_DIR, self.cat_name, USER_DEFAULT_FILE)
        config = ConfigParser.ConfigParser()
        config.read(fname)
        USER_SUBROUTINES = config.sections()
        for section in config.sections() :
            for key, val in config.items(section) :
                USER_VALUES[section + ':' + key] = val

    def read_excluded_msgs(self):
        global EXCL_MESSAGES

        EXCL_MESSAGES = {}
        fname = os.path.join(NCAM_DIR, CATALOGS_DIR, self.cat_name, EXCL_MSG_FILE)
        config = ConfigParser.ConfigParser()
        config.read(fname)
        for section in config.sections() :
            for key, val in config.items(section) :
                EXCL_MESSAGES[section + ':' + key] = val

    def add_excluded_msg(self, ftype, msgid):
        fname = os.path.join(NCAM_DIR, CATALOGS_DIR, self.cat_name, EXCL_MSG_FILE)
        parser = ConfigParser.ConfigParser()
        parser.read(fname)

        if not parser.has_section(ftype) :
            parser.add_section(ftype)
        parser.set(ftype, 'msgid-%d' % msgid, 'exclude')

        with open(fname, 'w') as configfile:
            parser.write(configfile)

        self.read_excluded_msgs()

    def val_show_all(self, ftype = None):
        global EXCL_MESSAGES
        fname = os.path.join(NCAM_DIR, CATALOGS_DIR, self.cat_name, EXCL_MSG_FILE)

        if ftype is None :
            EXCL_MESSAGES = {}
            if os.path.isfile(fname) :
                os.remove(fname)
        else :
            parser = ConfigParser.ConfigParser()
            parser.read(fname)

            if parser.has_section(ftype) :
                parser.remove_section(ftype)

                with open(fname, 'w') as configfile:
                    parser.write(configfile)

                self.read_excluded_msgs()

    def val_show_none(self, ftype = None) :
        fname = os.path.join(NCAM_DIR, CATALOGS_DIR, self.cat_name, EXCL_MSG_FILE)
        parser = ConfigParser.ConfigParser()

        if ftype is None :
            parser.add_section('ALL')
            parser.set('ALL', 'msgid-0', 'exclude')

        else :
            parser.read(fname)
            if not parser.has_section(ftype) :
                parser.add_section(ftype)
            parser.set(ftype, 'msgid-0', 'exclude')

        with open(fname, 'w') as configfile:
            parser.write(configfile)

        self.read_excluded_msgs()

    def val_all_excluded(self):
        """Return True if all validation messages are suppressed globally."""
        return 'ALL:msgid-0' in EXCL_MESSAGES

    def val_feat_excluded(self, ftype):
        """Return True if validation messages for a feature type are suppressed."""
        return ('%s:msgid-0' % ftype) in EXCL_MESSAGES

    def edit(self, nc):
        if pref_edit.edit_preferences(nc, default_metric, self.cat_name, NCAM_DIR, \
                self.ngc_init_str, self.ngc_post_amble, SYS_DIR) :
            self.read(None)
            return True
        return False

    def create_defaults(self):

        if self.use_pct :
            self.default = '%\n'
        else :
            self.default = ''
        self.default += _('(*** GCode generated by NativeCAM for LinuxCNC ***)\n\n')
        self.default += _('(*.ngc files are best viewed with Syntax Highlighting)\n')
        self.default += '(visit https://forum.linuxcnc.org/forum/20-g-code/'
        self.default +=     '30840-new-syntax-highlighting-for-gedit)\n'
        self.default += '(or https://github.com/FernV/Gcode-highlight-for-Kate)\n\n'

        if program_metric :
            self.default += _("G21  (metric)\n")
        else :
            self.default += _("G20  (imperial/inches)\n")
        self.default += (self.ngc_init_str + "\n\n")

        # Tool-table values are whatever the table holds and are not touched by
        # G20/G21, so any subroutine reading one has to bring it into program
        # units itself. 1.0 unless the Workpiece asked for units the machine
        # does not use. Emitted for every machine type: lib/utilities routines
        # read it too, and LinuxCNC validates named parameters at load time.
        self.default += ("#<_tbl_scale>               = %s\n"
                         % get_string(TBL_SCALE, 10, False))
        # One millimetre expressed in program units. Subroutine tolerances are
        # written as millimetres because that is what they were sized against -
        # a 0.001 nudge on a level radius is nothing in mm and 0.0254 mm in
        # inches, which moved a roughing level's Z stop by 0.05 mm. Anything
        # dimensional and hard-coded in lib/ must be multiplied by this.
        self.default += ("#<_mm>                      = %s\n\n"
                         % get_string(1.0 if program_metric else 1.0 / 25.4, 10, False))

        if self.cat_name == 'mill' :
            self.default += ("\n#<center_drill_depth>       = " + self.drill_center_depth + "\n\n")
            self.default += ("#<_pocket_expand_mode>      = " + self.pocket_mode + "\n\n")

        if self.cat_name in ['mill', 'lathe'] :
            self.default += _("(optimization values)\n")
            self.default += ("#<_tool_eng1>               = " + self.opt_eng1 + "\n")
            self.default += ("#<_tool_eng2>               = " + self.opt_eng2 + "\n")
            self.default += ("#<_tool_eng3>               = " + self.opt_eng3 + "\n\n")

            self.default += ("#<_feedfactor1>             = " + self.opt_ff1 + "\n")
            self.default += ("#<_feedfactor2>             = " + self.opt_ff2 + "\n")
            self.default += ("#<_feedfactor3>             = " + self.opt_ff3 + "\n")
            self.default += ("#<_feedfactor4>             = " + self.opt_ff4 + "\n")
            self.default += ("#<_feedfactor0>             = " + self.opt_ff0 + "\n\n")

            self.default += ("#<_speedfactor1>            = " + self.opt_sf1 + "\n")
            self.default += ("#<_speedfactor2>            = " + self.opt_sf2 + "\n")
            self.default += ("#<_speedfactor3>            = " + self.opt_sf3 + "\n")
            self.default += ("#<_speedfactor4>            = " + self.opt_sf4 + "\n")
            self.default += ("#<_speedfactor0>            = " + self.opt_sf0 + "\n\n")

        if self.cat_name == 'lathe' :
            self.default += _("(lathe default feed and speed values)\n")
            self.default += ("#<_feed_normal>             = 1.0\n")
            self.default += ("#<_rpm_normal>              = 1000.0\n")
            self.default += ("#<_spindle_dir>             = 3\n")
            self.default += ("#<_cooling_mode>            = 9\n")
            self.default += ("#<_rough_feed>              = 100.0\n")
            self.default += ("#<_rough_cut>               = [1.0 * #<_mm>]\n")
            self.default += ("#<_finish_feed>             = 50.0\n")
            self.default += ("#<_finish_cut>              = [0.25 * #<_mm>]\n")
            self.default += ("#<_z_clear>                 = [2.0 * #<_mm>]\n")
            self.default += ("#<_x_clear>                 = [2.0 * #<_mm>]\n")
            self.default += ("#<_ix_clear>                = [1.0 * #<_mm>]\n")
            self.default += ("#<_diameter_mode>           = 2.0\n")
            self.default += ("#<_x_clamp_r>               = 999999.0\n")
            self.default += ("#<_trace_stop_rec>          = 0.0\n")
            self.default += ("#<_mill_data_rev>           = 0.0\n")
            self.default += ("#<_depth_reached>           = 0.0\n")
            self.default += ("#<_cut_current_x>           = 0.0\n")
            self.default += ("#<_cut_current_y>           = 0.0\n")
            self.default += ("#<_cut_current_z>           = 0.0\n")
            self.default += ("#<_cut_phys_x>              = 0.0\n")
            self.default += ("#<_cut_phys_z>              = 0.0\n")
            self.default += ("#<_pass_z_dir>              = 1.0\n")
            self.default += ("#<_x_wall_dir>              = 0.0\n")
            self.default += ("#<_level_blocked>           = 0.0\n")
            self.default += ("#<_lo_rad_cap>              = 0.0\n")
            self.default += ("#<_pl_ret_mode>             = 0.0\n")
            self.default += ("#<_pl_ret_dist>             = [1.0 * #<_mm>]\n")
            self.default += ("#<_pl_park_on>              = 0.0\n")
            self.default += ("#<_pl_park_x>               = 0.0\n")
            self.default += ("#<_pl_park_z>               = 0.0\n")
            self.default += ("#<_pl_prev_lvl>             = 0.0\n")
            self.default += ("#<_pl_zc_ovr>               = 0.0\n")
            self.default += ("#<_pl_z_clear>              = [1.0 * #<_mm>]\n")
            self.default += ("#<_pl_multi_cross>          = 0.0\n")
            self.default += ("#<_pl_level_z_end>          = 0.0\n")
            self.default += ("#<_pl_resume_found>         = 0.0\n")
            self.default += ("#<_pl_resume_z>             = 0.0\n")
            self.default += ("#<_pl_pause_on>             = 0.0\n")
            self.default += ("#<_tip_cam>                = 0.0\n")
            self.default += ("#<_pl_pass_from>           = 0.0\n")
            self.default += ("#<_pl_min_pass>            = 0.0\n")
            self.default += ("#<_pl_fc_base>             = 0.0\n")
            self.default += ("#<_pl_fc_n>                = 0.0\n")
            self.default += ("#<_pl_cam_dir>             = 0.0\n")
            self.default += ("#<_pl_cam_n>               = 0.0\n")
            self.default += ("#<_pl_cam_max>             = 0.0\n")
            self.default += ("#<_pl_side>                = 0.0\n")
            self.default += ("#<_pl_env_base>            = 0.0\n")
            self.default += ("#<_pl_env_count>           = 0.0\n")
            self.default += ("#<_pl_id_ret>              = 0.0\n")
            self.default += ("#<_pl_x_sgn>               = 1.0\n")
            self.default += ("#<_pl_sectioning>           = 0.0\n")
            self.default += ("#<_pl_sect_count>           = 0.0\n")
            self.default += ("#<_pl_sect_mode>            = 0.0\n")
            self.default += ("#<_pl_sect_top_dia>         = 0.0\n")
            self.default += ("#<_tip_nose_dia>            = " + self.tip_nose_dia + "\n")
            self.default += ("#<_tip_orient>              = " + self.tip_orient + "\n")
            self.default += ("#<_tip_cam_r>               = 0.0\n")
            self.default += ("#<_tip_cam_l>               = 0.0\n")
            self.default += ("#<_tip_off_z>               = 0.0\n")
            self.default += ("#<_tip_off_x>               = 0.0\n")
            self.default += ("#<_tip_comp_d>              = 0.0\n")
            self.default += ("#<_tip_comp_l>              = 0.0\n")
            self.default += ("#<_tip_lead_w>              = 0.0\n\n")

        if self.cat_name == 'mill' :
            self.default += ("#<_probe_func>              = 38." + self.ngc_probe_func + "\n")
            self.default += ("#<_probe_feed>              = " + self.ngc_probe_feed + "\n")
            self.default += ("#<_probe_latch>             = " + self.ngc_probe_latch + "\n")
            self.default += ("#<_probe_latch_feed>        = " + self.ngc_probe_latch_feed + "\n")
            self.default += ("#<_probe_safe>              = " + self.ngc_probe_safe + "\n")
            self.default += ("#<_probe_tip_dia>           = " + self.ngc_probe_tip_dia + "\n\n")
            self.default += ("#<_probe_tool_len_comp>     = " + self.probe_tool_len_comp + "\n")
            self.default += ("#<probe_height>             = " + self.ngc_probe_height + "\n")
            self.default += ("#<_tool_probe_z>            = 0.0\n")

        if self.cat_name in ['mill', 'plasma', 'lathe'] :
            if self.ngc_off_rot_coord_system < 5 :
                coord = str(5 + self.ngc_off_rot_coord_system)
            else :
                coord = '9.' + str(self.ngc_off_rot_coord_system - 4)
            self.default += ("\n#<_off_rot_coord_system>    = 5" + coord + "\n\n")

            self.default += ("#<_mill_data_start>         = 70\n")
            self.default += ("#<in_polyline>              = 0\n\n")

            if self.has_Z_axis :
                self.default += ("#<_has_z_axis>              = 1\n\n")
            else :
                self.default += ("#<_has_z_axis>              = 0\n\n")

            self.default += ("#<_show_final_cuts>         = " + self.ngc_show_final_cut + "\n")
            self.default += ("#<_show_bottom_cut>         = " + self.ngc_show_bottom_cut + "\n\n")

            self.default += ("#<_spindle_all_time>        = " + self.spindle_all_time + "\n\n")

        if self.cat_name in ['mill', 'lathe'] :
            self.default += ("#<_spindle_speed_up_delay>  = " + self.ngc_spindle_speedup_time + "\n\n")

        if self.cat_name == 'plasma' :
            self.default += ("#<_plasma_test_mode>        = " + self.plasma_test_mode + "\n\n")

        self.default += _("(end defaults)\n\n")

        self.default += ("#<_units_radius>            = 1  (for backward compatibility)\n")
        self.default += ("#<_units_width>             = 1  (for backward compatibility)\n")
        if self.cat_name in ['mill', 'lathe'] :
            self.default += ("#<_units_cut_depth>         = 1  (for backward compatibility)\n\n")
        self.default += ("#<_tool_dynamic_dia>        = 0.0\n\n")

        self.default += _('(This is a built-in safety to help avoid gouging into your work piece)\n')
        if self.cat_name in ['mill', 'plasma'] :
            self.default += ("/ o<safety_999> if [#<_show_final_cuts>]\n")
            self.default += ("/    o<safety_9999> repeat [1000]\n")
            self.default += ("/       M123\n")
            self.default += ("/       M0\n")
            self.default += ("/    o<safety_9999> endrepeat\n")
            self.default += ("/ o<safety_999> endif\n\n")
        else :
            self.default += ("/  o<safety_9999> repeat [1000]\n")
            self.default += ("/    M123\n")
            self.default += ("/    M0\n")
            self.default += ("/  o<safety_9999> endrepeat\n\n")

        self.default += _('\n(sub definitions)\n')

# gladevcp's aux-app loader globs every .py file in its own symlink-farm
# directory and imports each as an independent top-level module - it never
# adds this file's own real directory to sys.path. Do that ourselves so the
# split-out mixins below resolve here even when ncam.py is only reachable
# through that symlink farm (aux_gladevcp_target/), not this real path.
_ncam_real_dir = os.path.dirname(os.path.realpath(__file__))
if _ncam_real_dir not in sys.path:
    sys.path.insert(0, _ncam_real_dir)

# Standalone (./ncam.py) loads this file as '__main__', so each mixin's
# `import ncam` below would execute it a SECOND time under the name 'ncam' -
# and that second pass re-enters these same imports while the first pass has
# left them half-initialized ("cannot import name 'NCamFeatureTreeMixin' from
# partially initialized module"). Alias ourselves into sys.modules first: the
# mixins then bind this very module - which already carries every name they
# import, since all of them are defined above - and module-level state such as
# NCAM_DIR / CURRENT_PROJECT stays a single shared copy instead of two.
if __name__ == '__main__' :
    sys.modules.setdefault('ncam', sys.modules['__main__'])

import lathe_sections
from ncam_feature_tree import NCamFeatureTreeMixin
from ncam_project_io import NCamProjectIOMixin
from ncam_ui_chrome import NCamUIChromeMixin
from ncam_menu_catalog import NCamMenuCatalogMixin
from ncam_app_actions import NCamAppActionsMixin
from ncam_treeview import NCamTreeviewMixin
from ncam_preferences_actions import NCamPreferencesActionsMixin
from ncam_preview_ui import NCamPreviewMixin


class NCam(NCamFeatureTreeMixin, NCamProjectIOMixin, NCamUIChromeMixin,
           NCamMenuCatalogMixin, NCamAppActionsMixin, NCamTreeviewMixin,
           NCamPreferencesActionsMixin, NCamPreviewMixin, gtk.Box):
    __gtype_name__ = "NCam"
    __gproperties__ = {}
    __gproperties = __gproperties__

    def __init__(self, *a, **kw):
        # Standalone: __main__ builds GtkDialog then NCam() before vbox.add(ncam), so there is no
        # parent during __init__ — pass accel_toplevel=window to attach AccelGroup before create_menubar().
        self._accel_toplevel_override = kw.pop('accel_toplevel', None)
        global NCAM_DIR, default_metric, NGC_DIR, no_ini, TOOL_TABLE, \
            GLOBAL_PREF, machine_metric

        arg_start = (sys.argv[0:].index('-U') + 1) if "-U" in sys.argv[0:] else 1
        opt, optl = 'U:x:c:i:t', ["catalog=", "ini="]
        try :
            optlist, arg = getopt.getopt(sys.argv[arg_start:], opt, optl)
            optlist = dict(optlist)
        except getopt.GetoptError as err:
            err_exit(err)

        # initialize class variables
        self.add_iconview = None
        self.can_add_to_group = False
        self.can_delete_duplicate = False
        self.can_move_down = False
        self.can_move_up = False
        self.can_remove_from_group = False
        self.catalog_dir = DEFAULT_CATALOG
        self.catalog_path = None
        self.catalog_src = None
        self.click_x = 0
        self.click_y = 0
        self.details_filter = None
        self.editor = DEFAULT_EDITOR
        self.file_changed = False
        self.focused_widget = None
        self.icon_store = None
        self.items_lpath = None
        self.items_path = None
        self.items_ts_parent_s = None
        self.iter_next = None
        self.iter_previous = None
        self.iter_selected_type = tv_select.none
        self.show_not_connected = False
        self.menubar = None
        self.name_cell = None
        self.name_cell2 = None
        self.nc_toolbar = None
        self.newnamedlg = None
        self.params_scroll = None
        self.path_to_new_selected = None
        self.path_to_old_selected = None
        self.selected_feature = None
        self.selected_feature_itr = None
        self.selected_feature_parent_itr = None
        self.selected_feature_path = None
        self.selected_feature_ts_itr = None
        self.selected_param = None
        self.selected_type = 'xxx'
        self.mi_chunits = None
        self.mi_rename_list = []
        self.mi_chnggrp_list = []
        self.mi_setdigits_list = []
        self.mi_datatype_list = []
        self.mi_reverttype_list = []
        self.mi_current_list = []
        self.selection = None
        self.timeout = None
        self._ncam_shutting_down = False
        self.treestore_selected = None
        self.treeview = None
        self.treeview2 = None
        self.tv1_icon_cell = None
        self.tv2_icon_cell = None
        self.undo_list = []
        self.undo_pointer = -1

        self.pref = Preferences()
        TOOL_TABLE = Tools()

        machine_metric = True

        if "-c" in optlist :
            self.catalog_dir = optlist["-c"]
        elif "--catalog" in optlist :
            self.catalog_dir = optlist["--catalog"]

        ini = os.getenv("INI_FILE_NAME")
        if "-i" in optlist :
            ini = optlist["-i"]
        elif "--ini" in optlist :
            ini = optlist["--ini"]

        no_ini = ini is None

        if no_ini :
            # standalone with no --ini:
            inifilename = 'NA'
            # beware, files expected/created in this dir
            NCAM_DIR = os.path.expanduser('~/nativecam')
            NGC_DIR = NCAM_DIR + '/' + NGC_DIR
        else :
            try :
                inifilename = os.path.abspath(ini)
                ini_instance = linuxcnc.ini(ini)
            except Exception as detail :
                err_exit(_("Open fails for ini file : %(inifilename)s\n\n%(detail)s") % \
                           {'inifilename':inifilename, 'detail':detail})

            require_ini_items(inifilename, ini_instance)

            val = ini_instance.find('DISPLAY', 'DISPLAY')
            if val not in ['axis', 'gmoccapy', 'gscreen'] :
                mess_dlg(_("DISPLAY can only be 'axis', 'gmoccapy' or 'gscreen'"))
                sys.exit(-1)

            val = ini_instance.find('DISPLAY', 'GLADEVCP')
            if val is None :
                val = ini_instance.find('DISPLAY', 'EMBED_TAB_COMMAND')

            if val is not None :
                if 'mill' in val :
                    self.catalog_dir = 'mill'
                elif 'lathe' in val :
                    self.catalog_dir = 'lathe'
                elif 'plasma'in val :
                    self.catalog_dir = 'plasma'

            val = ini_instance.find('DISPLAY', 'LATHE')
            if (val is not None) and val.lower() in ['1', 'true'] :
                self.catalog_dir = 'lathe'

            self.pref.ngc_init_str = ini_instance.find('RS274NGC', 'RS274NGC_STARTUP_CODE')

            val = ini_instance.find('EMCIO', 'TOOL_TABLE')
            TOOL_TABLE.set_file(os.path.join(os.path.dirname(ini), val))

            machine_metric = ini_instance.find('TRAJ', 'LINEAR_UNITS') in ['mm', 'metric']
            default_metric = machine_metric

            val = ini_instance.find('DISPLAY', 'EDITOR')
            if val is not None :
                self.editor = val

            val = ini_instance.find('TRAJ', 'COORDINATES')
            if val is not None :
                self.pref.has_Z_axis = ('Z' in val)

        print("\nNativeCAM info:")
        print("   inifile = %s" % inifilename)
        print("  NCAM_DIR = %s" % NCAM_DIR)
        print("   SYS_DIR = %s" % SYS_DIR)
        print("   program = %s\n" % os.path.realpath(__file__))

        fromdirs = [CATALOGS_DIR, CUSTOM_DIR]

        if no_ini :
            self.ask_to_create_standalone(fromdirs)

        # first use:copy, subsequent: update
        if SYS_DIR != NCAM_DIR :
            self.update_user_tree(fromdirs, NCAM_DIR)

        if ini is not None :
            require_ncam_lib(inifilename, ini_instance)

        TOOL_TABLE.load_table()

        # find the catalog and menu file
        catname = self.catalog_dir + '/menu-custom.xml'
        cat_dir_name = search_path(search_warning.none, catname, CATALOGS_DIR)
        if cat_dir_name is not None :
            print(_('Using %s\n') % (catname))
        else :
            catname = self.catalog_dir + '/menu.xml'
            cat_dir_name = search_path(search_warning.dialog, catname, CATALOGS_DIR)
            print(_('Using default %(mnu)s,  no %(dir)s/menu-custom.xml found\n') %
                  {'mnu':catname, 'dir':self.catalog_dir})
        if cat_dir_name is None :
            sys.exit(1)

        with open(cat_dir_name) as f:
            mnu_xml = f.read()
        mnu_xml = re.sub(r"_\(", "", mnu_xml)
        mnu_xml = re.sub(r"\)_", "", mnu_xml)
        self.catalog = etree.fromstring(mnu_xml)

        self.pref.read(self.catalog_dir)
        GLOBAL_PREF = self.pref

        # main_window
        gtk.Box.__init__(self, orientation=gtk.Orientation.VERTICAL, *a, **kw)
        self.builder = gtk.Builder()
        try :
            with io.open(os.path.join(SYS_DIR, "ncam.glade")) as f:
                gf = f.read()
        except IOError as reason :
            err_exit(reason)

        # testing translation file
        if translate_test :
            gf = translate(gf)
        else :
            self.builder.set_translation_domain('nativecam')

        self.builder.add_from_string(gf)

        self.get_widgets()
        parent = self.main_box.get_parent()
        if parent:
            parent.remove(self.main_box)
        # Left-edge drag grip: resizing the panel width inside the embedding GUI.
        # The AXIS gladevcp container frame follows the plug's size request, so
        # adjusting our own request while dragging resizes the whole side panel.
        self._resize_grip = gtk.EventBox()
        self._resize_grip.set_size_request(8, -1)
        self._resize_grip.add(gtk.Separator(orientation=gtk.Orientation.VERTICAL))
        self._resize_grip.add_events(gdk.EventMask.BUTTON_PRESS_MASK |
                                     gdk.EventMask.BUTTON_RELEASE_MASK |
                                     gdk.EventMask.POINTER_MOTION_MASK)
        self._resize_grip.connect('realize', self._grip_realize)
        self._resize_grip.connect('button-press-event', self._grip_press)
        self._resize_grip.connect('button-release-event', self._grip_release)
        self._resize_grip.connect('motion-notify-event', self._grip_motion)
        self._grip_drag = None
        grip_row = gtk.Box(orientation=gtk.Orientation.HORIZONTAL, spacing=0)
        # the rail stays visible when the panel is rolled away, so it has to sit
        # outside main_box - everything else in the row gets hidden
        grip_row.pack_start(self.build_collapse_rail(), False, False, 0)
        grip_row.pack_start(self._resize_grip, False, False, 0)
        grip_row.pack_start(self.main_box, True, True, 0)
        grip_row.show()
        self._collapse_rail.show_all()
        self._resize_grip.show_all()
        self.pack_start(grip_row, True, True, 0)

        self.on_scale_change_value(self)

        # create treestore and treeview
        self.treestore = gtk.TreeStore(object, str, bool, bool)
        self.master_filter = self.treestore.filter_new()

        self.details_filter = self.treestore.filter_new()
        self.details_filter.set_visible_column(3)

        self.create_treeview()

        # create actions and add menu and toolbars
        self.action_group = gtk.ActionGroup(name="my_actions")
        self.accel_group = gtk.AccelGroup()
        self.accels = {}
        self.gaction_group = Gio.SimpleActionGroup()
        self.insert_action_group("app", self.gaction_group)
        self.create_actions()

        self.get_actions_reference()
        w = self._accel_toplevel_override
        if w is None:
            tw = self.get_toplevel()
            if tw is not None and tw != self and isinstance(tw, gtk.Window):
                w = tw
        self._prime_accel_for_window(w)
        self.create_menubar()

        def create_gtb():
            tb = gtk.Toolbar()
            tb.set_style(gtk.ToolbarStyle.ICONS)
            tb.set_can_focus(False)
            
            items = [
                ('Regen', 'gtk-execute'),
                ('Send', 'gtk-jump-to'),
                None,
                ('Add', 'gtk-add'),
                ('Duplicate', 'gtk-copy'),
                ('Delete', 'gtk-remove'),
                None,
                ('Undo', 'gtk-undo'),
                ('Redo', 'gtk-redo'),
                None,
                ('MoveUp', 'gtk-go-up'),
                ('MoveDown', 'gtk-go-down'),
                None,
                ('AppendItm', 'gtk-indent'),
                ('RemoveItm', 'gtk-unindent'),
                None,
                ('Collapse', 'gtk-zoom-out')
            ]
            
            for item in items:
                if item is None:
                    tb.insert(gtk.SeparatorToolItem(), -1)
                else:
                    name, stock = item
                    act = self._actions.get(name) or self.action_group.get_action(name)
                    if name == 'Send' :
                        # Send carries the radio that decides whether it
                        # regenerates first, so it is a MenuToolButton - the
                        # same widget the Contour/Primitives toolbar menus use.
                        ti = gtk.MenuToolButton()
                        ti.set_menu(self.create_send_mode_menu())
                        self.send_tool_button = ti
                    else :
                        ti = gtk.ToolButton()
                    ti.set_action_name("app." + name)
                    ti.set_icon_name(stock)
                    tooltip = getattr(act, '_tooltip', None) or (hasattr(act, 'get_tooltip') and act.get_tooltip())
                    if tooltip:
                        ti.set_tooltip_markup(tooltip)
                    tb.insert(ti, -1)
            return tb

        self.main_toolbar = create_gtb()
        self.main_box.pack_start(self.main_toolbar, False, False, 0)
        self.main_toolbar.show_all()

        self.get_toolbar_actions()
        self.create_nc_toolbar()

        # NativeCAM's own toolpath preview, under the tree/params area
        self.create_preview_pane()

        self.create_popups()

        self.create_add_dialog()

        self.builder.connect_signals(self)
        self.set_preferences()

        if not os.path.isfile(os.path.join(NCAM_DIR, NGC_DIR, 'M123')):
            create_M_file()

        try :
            self.load_currentWork()
        except Exception as e :
            print(_('Error loading current work: %s') % str(e))
            print(_('Starting with empty project'))
        self.treeview.connect("cursor-changed", self.get_selected_feature)
        self.get_selected_feature(self.treeview)

        # AccelGroup must be on the GtkWindow *before* first map/show, or GtkAccelLabel CRITICAL.
        # connect('realize', ...) after show_all() misses the first realize — too late for embed.
        self.connect('realize', self._on_realize)
        self._setup_toplevel_integration()
        # Tiny first allocation (e.g. tab not sized yet) → GtkToolbar negative width / distribute CRITICAL.
        self.set_size_request(120, 80)

        # Defer show_all() to the parent/host GUI to prevent XEMBED realization failures.
        # Protect addVBox from being shown automatically when the parent calls show_all().
        self.addVBox.set_no_show_all(True)

        for mi in self.mi_current_list: mi.set_visible(not self.pref.autosave)
        self.addVBox.hide()
        self.set_layout(None)

        self.feature_Hpane.set_position(int(self.tv_w_adj.get_value()))

        self.clipboard = gtk.Clipboard.get(gdk.SELECTION_CLIPBOARD)
        self.edit_menu_activate()
        self.treeview.grab_focus()
        self.show_not_connected = True




def verify_ini(fname, ctlog, in_tab) :
    path2ui = os.path.join(SYS_DIR, 'ncam.ui')
    req = '# required NativeCAM item :\n'

    with open(fname, 'r') as b :
        txt = b.read()
    if (path2ui not in txt) or ('my-stuff' not in txt) :
        if not os.path.exists(fname + '.bak') :
            with open(fname + '.bak', 'w') as b :
                b.write(txt)
                print(_('Backup file created : %s.bak') % fname)

        if (txt.find('--catalog=mill') > 0) or (txt.find('-cmill') > 0) :
            ctlog = 'mill'
        elif (txt.find('--catalog=lathe') > 0) or (txt.find('-clathe') > 0) :
            ctlog = 'lathe'
        elif (txt.find('--catalog=plasma') > 0) or (txt.find('-cplasma') > 0) :
            ctlog = 'plasma'

        txt1 = ''
        txt2 = txt.split('\n')
        for line in txt2 :
            if line.strip() == '=':
                continue
            txt1 += line.lstrip(' \t') + '\n'

        parser = ConfigParser.RawConfigParser(strict=False)
        try :
            parser.read_string(txt1)

            dp = parser.get('DISPLAY', 'DISPLAY').lower()
            if dp not in ['gmoccapy', 'axis', 'gscreen'] :
                mess_dlg(_("DISPLAY can only be 'axis', 'gmoccapy' or 'gscreen'"))
                sys.exit(-1)

            try :
                old_sub_path = ':' + parser.get('RS274NGC', 'SUBROUTINE_PATH')
            except :
                old_sub_path = ''

            try :
                c = parser.get('DISPLAY', 'LATHE')
                if c.lower() in ['1', 'true'] :
                    ctlog = 'lathe'
            except :
                pass

            txt = re.sub(r"%s" % req, '', txt)

            if dp == 'axis' :
                if in_tab :
                    newstr = '%s%s%s%s %s\n' % (req, 'EMBED_TAB_NAME = NativeCAM\n', \
                            'EMBED_TAB_COMMAND = gladevcp -x {XID} -U --catalog=', \
                            ctlog, path2ui)
                    txt = re.sub(r"\[DISPLAY\]", "[DISPLAY]\n" + newstr, txt)
                else :
                    newstr = '%sGLADEVCP = -U --catalog=%s %s\n' % (req, ctlog, path2ui)
                    try :
                        oldstr = 'GLADEVCP = %s' % parser.get('DISPLAY', 'gladevcp')
                        txt = re.sub(re.escape(oldstr), newstr, txt, count=1)
                    except :
                        txt = re.sub(r"\[DISPLAY\]", "[DISPLAY]\n" + newstr, txt)

            elif (dp == 'gmoccapy') :
                if in_tab :
                    newstr = '%s%s%s%s%s %s\n' % (req, 'EMBED_TAB_NAME = NativeCAM\n', \
                            'EMBED_TAB_LOCATION = ntb_user_tabs\n', \
                            'EMBED_TAB_COMMAND = gladevcp -x {XID} -U --catalog=', \
                            ctlog, path2ui)
                    txt = re.sub(r"\[DISPLAY\]", "[DISPLAY]\n" + newstr, txt)
                else :
                    newstr = '%sEMBED_TAB_LOCATION = box_right\n' % req
                    try :
                        oldstr = 'EMBED_TAB_LOCATION = %s' % parser.get('DISPLAY', 'embed_tab_location')
                        txt = re.sub(re.escape(oldstr), newstr, txt, count=1)
                    except :
                        txt = re.sub(r"\[DISPLAY\]", "[DISPLAY]\n" + newstr, txt)

                    newstr = '%sEMBED_TAB_NAME = right_side_panel\n' % req
                    try :
                        oldstr = 'EMBED_TAB_NAME = %s' % parser.get('DISPLAY', 'embed_tab_name')
                        txt = re.sub(re.escape(oldstr), newstr, txt, count=1)
                    except :
                        txt = re.sub(r"\[DISPLAY\]", "[DISPLAY]\n" + newstr, txt)

                    newstr = '%sEMBED_TAB_COMMAND = gladevcp -x {XID} -U --catalog=%s %s\n' % (req, ctlog, path2ui)
                    try :
                        oldstr = 'EMBED_TAB_COMMAND = %s' % parser.get('DISPLAY', 'embed_tab_command')
                        txt = re.sub(re.escape(oldstr), newstr, txt, count=1)
                    except :
                        txt = re.sub(r"\[DISPLAY\]", "[DISPLAY]\n" + newstr, txt)

            else :  # gscreen
                newstr = '%sEMBED_TAB_COMMAND = gladevcp -x {XID} -U --catalog=%s %s\n' % (req, ctlog, path2ui)
                try :
                    oldstr = 'EMBED_TAB_COMMAND = %s' % parser.get('DISPLAY', 'embed_tab_command')
                    txt = re.sub(re.escape(oldstr), newstr, txt, count=1)
                except :
                    txt = re.sub(r"\[DISPLAY\]", "[DISPLAY]\n" + newstr, txt)

                newstr = '%sEMBED_TAB_LOCATION = vcp_box\n' % req
                try :
                    oldstr = 'EMBED_TAB_LOCATION = %s' % parser.get('DISPLAY', 'embed_tab_location')
                    txt = re.sub(re.escape(oldstr), newstr, txt, count=1)
                except :
                    txt = re.sub(r"\[DISPLAY\]", "[DISPLAY]\n" + newstr, txt)

                newstr = '%sEMBED_TAB_NAME = NativeCAM\n' % req
                try :
                    oldstr = 'EMBED_TAB_NAME = %s' % parser.get('DISPLAY', 'embed_tab_name')
                    txt = re.sub(re.escape(oldstr), newstr, txt, count=1)
                except :
                    txt = re.sub(r"\[DISPLAY\]", "[DISPLAY]\n" + newstr, txt)

            newstr = '%sPROGRAM_PREFIX = ncam/scripts/\n' % req
            try :
                oldstr = 'PROGRAM_PREFIX = ' + parser.get('DISPLAY', 'program_prefix')
                txt = re.sub(re.escape(oldstr), newstr, txt, count=1)
            except :
                txt = re.sub(r"\[DISPLAY\]", "[DISPLAY]\n" + newstr, txt)

            newstr = '%sNCAM_DIR = ncam\n' % req
            try :
                oldstr = 'NCAM_DIR = ' + parser.get('DISPLAY', 'ncam_dir')
                txt = re.sub(re.escape(oldstr), newstr, txt, count=1)
            except :
                txt = re.sub(r"\[DISPLAY\]", "[DISPLAY]\n" + newstr, txt)

            if not 'ncam/my-stuff:ncam/lib/' in old_sub_path :
                newstr = '%sSUBROUTINE_PATH = ncam/my-stuff:ncam/lib/%s:ncam/lib/utilities%s\n' % \
                    (req, ctlog, old_sub_path)
                try :
                    oldstr = 'SUBROUTINE_PATH = ' + parser.get('RS274NGC', 'subroutine_path')
                    txt = re.sub(re.escape(oldstr), newstr, txt, count=1)
                except :
                    txt = re.sub(r"\[RS274NGC\]", "[RS274NGC]\n" + newstr, txt)

            with open(fname, 'w') as b :
                b.write(txt)
                print(_('Success in modifying inifile :\n  %s') % fname)

        except Exception as detail :
            err_exit(_('Error modifying ini file\n%(err_details)s') % {'err_details':detail})

def usage():
    print("""
Standalone Usage:
   ncam [Options]

Options :
    -h | --help                this text
   (-i | --ini=) inifilename   inifile used
   (-c | --catalog=) catalog   valid catalogs = mill, plasma, lathe
    -t | --tab                 axis and gmoccapy only, put NativeCAM in a new tab

To prepare your inifile to use NativeCAM embedded,
   a) Start in a working directory with your LinuxCNC configuration ini file
   b) Type this command :
     ncam (-i | --ini=)inifilename (-c | --catalog=)(valid catalog for this configuration)

   A backup of your inifile will be created before it is modified.

   After success, you can use it embedded  :
     linuxcnc inifilename

""")

if __name__ == "__main__":
    NCAM_STANDALONE = True
    # process args
    args = sys.argv[1:]
    if "-h" in args or "--help" in args:
        usage()
        sys.exit(0)

    try :
        optlist, args = getopt.getopt(sys.argv[1:], 'c:i:t', ["catalog=", "ini="])
    except getopt.GetoptError as err:
        print(err)  # will print something like "option -a not recognized"
        usage()
        sys.exit(2)

    optlist = dict(optlist)

    if "-i" in optlist :
        ini = optlist["-i"]
    elif "--ini" in optlist :
        ini = optlist["--ini"]
    else :
        ini = None

    if (ini is not None) :
        if "-c" in optlist :
            catalog = optlist["-c"]
        elif "--catalog" in optlist :
            catalog = optlist["--catalog"]
        else :
            catalog = DEFAULT_CATALOG
        if not catalog in VALID_CATALOGS :
            usage()
            sys.exit(3)

        in_tab = ("-t" in optlist) or ("--tab" in optlist)
        verify_ini(os.path.abspath(ini), catalog, in_tab)

    window = gtk.Dialog(title=APP_TITLE, modal=True)
    ncam = NCam(accel_toplevel=window)
    window.get_content_area().add(ncam)
    ncam.show_all()
    for mi in ncam.mi_current_list:
        mi.set_visible(True)
    window.connect("destroy", gtk.main_quit)
    window.set_default_size(400, 800)
    exit(window.run())
