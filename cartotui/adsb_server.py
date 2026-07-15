"""Detect, plan and install a local ADS-B server — the thing that feeds port 30003.

CartoTUI only *reads* ADS-B. Something else has to decode 1090MHz off an SDR and
serve it. This module works out what that something can be on the current host
and, on Linux, installs it.

Package availability is probed at runtime rather than hard-coded. FlightAware's
repo ships dump1090-fa for armhf/arm64 Debian only (its Release file advertises
no amd64), and dump1090-mutability's suite coverage moves around, so a baked-in
matrix goes stale and fails on someone else's machine. ``apt-cache policy`` is
asked instead.

Nothing here installs anything without an explicit caller decision: build a plan,
show it, then run it.
"""

from __future__ import annotations

import os
import platform
import shutil
import socket
import subprocess
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

SBS_PORT = 30003

FA_REPO_DEB = ("https://www.flightaware.com/adsb/piaware/files/packages/pool/piaware/f/"
               "flightaware-apt-repository/flightaware-apt-repository_1.3_all.deb")
FA_SUITES = ("bullseye", "bookworm", "trixie")
FA_ARCHS = ("armhf", "arm64")

READSB_SCRIPT = "https://raw.githubusercontent.com/wiedehopf/adsb-scripts/master/readsb-install.sh"
ZADIG_URL = "https://zadig.akeo.ie/"

KNOWN_SERVERS = ("dump1090-fa", "dump1090-mutability", "readsb", "dump1090")


@dataclass
class Backend:
    """One way to get a feed on this host."""

    key: str
    title: str
    note: str
    commands: List[str] = field(default_factory=list)
    manual_steps: List[str] = field(default_factory=list)
    needs_root: bool = False
    automatable: bool = True


@dataclass
class Facts:
    system: str
    arch: str
    distro_id: str = ""
    distro_like: str = ""
    codename: str = ""
    has_apt: bool = False
    has_systemd: bool = False

    @property
    def is_debian_family(self) -> bool:
        return self.distro_id == "debian" or "debian" in self.distro_like

    @property
    def fa_eligible(self) -> bool:
        """FlightAware ships dump1090-fa only for ARM Debian."""
        return (self.is_debian_family and self.has_apt
                and self.arch in FA_ARCHS and self.codename in FA_SUITES)


def _run(cmd: List[str], timeout: float = 20.0) -> Tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except (OSError, subprocess.SubprocessError):
        return 127, ""


def _read_os_release() -> Dict[str, str]:
    out: Dict[str, str] = {}
    try:
        with open("/etc/os-release", encoding="utf-8") as f:
            for line in f:
                if "=" not in line:
                    continue
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return out


def host_facts() -> Facts:
    """Describe the current host well enough to pick a backend."""
    system = platform.system()
    arch = platform.machine().lower()
    if system == "Linux":
        rc, out = _run(["dpkg", "--print-architecture"])
        if rc == 0 and out.strip():
            arch = out.strip()
        elif arch in ("x86_64", "amd64"):
            arch = "amd64"
        elif arch in ("aarch64", "arm64"):
            arch = "arm64"
        osr = _read_os_release()
        return Facts(
            system=system,
            arch=arch,
            distro_id=osr.get("ID", "").lower(),
            distro_like=osr.get("ID_LIKE", "").lower(),
            codename=(osr.get("VERSION_CODENAME") or "").lower(),
            has_apt=shutil.which("apt-get") is not None,
            has_systemd=os.path.isdir("/run/systemd/system"),
        )
    return Facts(system=system, arch=arch)


def apt_candidate(pkg: str) -> Optional[str]:
    """Return the installable version of ``pkg``, or None.

    Asks apt instead of trusting a hard-coded distro matrix.
    """
    if shutil.which("apt-cache") is None:
        return None
    rc, out = _run(["apt-cache", "policy", pkg])
    if rc != 0:
        return None
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("Candidate:"):
            v = line.split(":", 1)[1].strip()
            return None if v in ("(none)", "") else v
    return None


def detect_sdr() -> List[str]:
    """Best-effort list of attached SDR devices."""
    found: List[str] = []
    system = platform.system()
    if system == "Linux":
        if shutil.which("rtl_test"):
            rc, out = _run(["rtl_test", "-t"], timeout=8.0)
            for line in out.splitlines():
                s = line.strip()
                if s and s[0].isdigit() and ":" in s:
                    found.append(s)
        if not found and shutil.which("lsusb"):
            rc, out = _run(["lsusb"])
            for line in out.splitlines():
                low = line.lower()
                if "rtl2832" in low or "realtek" in low and "dvb" in low:
                    found.append(line.strip())
                elif "0bda:2838" in low or "0bda:2832" in low:
                    found.append(line.strip())
        return found
    if system == "Windows":
        ps = ("Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -match "
              "'VID_0BDA&PID_283[28]' -or $_.FriendlyName -match 'RTL2832|Bulk-In' } | "
              "ForEach-Object { $_.FriendlyName }")
        rc, out = _run(["powershell", "-NoProfile", "-Command", ps], timeout=25.0)
        if rc == 0:
            found = [ln.strip() for ln in out.splitlines() if ln.strip()]
    return found


