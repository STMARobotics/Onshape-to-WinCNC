# Onshape-to-WinCNC
---
A simple desktop application to convert Onshape CAM Studio .nc files to be compatible with ShopSabre WinCNC.

Brought to you by FRC 7028 Binary Battalion in collaboration with FRC 4607 CIS.

Python is required to run the program—you can install it via the Microsoft Store.

WARNING: Use at your own risk. Always simulate before executing toolpaths.

---

# What does the script do?
This script takes G-code exported from Onshape CAM Studio and rewrites it into a format that ShopSabre’s WinCNC controller can safely and reliably run. WinCNC is far more strict than generic Fanuc-style posts, so the script cleans and restructures the file: it removes unsupported tokens (program numbers, comments, redundant modal codes), splits combined commands (like S and M3), forces WinCNC-safe arc formatting, normalizes motion commands, and ensures the correct placement of things like tool-length cancel (G49). It also includes optional removal of mist and tool-change commands via GUI checkboxes. When you leave those options unchecked the converter rewrites `M7/M9` into WinCNC mister commands (`M11C<port>` on / `M12C<port>` off) and keeps `T`/`M6` pairs together in the `TX M6` format WinCNC expects so automated tool changes remain intact. Before converting, the script analyzes Z-values after spindle start to detect if Onshape’s Setup → Position Type or zero plane is wrong—warning for top-of-stock setups that never cut below Z0 and for bottom-of-part setups that dip below Z0. The result is a clean .tap file prefixed with `SS23_` by default (you can change the naming pattern in **Customize → Output Settings…**), ready to run on a ShopSabre without syntax errors, unexpected behavior, or manual editing.

---

## How to Build the Executable (one-time for developers)

You only need to do this if you want to create or update `Onshape-to-WinCNC.exe`.

### Prerequisites (Windows 10/11)

1. Install **Python 3.10–3.12** (64-bit) from https://www.python.org/downloads/  
   → During install: check **"Add Python to PATH"**

2. Download or clone this repository

### Build Steps (super simple)

Open **Command Prompt** or **PowerShell** (no admin needed) and run these commands:

```bat
:: 1. Go to the project folder
cd path\to\Onshape-to-WinCNC-Converter

:: 2. Install PyInstaller (only needed once)
pip install --upgrade pyinstaller

:: 3. Build the single-file executable
pyinstaller --onefile --windowed --icon="app.ico" --add-data "token_replacements.json;." "onshape-to-wincnc.pyw"
