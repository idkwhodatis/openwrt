# QWRT U-Boot package analysis (BE18000) — what is in `QWRT/UBoot`

Status: analysis only. Nothing was flashed and no device state was touched.
Evidence source: the two ZIPs and the loose `.bin` files in `QWRT/UBoot`, compared
against the previously captured live partitions
(`QWRT/extracted/live-be18000/firmware/boot/appsbl.bin`,
`.../appsblenv.bin`, `.../mibib.bin`).

## 1. Artifacts and hashes

| File | Size | SHA-256 |
|---|---|---|
| `BE10000_Uboot_MIBIB_MAX.zip` | 288,049 | `acd19d2114339edafbfa11bce79290124a75e2e28c6cd2c9a224be7e2d5c4816` |
| `BE10000_Uboot_MIBIB_v2.zip` | 288,864 | `9e564ac6ed3120cc65b0897eedc83b8fd52451f5f9e83696a47b3ca254aa2f2b` |
| `uboot中文.bin` (loose) | 549,912 | `a82b54764a7a3aad49651d702a85ccd645dc51369b1492f2697cd1fb98c1b1e7` |
| `mibib中文.bin` (loose) | 262,144 | `3d05f0139a8b551ed955b0aa1a20d9e4442da0ae83cba2fe5d644449e7062cc2` |
| MAX zip → `uboot.bin` | 549,912 | `a82b54764a7a3aad49651d702a85ccd645dc51369b1492f2697cd1fb98c1b1e7` |
| v2 zip → `uboot.bin` | 549,912 | `a82b54764a7a3aad49651d702a85ccd645dc51369b1492f2697cd1fb98c1b1e7` |
| MAX zip → `mibib.bin` | 262,144 | `e482188b9d950fd6fa8375df002f143600911a4472e186c9172d072e0fd034a0` |
| v2 zip → `mibib.bin` | 262,144 | `3d05f0139a8b551ed955b0aa1a20d9e4442da0ae83cba2fe5d644449e7062cc2` |
| live `0:APPSBL` (`mtd18`) | 1,572,864 | `9910e95d3f02590475ff05c8a261618f75b2f693c0fe00157ddcd39cc45dee94` |
| live `0:MIBIB` (`mtd2`) | 1,048,576 | `7b42075098c82de8ef29655b04d740cee9aa9dd643e7de72f554ac7d0ee6a576` |

Readme (it is UTF-8, not GBK):

```text
把文件上传到路由器，使用如下命令刷入即可
mtd write mibib.bin /dev/mtd2
mtd write uboot.bin /dev/mtd18

注意：写入后需要重新在uboot刷入固件
```

## 2. There is only one U-Boot, not two

`BE10000_Uboot_MIBIB_MAX.zip` and `BE10000_Uboot_MIBIB_v2.zip` contain the
**same** `uboot.bin` (`a82b5476…`). The loose `uboot中文.bin` is the same file
again. Only `mibib.bin` differs between the two packages.

**The U-Boot currently on the device is this exact build.** The first
549,912 bytes of the live `0:APPSBL` partition are byte-identical to
`uboot.bin`:

```text
live appsbl.bin[:549912] == uboot.bin   ->  True
```

Version strings in both the package and the live partition:

```text
U-Boot 2016.01 (Jan 01 2024 - 17:16:24 +0000)
uboot2.0 version:24.01.02          (web recovery UI)
```

So there is no newer/older U-Boot to pick from here, and no reason to update it.

The remaining `549,912 … 1,572,864` bytes of the live partition are **not** part
of the image (entropy ≈ 7.97 bit/byte, no gzip/xz/lzma/bzip2 stream, no second
ELF). They are almost certainly residual bytes from the image that was in
`0:APPSBL` before QWRT was written (the factory bootloader), because only the
first 549,912 bytes were overwritten. Treat them as unknown, not as a backup.

## 3. Which package matches this unit: MAX

