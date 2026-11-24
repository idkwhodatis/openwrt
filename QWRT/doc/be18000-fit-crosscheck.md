# BE18000 OpenWrt FIT vs live QWRT FIT cross-check

## Current preinit-debug factory image

Compared `build/debug/factory.ubi` (SHA-256
`da37791bd5a5526ff23de5dcf4d59d90d4ecf42f2c4317a17eda42a7cb5c7e75`)
with the saved working QWRT kernel volume. The full QWRT dump hashes to
`bc08f017d701c058b8a0800e36b363ca0b622b77d0b85be387eb4fc680822fa1`,
matching the independent volume extraction from the pre-flash backup.
The debug FIT was reconstructed from volume 0 in logical eraseblock order.

| Measurement | Working QWRT | Preinit debug |
| --- | ---: | ---: |
| FIT totalsize, excluding volume padding | 5,484,624 | 6,041,636 |
| Gzip payload bytes | 5,397,564 | 5,994,683 |
| Decompressed arm64 Image bytes | 12,118,024 | 15,124,488 |
| ARM64 header text_offset | 0x80000 | 0 |
| ARM64 header image_size | 12,554,240 | 15,466,496 |
| FIT load and entry | 0x42080000 | 0x42080000 |

Selected the named config in each FIT, followed both references and
recomputed CRC32 and SHA-1 over each referenced payload. All eight checks
passed. Both gzip streams decompressed and both outputs have the ARM64
Image magic. Debug FIT SHA-256 over its exact totalsize is
`3b874203b80dd9b4aec0b952d3428e7df04092be2eade346eb463c03fab33d3f`.

**Selection.** File offsets below refer to the live-matched APPSBL executable.
The NAND path contains a named UBI read of `kernel`. At `0x14d72` the
boot path checks the image at `0x50000000`; its FIT branch calls the
selector at `0x14b04`. It checks an environment override named
`config_name`, otherwise iterates the control FDT's root `config_name`
strings, looks each name up in the uploaded FIT, and formats
`bootm 0x%x#%s` on success. Lookup failure can return an error.
The FIT default alone is therefore insufficient proof. The saved
environment has no override. The control FDT's runtime list has not been
recovered, but the known working FIT has the same **single** configuration
`config@al02-c4` as debug. With the same selector inputs, any name that
selects the working FIT selects the candidate. Its references to
`kernel-1` and `fdt-1` both resolve.

**Load.** The installed bootloader passes a 64 MiB output limit at
`0x1b82a` to the image loader; its gzip branch passes that limit to the
decompressor at `0x1b78a`. The debug output fits, and its destination
is clear of the staged FIT at `0x50000000`. Successful handoff remains
unobserved. Unlike QWRT, the debug Image's zero text offset paired with
the inherited FIT load address misses the arm64 boot protocol's 2 MiB
base alignment by 512 KiB. The debug kernel is relocatable; see the
[alignment assessment](be18000-no-ssh-audit.md). This is a real difference
without a demonstrated boot failure.

**Root filesystem.** The saved QWRT runtime cmdline in
`backup/be18000-20261122/device/logs/identity.txt` contains both the
environment argument sets, then the DT-appended block root. The installed
binary references the concatenation of `bootargs`, `fsbootargs` and
`rootwait` at `0x148e0`. With the same environment and handoff, debug
inherits `ubi.mtd=rootfs` and `rootfstype=squashfs`; its own DT and
kernel patch append the final `root=/dev/ubiblock0_1`. Candidate volume
1 is named `rootfs` and starts with SquashFS magic. The built kernel enables
UBI block and rootfs auto-block creation. If the duplicate attachment
attempt fails after a successful first attach, built-in UBI keeps the first
attachment (`drivers/mtd/ubi/build.c`, `ubi_init_attach`). This does not
verify that NAND actually registered, attached or mounted on the failed boot.

## Earlier baseline

The following comparison covers the candidate rebuilt at merge `7c4b10bc78`
on 2026-11-22.

## Artifacts

Build outputs under `QWRT/extracted/be18000-build/` (recorded in
`sha256sums`):

| File | SHA-256 |
|---|---|
| `...-initramfs-uImage.itb` | `8bef93f87430a5259dc41827f7b5d98a44d02cf0a8ca16c82ca05e00c740ec3c` |
| `...-squashfs-factory.ubi` | `2e66f3e5509f45c5757e0759cd1f50341b34bdbca362b3ba3e0ab96e627e9eb0` |
| `...-squashfs-sysupgrade.bin` | `9a49ada011944156393a5081acb2b170818734c5b17a48e7cb41a074aeb95be7` |

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
kernel_desc       ARM64 OpenWrt Linux-6.18.64      ARM64 OpenWrt Linux-5.4.250      ARM64 OpenWrt Linux-6.18.64
fdt_desc          ARM64 OpenWrt xiaomi_be18000 ...  ARM64 OpenWrt xiaomi_be18000 ...  ARM64 OpenWrt xiaomi_be18000 ...
bootargs_append   root=/dev/ubiblock0_1            root=/dev/ubiblock0_1 cnss2...   root=/dev/ubiblock0_1
compatible        xiaomi,be18000                   xiaomi,be18000                   xiaomi,be18000
```

Kernel/FDT payload differences are expected: the built images carry
Linux 6.18.64 and our 45,555-byte DTB; the live QWRT FIT carries Linux
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
FIT kernel image bytes 5994227 compression gzip
decompressed kernel bytes 15124488
bootargs-append -> 12607712
Linux version 6.18.64 ... aarch64-openwrt-linux-musl-gcc ...
```

The DTB in the built FIT has `chosen/bootargs-append = " root=/dev/ubiblock0_1"`.
So the effective cmdline ends with `root=/dev/ubiblock0_1` even though U-Boot
passes `root=mtd:ubi_rootfs`.

UBI volumes in `factory.ubi`:

```text
volume 0 "kernel"      48 LEBs
volume 1 "rootfs"      83 LEBs
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
3. **FDT size/model.** Our 45,555-byte DTB is smaller than the live
   85,168-byte QSDK DTB and uses `model = "Xiaomi BE18000"` (the live
   QWRT DTB says `"Xiaomi Router BE18000 Pro Max (Wi-Fi 7 320Mhz)"`).
   `compatible` matches, which is what drivers bind on.
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
