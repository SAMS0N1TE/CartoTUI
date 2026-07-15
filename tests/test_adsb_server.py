from __future__ import annotations

from cartotui import adsb_server as S
from cartotui.adsb_server import Backend, Facts


def _facts(**kw):
    base = dict(system="Linux", arch="arm64", distro_id="debian", distro_like="",
                codename="bookworm", has_apt=True, has_systemd=True)
    base.update(kw)
    return Facts(**base)


def test_flightaware_repo_is_arm_debian_only():
    """FlightAware's Release file advertises armhf/arm64 only, and Debian suites.

    Offering dump1090-fa anywhere else produces an apt install that cannot
    resolve the package.
    """
    assert _facts(arch="arm64", codename="bookworm").fa_eligible is True
    assert _facts(arch="armhf", codename="bullseye").fa_eligible is True
    assert _facts(arch="armhf", codename="trixie").fa_eligible is True

    assert _facts(arch="amd64", codename="bookworm").fa_eligible is False
    assert _facts(arch="i386", codename="bookworm").fa_eligible is False
    assert _facts(arch="arm64", codename="noble").fa_eligible is False
    assert _facts(arch="arm64", codename="buster").fa_eligible is False
    assert _facts(arch="arm64", codename="bookworm", has_apt=False).fa_eligible is False


def test_ubuntu_is_debian_family_but_not_fa_eligible():
    u = _facts(distro_id="ubuntu", distro_like="debian", codename="noble", arch="amd64")
    assert u.is_debian_family is True
    assert u.fa_eligible is False


def test_pi_offers_dump1090_fa_first(monkeypatch):
    monkeypatch.setattr(S, "apt_candidate", lambda pkg: None)
    plan = S.plan_backends(_facts(arch="arm64", codename="bookworm"))
    assert plan[0].key == "dump1090-fa"
    assert plan[0].automatable is True
    assert any(b.key == "readsb" for b in plan)


def test_amd64_never_offers_dump1090_fa(monkeypatch):
    monkeypatch.setattr(S, "apt_candidate", lambda pkg: "1.15")
    plan = S.plan_backends(_facts(arch="amd64", codename="bookworm"))
    keys = [b.key for b in plan]
    assert "dump1090-fa" not in keys
    assert keys[0] == "dump1090-mutability"


def test_mutability_only_offered_when_apt_says_so(monkeypatch):
    monkeypatch.setattr(S, "apt_candidate", lambda pkg: None)
    plan = S.plan_backends(_facts(arch="amd64", codename="trixie"))
    keys = [b.key for b in plan]
    assert "dump1090-mutability" not in keys
    assert keys == ["readsb"]


def test_readsb_is_always_a_fallback(monkeypatch):
    monkeypatch.setattr(S, "apt_candidate", lambda pkg: None)
    for arch in ("amd64", "arm64", "riscv64"):
        plan = S.plan_backends(_facts(arch=arch))
        assert any(b.key == "readsb" for b in plan), arch


def test_readsb_is_not_silently_automated(monkeypatch):
    """readsb pipes a third-party script into root. Never run that unattended."""
    monkeypatch.setattr(S, "apt_candidate", lambda pkg: None)
    plan = S.plan_backends(_facts(arch="amd64"))
    readsb = next(b for b in plan if b.key == "readsb")
    assert readsb.automatable is False
    assert any("less " in c for c in readsb.commands)


def test_windows_plan_is_guided_not_automated():
    plan = S.plan_backends(Facts(system="Windows", arch="amd64"))
    assert len(plan) == 1
    b = plan[0]
    assert b.automatable is False
    assert b.commands == []
    assert b.manual_steps
    assert any("Zadig" in s for s in b.manual_steps)
    assert any(str(S.SBS_PORT) in s for s in b.manual_steps)


def test_unknown_platform_has_no_plan():
    assert S.plan_backends(Facts(system="Haiku", arch="ppc")) == []


def test_fa_repo_url_pins_the_verified_version():
    assert "flightaware-apt-repository_1.3_all.deb" in S.FA_REPO_DEB
    assert S.FA_REPO_DEB.startswith("https://")


def test_describe_plan_shows_commands_and_root():
    b = Backend(key="k", title="T", note="N", commands=["sudo apt-get install -y x"],
                needs_root=True)
    text = S.describe_plan(b)
    assert "sudo apt-get install -y x" in text
    assert "root" in text.lower()


def test_describe_plan_shows_manual_steps():
    b = Backend(key="k", title="T", note="N", manual_steps=["do a thing"],
                automatable=False)
    text = S.describe_plan(b)
    assert "manual" in text.lower()
    assert "do a thing" in text


def test_run_plan_refuses_manual_backend():
    b = Backend(key="k", title="T", note="N", manual_steps=["x"], automatable=False)
    assert S.run_plan(b, echo=lambda *_: None) == 1


def test_run_plan_stops_at_first_failure(monkeypatch):
    calls = []

    def fake_call(cmd, shell=False):
        calls.append(cmd)
        return 0 if cmd == "one" else 3

    monkeypatch.setattr(S.subprocess, "call", fake_call)
    b = Backend(key="k", title="T", note="N", commands=["one", "two", "three"])
    rc = S.run_plan(b, echo=lambda *_: None)
    assert rc == 3
    assert calls == ["one", "two"]


def test_apt_candidate_parses_policy(monkeypatch):
    monkeypatch.setattr(S.shutil, "which", lambda n: "/usr/bin/apt-cache")
    monkeypatch.setattr(S, "_run", lambda *a, **k: (
        0, "dump1090-mutability:\n  Installed: (none)\n  Candidate: 1.15~x\n"))
    assert S.apt_candidate("dump1090-mutability") == "1.15~x"


def test_apt_candidate_none_when_unavailable(monkeypatch):
    monkeypatch.setattr(S.shutil, "which", lambda n: "/usr/bin/apt-cache")
    monkeypatch.setattr(S, "_run", lambda *a, **k: (
        0, "dump1090-fa:\n  Installed: (none)\n  Candidate: (none)\n"))
    assert S.apt_candidate("dump1090-fa") is None


def test_apt_candidate_none_without_apt(monkeypatch):
    monkeypatch.setattr(S.shutil, "which", lambda n: None)
    assert S.apt_candidate("anything") is None
