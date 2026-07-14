import os
import tempfile

_iso = tempfile.mkdtemp(prefix="cartotui_test_")
os.environ["APPDATA"] = _iso
os.environ["XDG_CONFIG_HOME"] = _iso
os.environ["CARTOTUI_CONFIG"] = os.path.join(_iso, "config.json")
