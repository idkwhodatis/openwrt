# BE18000 mainline OpenWrt: Phase A/B/C offline build manifest

Date: 2026-11-21; review fixes 2026-11-22

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
  identity, UART console, `ipq9574_s1` regulator, the live
  `tzapp@49B00000` (6 MiB, `no-map`) reservation, the three QCN9224
  host windows, live MIBIB partitions, ART/ETHPHYFW NVRAM cells,
  LEDs/buttons, PWM, I2C sensors, ramoops.
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
- NSSCC owns the shared GPIO60 reset.  The board sets
  `reset-post-delay-us = <100000>` and target patch 0363 makes the
  driver sleep after deasserting the GPIO, preserving the QSDK
  100-110 ms assert and 100-110 ms settle intervals.  The NSSCC
  package reference is the SoC CMN PLL `ETH0_50MHZ_CLK`; the four
  UNIPHY 125 MHz inputs are not wired (`<0>`), and two 312.5 MHz fixed
  clocks supply the PCS RX/TX roots.  `&mdio` runs at 6.25 MHz.
- The 50 MHz parent is supported by the QCA8084 binding, the live QSDK
  MDIO node covering the CMN PLL block at `0x9b000` with
  `mdio_clk_fixup`, and the working QWRT mainline reference.  The
  physical board trace still needs a scope check.
- Board DTS `&qcom_ppe`: ports 1-4 use PCS0 channels 0-3 and
  `10g-qxgmii`, labels `lan1`-`lan4`; port 5 uses PCS1 channel 0 and
  `usxgmii`, label `wan`.  Port 6/SFP is deferred.
- LAN ports use ART MAC offset +1 and WAN uses offset 0.

Review fixes (2026-11-22):

- Reserved the live TrustZone application window
  `tzapp@49B00000`, size `0x600000`, with `no-map`.  The SoC dtsi
  already reserves bootloader, SBL and TZ regions; this adds the
  missing TZ application hand-off window.
- `platform_check_image` for `xiaomi,be18000` now requires exactly one
  `sysupgrade-xiaomi_be18000/` directory with non-empty `CONTROL`, a FIT
  kernel and a squashfs root.  `nand_do_platform_check` verifies the
  archive first; any other container or an ambiguous multi-board tar
  returns 74, so `sysupgrade -F` cannot dispatch a raw `factory.ubi`
  recovery image or a different board directory to NAND.
- Added the tracked buildroot seed
  `target/linux/qualcommbe/ipq95xx/xiaomi_be18000.config` and
  documented the owner-supplied board-2 prerequisite for a build from a
  fresh directory.  The seed selects only core packages, so feeds are
  optional and do not affect the generated image.
- Second review corrected the NSSCC parent clocks: the package
  reference is `&cmn_pll ETH0_50MHZ_CLK`, not the 25 MHz XO; the four
  UNIPHY 125 MHz inputs are not wired (`<0>`), and the MDIO bus runs at
  6.25 MHz.  This matches the working QWRT mainline BE10000 reference
  and the QCA8084 binding.
- Cold-boot review added the missing GPIO60 settling interval.  The
  NSSCC node sets `reset-post-delay-us = <100000>` and patch 0363 makes
  the driver sleep after deasserting the reset, matching the QSDK
  100-110 ms assert and 100-110 ms settle sequence.  The 50 MHz
  reference source is retained with the QSDK CMN PLL/MDIO evidence; a
  board-level scope check remains a hardware gate.

Independent review triage (2026-11-22):

- MDIO pinmux is not missing: `ipq9574.dtsi` sets
  `pinctrl-0 = <&mdio_pins>` on `mdio@90000`; the compiled DTB carries
  it.
- The four LAN ports intentionally share ART MAC +1.  The live system
  uses `...:dd` for `eth0`-`eth3` and `br-lan`; the QSDK `dp2`/`dp3`
  consecutive values are not the live interface MACs.
- The `bootloader`, `SBL`, `TZ` and `SMEM` reservations come from the
  SoC dtsi and are present in the compiled DTB; only `tzapp` is
  board-local.
- GPIO60 reset polarity follows the working mainline reference
  (`GPIO_ACTIVE_LOW`); the live QSDK `phy-reset-gpio` flag is not the
  mainline binding.
- The four `<0>` NSSCC parents match the working reference and are
  intentionally empty because those UNIPHY inputs are not wired.
- A fresh copy with no feeds completed `make defconfig` with the same
  five seed selections; the full build was performed in the copied WSL
  tree.

## Artifacts

Artifacts are archived under `QWRT/extracted/be18000-build/`.

