# BE18000 recovery and first-flash runbook (MAX layout)

Status: prepared offline. **Not executed on hardware.** The router is currently
disconnected; every step below needs to be walked once with serial attached
before it is trusted.

This runbook uses only what was proven from the saved live unit:
the MAX MIBIB (byte-identical to live `0:MIBIB`), the live `0:APPSBLENV`,
the QWRT U-Boot command set, and the built Phase A images.

## 1. Confirmed facts

Partition map (`MAX`, identical to the live table). mtd numbers assume the
DTS lists the MIBIB entries in this order; confirm with `cat /proc/mtd`.

| mtd | name | offset | size |
|---|---|---|---|
| 2 | `0:MIBIB` | `0x300000` | `0x100000` |
| 17 | `0:APPSBLENV` | `0x1100000` | `0x80000` |
| 18 | `0:APPSBL` | `0x1180000` | `0x180000` |
| 19 | `0:APPSBL_1` | `0x1300000` | `0x180000` |
| 20 | `0:ART` | `0x1480000` | `0x140000` |
| 21 | `0:ETHPHYFW` | `0x15c0000` | `0x100000` |
| 24 | `rootfs` | `0x1780000` | `0xbe00000` (190 MiB) |
| 25 | `bdata` | `0xd580000` | `0x40000` |
| 26 | `crash` | `0xd5c0000` | `0x40000` |
| 27 | `crash_syslog` | `0xd600000` | `0x40000` |

Live environment (from `appsblenv.bin`):

```text
bootcmd=bootipq            bootdelay=5         boot_wait=on
ipaddr=192.168.31.1        serverip=192.168.31.100   netmask=255.255.255.0
bootargs=ubi.mtd=rootfs root=mtd:ubi_rootfs rootfstype=squashfs \
         cnss2.enable_mlo_support=1 rootwait
fsbootargs=ubi.mtd=rootfs root=mtd:ubi_rootfs rootfstype=squashfs \
         cnss2.enable_mlo_support=1
model=RC01                 machid=8050301      fdt_high=0x48500000
flag_boot_rootfs=0         flag_boot_type=2    flag_boot_success=1
```

Built images (`QWRT/extracted/be18000-build/`):

```text
openwrt-qualcommbe-ipq95xx-xiaomi_be18000-initramfs-uImage.itb
openwrt-qualcommbe-ipq95xx-xiaomi_be18000-squashfs-factory.ubi
openwrt-qualcommbe-ipq95xx-xiaomi_be18000-squashfs-sysupgrade.bin
```

FIT contract (verified in [the FIT cross-check](be18000-fit-crosscheck.md)):
`config@al02-c4`, gzip, load/entry `0x42080000`, UBI `kernel` volume, and
`chosen/bootargs-append = " root=/dev/ubiblock0_1"` consumed by kernel hack
920 (a FIT-root `append-bootargs` is optional).

## 2. Bench setup

- USB-TTL on the debug UART, **115200 8N1**, 3.3 V. Do not use the 5 V pin.
- Ethernet from a PC to a LAN port; PC address `192.168.31.100/24`.
- TFTP server rooted at the build directory; HTTP/`nc` available for the
  larger `factory.ubi`.
- Controllable power, and a second terminal capturing the serial log.
- Keep the MAX `uboot.bin` and `mibib.bin` on the PC as the known-good pair.

## 3. Step 0 — back up before writing anything

Enter the U-Boot prompt by pressing a key during the 5 s `bootdelay`, then
boot the OpenWrt initramfs **read-only**:

```text
setenv ipaddr 192.168.31.1
setenv serverip 192.168.31.100
tftpboot 0x50000000 openwrt-qualcommbe-ipq95xx-xiaomi_be18000-initramfs-uImage.itb
bootm 0x50000000
```

From the initramfs:

```sh
cat /proc/mtd
rootfs_mtd=$(awk '$4 ~ /rootfs/ { gsub(/[^0-9]/, "", $1); print $1 }' /proc/mtd)
[ -n "$rootfs_mtd" ] || { echo "rootfs MTD not found"; exit 1; }
rootfs_dev=/dev/mtd${rootfs_mtd}
echo "rootfs MTD: $rootfs_dev"

nanddump -f /tmp/mtd2.bin  /dev/mtd2      # MIBIB
nanddump -f /tmp/mtd17.bin /dev/mtd17     # APPSBLENV
nanddump -f /tmp/mtd18.bin /dev/mtd18     # APPSBL
nanddump -f /tmp/mtd19.bin /dev/mtd19     # APPSBL_1  (never dumped before)
nanddump -f /tmp/mtd20.bin /dev/mtd20     # ART
nanddump -f /tmp/mtd21.bin /dev/mtd21     # ETHPHYFW
dd if="$rootfs_dev" of=/tmp/rootfs-ubi.bin bs=128k   # whole UBI area
dd if=/dev/mtd25 of=/tmp/mtd25.bin bs=64k            # bdata
sha256sum /tmp/mtd*.bin /tmp/rootfs-ubi.bin
```

If `nanddump` is not in the initramfs, substitute
`dd if=/dev/mtdN of=/tmp/mtdN.bin bs=128k` (data only; no OOB).

Copy the files off the router (either works; `nc` is the fallback when the
initramfs has no ssh):

```sh
# router -> PC push
nc 192.168.31.100 9000 < /tmp/mtd18.bin
# PC side: ncat -l -p 9000 > mtd18.bin
```

Checks: `mtd18` is 1,572,864 bytes and its first 549,912 bytes must hash to
`a82b54764a7a3aad49651d702a85ccd645dc51369b1492f2697cd1fb98c1b1e7`.
`mtd19` is the unknown one; keep it even if it looks empty.
Do not continue until every file is off the router and hashed.

