# BE18000 OpenWrt FIT vs live QWRT FIT cross-check

Status: offline check of the already-built Phase A artifacts. No hardware was
used. This closes the "does our FIT match what `bootipq` expects" question.

## Artifacts

Build outputs under `QWRT/extracted/be18000-build/` (recorded in
`sha256sums`):

| File | SHA-256 |
|---|---|
| `...-initramfs-uImage.itb` | `a7178a71e4bf4ad824bdc180f05b8a223d2a88f57582477f9432b4f7861fa9f8` |
| `...-squashfs-factory.ubi` | `83947e3d5da442906c6033ea1f34fa02eb3467867d56b71ccef2386915a7e403` |
| `...-squashfs-sysupgrade.bin` | `023dbcdab619474d6ab8f0e0814ad237451b6dac857820be2ca21b944a700270` |

Live reference: `QWRT/extracted/live-be18000/firmware/live-kernel.fit`.

## Method

`QWRT/UBoot/compare_fit.py` parses the FDT of each FIT directly (no
`mkimage` needed), reads the board DTB out of the `fdt-*` image, and parses
the `kernel` volume out of `factory.ubi` with a minimal UBI reader
(PEB 0x20000, VID header 0x800, data offset 0x1000).  The UBI volume
table is read directly; the `rootfs_data` autoresize marker comes from
`ubi_vtbl_record.flags` bit 0, not from an empty-LEB heuristic.

```bash
python QWRT/UBoot/compare_fit.py
python QWRT/UBoot/check_bootargs_patch.py
```

## Result

```text
field             built initramfs FIT              live QWRT FIT                    built factory.ubi kernel volume
default_config    config@al02-c4                   config@al02-c4                   config@al02-c4
compression       gzip                             gzip                             gzip
load              0x42080000                       0x42080000                       0x42080000
entry             0x42080000                       0x42080000                       0x42080000
arch              arm64                            arm64                            arm64
os                linux                            linux                            linux
fdt_desc          ARM64 OpenWrt xiaomi_be18000 ...  ARM64 OpenWrt xiaomi_be18000 ...  ARM64 OpenWrt xiaomi_be18000 ...
bootargs_append   root=/dev/ubiblock0_1            root=/dev/ubiblock0_1 cnss2...   root=/dev/ubiblock0_1
compatible        xiaomi,be18000                   xiaomi,be18000                   xiaomi,be18000
```

Kernel/FDT payload differences are expected: the built images carry
Linux 6.18.60 and our 45,531-byte DTB; the live QWRT FIT carries Linux
5.4.250 and an 85,168-byte QSDK DTB. Everything `bootipq` selects on matches.

The `bootargs_append` row is the **board DTB** `chosen/bootargs-append`, not a
FIT-root property. Both FIT roots contain only `timestamp`, `description` and
`#address-cells`, exactly like the live QWRT FIT. That is expected and is not a
defect: mainline consumes the DTB property (next section).

## How `root=/dev/ubiblock0_1` reaches the kernel

The installed QWRT U-Boot is the deciding factor. The checked-in QSDK
`cmd_bootqca.c` defines `FIT_BOOTARGS_PROP "append-bootargs"` and reads it
from the FIT root, falling back to the env `fsbootargs`. The installed
binary, however, contains neither `append-bootargs` nor `bootargs-append` as
a string, so we cannot claim it reads a FIT-root property. What is certain:
the live env `fsbootargs` is `root=mtd:ubi_rootfs` (wrong for mainline), and
neither the live nor the built FIT root carries a bootargs property.

The built mainline kernel supplies it instead. OpenWrt's
`target/linux/generic/hack-6.18/920-device_tree_cmdline.patch` adds:

```c
p = of_get_flat_dt_prop(node, "bootargs-append", &l);
if (p != NULL && l > 0)
        strlcat(cmdline, p, COMMAND_LINE_SIZE);
```

`early_init_dt_scan_chosen()` appends the DTB property **after** the
bootloader cmdline, so the last `root=` wins. Verified on the built kernel:

```text
FIT kernel image bytes 5986906 compression gzip
decompressed kernel bytes 15124488
bootargs-append -> 12606288
Linux version 6.18.60 ... aarch64-openwrt-linux-musl-gcc ...
```

The DTB in the built FIT has `chosen/bootargs-append = " root=/dev/ubiblock0_1"`.
So the effective cmdline ends with `root=/dev/ubiblock0_1` even though U-Boot
passes `root=mtd:ubi_rootfs`.

UBI volumes in `factory.ubi`:

```text
volume 0 "kernel"      48 LEBs
volume 1 "rootfs"      80 LEBs
volume 2 "rootfs_data" 0 data LEBs, autoresize
```

The live unit has `kernel`, `rootfs`, `rootfs_data`, and
`root=/dev/ubiblock0_1` maps to volume 1 (`rootfs`) as required.

## Differences and risk

1. **Image node names.** OpenWrt emits `kernel-1`/`fdt-1`; QWRT emits
   `kernel@1`/`fdt@1`. The `/configurations/config@al02-c4` node references
   them, and `bootipq` boots by configuration name, so this should be
   irrelevant. Watch it on the first RAM boot; it is the only structural
   difference found.
2. **Extra live bootargs.** The live append is
   `root=/dev/ubiblock0_1 cnss2.enable_mlo_support=0 swiotlb=1 coherent_pool=2M`.
   `cnss2` is QSDK-only. `swiotlb=1`/`coherent_pool=2M` are optional;
   add them only if the RAM boot needs them.
3. **FDT size/model.** Our DTB is smaller and uses
   `model = "Xiaomi BE18000"` (the live QWRT DTB says
   `"Xiaomi Router BE18000 Pro Max (Wi-Fi 7 320Mhz)"`). `compatible` matches,
   which is what drivers bind on.
4. **`append-bootargs` is not in the FIT root.** It is in the board DTB
   `chosen` node, and the mainline kernel's generic hack 920 consumes it
   (verified above). A FIT-root property would only matter for a U-Boot that
   does not pass the DTB through; it is not needed here and is not emitted by
   `mkits.sh`.

## Verdict

The offline FIT (initramfs and factory `kernel` volume) satisfies the boot
contract proven by the live unit: `config@al02-c4`, gzip, load/entry
`0x42080000`, UBI volume `kernel`, and a cmdline ending in
`root=/dev/ubiblock0_1` via the DTB `chosen/bootargs-append` plus kernel hack
920. If that path is ever removed, the fallback is to set the U-Boot env
`fsbootargs` to include `root=/dev/ubiblock0_1`.

The remaining verification is the hardware RAM boot
(`tftpboot` + `bootm`) described in
[the recovery runbook](be18000-recovery-runbook.md).
