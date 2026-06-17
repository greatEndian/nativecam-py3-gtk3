# QtVCP / QTDragon Integration Findings

This document outlines the architectural research, limitations, and potential solutions for embedding the GTK3 NativeCAM port inside a modern Qt5/Qt6 environment like QTDragon (Increment 6).

## 1. The XEMBED Protocol vs. Simple Reparenting
NativeCAM historically relies on the X11 `XEMBED` protocol to embed itself inside LinuxCNC interfaces (AXIS, Gmoccapy). It uses `Gtk.Plug`, which expects the host GUI to provide a `Gtk.Socket` (or an equivalent XEMBED-compliant container).

In our Proof-of-Concept (`tests/qtvcp_embed_poc.py`), we attempted to embed the `Gtk.Plug` directly into a Qt5 `QFrame` using its native X11 `winId()`. 

### POC Results
- **Rendering (PASS):** The GTK3 window reparents perfectly. X11 composites the GTK child inside the Qt frame without visual tearing.
- **Mouse Events (PASS):** Mouse clicks (e.g., clicking a GTK button) work out of the box because the X11 server routes pointer events directly to the window directly beneath the cursor.
- **Keyboard Focus (FAIL):** GTK text entries cannot be typed into, and the `Tab` key does not cycle focus between Qt and GTK widgets.

## 2. Root Cause of the Focus Failure
Embedding a window via X11 reparenting is not the same as full XEMBED integration. 

The XEMBED protocol defines specific client/host messages required to negotiate focus. When a user clicks a GTK Entry, the GTK child sends an XEMBED message asking the host for keyboard focus. Because Qt5 removed `QX11EmbedContainer` (which used to handle these messages), the Qt host silently ignores the request and traps all keyboard events.

## 3. The Wayland Blocker
As documented in `COMPATIBILITY.md`, this entire mechanism (reparenting X11 IDs) fundamentally crashes on modern Wayland display servers. Any long-term embedding solution must account for Wayland's strict security model, which deliberately forbids cross-process window embedding without specific compositor extensions.

## 4. Proposed Architectural Solutions
To proceed with QTDragon integration, we must choose one of the following architectural paths:

### Path A: Independent Window (Recommended)
Instead of true embedding, NativeCAM launches as a standalone, borderless window. The Qt host communicates with NativeCAM via a local socket/IPC to tell it where to physically position itself on the screen (e.g., "dock" itself over a specific blank `QFrame`). 
- **Pros:** Wayland-safe, zero focus stealing issues, entirely decouples GTK and Qt event loops.
- **Cons:** Requires IPC synchronization to handle window resizing/moving.

### Path B: Virtual Framebuffer / VNC
NativeCAM renders headless, and streams its UI into a Qt canvas via a lightweight local VNC or memory-mapped framebuffer.
- **Pros:** Extremely modern, completely isolates toolkits.
- **Cons:** High performance overhead, complex implementation.

### Path C: Wait for / Contribute to QtVCP XEMBED bindings
If the LinuxCNC QtVCP framework implements a custom Python X11 event filter to manually route XEMBED focus messages, we could hook into that.
- **Pros:** Behaves like legacy AXIS.
- **Cons:** Does not solve the Wayland blocker.