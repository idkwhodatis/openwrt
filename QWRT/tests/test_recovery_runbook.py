#!/usr/bin/env python3
"""Check the first-flash runbook against the archived factory image."""
import contextlib
import hashlib
import importlib.util
import io
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RUNBOOK = REPO / "QWRT" / "doc" / "be18000-recovery-runbook.md"
MANIFEST = REPO / "QWRT" / "doc" / "be18000-phase-a-build-manifest.md"
BUILD = REPO / "QWRT" / "extracted" / "be18000-build"
FACTORIES = list(BUILD.glob("*-squashfs-factory.ubi"))
FACTORY = FACTORIES[0] if FACTORIES else None


def load_compare_fit():
    path = REPO / "QWRT" / "UBoot" / "compare_fit.py"
    spec = importlib.util.spec_from_file_location("compare_fit", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    if FACTORY is None:
        print("skip: archived factory.ubi not present")
        return
    text = RUNBOOK.read_text(encoding="utf-8")
    match = re.search(r"sha256sum /tmp/factory\.ubi\s+# must be ([0-9a-f]{64})",
                      text)
    assert match, "first-flash factory.ubi digest is missing"
    digest = hashlib.sha256(FACTORY.read_bytes()).hexdigest()
    assert match.group(1) == digest, "runbook factory.ubi digest is stale"

    envtools = (REPO / "package" / "boot" / "uboot-tools" / "uboot-envtools" /
                "files" / "qualcommbe_ipq95xx")
    envtext = envtools.read_text(encoding="utf-8")
    assert ('ubootenv_add_mtd "0:APPSBLENV" "0x0" "0x10000" "0x20000" "1"'
            in envtext), "APPSBLENV fw_env layout is unsafe"
    assert ("grep -qx '/dev/mtd17 0x0 0x10000 0x20000 1' /etc/fw_env.config"
            in text), "runbook does not verify the generated fw_env layout"

    assert "/sys/class/ubi/ubi*/mtd_num" in text
    assert "/sys/class/mtd/mtd${rootfs_mtd}/ubi_num" not in text
    mount_check = ("/dev/(ubi${ubi_num}_[0-9]+|ubiblock${ubi_num}_[0-9]+|"
                   "mtd${rootfs_mtd})([[:space:]]|$)|ubi${ubi_num}:")
    assert mount_check in text
    assert (text.index(mount_check) <
            text.index('ubidetach -d "$ubi_num"')), \
        "UBI mount check must run before detach"
    assert "rootfs UBI is mounted" in text
    assert "ubi[0-9]+_" not in text
    assert "rootfs_data" in text and "(vol 2)" in text
    assert "edbe63e5fb1b6b53d2bbb207b928be959f0efa2c06a86cc90a55d56628093526" not in text

    assert "MIBIB table is not the known MAX layout" in text
    assert "MAX layout mismatch" in text
    assert 'check_mtd "rootfs" 24 be00000' in text
    assert "v2 layout: overlay present" in text
    assert "truncated rootfs UBI backup" in text
    assert "rollback backup truncated" in text
    assert "ip addr add 192.168.31.1/24" in text
    assert "ping -c 1 192.168.31.100" in text
    assert "be18000-backup.tar" in text
    assert "backup.sha256" in text
    assert "sha256sum -c backup.sha256" in text
    assert "expected 199229440" in text
    assert "ncat -l -p 9001 <" in text
    assert "nc 192.168.31.100 9001 > /tmp/factory.ubi" in text
    assert "expected 17432576" in text
    assert "Do **not** run sysupgrade from the first boot" in text
    assert "booted successfully at least twice" in text
    assert "nc -l -p 9001 > /tmp/factory.ubi" not in text
    assert "192.168.1.100/24" in text
    assert "dd if=/dev/mtd2 bs=256k count=1" in text
    assert "e482188b9d950fd6fa8375df002f143600911a4472e186c9172d072e0fd034a0" in text
    assert "7b42075098c82de8ef29655b04d740cee9aa9dd643e7de72f554ac7d0ee6a576" in text

    manifest = MANIFEST.read_text(encoding="utf-8")
    rows = re.findall(
        r"`(openwrt-[^`]+|profiles\.json)` \| ([\d,]+) \| `([0-9a-f]{64})`",
        manifest)
    assert rows, "manifest artifact table is missing"
    for name, size, expected in rows:
        path = BUILD / name
        assert path.exists(), f"missing archived artifact {name}"
        assert path.stat().st_size == int(size.replace(",", "")), name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, name

    compare_fit = load_compare_fit()
    with contextlib.redirect_stdout(io.StringIO()):
        volumes, names, autoresize = compare_fit.ubi_volumes(str(FACTORY))
    assert names.get(0) == "kernel"
    assert names.get(1) == "rootfs"
    assert names.get(2) == "rootfs_data"
    assert 2 in autoresize, "rootfs_data must carry UBI_VTBL_AUTORESIZE_FLG"
    assert not volumes.get(2), "rootfs_data must have no data LEBs yet"

    print(f"ok factory digest {digest}")
    print("ok APPSBLENV fw_env layout")
    print("ok rootfs MTD detach and three-volume checks")


if __name__ == "__main__":
    main()
