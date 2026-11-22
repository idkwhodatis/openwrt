# BE18000 mainline OpenWrt: Phase A/B/C offline build manifest

Date: 2026-11-21

This manifest records the successful offline build of the
`qualcommbe/ipq95xx` image for the modified BE10000 identified as
`xiaomi,be18000`.  It is evidence for the source, image-layout and
static board-DTS gates only.  No serial console, RAM boot, NAND write,
PHY probe or radio probe has been performed.

## Source and build host

| Item | Value |
|---|---|
| Source tree | fork `idkwhodatis/openwrt`, Phase A/B/C implementation |
| Build host | WSL2 Ubuntu 22.04, `/home/leaf/be18000-build` (case-sensitive ext4) |
| Target | `qualcommbe`, subtarget `ipq95xx` |
| Device | `CONFIG_TARGET_qualcommbe_ipq95xx_DEVICE_xiaomi_be18000=y` |
| Rootfs | squashfs plus `CONFIG_TARGET_ROOTFS_INITRAMFS=y` |
| Kernel | Linux 6.18.60, aarch64, musl, GCC 14.4.0 |
| Build command | `make REVISION=be18000 -j16 V=s` |

The copied build tree has no `.git`, so `REVISION=be18000` is supplied
on the command line.  Without it, base-files carries the invalid APK
version suffix `~unknown`.

Phase A source changes:

- `target/linux/qualcommbe/image/ipq95xx.mk`: `Device/xiaomi_be18000`
  with gzip `FitImage`, `UbiFit`, `KERNEL_LOADADDR=0x42080000`,
  `DEVICE_DTS_CONFIG=config@al02-c4`, `BLOCKSIZE=0x20000`,
  `PAGESIZE=2048`, `SUBPAGESIZE=2048`, `VID_HDR_OFFSET=2048`,
  `IMAGE_SIZE=199229440` (`0xbe00000`).
- `target/linux/qualcommbe/dts/ipq9574-xiaomi-be18000.dts`: board
  identity, UART console, `ipq9574_s1` regulator, reserved memory,
  live MIBIB partitions, ART/ETHPHYFW NVRAM cells, LEDs/buttons, PWM,
  I2C sensors, ramoops.
- `package/firmware/ipq-wifi-xiaomi-be18000/`: live 292,256-byte
  `board-2.bin` installed through `install-overlay`.
- `target/linux/qualcommbe/ipq95xx/base-files/etc/board.d/02_network`
  and `.../lib/upgrade/platform.sh`: Xiaomi interface and NAND upgrade
  cases.
- `package/boot/uboot-tools/uboot-envtools/files/qualcommbe_ipq95xx`:
  `0:APPSBLENV` `fw_env` configuration for Xiaomi.
- `package/kernel/mac80211/ath.mk`: `kmod-ath12k` declares
  `+kmod-mhi-bus`.

Phase B/C source changes:

- Board DTS `&mdio`: enabled QCA8084 NSSCC at `0x18`, package at `1`,
  four QCA8084 PHYs at `1`-`4`, `pcs-phy@6`, `xpcs-phy@7` with four
  XPCS channel clock/reset sets, and AQR113C at C45 address 0 with the
  `0:ETHPHYFW` nvmem firmware.
- NSSCC owns the shared GPIO60 reset.  NSSCC reference inputs are fixed
  clock nodes at 25 MHz XO, 125 MHz UNIPHY0/1 RX/TX and 312.5 MHz
  UNIPHY1 RX/TX 312P5M; the real package clock tree remains unverified.
- Board DTS `&qcom_ppe`: ports 1-4 use PCS0 channels 0-3 and
  `10g-qxgmii`, labels `lan1`-`lan4`; port 5 uses PCS1 channel 0 and
  `usxgmii`, label `wan`.  Port 6/SFP is deferred.
- LAN ports use ART MAC offset +1 and WAN uses offset 0.

## Artifacts

Artifacts are archived under `QWRT/extracted/be18000-build/`.

| File | Size | SHA-256 |
|---|---:|---|
| `openwrt-qualcommbe-ipq95xx-xiaomi_be18000-initramfs-uImage.itb` | 18,103,892 | `642bbc2fc34c155be04b23a2f648a26f1ebf15d352778c79f06e5a226b55f41c` |
| `openwrt-qualcommbe-ipq95xx-xiaomi_be18000-squashfs-factory.ubi` | 17,039,360 | `14d5fce6e884ceb6e1b063373fae8659be843c478f948d40d22c7af320b39923` |
| `openwrt-qualcommbe-ipq95xx-xiaomi_be18000-squashfs-sysupgrade.bin` | 16,097,541 | `3975ea1398ff3785256b3ada179c67f3d8745a51e2ed0eb60ceb236bded1082f` |
| `openwrt-qualcommbe-ipq95xx-xiaomi_be18000.manifest` | 4,471 | `7f22d11663e8815013c4c01f63caba77cc71fb3d051784193e81a5251d950823` |
| `profiles.json` | 2,123 | `56e32fe63e431b296bdf23082ac56f4176be745778c352806648a199671cd7ac` |

