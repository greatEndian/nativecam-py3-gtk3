# NativeCAM for LinuxCNC (Python 3 & GTK3 Port)

This is a ported version of **NativeCAM** for LinuxCNC, migrated from
Python 2.7 / GTK2 to **Python 3** and **GTK3**. Designed for compatibility
with **Debian 13 Trixie** and **LinuxCNC 2.9+**.

## Key Changes in this Port

- **Python 3 Migration** — fully updated codebase for modern Python interpreters
- **GTK3 Integration** — UI migrated from GTK2 for better rendering and compatibility
- **Horizontal Side Drilling** — new Side Drill feature for multi-spindle machines (Top / Bottom / Left / Right)
- **Horizontal Tool Visualization** — correct tool orientation display in AXIS for side spindles
- **Phantom Window Fix** — GTK popup windows are properly closed when LinuxCNC exits
- **Debian 13 Trixie Ready** — tested with LinuxCNC 2.9 on Debian 13

## Installation

### 1. From Debian Package (Recommended)
Download the latest release from the [Releases](https://github.com/greatEndian/nativecam-py3-gtk3/releases) page. Install it using:

```bash
sudo apt install ./nativecam_2.0b-4_all.deb
```

### 2. From Source / Development Setup
If you are running from source or want to contribute, you can install the dependencies manually:

```bash
# Install system dependencies (Debian/Ubuntu)
sudo apt update
sudo apt install python3-gi gir1.2-gtk-3.0 python3-lxml python3-tk

# Or use pip (ensure you have system build dependencies for PyGObject)
pip install -r requirements.txt
```

## Usage

Run `ncam -h` for help and all command line options.

### 1. Stand-alone mode

```bash
ncam
```

Creates and uses the `~/nativecam` directory. Requires correct
`SUBROUTINE_PATH` in your LinuxCNC INI file to be fully functional.

### 2. Embedded mode

Use with any of the supplied examples from the LinuxCNC Configuration Selector,
or embed into your own INI file:

```bash
# Run in the directory containing your .ini file:
ncam -i inifilename -c mill   # or: plasma | lathe
```

This will create a backup and automatically modify your INI file.
Then start LinuxCNC normally:

```bash
linuxcnc inifilename
```

To choose where projects are opened and saved, use **Projects → Working Directory…**.
Paste a folder path or use **Browse**, then press **OK** to open the project
chooser there. NativeCAM remembers the folder separately for mill, lathe, and
plasma, and uses it for **Open Project**, **Save Project As**, and **Import**.

In standalone mode, projects inside a LinuxCNC configuration use that
configuration's matching catalog and units for the preview and tool table.
LinuxCNC does not need to be running. An INI supplied explicitly takes priority.

The lathe **Turning** toolbar button opens the operation chooser. Choose
**Outside roughing**, **Inside roughing**, **Outside finishing**, or
**Inside finishing** to start a profile with its side and operation set.
Add lines/arcs from **Profile geometry** to its **Items** group. **Custom profile**
retains the combined roughing/finishing setup. Facing, threading and parting
are also available in the chooser. Dedicated outside/inside/face grooving and
lathe drilling are marked **planned** and disabled until their generators exist.

**Merge with previous** is hidden only on the first profile item and is
available from the second **Line To**. The second item's join uses the
polyline's **Start Diameter** and **Start Z** as the first line's reference.
**Radius** creates a circular join; **Chamfer** creates a straight bevel.
Merge settings on the first item are ignored.
On the second item, **Radius → Flip** chooses the opposite side of the starting
corner between straight lines. For example, with Start Diameter 50, a corner
at X25 Z0 and an R5 join into negative Z, Flip changes the start from X35 Z0
to X15 Z0; both arcs end at X25 Z−5 in diameter mode. The same Flip selects
the starting side for every chamfer style, without swapping its dimensions.

**Roughing** and **Finishing** each have independent front and back tangential
extensions, measured in the Z/radius plane. Roughing extends both its profile
and each pass: the front continues the existing entry path, while the back
follows the local compensated profile tangent. This also works with Sectioning
off. Prefinish uses the finishing extensions. Older projects retain their
saved extension lengths in both groups when reopened.

Under **Tool Change → Tool and usage**, set **Dwell after spindle (s)** below
**Start spindle** and **Dwell after cooling (s)** below **Use cooling**.
They emit `G4 Pseconds` after `M3`/`M4` and `M7`/`M8`, respectively. Coolant
waits when it turns on; repeated operations with coolant already on do not
wait again. Zero disables a wait. Values stay in seconds in inch programs.

Each operation has an **Operator notes** field at the end of its properties.
Notes are saved in the project and printed beside the operation in Raw and
Flat G-code. **Miscellaneous → Comment** inserts a standalone operator comment.
Flat preserves executable reset/setup blocks from manual and inserted-file
G-code. Movement is expanded through the interpreter; operator notes remain
comments.
Flat also states the active work coordinate system, including `G54`, before
motion and preserves changes through `G59.3`; no manual setup feature is needed
to select the program's work offset.

**View → Remember Window and Layout** is enabled by default. It restores the
NativeCAM window size and position, pane dividers, view layout and preview
display options from the previous session. Turn it off to stop automatic
session saving and use the default window geometry and divider positions.

The default operation menu follows application updates. For a custom menu,
save it as `catalogs/lathe/menu-custom.xml` in the NativeCAM configuration folder;
that override takes priority and is preserved.

Regeneration shows a pulsing progress bar with the current stage and elapsed
time. Property sections in all categories start collapsed; click a bold section heading
or its arrow to show or hide its properties. Opened sections stay open when
switching features within the session.

Lathe Polyline keeps its configured roughing lead-in by default. Under
**Lead in / out**, enable **Skip lead-in in cleared metal** only when you want
the entry optimization to omit approaches through material already removed.

Polyline roughing pecks start after the lead-in. Set **Peck length**, optional
**Peck retract**, and **Peck dwell** under **Roughing**. A nonzero retract can
use **Working feed** (choose the tool's roughing or finishing feed) or **Rapid**.
Each intermediate peck stops, retracts, dwells if set, returns to its endpoint
and continues. With zero retract, dwell happens only at the full pass end.
Preview marks peck stops with small dots and displays the remaining dwell time.
Playback speed scales the dwell pauses.

Opening a property editor pauses preview playback at the current tool position.
Edit or cancel, then use **Generate** for the updated path or **Play** to resume.
Property lists close with **Escape** or a click outside; clicking a choice or
pressing **Enter** selects it.

With **Final contour** spacing and artificial sectioning, **Skip thin roughing
passes** also redistributes a thin landing on the first roughing floor when
the threshold and depth of cut permit it. The required floor is retained.

Finishing **Back to front** follows one continuous contour and ignores
**X wall cut**. **Both directions** starts front to back and alternates on
subsequent finishing passes as their allowance steps down. Wall splitting
applies only to its front-to-back passes.

With **Sectioning** enabled, **Section front tangential extension** adds to the
roughing front extension and moves each
entry start backward along its existing entry path toward the previously cut
area, continuing its profile-angle ramp where present. The normal cutting
start and depth stay fixed. **Section back tangential extension** separately
adds to the roughing back extension along its profile tangent. Physical front/back retain their
meaning in reverse. Each defaults to 0; extensions shorten where the profile,
remaining stock or lead clearance blocks them.

## Tutorials

- [NativeCAM on YouTube](https://www.youtube.com/channel/UCjOe4VxKL86HyVrshTmiUBQ)
- [LinuxCNC Forum Thread](https://forum.linuxcnc.org/forum/40-subroutines-and-ngcgui)

## Credits

Original NativeCAM developed by [Fernand Veilleux (FernV)](https://github.com/FernV/NativeCAM).  
Python 3 / GTK3 migration and Side Drill feature maintained by greatEndian.
