# BE18000 recovery and first-flash runbook (MAX layout)

Status: prepared offline. **Not executed on hardware.** A read-only QWRT
baseline was captured over Wi-Fi on 2026-11-22; serial, TFTP and every NAND
write are still untested.  Walk each step below once with serial attached
before trusting it.

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

The live environment CRC validates over the first 64 KiB only, while the
NAND erase block is 128 KiB.  The mainline image generates
`/dev/mtd17 0x0 0x10000 0x20000 1` for `fw_env`.  The stock QWRT
`/etc/fw_env.config` (`0x40000 0x20000 2`) is wrong and must not be copied.

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
cat /etc/fw_env.config
grep -qx '/dev/mtd17 0x0 0x10000 0x20000 1' /etc/fw_env.config || {
    echo "APPSBLENV fw_env layout mismatch"; exit 1; }
fw_printenv bootcmd bootargs fsbootargs flag_boot_rootfs flag_boot_type flag_boot_success

rootfs_mtd=$(awk '$4 ~ /rootfs/ { gsub(/[^0-9]/, "", $1); print $1 }' /proc/mtd)
[ -n "$rootfs_mtd" ] || { echo "rootfs MTD not found"; exit 1; }
rootfs_dev=/dev/mtd${rootfs_mtd}
rootfs_size=$(awk '$4 ~ /rootfs/ { print $2; exit }' /proc/mtd)
[ -n "$rootfs_size" ] || { echo "rootfs MTD size not found"; exit 1; }
echo "rootfs MTD: $rootfs_dev (0x$rootfs_size)"

nanddump -f /tmp/mtd2.bin  /dev/mtd2      # MIBIB
nanddump -f /tmp/mtd17.bin /dev/mtd17     # APPSBLENV
nanddump -f /tmp/mtd18.bin /dev/mtd18     # APPSBL
nanddump -f /tmp/mtd19.bin /dev/mtd19     # APPSBL_1  (never dumped before)
nanddump -f /tmp/mtd20.bin /dev/mtd20     # ART
nanddump -f /tmp/mtd21.bin /dev/mtd21     # ETHPHYFW
dd if="$rootfs_dev" of=/tmp/rootfs-ubi.bin bs=128k || {
    echo "rootfs UBI backup read failed"; exit 1; }
dd if=/dev/mtd25 of=/tmp/mtd25.bin bs=64k            # bdata

rootfs_backup_bytes=$(wc -c < /tmp/rootfs-ubi.bin)
[ "$rootfs_backup_bytes" -eq $((0x$rootfs_size)) ] || {
    echo "truncated rootfs UBI backup: $rootfs_backup_bytes bytes, expected $((0x$rootfs_size))";
    exit 1; }
cd /tmp
sha256sum mtd*.bin rootfs-ubi.bin > backup.sha256
cat backup.sha256
```

If `nanddump` is not in the initramfs, substitute
`dd if=/dev/mtdN of=/tmp/mtdN.bin bs=128k` (data only; no OOB).

The `ipaddr`/`serverip` values from U-Boot do not carry into Linux. Configure
the initramfs LAN interface first, then transfer all backups, including the
190 MiB `rootfs-ubi.bin`:

```sh
ip addr show
# Use the LAN interface shown above (normally lan1 or br-lan).
lan_if=lan1
ip link set "$lan_if" up
ip addr add 192.168.31.1/24 dev "$lan_if" 2>/dev/null || true
ip addr show dev "$lan_if"
ping -c 1 192.168.31.100
```

If the PC does not answer, correct the interface name/address before
continuing. Then start the listener on the PC **before** the router command:

```sh
# PC first:
ncat -l -p 9000 > be18000-backup.tar

# Router:
cd /tmp
tar -cf - mtd2.bin mtd17.bin mtd18.bin mtd19.bin mtd20.bin mtd21.bin \
    mtd25.bin rootfs-ubi.bin backup.sha256 | nc 192.168.31.100 9000
