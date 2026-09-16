#!/usr/bin/env python3
# coding: utf-8
"""Write a file so a concurrent reader never sees a half-written one.

GTK-free, and imports nothing from `ncam` - the same shape as
`lathe_sections.py`, so it is unit-testable with plain `python3`.

WHY. `with open(path, "w") as f: f.write(text)` truncates the file at open()
and only then fills it, so any reader inside that window sees a SHORT file.
Measured on `ncam.ngc` (`analysis/213`): 2 of 165 preview parses died with

    File ended with no percent sign (%) or program end (M2)
    | o<poly_lathe_mill> endsub

- rs274 hitting EOF in the middle of a subroutine - because Regenerate
rewrote the file while a preview was still reading it. LinuxCNC loading the
same path can read it just as torn, and AXIS is handed that path by name
(`ncam.py:546` `_tk_axis_remote_open`), not as an already-open descriptor.

The fix is the ordinary one: write a temp file beside the target, flush it to
disk, then `os.replace()` it over the target. `os.replace` is atomic on POSIX,
so a reader gets either the whole old file or the whole new one - never a
prefix of either.
"""
import os
import threading


def write_atomic(path, text, encoding=None):
    """Replace `path` with `text` atomically. Returns `path`.

    The temp file is created in the target's OWN directory, because
    `os.replace` is only atomic within one filesystem, and with a plain
    `open()` so it inherits the umask rather than `mkstemp`'s 0600. An
    existing file's mode is then reapplied explicitly: `os.replace` swaps the
    temp file's inode into place, so without this the generated file would
    silently change permissions.

    The temp name carries pid and thread id so two writers cannot collide on
    it, and it is removed if anything fails - a failed write must not leave
    litter beside the real file.
    """
    d = os.path.dirname(os.path.abspath(path))
    tmp = os.path.join(d, '.%s.tmp-%d-%d' % (os.path.basename(path),
                                             os.getpid(),
                                             threading.get_ident()))
    try:
        mode = os.stat(path).st_mode & 0o777
    except OSError:
        mode = None
    try:
        with open(tmp, 'w', encoding=encoding) as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        if mode is not None:
            os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    return path
