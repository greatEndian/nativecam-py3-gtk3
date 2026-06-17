# NativeCAM Installation Helper

Follow these steps to install and run the Python 3 / GTK3 port of NativeCAM.

## 1. System Preparation
Ensure your LinuxCNC environment is active.
```bash
# Verify LinuxCNC variables
linuxcnc_var all
```

## 2. Installation

### Method A: Debian Package (Recommended)
```bash
sudo apt update
sudo apt install ./nativecam_2.0b-4_all.deb
```

### Method B: Source / Development Setup
```bash
# 1. Install system libraries
sudo apt update
sudo apt install python3-gi gir1.2-gtk-3.0 python3-lxml python3-tk

# 2. Install python requirements
pip install -r requirements.txt
```

## 3. Running NativeCAM

### Standalone Mode (UI Only)
```bash
./ncam.py
```

### Embedded Mode (Tab inside LinuxCNC)
```bash
# Run this in your configuration directory
./ncam.py -i your_machine.ini -c mill  # or lathe/plasma
linuxcnc your_machine.ini
```

## 4. Post-Installation Check
Consult `VERIFICATION-GUIDE.md` to perform the "Lathe Polyline" and "UI Scaling" tests to ensure the installation is 100% functional.
