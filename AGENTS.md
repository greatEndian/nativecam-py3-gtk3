# Repository Guidelines

## Project Structure & Module Organization

NativeCAM is a Python 3/GTK3 conversational CAM application for LinuxCNC.

- `ncam.py` is the entry point; `ncam_*.py` modules handle UI, project files, menus, and previews. `lathe_sections.py` and `lathe_comp.py` contain GTK-independent geometry.
- `catalogs/{mill,lathe,plasma}/` defines operation menus; `cfg/` contains feature parameters and generation templates; `lib/` contains G-code subroutines.
- `graphics/`, `*.glade`, and `locale/` hold assets, UI definitions, and translations. `defaults/` and `examples/` provide initial settings and sample projects.
- Root-level `test_*.py` files are regression drivers. `configs/sim/` supplies LinuxCNC simulations; `debian/` contains packaging.

## Build, Test, and Development Commands

Install system dependencies and Python requirements as described in `README.md`, including GTK3/PyGObject, lxml, Tk, and LinuxCNC for integration checks.

```bash
./ncam.py                              # Standalone GUI; uses ~/nativecam
python3 run_tests.py                   # Serial default regression suite
python3 run_tests.py test_lathe_comp.py # Run one selected driver
python3 cam_map.py                     # Check cfg/Python/G-code relationships
flake8 ncam.py ncam_*.py lathe_sections.py pref_edit.py
bash debian/makedeb.sh                 # Interactive Debian package build
linuxcnc configs/sim/axis/ncam_demo/lathe-mm.ini
```

Python changes run directly; no compilation step is required.

## Coding Style & Naming Conventions

Use four-space indentation, `snake_case` functions/modules, `PascalCase` classes, and uppercase constants. Match surrounding code and avoid unrelated reformatting. `.flake8` selects `E9,F63,F7,F82`, recognizes gettext's `_`, and sets a 127-character line limit.

Compute geometry in Python at generation time; keep G-code subroutines focused on executing generated tables. Keep geometry helpers independent of GTK and `ncam` imports. Run `cam_map.py` before changes spanning templates, builders, or subroutines.

## Testing Guidelines

Tests are standalone Python scripts, without a pytest harness or a declared coverage percentage. Name regression drivers `test_<behavior>.py` and make failed checks return nonzero. Add a reproducer for behavior changes and verify generated motion with `rs274` where relevant.

Run integration drivers serially to avoid interpreter contention. GUI tests may require X11 or `xvfb-run`. Inspect `SKIPPED` and `KNOWN FAIL` results; whole-catalog sweeps require explicit selection. Use scratch copies of LinuxCNC variable files during interpreter checks.

## Commit & Pull Request Guidelines

Recent commits commonly use `fix(scope): description`, `feat(scope): description`, `test(scope): description`, and `docs(scope): description`. Keep subjects specific and changes focused.

Describe the problem, resulting behavior, affected machine/catalog, and validation commands with outcomes. Link relevant issues and include screenshots for UI changes. Keep generated files and unrelated local changes out of commits.