def port_open(host: str = "127.0.0.1", port: int = SBS_PORT, timeout: float = 0.6) -> bool:
    try:
        s = socket.create_connection((host, port), timeout=timeout)
    except OSError:
        return False
    try:
        s.close()
    except Exception:
        pass
    return True


def server_status() -> Dict[str, object]:
    """What ADS-B server, if any, is installed and running here."""
    installed = [n for n in KNOWN_SERVERS if shutil.which(n)]
    service = ""
    active = False
    if shutil.which("systemctl"):
        for unit in ("dump1090-fa", "dump1090-mutability", "readsb"):
            rc, out = _run(["systemctl", "is-active", unit], timeout=8.0)
            if out.strip() == "active":
                service, active = unit, True
                break
    return {
        "installed": installed,
        "service": service,
        "active": active,
        "feeding": port_open(),
        "sdr": detect_sdr(),
    }


def _linux_backends(facts: Facts) -> List[Backend]:
    out: List[Backend] = []

    if facts.fa_eligible:
        deb = os.path.basename(FA_REPO_DEB)
        out.append(Backend(
            key="dump1090-fa",
            title="dump1090-fa (FlightAware)",
            note=("Best on Raspberry Pi. Serves SBS on 30003 out of the box "
                  "and installs a systemd service."),
            commands=[
                f"wget -O /tmp/{deb} {FA_REPO_DEB}",
                f"sudo dpkg -i /tmp/{deb}",
                "sudo apt-get update",
                "sudo apt-get install -y dump1090-fa",
                "sudo systemctl enable --now dump1090-fa",
            ],
            needs_root=True,
        ))

    if facts.has_apt and apt_candidate("dump1090-mutability"):
        out.append(Backend(
            key="dump1090-mutability",
            title="dump1090-mutability (distro package)",
            note=("In Debian for amd64. Older and unmaintained upstream, but it "
                  "installs cleanly and serves SBS on 30003."),
            commands=[
                "sudo apt-get update",
                "sudo apt-get install -y dump1090-mutability",
            ],
            needs_root=True,
        ))

    out.append(Backend(
        key="readsb",
        title="readsb (wiedehopf install script)",
        note=("Builds from source; works on amd64 and ARM, actively maintained. "
              "Downloads and runs a third-party script as root — read it first."),
        commands=[
            f"curl -fsSL -o /tmp/readsb-install.sh {READSB_SCRIPT}",
            "less /tmp/readsb-install.sh",
            "sudo bash /tmp/readsb-install.sh",
        ],
        needs_root=True,
        automatable=False,
    ))
    return out


def _windows_backends(facts: Facts) -> List[Backend]:
    return [Backend(
        key="dump1090-win",
        title="dump1090 for Windows (guided)",
        note=("Windows has no packaged ADS-B server. The SDR needs its driver "
              "replaced with WinUSB via Zadig, which is an admin GUI step that "
              "no script can safely drive."),
        manual_steps=[
            f"Install the WinUSB driver with Zadig ({ZADIG_URL}), run as Administrator:",
            "    Options > List all devices",
            "    select 'Bulk-In, Interface (Interface 0)'  (this is the SDR)",
            "    target driver WinUSB, then Replace Driver",
            "Get a Windows dump1090 build and unpack it (it needs rtlsdr.dll,",
            "    libusb-1.0.dll and pthreadVC2.dll from the rtl-sdr Windows release).",
            "Run it with SBS output enabled:",
            f"    dump1090.exe --net --net-sbs-port {SBS_PORT}",
            "Then point CartoTUI at it:",
            f"    .\\configure.ps1 adsb --source sbs1 --host localhost --port {SBS_PORT}",
        ],
        automatable=False,
    )]


def plan_backends(facts: Optional[Facts] = None) -> List[Backend]:
    """Ordered, runtime-probed ways to stand up a feed on this host."""
    facts = facts or host_facts()
    if facts.system == "Linux":
        return _linux_backends(facts)
    if facts.system == "Windows":
        return _windows_backends(facts)
    return []


def describe_plan(backend: Backend) -> str:
    lines = [f"{backend.title}", f"  {backend.note}", ""]
    if backend.manual_steps:
        lines.append("  These steps are manual:")
        lines.extend(f"    {s}" for s in backend.manual_steps)
        return "\n".join(lines)
    lines.append("  Will run:")
    lines.extend(f"    {c}" for c in backend.commands)
    if backend.needs_root:
        lines += ["", "  Needs root (sudo). You will be prompted."]
    return "\n".join(lines)


def run_plan(backend: Backend, echo=print) -> int:
    """Execute a backend's commands, stopping at the first failure."""
    if not backend.commands:
        echo("Nothing to run — this backend is manual.")
        return 1
    for cmd in backend.commands:
        echo(f"  $ {cmd}")
        rc = subprocess.call(cmd, shell=True)
        if rc != 0:
            echo(f"  failed ({rc}): {cmd}")
            return rc
    return 0
