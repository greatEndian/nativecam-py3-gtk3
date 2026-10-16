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

With **Sectioning** enabled, **Section front tangential extension** moves each
entry start backward along its existing entry path toward the previously cut
area, continuing its profile-angle ramp where present. The normal cutting
start and depth stay fixed. **Section back tangential extension** separately
extends the back along its profile tangent. Physical front/back retain their
meaning in reverse. Each defaults to 0; extensions shorten where the profile,
remaining stock or lead clearance blocks them.

## Tutorials

- [NativeCAM on YouTube](https://www.youtube.com/channel/UCjOe4VxKL86HyVrshTmiUBQ)
- [LinuxCNC Forum Thread](https://forum.linuxcnc.org/forum/40-subroutines-and-ngcgui)

## Credits

Original NativeCAM developed by [Fernand Veilleux (FernV)](https://github.com/FernV/NativeCAM).  
Python 3 / GTK3 migration and Side Drill feature maintained by greatEndian.