## FIT inspection

Both the standalone initramfs FIT and the kernel volume inside
`factory.ubi` report:

- Default configuration: `config@al02-c4`
- Kernel compression: gzip
- Load/entry: `0x42080000`
- FDT description: `xiaomi_be18000`
- FDT size: 43,199 bytes

The embedded board DTB reports:

```text
model:               Xiaomi BE18000
compatible:          xiaomi,be18000 qcom,ipq9574-ap-al02-c4 qcom,ipq9574
chosen bootargs-append: " root=/dev/ubiblock0_1"
rootfs partition:    rootfs @ 0x1780000, size 0xbe00000
0:ART nvmem:         mac-base
0:ETHPHYFW nvmem:    aqr-fw @ 0x28, size 0x60002
ramoops:             0x4dd00000, size 0x400000
QCN9224 windows:     0x50f00000 / 0x54100000 / 0x57300000, 0x3200000 each
```

Ethernet nodes in the same DTB:

```text
mdio:                okay
QCA8084 NSSCC:       qcom,qca8084-nsscc @ 0x18
QCA8084 package:     qcom,qca8084-package @ 1
package mode:        0 (PCS1 10G-QXGMII, PCS0 unused)
address fixup:       1 2 3 4 5 6 7
PHYs:                1, 2, 3, 4 (ethernet-phy-id004d.d180)
PCS/XPCS:            pcs-phy@6, xpcs-phy@7 with four channels
PPE port 1-4:        lan1-lan4, phy-mode 10g-qxgmii
PPE port 5:          wan, phy-mode usxgmii
AQR113C:             C45 address 0, nvmem-cell "firmware"
```

## UBI layout

`ubireader_display_info` on `factory.ubi`:

- Min I/O 2048, LEB 126,976 bytes, PEB 131,072 bytes
- 130 PEBs total (128 data, 2 layout)
- Volume `kernel`, ID 0, 48 PEBs
- Volume `rootfs`, ID 1, 80 PEBs, squashfs
- Volume `rootfs_data`, ID 2, `autoresize`

The `kernel` volume is a FIT; `mkimage -l` reports the same
`config@al02-c4`, gzip and `0x42080000` values as the standalone FIT.

## Root filesystem contents

Extracted from the sysupgrade root and from the factory UBI `rootfs`
volume:

- `/lib/firmware/ath12k/QCN9274/hw2.0/board-2.bin` is 292,256 bytes
  with SHA-256
  `0fcbb66e0a229bafc2bad9dd7cc8a5488134f4808673e73cd2808437849ab9e6`.
  This is the live Xiaomi board-2, applied after the official
  `ath12k-firmware-qcn9274` package.
- `/lib/firmware/ath12k/QCN9274/hw2.0/firmware-2.bin` is present
  (16,035,896 bytes).
- `/etc/uci-defaults/30_uboot-envtools` contains the
  `xiaomi,be18000` `0:APPSBLENV` case.
- `/etc/openwrt_release` reports `OpenWrt SNAPSHOT be18000`.

Package manifest subset:

```text
ath12k-firmware-qcn9274 20261019-r1
ipq-wifi-xiaomi_be18000 1
kmod-ath12k 6.18.60.7.2-r15
kmod-mhi-bus 6.18.60-r1
kmod-qrtr 6.18.60-r1
kmod-qrtr-mhi 6.18.60-r1
kmod-qcom-ppe 6.18.60-r1
kmod-sfp 6.18.60-r1
kmod-pstore 6.18.60-r1
kmod-ramoops 6.18.60-r1
kmod-hwmon-emc2305 6.18.60-r1
kmod-hwmon-lm63 6.18.60-r1
kmod-leds-pwm 6.18.60-r1
```

## Reproduce

```sh
rsync -a --delete \
  --exclude=/.git --exclude=/QWRT --exclude=/qsdk \
  --exclude=/build_dir --exclude=/staging_dir --exclude=/tmp \
  --exclude=/bin --exclude=/dl --exclude=/.config \
  --exclude='/build*.log' --exclude='/build*.rc' \
  /path/to/openwrt/ ~/be18000-build/
cd ~/be18000-build
make defconfig
make REVISION=be18000 -j"$(nproc)" V=s
```

## Remaining gates

This manifest does **not** establish:

- a successful RAM boot or serial console on the actual unit;
- QCA8084 package probe, PHY ID reads, clock/reset programming, or
  2.5G/10G link and traffic (the static DTS nodes are present);
- PCIe enumeration, board-2 selection or QCN9224 firmware start;
- cold-boot calibration, 5G/6G operation or MLO;
- NAND writes, sysupgrade or recovery on hardware.

The next hardware step is the serial/RAM-FIT gate in the port plan.  Do
not flash the factory UBI until the protected partitions are backed up
and the recovery path has been rehearsed.