```

`/tmp` is RAM and does not survive a reboot. The extracted PC copy is the
rollback source. Verify every surviving file before continuing:

```sh
mkdir -p be18000-backup
tar -xf be18000-backup.tar -C be18000-backup
cd be18000-backup
sha256sum -c backup.sha256
rootfs_bytes=$(wc -c < rootfs-ubi.bin)
[ "$rootfs_bytes" -eq 199229440 ] || {
    echo "rollback copy truncated: $rootfs_bytes bytes, expected 199229440";
    exit 1; }
sha256sum rootfs-ubi.bin | tee rootfs-ubi.sha256
```

Do not proceed until `sha256sum -c backup.sha256` passes and
`rootfs-ubi.bin` is exactly 190 MiB (`0xbe00000`).

Checks: `mtd18` is 1,572,864 bytes and its first 549,912 bytes must hash to
`a82b54764a7a3aad49651d702a85ccd645dc51369b1492f2697cd1fb98c1b1e7`.
`mtd19` is the unknown one; keep it even if it looks empty.
Do not continue until every file is off the router and hashed.

## 4. Step 1 — first OpenWrt write

Still in the initramfs, pull `factory.ubi` (17,432,576 bytes) from the PC
using the router as the client, as in the backup transfer:

```sh
# PC first:
ncat -l -p 9001 < openwrt-qualcommbe-ipq95xx-xiaomi_be18000-squashfs-factory.ubi

# Router:
nc 192.168.31.100 9001 > /tmp/factory.ubi
factory_bytes=$(wc -c < /tmp/factory.ubi)
[ "$factory_bytes" -eq 17432576 ] || {
    echo "truncated factory.ubi: $factory_bytes bytes, expected 17432576";
    exit 1; }
sha256sum /tmp/factory.ubi   # must be 2e66f3e5509f45c5757e0759cd1f50341b34bdbca362b3ba3e0ab96e627e9eb0
```

Resolve the `rootfs` mtd by name, then detach any UBI that the bootloader's
`ubi.mtd=rootfs` command line attached during the initramfs boot:

```sh
rootfs_mtd=$(awk '$4 ~ /rootfs/ { gsub(/[^0-9]/, "", $1); print $1 }' /proc/mtd)
[ -n "$rootfs_mtd" ] || { echo "rootfs MTD not found"; exit 1; }
rootfs_dev=/dev/mtd${rootfs_mtd}
echo "rootfs MTD: $rootfs_dev"

mtd_size() {
    awk -v n="$1" '$4 == "\""n"\"" { print $2; exit }' /proc/mtd
}
mtd_index() {
    awk -v n="$1" '$4 == "\""n"\"" { gsub(/[^0-9]/, "", $1); print $1; exit }' /proc/mtd
}
check_mtd() {
    name="$1"; want_idx="$2"; want_size="$3"
    idx=$(mtd_index "$name"); size=$(mtd_size "$name")
    if [ "$idx" != "$want_idx" ] || [ -z "$size" ] ||
       [ $((0x$size)) -ne $((0x$want_size)) ]; then
        echo "MAX layout mismatch: $name mtd=${idx:-missing} size=${size:-missing}, expected mtd$want_idx/0x$want_size"
        exit 1
    fi
}

mibib_sha=$(dd if=/dev/mtd2 bs=256k count=1 2>/dev/null | sha256sum | cut -d' ' -f1)
[ "$mibib_sha" = e482188b9d950fd6fa8375df002f143600911a4472e186c9172d072e0fd034a0 ] || {
    echo "MIBIB table is not the known MAX layout; stop"; exit 1; }

check_mtd "0:MIBIB" 2 100000
check_mtd "0:APPSBLENV" 17 80000
check_mtd "0:APPSBL" 18 180000
check_mtd "0:APPSBL_1" 19 180000
check_mtd "0:ART" 20 140000
check_mtd "0:ETHPHYFW" 21 100000
check_mtd "rootfs" 24 be00000
check_mtd "bdata" 25 40000
check_mtd "crash" 26 40000
check_mtd "crash_syslog" 27 40000
[ -z "$(mtd_size overlay)" ] || { echo "v2 layout: overlay present"; exit 1; }