## 4. Step 1 — first OpenWrt write

Still in the initramfs, fetch `factory.ubi` (17,039,360 bytes) to `/tmp`:

```sh
# PC push, or wget from a local HTTP server
nc -l -p 9001 > /tmp/factory.ubi
sha256sum /tmp/factory.ubi   # must be ca94bc133adcfbed495567e368056aa46be971256635a77d7b2e32e63f0cc6cf
```

Resolve the `rootfs` mtd by name, then detach any UBI that the bootloader's
`ubi.mtd=rootfs` command line attached during the initramfs boot:

```sh
rootfs_mtd=$(awk '$4 ~ /rootfs/ { gsub(/[^0-9]/, "", $1); print $1 }' /proc/mtd)
[ -n "$rootfs_mtd" ] || { echo "rootfs MTD not found"; exit 1; }
rootfs_dev=/dev/mtd${rootfs_mtd}
echo "rootfs MTD: $rootfs_dev"

if [ -e /sys/class/mtd/mtd${rootfs_mtd}/ubi_num ]; then
    ubidetach -m "$rootfs_mtd" || { echo "UBI detach failed"; exit 1; }
fi
[ ! -e /sys/class/mtd/mtd${rootfs_mtd}/ubi_num ] ||
    { echo "UBI still attached"; exit 1; }
if grep -qE "(${rootfs_dev}( |$)|ubi[0-9]+_|ubiblock[0-9]+_)" /proc/mounts; then
    echo "rootfs UBI is mounted"; exit 1
fi
```

If `ubidetach -m` is unavailable, stop and resolve the attached UBI with
`ubinfo -a` and `/sys/class/mtd/mtd${rootfs_mtd}/ubi_num` before writing.
Do not run `ubiformat` while the existing UBI is attached or mounted.

Write only the resolved `rootfs` mtd:

```sh
ubiformat "$rootfs_dev" -y -f /tmp/factory.ubi
```

`ubiformat` erases the 190 MiB area and writes the image's three volumes:
`kernel` (vol 0), `rootfs` (vol 1), and an autoresizing `rootfs_data`
(vol 2). OpenWrt uses and resizes `rootfs_data` on first boot. Do **not**
use `nand write` for a UBI image, and do not touch any other mtd.

Reboot. Expected: U-Boot `bootipq` reads the `kernel` volume, the kernel
cmdline ends with `root=/dev/ubiblock0_1`, and OpenWrt reaches the login
prompt. If it does not, go to section 6.

After the first successful boot, use the normal image:

```sh
sysupgrade -n openwrt-qualcommbe-ipq95xx-xiaomi_be18000-squashfs-sysupgrade.bin
```

## 5. Step 2 — verify, then keep the U-Boot

```sh
cat /proc/mtd
ubinfo -a                 # kernel, rootfs, rootfs_data
fw_printenv bootcmd bootargs fsbootargs
```

Expected: `bootcmd=bootipq`; the U-Boot version is still
`U-Boot 2016.01 (Jan 01 2024 ...)`. **Do not reflash the bootloader as part
of the OpenWrt install.** It is already the exact image in `QWRT/UBoot` and
there is no rebuild path in this tree.

## 6. Recovery paths

**A. Serial + TFTP (preferred).** Power-cycle, press a key during
`bootdelay`, then repeat the `tftpboot`/`bootm` from section 3. This works
even with a corrupt UBI, because the initramfs is loaded into RAM.

**B. U-Boot web recovery.** Connect the PC at `192.168.31.100/24` and open
`http://192.168.31.1` (live env) or `http://192.168.1.1` (built-in default;
confirm which one answers). Pages: `/index.html`, `/flashing.html`,
`/uboot.html`, `/mibib.html`, `/art.html`.

- **U-Boot** page runs `flash 0:APPSBL; flash 0:APPSBL_1` — it rewrites both
  copies. Only use the MAX `uboot.bin`.
- **MIBIB** page expects exactly 1,048,576 bytes. The ZIP's `mibib.bin` is
  262,144 bytes, so pad it with `0xFF` to 1 MiB first.
- **ART** page expects exactly 1,310,720 bytes.
- **Firmware** page is QWRT's own UBI-volume updater; it is **not** a
  `ubiformat` for `factory.ubi`.

**C. From QWRT Linux.** The package readme says:

```sh
mtd write mibib.bin /dev/mtd2
mtd write uboot.bin /dev/mtd18
```

That updates the primary `0:APPSBL` only; `0:APPSBL_1` is left as-is. The web
U-Boot page is the way to update both.

**D. MIBIB reflash.** Only if mtd2 is corrupt. Use the MAX table; never the
v2 table (it moves bdata/crash and splits rootfs into 120 MiB + 70 MiB
`overlay`). Re-check `mtd2` against `e482188b9d950fd6fa8375df002f143600911a4472e186c9172d072e0fd034a0`
after writing.

## 7. Stop conditions

- Secure-boot fuse state unknown **and** an unsigned APPSBL write is
  proposed: stop. The live unit is on the unsigned path, but that was only
  proven for this unit.
- `mtd19` backup missing: do not proceed to any MIBIB/APPSBL write.
- `factory.ubi` hash mismatch: do not write.
- First boot fails twice: reflash the initramfs, keep the UBI backup, and
  capture the serial log before changing anything else.

## 8. Do not

- Do not flash `BE10000_Uboot_MIBIB_v2.zip`.
- Do not treat the last ~1 MB of mtd18 as a backup image; it is residual.
- Do not `nand write` a raw UBI image.
- Do not `ubiformat` any mtd other than the one resolved as `rootfs`
  (usually mtd24).