| File | Size | SHA-256 |
|---|---:|---|
| `openwrt-qualcommbe-ipq95xx-xiaomi_be18000-initramfs-uImage.itb` | 18,104,852 | `8a7ada4ac87254ab231a313e9af6ef8b4354ad366550fc367e3939cc46343cf8` |
| `openwrt-qualcommbe-ipq95xx-xiaomi_be18000-squashfs-factory.ubi` | 17,039,360 | `17d350daa7afa77769229210f60d11e9624e990305f5b966489525991678ff98` |
| `openwrt-qualcommbe-ipq95xx-xiaomi_be18000-squashfs-sysupgrade.bin` | 16,097,541 | `bf367e97f45adfd4424eb78ec8934be97eb21a1832f3d89538ec295b2ad45aa1` |
| `openwrt-qualcommbe-ipq95xx-xiaomi_be18000.manifest` | 4,471 | `7f22d11663e8815013c4c01f63caba77cc71fb3d051784193e81a5251d950823` |
| `profiles.json` | 2,123 | `2f9b2e2d2af0d6e6962edd0c459bda98f5788a0ad1f6b5c31e5afd10df6d8df1` |
| `config.buildinfo` | 152 | `b65255fd8dbd33a196f1aad512d07e5c8a28188de75c82bb25561d2447abc4b3` |

## FIT inspection

Both the standalone initramfs FIT and the kernel volume inside
`factory.ubi` report:

- Default configuration: `config@al02-c4`
- Kernel compression: gzip
- Load/entry: `0x42080000`
- FDT description: `xiaomi_be18000`
- FDT size: 42,827 bytes

The embedded board DTB reports:

```text
model:               Xiaomi BE18000
compatible:          xiaomi,be18000 qcom,ipq9574-ap-al02-c4 qcom,ipq9574
chosen bootargs-append: " root=/dev/ubiblock0_1"
rootfs partition:    rootfs @ 0x1780000, size 0xbe00000
0:ART nvmem:         mac-base
0:ETHPHYFW nvmem:    aqr-fw @ 0x28, size 0x60002
tzapp:               0x49b00000, size 0x600000 (no-map)
ramoops:             0x4dd00000, size 0x400000
QCN9224 windows:     0x50f00000 / 0x54100000 / 0x57300000, 0x3200000 each
```

Ethernet nodes in the same DTB:

```text
mdio:                okay, 6,250,000 Hz
QCA8084 NSSCC:       qcom,qca8084-nsscc @ 0x18
NSSCC reset:         GPIO60 active-low, 100,000 us post-delay
NSSCC reference:     cmn_pll ETH0_50MHZ_CLK + two 312.5 MHz roots
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
  `ath12k-firmware-qcn9274` package.  It is owner-supplied device data
  and is intentionally not tracked; a fresh build must place and verify
  it as described under Reproduce.
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

A fresh build needs three inputs: the source at the commit containing
this manifest, the owner-supplied board-2 binary, and the tracked
buildroot seed.  Feeds are optional: the seed selects only core
packages, so no feed revision affects the generated image.  The board-2
binary is deliberately not committed while its redistribution rights
are unresolved.

```sh
# 1. Source.  Check out the commit containing this manifest.
cd /path/to/openwrt
# Feeds are only needed for menuconfig or extra feed packages:
# ./scripts/feeds update -a
# ./scripts/feeds install -a

# 2. Owner-supplied board-2 (not tracked).
cp /path/to/board-live-be18000.qcn9274 \
   package/firmware/ipq-wifi-xiaomi-be18000/files/board-2.bin
sha256sum package/firmware/ipq-wifi-xiaomi-be18000/files/board-2.bin
# Expect 292256 bytes and
# 0fcbb66e0a229bafc2bad9dd7cc8a5488134f4808673e73cd2808437849ab9e6

# 3. Target/device seed and build.
cp target/linux/qualcommbe/ipq95xx/xiaomi_be18000.config .config
make defconfig
make REVISION=be18000 -j"$(nproc)" V=s
```

The seed selects target `qualcommbe`, subtarget `ipq95xx`, device
`xiaomi_be18000`, the initramfs image and `kmod-input-core`;
`make defconfig` fills in the remaining target, package and image
defaults.  The archived 152-byte `config.buildinfo` is the complete
non-default diff, not a truncated package list: `DEVICE_PACKAGES` in
`target/linux/qualcommbe/image/ipq95xx.mk` supplies the per-device
packages.  `REVISION=be18000` keeps the release string stable.  The
copied WSL tree used for this manifest has no `.git`, so it is mandatory
there; in a fresh clone it is optional but recommended.

For the copied WSL tree, sync without stale files or host build outputs
first, then apply steps 2 and 3:

```sh
rsync -a --delete \
  --exclude=/.git --exclude=/QWRT --exclude=/qsdk \
  --exclude=/build_dir --exclude=/staging_dir --exclude=/tmp \
  --exclude=/bin --exclude=/dl --exclude=/.config \
  --exclude='/build*.log' --exclude='/build*.rc' \
  /path/to/openwrt/ ~/be18000-build/
cd ~/be18000-build
cp /path/to/board-live-be18000.qcn9274 \
   package/firmware/ipq-wifi-xiaomi-be18000/files/board-2.bin
cp target/linux/qualcommbe/ipq95xx/xiaomi_be18000.config .config
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
