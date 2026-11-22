# BE18000 mainline OpenWrt: Phase A offline build manifest

Date: 2026-11-21

This manifest records the first successful offline build of the
`qualcommbe/ipq95xx` image for the modified BE10000 identified as
`xiaomi,be18000`.  It is evidence for the source and image-layout gates
only.  No serial console, RAM boot, NAND write or radio probe has been
performed.

## Source and build host

| Item | Value |
|---|---|
| Source tree | fork `idkwhodatis/openwrt`, commit `da61e6e6b2` plus the Phase A changes below |
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

## Artifacts

Artifacts are archived under `QWRT/extracted/be18000-build/`.

| File | Size | SHA-256 |
|---|---:|---|
| `openwrt-qualcommbe-ipq95xx-xiaomi_be18000-initramfs-uImage.itb` | 18,098,808 | `3285bc24991cdd536bb5b57a3482f5e6c6f77b3c6d59c156668fa0fdb0d02e84` |
| `openwrt-qualcommbe-ipq95xx-xiaomi_be18000-squashfs-factory.ubi` | 17,039,360 | `4423af87622efac76c0e8aba1fe24b675f205604878bdb6bfac0348493d6da22` |
| `openwrt-qualcommbe-ipq95xx-xiaomi_be18000-squashfs-sysupgrade.bin` | 16,097,541 | `aee932fc90e66528bcb618ab0e8deff169078502078d907dccd2131cb40457c3` |
| `openwrt-qualcommbe-ipq95xx-xiaomi_be18000.manifest` | 4,471 | `7f22d11663e8815013c4c01f63caba77cc71fb3d051784193e81a5251d950823` |
| `profiles.json` | 2,123 | `950f08c649a112d14c24c25ddd240a17e7448bdf45e020b5b78916d8e804fbf2` |

## FIT inspection

Both the standalone initramfs FIT and the kernel volume inside
`factory.ubi` report:

- Default configuration: `config@al02-c4`
- Kernel compression: gzip
- Load/entry: `0x42080000`
- FDT description: `xiaomi_be18000`
- FDT size: 37,881 bytes

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
- Ethernet, QCA8084, AQR113C or SFP operation;
- PCIe enumeration, board-2 selection or QCN9224 firmware start;
- cold-boot calibration, 5G/6G operation or MLO;
- NAND writes, sysupgrade or recovery on hardware.

The next hardware step is the serial/RAM-FIT gate in the port plan.  Do
not flash the factory UBI until the protected partitions are backed up
and the recovery path has been rehearsed.
