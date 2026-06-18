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

## Tutorials

- [NativeCAM on YouTube](https://www.youtube.com/channel/UCjOe4VxKL86HyVrshTmiUBQ)
- [LinuxCNC Forum Thread](https://forum.linuxcnc.org/forum/40-subroutines-and-ngcgui)

## Credits

Original NativeCAM developed by [Fernand Veilleux (FernV)](https://github.com/FernV/NativeCAM).  
Python 3 / GTK3 migration and Side Drill feature maintained by greatEndian.
