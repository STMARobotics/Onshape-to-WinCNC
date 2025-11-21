# Onshape-to-WinCNC
---
A simple desktop application to convert Onshape CAM Studio .nc files to be compatible with ShopSabre WinCNC.

Brought to you by FRC 7028 Binary Battalion in collaboration with FRC 4607 CIS.

Python is required to run the program—you can install it via the Microsoft Store.

WARNING: Use at your own risk. Always simulate before executing toolpaths.

---

# What does the script do?
The converter ingests a .nc program exported from Onshape CAM Studio and rewrites it so ShopSabre’s WinCNC controller accepts it without manual edits. Processing is driven by `token_replacements.json` (editable from the GUI) and applies several WinCNC-safe transforms:

* Comment handling: semicolon comments are stripped; parentheses comments become standalone bracketed lines; top-of-file items like `%` and `O` program numbers are commented out per the JSON `line_patterns` rules.
* Command normalization: combined spindle speed / start tokens are split (`S####` on its own line followed by `M3`/`M4`/`M5`); lines with multiple G/M words are separated so each line carries only one modal command.
* Motion safety: the previous motion mode is reinserted when WinCNC requires it (e.g., arcs regain the last `G2/G3` when only IJ/JK/R coordinates are present; linear moves regain `G0/G1` when coordinates appear without a modal motion word).
* Token rewriting: every token passes through the JSON-driven replacement table—empty replacements delete codes like `M6`, while mappings annotate or translate codes (e.g., `M7/M8/M9` to `M11C8`/`M12C8`, plane selection comments, canned-cycle cancel, tool number bracketing).
* Post-processing: duplicate or early `G49` lines are dropped until after spindle stop, and two blank lines are enforced after the first `G90` for readability.

Output files receive a bracketed ASCII-art header and are written as `.tap` files. By default the output name is prefixed with `SS23_`, but the **Output Settings…** dialog lets you choose a destination directory and swap between prefix/suffix naming.

---
# How to Run the Tool
### For Normal Users (99% of people) — Just Double-Click!

1. Download the latest version from the **Releases** page:  
   → https://github.com/STMARobotics/Onshape-to-WinCNC/releases/latest
2. Click on **Onshape-to-WinCNC.exe** to download it
3. Double-click the downloaded `Onshape-to-WinCNC.exe` file  
   → The converter window opens instantly — no installation needed!

That’s it! Works on any Windows 10/11 computer, even if Python is not installed.

## Run from Command Line
### Prerequisites (Windows 10/11)

1. Install **Python 3.10–3.12** (64-bit) from https://www.python.org/downloads/  
   → During install: check **"Add Python to PATH"**

2. Download or clone this repository

```bat
:: 1. Open Command Prompt or PowerShell
:: 2. Navigate to the folder containing the .pyw file
cd C:\path\to\your\folder

:: 3. Run with Python (requires Python 3.10–3.12 installed)
python onshape-to-wincnc.pyw
```

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
