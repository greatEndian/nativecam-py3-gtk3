#!/usr/bin/env python3
# coding: utf-8
"""DEMO, not a test - the GTK3 Paned size-allocate recursion, by hand.

Renamed out of `test_*` on 2026-09-10. It was `test_paned.py`: twenty lines, no
assertion, no check, no `assert` anywhere, and `# Gtk.main()` commented out at
the bottom. Every driver sweep ran it and counted it green while it proved
nothing - a permanent false pass. Found by the sweep in `analysis/126`.

What it demonstrates is real and is recorded in CLAUDE.md as a port gotcha: a
`size-allocate` handler that calls `set_position` emits another size-allocate,
which calls `set_position` again. The cure is `if pos != new_pos`. The handler
below is the UNGUARDED form deliberately - it is the bug, kept so the shape is
readable.

WHY IT IS NOT A TEST. It was rewritten as one, with the guard asserted and a
negative control, and the control PASSED: without the guard the handler still
settles here, because a headless run never drives the allocation loop hard
enough to re-enter. A check whose negative control passes is not a gate - it is
the same false green in a better disguise - so this stays an explicit demo,
run by hand when someone is looking at that gotcha.

    python3 demo_paned_recursion.py
"""
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk                                    # noqa: E402


def on_size_allocate(widget, allocation):
    print("Allocated: %dx%d" % (allocation.width, allocation.height))
    pos = widget.get_position()
    print("Position: %d" % pos)
    # UNGUARDED ON PURPOSE - the guard would be `if pos != allocation.width - 150`
    if pos > allocation.width - 150:
        widget.set_position(allocation.width - 150)


w = Gtk.Window()
p = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
p.connect("size-allocate", on_size_allocate)
p.pack1(Gtk.Label(label="Left"), True, False)
p.pack2(Gtk.Label(label="Right"), True, False)
p.set_position(500)
w.add(p)
w.show_all()
# Gtk.main()