The live `0:MIBIB` dump, first 256 KiB: `e482188b9d950fd6fa8375df002f143600911a4472e186c9172d072e0fd034a0`,
which is **exactly** `MAX/mibib.bin`. The two tables are identical entry for
entry. The v2 table is different and does **not** match the device.

| # | Name | Offset | Size | MAX | live | v2 |
|---|---|---|---|---|---|---|
| 24 | `rootfs` | `0x01780000` | 190 MiB (`0xbe00000`) | ✔ | ✔ | 120 MiB (`0x7800000`) |
| 25 | `bdata` | `0x0d580000` | 256 KiB | ✔ | ✔ | `0x08f80000` |
| 26 | `crash` | `0x0d5c0000` | 256 KiB | ✔ | ✔ | `0x08fc0000` |
| 27 | `crash_syslog` | `0x0d600000` | 256 KiB | ✔ | ✔ | `0x09000000` |
| 28 | `overlay` | — | — | — | — | `0x09040000` 70 MiB |

Entries 0–23 (`0:SBL1` … `0:LICENSE`) are identical in all three. The v2 table
splits the same 190 MiB into `rootfs` + a separate `overlay` **mtd** partition;
MAX keeps one 190 MiB `rootfs` partition and lets UBI hold `rootfs_data`.

`target/linux/qualcommbe/dts/ipq9574-xiaomi-be18000.dts` already describes the
MAX layout (`rootfs` `0x1780000`/`0xbe00000`, `bdata` `0xd580000`, `crash`
`0xd5c0000`, `crash_syslog` `0xd600000`), so the DTS and the live unit agree.

**Do not flash `v2/mibib.bin` on this unit.** It would move `bdata`/`crash` and
split the rootfs area. If a MIBIB reflash is ever needed, use MAX.

## 4. What this U-Boot is and can do

- QSDK U-Boot 2016.01 fork (QWRT build), **ELF32 / ARM, Thumb-2**, entry
  `0x4a400000`; executable payload starts at file offset `0x12000`
  (`0x74418` bytes). The first `0x12000` bytes are a container header (ELF
  header/phdrs plus a small hash-like blob at `0x1000`).
- Boot flow: `bootcmd=bootipq`; `bootipq` reads the **`kernel` UBI volume** from
  the mtd `rootfs` partition and boots the FIT (`ubi read 0x%x kernel`).
- Shell commands present (from the compiled command table): `httpd`,
  `tftpboot`, `bootipq`, `bootm`, `ubi`, `sf`, `saveenv`, `setenv`,
  `printenv`, `dhcp`, `ping`; `flash` and `nand` also appear in the compiled
  command strings used by the updater and the restore script.
- Web recovery pages: **Firmware**, **ART**, **MIBIB**, **U-Boot**.
  - `name="firmware"` → `Upgrade type: firmware`
  - `name="art"` → `Upgrade type: ART`
  - `name="mibib"` → `Upgrade type: MIBIB`
  - `name="uboot"` → `Upgrade type: U-Boot` → `flash 0:APPSBL; flash 0:APPSBL_1`
  - The uploader checks exact size (`## Error: wrong file size, should be: %d bytes!`).
    For ART and MIBIB that is the partition size, i.e. 1,310,720 and
    1,048,576 bytes (derived from the partition map, not separately proven).
    The 262,144-byte `mibib.bin` in the ZIP is therefore a `mtd write` file, not
    a web-UI file; pad it to 1 MiB if the web page is used.
- **A whole UBI upload has its own Firmware handler branch.** Thumb
  disassembly of the live-matched binary (offsets below are file offsets)
  shows the classifier at `0x55964`. After checking a separate marker at
  offset `0x5c`, it checks the first four bytes for `UBI#` and returns 3.
  The 17,432,576-byte preinit debug factory image (SHA-256 `da37791b…`)
  has `ff ff ff ff` at `0x5c` and `UBI#` at zero, so it selects this branch.
