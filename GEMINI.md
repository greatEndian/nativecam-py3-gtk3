# NativeCAM for LinuxCNC (Python 3 & GTK3 Port)

This project is a conversational programming interface for LinuxCNC, ported to Python 3 and GTK3. It allows users to create G-code for various machining operations (mill, lathe, plasma) through a graphical interface without needing to write manual G-code.

## Project Overview

- **Purpose:** Conversational CAM for LinuxCNC.
- **Main Technologies:** Python 3, GTK3 (via PyGObject), `lxml` for XML/Glade processing.
- **Architecture:**
  - `ncam.py`: The main entry point and core logic for the application.
  - `pref_edit.py`: Preference and configuration editor.
  - `lib/`: Contains machine-specific logic (mill, lathe, plasma) and general utilities.
  - `catalogs/`, `cfg/`, `defaults/`: Configuration and catalog files defining available operations and their parameters.
  - `configs/`: Sample LinuxCNC configurations for embedding NativeCAM.
  - `graphics/`: UI icons and images.
  - `locale/`: Internationalization files.

- **Key Project Files:**
  - `GEMINI.md`: Main project documentation and mandates.
  - `GITHUB-PRACTICES.md`: Standards for GitHub collaboration and workflow.
  - `DEV-WORKFLOW.md`: Detailed development and release processes.
  - `LEARNINGS-LOG.md`: Historical record of project lessons and architectural decisions.
  - `TASKS.md`: Project roadmap and pending items.

## Building and Running

### Running Standalone
You can run NativeCAM as a standalone application for development or testing:
```bash
./ncam.py
```

### Running Embedded in LinuxCNC
NativeCAM is often used as a tab or panel within LinuxCNC interfaces (AXIS, Gmoccapy, etc.).
```bash
# To embed into an INI file and create a backup:
./ncam.py -i <inifilename> -c <mill|lathe|plasma>
```

### Building Debian Package
The project uses standard Debian packaging tools.
```bash
cd debian
./makedeb.sh
```
This script runs `debuild` to create a `.deb` package in the parent directory.

## Development Conventions

- **Python Version:** Python 3.
- **UI Framework:** GTK3. Note that many `Gtk.Action` and `UIManager` calls are still used, which trigger deprecation warnings in modern GTK3.
- **Code Style:** Follows existing patterns in `ncam.py`. The codebase is relatively large and consolidated in a few main files.
- **Configuration:** Operations are defined in `.cfg` files within the `cfg/` directory. These files specify the parameters and G-code generation logic for each feature.
- **Packaging:** Adheres to Debian packaging standards for LinuxCNC auxiliary applications. Files are typically installed to `/usr/share/linuxcnc/aux_gladevcp/NativeCAM`.

## Key Files and Scripts

- `ncam.py`: Main application logic.
- `pref_edit.py`: Configuration editor for user preferences.
- `ttt`: Integration script for `truetype-tracer` (used for engraving).
- `restore_lcnc.py`: Utility to restore LinuxCNC configuration or setup symbolic links for development.
- `ncam.glade`, `ncam_pref.glade`: GTK UI definitions.
- `debian/rules`: Defines how the project is installed and packaged.
