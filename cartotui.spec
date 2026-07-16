from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = collect_data_files("cartotui")
hiddenimports = collect_submodules("cartotui")

a = Analysis(
    ["packaging/windows_entry.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="cartotui",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    icon="logo_1.ico",
)
