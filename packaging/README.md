# Windows build

Build the standalone `cartotui.exe` on Windows:

```
pip install pyinstaller
pip install .
pyinstaller cartotui.spec
```

The exe lands in `dist/cartotui.exe`. The icon is `logo_1.ico` at the repo root.

Build the native renderer first. `cartotui.spec` bundles
`libcarto/build/carto.dll` when it exists, and warns when it does not -- without
it the exe falls back to the pure-Python vector renderer, which is several times
slower on a busy map.

```
.\setup.ps1            # builds libcarto/build/carto.dll
pyinstaller cartotui.spec
```

The status bar shows `C` or `PY` next to the render time, so you can tell at a
glance which renderer a build ended up with.