- The Firmware handler compares the result to 3 at `0x5910a`. The matching
  branch uses the command string at `0x64b6f`, which sets `bootargs` and
  `fsbootargs` including `ubi.mtd=rootfs`, sets `bootcmd=bootipq`, saves the
  environment, erases two 512 KiB ranges starting at `0x400000` and
  `0x480000`, then issues `flash rootfs`. The board partition map names
  those ranges `0:BOOTCONFIG` and `0:BOOTCONFIG1`. The sequence uses
  semicolons. Its presence does not establish the result of each operation
  during the owner's upload.
- The related QSDK source (`common/cmd_flashwrite.c`, `do_flash`) first
  looks up the named NAND partition. The UBI-volume writer is a fallback
  when partition lookup fails. The live partition table has a physical
  `rootfs` partition. The separate volume-replacement string at `0x72d2b`
  therefore does not establish a volume-by-volume web upload. The actual
  post-flash partition contents have not been read back.
- The built-in default environment is minimal
  (`ipaddr=192.168.1.1`, `serverip=192.168.1.2`, `bootdelay=2`,
  `bootargs=console=ttyMSM0,115200n8`, `bootcmd=bootipq`). The live
  `0:APPSBLENV` overrides it with `ipaddr=192.168.31.1`,
  `serverip=192.168.31.100`, `bootdelay=5`, `model=RC01`,
  `fsbootargs=ubi.mtd=rootfs root=mtd:ubi_rootfs rootfstype=squashfs
  cnss2.enable_mlo_support=1`, `flag_boot_type=2`, `flag_boot_rootfs=0`,
  and `fdt_high=0x48500000`.

## 5. Can this U-Boot be rebuilt from the checked-in tree?

Not as-is.

- `qsdk/qca/src/u-boot-2016` is the same 2016.01 family and has
  `ipq9574_defconfig` / `ipq9574-al02-c4.dts`, but its defconfig has
  `# CONFIG_CMD_NAND is not set`, `# CONFIG_CMD_SPI is not set`, no UBI
  command and no web server.
- No QSDK `ipq95xx`/`ipq9574` defconfig in this tree enables `CONFIG_CMD_NAND`
  or `CONFIG_CMD_UBI`, and the `pepe2k/u-boot_mod` web UI source is not here.
- Upstream U-Boot's `qcom_ipq9574_mmc_defconfig` is eMMC-only (no NAND/UBI),
  so it cannot replace this bootloader on a NAND board.

Conclusion unchanged: **keep the installed QWRT U-Boot.** A rebuild is a
separate project (reconstruct the NAND/UBI/web config against the QSDK tree and
prove it via TFTP/RAM boot before touching `0:APPSBL`).

## 6. Next actions

No-hardware work that is still worth doing:

1. Add the MAX/v2 warning and the hash table above to the port docs, and keep
   the MAX package as the known-good U-Boot reference for this unit.
2. Verify the OpenWrt FIT we generate against the live QWRT FIT
   (`QWRT/extracted/live-be18000/firmware/live-kernel.fit`): same `config@…`
   name, gzip, load/entry `0x42080000`, UBI `kernel` volume, and
   `append-bootargs` carrying `root=/dev/ubiblock0_1`.
3. Write the recovery runbook: serial + TFTP initramfs first, `ubiformat` only
   after a full NAND backup.

On the next hardware session, in this order:

1. **Full NAND backup** (all partitions, not just `appsbl`): `0:APPSBL`,
   `0:APPSBL_1`, `0:APPSBLENV`, `0:MIBIB`, `0:ART`, `0:ETHPHYFW`, `bdata`,
   `crash`, `crash_syslog`, and the UBI `rootfs` area.
2. `mtd18` vs `mtd19` diff — we still do not know what is in the backup copy.
3. Boot an OpenWrt initramfs from TFTP (`tftpboot` + `bootm`) **without writing
   flash**, and confirm `bootipq`/FIT/UBI behaviour.
4. Only then `ubiformat` the `rootfs` mtd and write the OpenWrt UBI/FIT.

## 7. Reproduce

`QWRT/UBoot/inspect_uboot.py` decodes the MIBIB table, verifies the live/live
prefix match, and prints the U-Boot version and web-UI strings. It only reads
files.
