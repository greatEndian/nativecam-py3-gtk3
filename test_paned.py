import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

def on_size_allocate(widget, allocation):
    print(f"Allocated: {allocation.width}x{allocation.height}")
    pos = widget.get_position()
    print(f"Position: {pos}")
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
