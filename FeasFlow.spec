# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for FeasFlow — multi-engine power plant feasibility desktop app.
# Build:  pyinstaller FeasFlow.spec --noconfirm

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# customtkinter ships JSON theme assets that must be bundled as data.
ctk_datas = collect_data_files("customtkinter")

hiddenimports = []
hiddenimports += collect_submodules("engines")
hiddenimports += [
    "customtkinter",
    "openpyxl",
    "openpyxl.chart",
    "matplotlib.backends.backend_tkagg",
    "matplotlib.backends.backend_pdf",
    "PIL._tkinter_finder",
]

a = Analysis(
    ["feas_main.py"],
    pathex=[],
    binaries=[],
    datas=ctk_datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "scipy", "pandas", "PyQt5", "PyQt6", "PySide2", "PySide6",
        "IPython", "notebook", "pytest", "streamlit", "plotly",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

# --- onedir build (COLLECT) ---
# A folder-based build does NOT self-extract to %TEMP% at launch, which is the
# behaviour Windows Defender heuristics most often false-positive on. Much less
# likely to be blocked than --onefile. Distribute by zipping the whole
# dist/FeasFlow/ folder; the user runs FeasFlow.exe inside it.
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="FeasFlow",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,              # UPX packing is itself a common AV trigger
    console=False,          # windowed app, no console
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="icon.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="FeasFlow",
)
