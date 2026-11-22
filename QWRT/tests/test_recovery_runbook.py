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
    print("ok rootfs MTD detach and three-volume checks")


if __name__ == "__main__":
    main()
