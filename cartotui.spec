import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = collect_data_files("cartotui")
hiddenimports = collect_submodules("cartotui")

# The ctypes binding is imported by path at runtime rather than as a package, so
# PyInstaller cannot see it. Ship it where libcarto_backend looks.
for _mod in ("carto_ffi.py", "packer.py"):
    _src = os.path.join("bindings", "python", _mod)
    if os.path.exists(_src):
        datas.append((_src, os.path.join("bindings", "python")))

# Bundle the native renderer when one has been built. Without it the exe falls
# back to the pure-Python vector path, which is several times slower on a busy
# map -- so build libcarto before packaging.
binaries = []
_dll = os.path.join("libcarto", "build", "carto.dll")
if os.path.exists(_dll):
    binaries.append((_dll, os.path.join("libcarto", "build")))
else:
    print("cartotui.spec: WARNING - libcarto/build/carto.dll not found; the exe "
          "will ship without the native renderer. Run .\\setup.ps1 first.")

a = Analysis(
    ["packaging/windows_entry.py"],
    pathex=[],
    binaries=binaries,
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