rootfs_size=$(mtd_size rootfs)
# /tmp is RAM. If it was lost by a reboot, copy the verified
# rootfs-ubi.bin back from the PC backup before continuing.
[ -f /tmp/rootfs-ubi.bin ] || { echo "rollback backup missing"; exit 1; }
backup_bytes=$(wc -c < /tmp/rootfs-ubi.bin)
[ "$backup_bytes" -eq $((0x$rootfs_size)) ] || {
    echo "rollback backup truncated: $backup_bytes bytes, expected $((0x$rootfs_size))";
    exit 1; }

ubi_dev=
for f in /sys/class/ubi/ubi*/mtd_num; do
    [ -e "$f" ] || continue
    if [ "$(cat "$f")" = "$rootfs_mtd" ]; then
        ubi_dev=${f%/mtd_num}
        ubi_dev=${ubi_dev##*/}
        break
    fi
done

if [ -n "$ubi_dev" ]; then
    ubi_num=${ubi_dev#ubi}
    if grep -qE "/dev/(ubi${ubi_num}_[0-9]+|ubiblock${ubi_num}_[0-9]+|mtd${rootfs_mtd})([[:space:]]|$)|ubi${ubi_num}:" /proc/mounts; then
        echo "rootfs UBI is mounted on $ubi_dev; stop"; exit 1
    fi
    echo "detaching $ubi_dev from mtd${rootfs_mtd}"
    ubidetach -d "$ubi_num" || { echo "UBI detach failed"; exit 1; }
fi

for f in /sys/class/ubi/ubi*/mtd_num; do
    [ -e "$f" ] || continue
    if [ "$(cat "$f")" = "$rootfs_mtd" ]; then
        echo "UBI still attached to mtd${rootfs_mtd}"; exit 1
    fi
done

if grep -qE "/dev/mtd${rootfs_mtd}([[:space:]]|$)" /proc/mounts; then
    echo "rootfs MTD is mounted; stop"; exit 1
fi
```

If `ubidetach` is unavailable, stop and resolve the attached UBI with
`ubinfo -a` and `/sys/class/ubi/ubi*/mtd_num` before writing.
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

Do **not** run sysupgrade from the first boot. Keep this first successful
install running, reboot it once more, and complete section 5. Only after it
has booted successfully at least twice should you consider an update.

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

After the second successful boot and these checks, later updates can use:

```sh
sysupgrade -n openwrt-qualcommbe-ipq95xx-xiaomi_be18000-squashfs-sysupgrade.bin
```

## 6. Recovery paths

**A. Serial + TFTP (preferred).** Power-cycle, press a key during
`bootdelay`, then repeat the `tftpboot`/`bootm` from section 3. This works
even with a corrupt UBI, because the initramfs is loaded into RAM.

**B. U-Boot web recovery.** Connect the PC at `192.168.31.100/24` and open
`http://192.168.31.1` for the live environment. If only the built-in default
answers, change the PC to `192.168.1.100/24` and open `http://192.168.1.1`.
Confirm which address answers before uploading. Pages: `/index.html`,
`/flashing.html`, `/uboot.html`, `/mibib.html`, `/art.html`.

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

The 262,144-byte `mibib.bin` is the `mtd write` file; do not pad it for
this path. It writes the 256 KiB table and leaves the rest of the 1 MiB
MIBIB partition untouched. After writing, verify the first 256 KiB:

```sh
dd if=/dev/mtd2 bs=256k count=1 2>/dev/null | sha256sum
# e482188b9d950fd6fa8375df002f143600911a4472e186c9172d072e0fd034a0
```

That updates the primary `0:APPSBL` only; `0:APPSBL_1` is left as-is. The web
U-Boot page is the way to update both, and it expects a 1 MiB file.

**D. MIBIB reflash.** Only if mtd2 is corrupt. Use the MAX table; never the
v2 table (it moves bdata/crash and splits rootfs into 120 MiB + 70 MiB
`overlay`). The first 256 KiB of the live MIBIB is the MAX table
(`e482...`); the full 1 MiB partition hash is
`7b42075098c82de8ef29655b04d740cee9aa9dd643e7de72f554ac7d0ee6a576`.
Re-check only the table area after writing:

```sh
dd if=/dev/mtd2 bs=256k count=1 2>/dev/null | sha256sum
# must be e482188b9d950fd6fa8375df002f143600911a4472e186c9172d072e0fd034a0
```

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
