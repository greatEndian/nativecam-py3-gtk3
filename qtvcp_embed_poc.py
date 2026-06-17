#!/usr/bin/env python3
# coding: utf-8

import sys
import os
import subprocess

def run_gtk_child(xid):
    """The GTK3 application (simulating NativeCAM)"""
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk, Gdk

    # Verify X11 (Wayland does not support XEMBED)
    display = Gdk.Display.get_default()
    if display and not display.get_name().lower().startswith('x11') and not display.get_name().lower().startswith(':'):
        print(f"[GTK Child] Error: XEMBED requires X11. Detected: {display.get_name()}")
        sys.exit(1)

    print(f"[GTK Child] Connecting Gtk.Plug to XID: {xid}")
    
    plug = Gtk.Plug.new(xid)
    
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    box.set_border_width(10)
    
    lbl = Gtk.Label(label="<b>GTK3 NativeCAM Simulation</b>")
    lbl.set_use_markup(True)
    box.pack_start(lbl, False, False, 0)
    
    entry = Gtk.Entry()
    entry.set_text("GTK Entry - Test Focus Here")
    box.pack_start(entry, False, False, 0)
    
    btn = Gtk.Button(label="GTK Click Me")
    btn.connect("clicked", lambda b: print("[GTK Child] Button clicked!"))
    box.pack_start(btn, False, False, 0)
    
    plug.add(box)
    plug.show_all()
    
    plug.connect("destroy", lambda w: Gtk.main_quit())
    
    print("[GTK Child] GTK main loop started.")
    Gtk.main()

def run_qt_host():
    """The Qt5 application (simulating QtVCP / QTDragon)"""
    try:
        from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QPushButton, QLabel, QFrame
        from PyQt5.QtCore import Qt
    except ImportError:
        print("[Qt Host] Error: PyQt5 not found. Please install it using: pip install PyQt5")
        sys.exit(1)

    app = QApplication(sys.argv)
    
    main_win = QMainWindow()
    main_win.setWindowTitle("QtVCP / QTDragon Host Simulation")
    main_win.resize(600, 400)
    
    central = QWidget()
    main_win.setCentralWidget(central)
    
    layout = QVBoxLayout(central)
    
    lbl = QLabel("<b>Qt5 Host UI</b> (Below is the embedded GTK3 window)")
    lbl.setTextFormat(Qt.RichText)
    layout.addWidget(lbl)
    
    # Create the container for XEMBED
    # A QFrame works well as it can force a native window ID
    container = QFrame()
    container.setFrameShape(QFrame.StyledPanel)
    container.setAttribute(Qt.WA_NativeWindow)
    layout.addWidget(container, 1) # expand
    
    btn = QPushButton("Qt5 Button (Test Focus)")
    btn.clicked.connect(lambda: print("[Qt Host] Button clicked!"))
    layout.addWidget(btn)
    
    main_win.show()
    
    xid = int(container.winId())
    print(f"[Qt Host] Created container with XID: {xid}")
    
    # Spawn the GTK child process
    script_path = os.path.abspath(__file__)
    print("[Qt Host] Spawning GTK child process...")
    proc = subprocess.Popen([sys.executable, script_path, "--child", str(xid)])
    
    def cleanup():
        print("[Qt Host] Shutting down, terminating child...")
        proc.terminate()
        proc.wait()
        
    app.aboutToQuit.connect(cleanup)
    
    print("[Qt Host] Qt main loop started.")
    sys.exit(app.exec_())

if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == "--child":
        run_gtk_child(int(sys.argv[2]))
    else:
        run_qt_host()