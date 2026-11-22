#!/usr/bin/env python3
"""Compare the OpenWrt xiaomi_be18000 FIT with the live QWRT FIT.

Reads:
  QWRT/extracted/be18000-build/*-initramfs-uImage.itb
  QWRT/extracted/be18000-build/*-squashfs-factory.ubi  (kernel volume)
  QWRT/extracted/live-be18000/firmware/live-kernel.fit
"""
import glob
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
BUILD = os.path.join(REPO, "QWRT", "extracted", "be18000-build")
LIVE = os.path.join(REPO, "QWRT", "extracted", "live-be18000", "firmware")

FDT_MAGIC = 0xD00DFEED
PEB = 0x20000
VID_OFF = 2048
DATA_OFF = 4096
LEB = PEB - DATA_OFF


def cstr(blob, off):
    end = blob.find(b"\0", off)
    return blob[off:end].decode("latin1")


def parse_fdt(blob, base=0):
    (magic, total, off_struct, off_strings, off_rsv, version,
     last_comp, boot_cpu, size_strings, size_struct) = struct.unpack(">10I", blob[base:base + 40])
    if magic != FDT_MAGIC:
        raise ValueError(f"not an FDT at {base:#x}")
    strings = blob[base + off_strings:base + off_strings + size_strings]
    pos = base + off_struct
    root = None
    stack = []
    while True:
        tag = struct.unpack(">I", blob[pos:pos + 4])[0]
        pos += 4
        if tag == 1:
            end = blob.find(b"\0", pos)
            name = blob[pos:end].decode("latin1") or "/"
            pos = (end + 4) & ~3
            node = {"name": name, "props": {}, "children": []}
            if stack:
                stack[-1]["children"].append(node)
            else:
                root = node
            stack.append(node)
        elif tag == 2:
            stack.pop()
        elif tag == 3:
            ln, nameoff = struct.unpack(">II", blob[pos:pos + 8])
            pos += 8
            data = blob[pos:pos + ln]
            pos = (pos + ln + 3) & ~3
            stack[-1]["props"][cstr(strings, nameoff)] = data
        elif tag == 4:
            pass
        elif tag == 9:
            break
        else:
            raise ValueError(f"bad FDT tag {tag} at {pos:#x}")
    return root, total


def child(node, name):
    for c in node["children"]:
        if c["name"] == name:
            return c
    return None


def u32(node, prop, default=None):
    v = node["props"].get(prop)
    return struct.unpack(">I", v)[0] if v else default


def text(node, prop):
    v = node["props"].get(prop)
    return v.split(b"\0")[0].decode("latin1") if v else None


def fit_summary(blob, label):
    root, total = parse_fdt(blob)
    images = child(root, "images")
    confs = child(root, "configurations")
    knode = next(c for c in images["children"] if c["name"].startswith("kernel"))
    fnode = next(c for c in images["children"] if c["name"].startswith("fdt"))
    out = {
        "label": label,
        "total": total,
        "description": text(root, "description"),
        "default_config": text(confs, "default"),
        "compression": text(knode, "compression"),
        "load": f"{u32(knode, 'load'):#x}",
        "entry": f"{u32(knode, 'entry'):#x}",
        "arch": text(knode, "arch"),
        "os": text(knode, "os"),
        "kernel_desc": text(knode, "description"),
        "fdt_desc": text(fnode, "description"),
        "fdt_size": len(fnode["props"].get("data", b"")),
        "config_kernel": None,
        "config_fdt": None,
        "bootargs_append": None,
        "model": None,
        "compatible": None,
    }
    for c in confs["children"]:
        if c["name"].startswith("config@"):
            out["config_name"] = c["name"]
            out["config_kernel"] = text(c, "kernel")
            out["config_fdt"] = text(c, "fdt")
            out["config_desc"] = text(c, "description")
            break
    dtb = fnode["props"].get("data", b"")
    if dtb:
        droot, _ = parse_fdt(dtb)
        chosen = child(droot, "chosen")
        if chosen:
            out["bootargs_append"] = text(chosen, "bootargs-append")
        out["model"] = text(droot, "model")
        out["compatible"] = text(droot, "compatible")
    return out


def ubi_volumes(path):
    blob = open(path, "rb").read()
    vols = {}
    vtbl = {}
    for peb in range(0, len(blob), PEB):
        if blob[peb:peb + 4] != b"UBI#":
            continue
        vid = blob[peb + VID_OFF:peb + VID_OFF + 64]
        if vid[:4] != b"UBI!":
            continue
        vol_id, lnum = struct.unpack(">II", vid[8:16])
        data = blob[peb + DATA_OFF:peb + DATA_OFF + LEB]
        if vol_id == 0x7FFFEFFF:
            # volume table record: name at offset 16..16+128 after 4*3+1+1+2
            for i in range(0, len(data), 172):
                rec = data[i:i + 172]
                if len(rec) < 172:
                    break
                name_len = struct.unpack(">H", rec[14:16])[0]
                if 0 < name_len <= 127:
                    name = rec[16:16 + name_len].decode("latin1")
                    # ubi_vtbl_record.flags is byte 144; bit 0 is
                    # UBI_VTBL_AUTORESIZE_FLG.
                    autoresize = bool(rec[144] & 0x01)
                    vtbl[i // 172] = (name, autoresize)
            continue
        vols.setdefault(vol_id, {})[lnum] = data
    names = {}
    autoresize_volumes = set()
    for vol_id in sorted(set(vols) | set(vtbl)):
        leb_map = vols.get(vol_id, {})
        name, autoresize = vtbl.get(vol_id, (f"vol{vol_id}", False))
        names[vol_id] = name
        if autoresize:
            autoresize_volumes.add(vol_id)
        extra = " (autoresize)" if autoresize else ""
        print(f"  UBI volume {vol_id}: {name!r} lebs={len(leb_map)}{extra}")
    return vols, names, autoresize_volumes


def main():
    built_fit = glob.glob(os.path.join(BUILD, "*-initramfs-uImage.itb"))
    factory = glob.glob(os.path.join(BUILD, "*-squashfs-factory.ubi"))
    live_fit = os.path.join(LIVE, "live-kernel.fit")
    rows = []
    if built_fit:
        rows.append(fit_summary(open(built_fit[0], "rb").read(), "built initramfs FIT"))
    if os.path.exists(live_fit):
        rows.append(fit_summary(open(live_fit, "rb").read(), "live QWRT FIT"))
    if factory:
        print("factory.ubi volumes:")
        vols, names, autoresize_volumes = ubi_volumes(factory[0])
        for vol_id, leb_map in vols.items():
            if names.get(vol_id) == "kernel":
                data = b"".join(leb_map[i] for i in sorted(leb_map))
                rows.append(fit_summary(data, "built factory.ubi kernel volume"))
                break
    keys = ["default_config", "config_name", "config_desc", "compression", "load", "entry",
            "arch", "os", "kernel_desc", "fdt_desc", "fdt_size", "bootargs_append", "model", "compatible"]
    width = max(len(r["label"]) for r in rows) + 2
    print()
    print("field".ljust(18) + "".join(r["label"].ljust(width) for r in rows))
    for k in keys:
        print(k.ljust(18) + "".join(str(r.get(k)).ljust(width) for r in rows))
    print()
    for r in rows:
        print(f"{r['label']}: FIT totalsize {r['total']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
