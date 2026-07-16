# Windows build

Build the standalone `cartotui.exe` on Windows:

```
pip install pyinstaller
pip install .
pyinstaller cartotui.spec
```

The exe lands in `dist/cartotui.exe`. The icon is `logo_1.ico` at the repo root.

The native `libcarto` renderer is not bundled, so the exe uses the pure-Python
vector renderer. Everything else works the same.
