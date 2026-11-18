# BE10000 vs BE18000 QWRT firmware: 20 OpenWrt gap rounds

Research note, 2026-11-18. Read-only against the saved QWRT images and the
OpenWrt target source. The BE18000 and BE10000 are different board profiles
with the same AP-AL02-C4 hardware family; the goal is to identify what the
current OpenWrt `qualcommbe/ipq95xx` target already covers and what still has
to be added for each device.

## Evidence base

| Source | What it is |
|---|---|
| `QWRT/extracted/live-be18000/` | Live modified BE18000 QWRT dump: QWRT 5.4.250 / QSDK 12.2 R7, live DT/FIT/ART/UBI/APPSBLENV. |
| `QWRT/extracted/qsdk13-r26.09.05-be18000/` | QSDK13 reference for the modified BE18000: board DTS, QCN9224 firmware, fw INI, caldb addresses. |
| `QWRT/extracted/qwrt-25.12.2-be10000/` | QWRT 25.12.2 r48190 (`ipq95xx/generic`) for the standard BE10000, kernel 5.4.213 / QSDK 12.5: board DTS, UBI/FIT, BDFs, QWRT board scripts, BE7000 mainline draft. |
| `QWRT/doc/be18000-*.md` | Prior live probes, risk research, and port plan. |
| `target/linux/qualcommbe/` | Current OpenWrt target: DTS, `ipq95xx.mk`, patches, config, base-files. |

Method: each round has four parts: (1) probe the QWRT BE18000 firmware;
(2) probe the QWRT BE10000 firmware; (3) compare with the current OpenWrt
implementation; (4) record the uncovered work and a concrete plan. "Observed"
means read from a saved image or source file; "derived" means a direct
consequence; "inferred" means needs the board.

The two firmware generations are not interchangeable:

- **BE18000 live**: QWRT 5.4.250 / QSDK 12.2, modified radio profile
  (`xiaomi,be18000`), 3x QCN9224 (2.4G/5G/6G), SKY85798 6G FEM, live BDFs
  `bdwlan.b0001/2/4`, variants `Xiaomi_BE18000_live_1/2/4`, high-band ART
  blank, coldboot calibration, 2 GiB in the live DT.
- **BE10000**: QWRT 25.12.2 / QSDK 12.5, standard BE10000 profile, 3x
  QCN62xx family (2.4G/5G/5G), BDFs `bdwlan.b01/b02/b04`, variants
  `Xiaomi_BE10000_1/4/2`, ART caldata at 0x58800/0x8A800/0xBC800,
  QWRT DTB hardcodes 1 GiB (retail hardware is 2 GiB).

The BE10000 README and `BE10000-vs-AL02C4.md` are extraction notes, not
mainline code; all plan items below still have to be implemented and tested.

## Round summary

| Round | Topic | Main gap |
|---:|---|---|
| 1 | Image/version/UBI/FIT | Two device definitions and a shared image layout |
| 2 | Board identity/memory/reserved memory | Per-device memory/reservations |
| 3 | NAND/MIBIB/ETHPHYFW/ART | Fixed MIBIB vs `qcom,smem-part` |
| 4 | U-Boot/FIT/bootargs/recovery | FIT `append-bootargs` + env/recovery |
| 5 | Ethernet port/PPE/PCS map | Mainline PPE/PCS nodes and `02_network` |
| 6 | QCA8084 package/NSSCC | QCA8084 package + NSSCC DTS |
| 7 | AQR113C/NVMEM/firmware | Per-device ETHPHYFW payload |
| 8 | SFP+ port 6 | EEPROM vs QCA SFP PHY |
| 9 | PCIe/WSI/board IDs | Per-device radio variants |
| 10 | WiFi BDF/board-2 | Two board-2 files and variants |
| 11 | Firmware/calibration | `firmware-2.bin`, coldboot vs ART |
| 12 | ART/BDF/caldata | Per-device caldata policy |
| 13 | MLO/DCS/auth | Opt-in MLO, no QSDK DCS |
| 14 | LEDs/buttons/PWM | Xiaomi board I/O nodes |
| 15 | I2C/fan/NFC/thermal | Board I2C/fan/NFC nodes |
| 16 | MAC/network/board.d | Xiaomi `02_network`/`01_leds` cases |
| 17 | Kernel config/packages | Mainline package/config delta |
| 18 | Existing OpenWrt device support | Common DTSI + two devices |
| 19 | Driver/binding coverage | What is upstream vs missing |
| 20 | Final gap matrix/roadmap | Implementation order and effort |

## Round 1: Image, firmware generation, UBI and FIT

**Probe QWRT BE18000 firmware.** The live dump is QWRT/QSDK 12.2
(5.4.250). The live FIT is `config@al02-c4`, gzip, load/entry
`0x42080000`, fdt `xiaomi_be18000`; the UBI has 1,520 LEBs of 126,976 B
with `kernel` 44, `rootfs` 407, `rootfs_data` 1,025; the rootfs mtd is
`0x1780000/0xbe00000`; the MIBIB has 28 entries.

**Probe QWRT BE10000 firmware.** The extracted image is QWRT 25.12.2
r48190 (`ipq95xx/generic`), kernel 5.4.213 / QSDK 12.5. It is a plain UBI
image: PEB 0x20000, page 2048, VID header 2048, LEB 0x1f000, image_seq
0x69ab329; `kernel` 46 LEBs (5,840,896 B), `rootfs` 446 LEBs
(56,631,296 B), `rootfs_data` empty/dynamic. Its FIT is also
`config@al02-c4`, gzip, load/entry `0x42080000`, fdt
`xiaomi_be10000`, Linux 5.4.213.

**Compare with OpenWrt.** `target/linux/qualcommbe/image/Makefile` has
`Device/FitImage` (gzip) and `Device/UbiFit` (`KERNEL_IN_UBI=1`,
`factory.ubi`), but no Xiaomi device. `Device/Default` uses
`KERNEL_LOADADDR=0x41000000`; `qcom_rdp433` uses lzma at its own address;
`sbe1v1k` uses gzip. There is no `ipq9574-xiaomi` DTS and no Xiaomi image
definition.

**Gap and plan.** Add a shared Xiaomi image baseline: `Device/FitImage` +
`Device/UbiFit`, `KERNEL_LOADADDR=0x42080000`, gzip, `config@al02-c4`,
`BLOCKSIZE=0x20000`, `PAGESIZE=2048`, `SUBPAGESIZE=2048`,
`VID_HDR_OFFSET=2048`, and a FIT-root `append-bootargs` for
`root=/dev/ubiblock0_1`. Then add two device wrappers:
`xiaomi_be10000` with BE10000 DTS/config and `xiaomi_be18000` with the
modified DTS/config. The BE10000 image rootfs is 56.6 MiB; the BE18000
rootfs volume is 49.2 MiB in a 190 MiB partition; both fit `UbiFit` but
need separate `IMAGE_SIZE`/rootfs volume expectations. Build/inspect both
`factory.ubi` and FIT before any hardware step.

## Round 2: Board identity, memory, and reserved memory

**Probe QWRT BE18000 firmware.** Live root:
`model = "Xiaomi Router BE18000 Pro Max (Wi-Fi 7 320Mhz)"` and
`compatible = "xiaomi,be18000", "qcom,ipq9574-ap-al02-c4",
"qcom,ipq9574-al02", "qcom,ipq9574"`. Live memory is 2 GiB at
`0x40000000`. The QCN9224 regions are `0x50f00000`, `0x54100000`,
`0x57300000` (0x3200000 each), caldb at +0x1e00000 (8 MiB), plus `tzapp`
and the disabled `q6_caldb_region`.

**Probe QWRT BE10000 firmware.** `board.dts` root is
`Xiaomi Router BE10000 (Wi-Fi 7)`, compatible `xiaomi,be10000` plus the
same QSDK `qcom,ipq9574-ap-al02-c4`/`qcom,ipq9574` strings. The DTB
hardcodes 1 GiB at `0x40000000`; the retail hardware is 2 GiB and the
stock U-Boot likely fixes it up. The QSDK regions are
`0x4f400000`, `0x51900000`, `0x53e00000` (0x2500000 each = 37 MiB),
`dma_pool1/2/3` 0x900000, `mlo_global_mem_0` 0x1100000; `tzapp` is at
`0x49B00000`.

**Compare with OpenWrt.** `sbe1v1k` has only `tzapp`; `rdp433` has the
RDP reserved map; the target config has `CONFIG_MTD_QCOMSMEM_PARTS`.
There is no Xiaomi memory node, no BE10000/BE18000 reserved map, and no
mainline caldb node. The live BE18000 QSDK map is not the mainline ath12k
memory map; mainline allocates DMA for most regions.

**Gap and plan.** Use 2 GiB memory on both devices (verify the BE10000
U-Boot fixup; do not copy the 1 GiB DTB). Add a per-device reserved-memory
section: `tzapp` common; BE18000 adds the three 50 MiB QCN9224 regions and
the 8 MiB caldb addresses; BE10000 does not need the QSDK cnss regions for
mainline ath12k, but needs the `tzapp` and any RAM the bootloader reserves.
Keep `memory@40000000` out of the reserved regions. If mainline ath12k is
given a `memory-region`, use only the regions it consumes; do not copy the
QSDK `dma_pool`/`mlo_global_mem` names.

## Round 3: NAND, MIBIB, ETHPHYFW, and ART

**Probe QWRT BE18000 firmware.** The live `0:MIBIB` table has 28 entries:
`0:ART 0x1480000/0x140000`, `0:ETHPHYFW 0x15c0000/0x100000`,
`rootfs 0x1780000/0xbe00000`, `bdata 0xd580000/0x40000`,
`crash`/`crash_syslog` 0x40000 each. NAND is QPIC, ECC 4/512, 8-bit,
training offset 0x16c0000. The live ART has BDFs at 0x1000/0x33000/
0x65000 and blank high-band slots.

**Probe QWRT BE10000 firmware.** The BE10000 `board.dts` uses
`qcom,smem-part` rather than a fixed partition list, with
`partition-0-ethphyfw` and an `aqr-fw@0` nvmem cell. The extracted UBI
image is 63.2 MiB (494 PEBs), NAND 256 MiB, ECC 4/512. The QWRT rootfs
scripts read ART at 0x58800/0x8A800/0xBC800; the `0:ethphyfw` cell is the
AQR source.

**Compare with OpenWrt.** `Device/UbiFit` exists; `CONFIG_MTD_QCOMSMEM_PARTS`
and `CONFIG_MTD_NAND_QCOM` are enabled; the target has RDP433 fixed
partition nodes and no Xiaomi NAND node. `11-ath12k-caldata` only has the
sbe1v1k fixed offsets. There is no `qcom,smem-part` BE10000 DTS and no
BE18000 fixed MIBIB DTS.

**Gap and plan.** Add two NAND descriptions: BE18000 uses the exact live
MIBIB table and fixed `0:ART`/`0:ETHPHYFW` partitions; BE10000 uses
`qcom,smem-part` plus the `partition-0-ethphyfw` nvmem layout. Both need
`nand-ecc-strength=4`, `nand-ecc-step-size=512`, QPIC pins and the
`aqr_fw@28/0x60002` cell. Use `ubiformat` for the rootfs mtd in both
cases; do not `nand write` a raw UBI image. Preserve ART/ETHPHYFW/APPSBL/
MIBIB.

## Round 4: U-Boot, FIT, bootargs, and recovery

**Probe QWRT BE18000 firmware.** Live `0:APPSBLENV` has
`bootcmd=bootipq`, `bootargs=ubi.mtd=rootfs root=mtd:ubi_rootfs
rootfstype=squashfs ... rootwait`, and `fsbootargs` without
`root=/dev/ubiblock0_1`. The live FIT root has no `append-bootargs`; the
live runtime `/chosen` has `bootargs-append = " root=/dev/ubiblock0_1
..."`. The U-Boot has web recovery pages and a secure-boot fuse check;
the live plain FIT uses the unsigned path.

**Probe QWRT BE10000 firmware.** Its FIT is the same `config@al02-c4`,
gzip, `0x42080000`; its `/chosen` has the same style of
`bootargs-append = " root=/dev/ubiblock0_1 cnss2.enable_mlo_support=1
swiotlb=1 coherent_pool=2M"`. `qwrt-files/etc/uci-defaults/30_uboot-envtools`
detects the `APPSBLENV` mtd and writes `/etc/fw_env.config` with a fixed
0x40000 env size (or the mtd size for NOR).

**Compare with OpenWrt.** `scripts/mkits.sh` emits the FIT but no
`append-bootargs`; `include/image-commands.mk` has no `-b` option.
`platform.sh` has no Xiaomi case; `uboot-envtools` is in the target
defaults. The live BE18000 FIT proves the config/load/gzip layout, but
the QSDK `chosen/bootargs-append` is not a mainline consumer.

**Gap and plan.** Add a common FIT-root `append-bootargs` path (extend
`Build/fit-its`/`mkits.sh` with a device variable) and use
`root=/dev/ubiblock0_1`, with optional `swiotlb=1 coherent_pool=2M`; do
not include `cnss2`. Add a Xiaomi `fw_env.config`/`30_uboot-envtools`
equivalent for the `APPSBLENV` mtd and a `platform.sh` NAND case. For
recovery, use a serial/TFTP initramfs and `ubiformat`; do not rely on the
web recovery accepting a raw `factory.ubi`. Check the secure-boot fuse
before flashing.

## Round 5: Ethernet ports, PPE, and PCS

**Probe QWRT BE18000 firmware.** Live `qcom,port_phyinfo`: ports 0-3 are
port_id 1-4 with PHY 1-4 (QCA8084 2.5G); port 4 is port_id 5, PHY 0
(C45 AQR113C); port 5 is port_id 6, PHY 0x1e, reset GPIO64, media-type
`sfp`. `dp1-4` are `sgmii` in QSDK12, `qusgmii` in QSDK13; `dp5/6` are
`sgmii` (12) or `usxgmii` (13). The live WAN is `eth4`.

**Probe QWRT BE10000 firmware.** Its `port_phyinfo` has the same PHY map
(1-4, 0, 0x1e). `qwrt-files/etc/board.d/02_network` explicitly lists
`xiaomi,be10000` and `xiaomi,be18000` as
`ucidef_set_interfaces_lan_wan "eth0 eth1 eth2 eth3 eth5" "eth4"`.
The BE7000 mainline draft uses `10g-qxgmii` for ports 1-4, `usxgmii` for
port 5 and `10gbase-r`/`sff,sfp` for port 6.

**Compare with OpenWrt.** The target has `qcom_ppe`, the PCS driver,
RDP433 port nodes (`pcs0_ch0..3`, `pcs1_ch0`, `pcs2_ch0`) and the
`kmod-qcom-ppe` package; it has no Xiaomi `qcom_ppe` nodes and no Xiaomi
`02_network` case. The current `02_network` only handles
kiwi/sbe1v1k/ln6001/qcom AP-AL02-C7.

**Gap and plan.** Add a shared `qcom_ppe` block for both Xiaomi devices:
ports 1-4 `10g-qxgmii` with PHYs 1-4 and `pcs0_ch0..3`; port 5
`usxgmii` with AQR C45 0 and `pcs1_ch0`; port 6 `usxgmii`/`10gbase-r`
with SFP and `pcs2_ch0`; per-port NSSCC clock/reset triples. Add labels
`lan1..4`, `wan`, `sfp` and `02_network` cases for `xiaomi,be10000` and
`xiaomi,be18000` using the QWRT LAN/WAN split. Do not copy the QSDK
`phyaddr_fixup`/`uniphyaddr_fixup` SSDK hacks; use the QCA8084 package
node and PCS handles.

## Round 6: QCA8084 package and NSSCC

**Probe QWRT BE18000 firmware.** Live MDIO is at `90000` with
`phy-reset-gpio = <&tlmm 60>`, `phyaddr_fixup = <0xc90f018>`,
`uniphyaddr_fixup = <0xc90f014>`, QCA8084 PHYs 1-4 and AQR 0. The QCA8084
PHYs report `phy_id 0x004dd180` and `phy_interface sgmii` in QSDK12;
QSDK13 uses `qusgmii`. The live board has no NSSCC DT node; the SSDK
programs the MHT clock/reset.

**Probe QWRT BE10000 firmware.** `board.dts` has the same MDIO block and
PHY addresses. The BE7000 mainline draft in the same extraction has a
`qcom,qca8084-nsscc` node plus `qcom,qca8084-package` with
`qcom,phy-addr-fixup = <1 2 3 4 5 6 7>` and package mode
`QCA808X_PCS1_10G_QXGMII_PCS0_UNUNSED`. The BE10000 README says to copy
that block, with hardware verification.

**Compare with OpenWrt.** The target has the QCA8084 PHY patches
(`0301`-`0312`), the upstream `qcom,qca8084-nsscc` driver and
`CONFIG_IPQ_NSSCC_QCA8K=y` in `config-default`. It has no QCA8084 package
node and no Xiaomi DTS. The BE7000 draft is not in the target tree.

**Gap and plan.** Add the common QCA8084 package/NSSCC block from the
BE7000 draft to both devices: `clock-controller@18` with reference/
UNIPHY clocks and reset; `ethernet-phy-package@1` with package mode 0,
`qcom,phy-addr-fixup`, per-PHY clocks/resets, `pcs-phy@6`, `xpcs-phy@7`.
Use `10g-qxgmii` for ports 1-4 and verify the NSSCC address, reset GPIO60
and reference clocks. The QCA8084 PHY patches are out-of-tree; treat the
first 2.5G link as a hardware gate, not a DT-only item.

## Round 7: AQR113C, ETHPHYFW, and 10G port

**Probe QWRT BE18000 firmware.** The 10G PHY is AQR113C at C45 address 0;
`0:ETHPHYFW` is an MBN image with header 0x28 and payload 0x60002 (Xiaomi
v5.6.7 PSDAdj). The payload CRC is 0x8ac4; U-Boot loads it. Live `dp5`
uses PHY 0 and the AQR is bound to the `Aquantia AQR113C` driver.

**Probe QWRT BE10000 firmware.** The standard BE10000 uses AQR113C at
C45 0, `partition-0-ethphyfw` with `aqr-fw@0`, and a (Netgear)
`AQR-G4_v5.6.7-AQR_VER1990.cld` in the extraction. The README says the
stock NAND `0:ethphyfw` is the source; the modified BE18000 has the Xiaomi
PSDAdj image instead. Port 5 is the WAN AQR.

**Compare with OpenWrt.** `config-default` has `CONFIG_AQUANTIA_PHY=y`;
the target patch `0350` adds `nvmem-cells = <&aqr_fw>` /
`nvmem-cell-names = "firmware"`; Linux v6.18 `aquantia_firmware.c` reads
the cell, validates CRC/header, and falls back to `firmware-name`. There
is no Xiaomi/ BE10000 DTS cell.

**Gap and plan.** Add the `0:ETHPHYFW` nvmem layout per device:
BE18000 at 0x28/0x60002 (Xiaomi payload); BE10000 at 0x28/0x60002
(stock payload). Add the AQR PHY node and port 5 `usxgmii`. Do not
substitute the Netgear VER1990 cld for the live Xiaomi image; do not
package either cld as the primary firmware. Keep the driver built-in
(`CONFIG_AQUANTIA_PHY=y`) and test the 10G link and firmware version.

## Round 8: SFP+ port 6

**Probe QWRT BE18000 firmware.** The SFP+ is ESS port 6, PHY 0x1e,
`phy_i2c_address = 0x1e`, reset GPIO64, `media-type = "sfp"`;
`ethtool -m` says "Not supported"; the live MDIO device at 0x1e binds
`QCA SFP` with `phy_id 0xaaaabbbb`; there is no direct i2c4 EEPROM node.

**Probe QWRT BE10000 firmware.** The BE10000 README says SFP EEPROM is on
`i2c@78b9000` (i2c4), reset/TX-disable GPIO64, and the `sff,sfp` model
is appropriate; QWRT ships `rpcd/ucode/sfp-info.uc` and the SFP LED
GPIO62. `port_phyinfo` still lists PHY 0x1e for the QSDK switch port.

**Compare with OpenWrt.** `kmod-sfp` (`CONFIG_SFP`, `CONFIG_MDIO_I2C`,
`sfp.ko`, `mdio-i2c.ko`) is available; `ipq9570-kiwi-dvk.dts` is the
`sff,sfp` example (`i2c-bus`, `los-gpios`). The target has no Xiaomi SFP
node; `config-6.18` has no `CONFIG_SFP`.

**Gap and plan.** Treat the two SFP implementations separately:
BE10000 gets an `sff,sfp` node on `blsp1_i2c4` with GPIO64
reset/TX-disable and the i2c EEPROM; BE18000 gets the QCA SFP 0x1e path
(or `managed = "in-band-status"` if the PHY driver is not usable) and
must not claim `ethtool -m` support. Add `kmod-sfp` to both images, defer
SFP until the QCA8084/AQR wired ports work, and validate module detect,
1G/10G link, and LED GPIO62.

## Round 9: PCIe controllers, WSI, and radio IDs

**Probe QWRT BE18000 firmware.** Three active controllers:
`pci@10000000` PERST 26/x1, `pci@20000000` PERST 29/x2, `pci@18000000`
PERST 23/x2; live domains 2/3/4; QSDK13 board IDs 1/2/4 for
2.4G/5G/6G; WSI indices 2/0/1. `pci@28000000` is disabled. The live
radio map is 3x QCN9224, 2.4/5/6.

**Probe QWRT BE10000 firmware.** Same PERST 26/29/23 and lanes 1/2/2,
same QSDK domains 2/3/4, but the radio map is 3x QCN62xx: pcie1 2.4G
board_id 1, pcie2 5G board_id 4, pcie3 5G board_id 2; BDFs b01/b04/b02;
there is no 6 GHz radio. The BE10000 QWRT `wsi` node and child memory
regions are QSDK-cnss2.

**Compare with OpenWrt.** `ipq9570-sbe1v1k.dts` has the mainline PCIe
template (PERST, `pcie@0` child, `wifi@0`, WSI ring, variants). The
target `02_network` path strings assume pcie1=domain1, pcie2=domain2,
pcie3=domain3. There is no Xiaomi PCIe/WSI node; the mainline binding
does not use `qcom,board_id`/`qcom,wsi_index`.

**Gap and plan.** Add common `&pcie1/2/3` nodes with PERST 26/29/23,
lane counts, `wifi@0` children, and the sbe1v1k WSI ring; per device set
the calibration variants: BE18000 `_live_1/_live_2/_live_4` for
2.4G/5G/6G, BE10000 `_1/_4/_2` for 2.4G/5G/5G. Put
`qcom,wsi-controller` on pcie2 (5G) for both, but verify the BE10000
5G/5G WSI graph separately. Do not add `qcom,board_id`, `qcom,wsi`,
`qcom,wsi_index`, or QSDK memory-region.

## Round 10: WiFi BDFs and board-2

**Probe QWRT BE18000 firmware.** Live BDFs:
`bdwlan.b0001` 63,488 B, `b0002` 100,352 B, `b0004` 102,400 B;
regdb 25,656 B; board-2 `board-live-be18000.qcn9274` 292,256 B; variants
`Xiaomi_BE18000_live_1/2/4`; key `qmi-chip-id=0,qmi-board-id=255`.
The live QMI IDs are chip 0/board 0xff.

**Probe QWRT BE10000 firmware.** BDFs: `bdwlan.b01` 63,488 B,
`b02` 100,352 B, `b04` 100,352 B; regdb 25,656 B; generated board-2
`board-xiaomi_be10000.qcn9274` 290,196 B; variants
`Xiaomi_BE10000_1/4/2`; same QMI key. The BDF set is the standard
BE10000 2.4G/5G/5G profile.

**Compare with OpenWrt.** `ipq-wifi` has `askey_sbe1v1k`,
`8devices_kiwi`, etc., and installs `.qcn9274` to
`ath12k/QCN9274/hw2.0/board-2.bin`; there is no Xiaomi BE10000/BE18000
board package. The official `ath12k-firmware-qcn9274` board-2 is a
different 2.6 MB file and must not win.

**Gap and plan.** Create two local board-2 packages/files (or one package
with both files selected by device) and wire `qcom,calibration-variant`
per radio. Verify the built image's board-2 hash, not just the source.
Do not merge the BE10000 and BE18000 BDFs into one variant: the RF paths
and band maps differ. Keep the live BE18000 modified BDFs as the
BE18000 profile, and the standard b01/b04/b02 as the BE10000 profile.

## Round 11: WiFi firmware and calibration strategy

**Probe QWRT BE18000 firmware.** Live QCN9224 `amss.bin` 7,319,552 B,
`m3.bin` 421,888 B, fw_version 0x110d8016 (2023-10-27); QSDK13 has
7,237,632 B `amss.bin` (WBE.1.5-01577, `9224.wlanfw.eval_v2Q`) and a
421,888 B `m3.bin`; coldboot is enabled for `ap-al02-c4`; the high-band
ART is blank; the live caches are zero.

**Probe QWRT BE10000 firmware.** The standard BE10000 image is
QWRT 25.12.2 / QSDK 12.5 (kernel 5.4.213), with the 2.4G/5G/5G BDFs and
the QWRT `read_caldata_to_fs.sh`/`wifi_fw_mount` scripts. The standard
BE10000 ART caldata at 0x58800/0x8A800/0xBC800 may be valid, unlike the
modified BE18000 high-band slots; the BE10000 README still warns that
the modified unit uses coldboot and generated caches.

**Compare with OpenWrt.** `ath12k` uses `firmware-2.bin` with AMSS/M3
(and dual-MAC) IEs; the QSDK raw `amss.bin`/`m3.bin` are not a drop-in.
Mainline `qmi.c` sets a fixed CALDB paddr=0 but has a DMA CALDB allocation
path; there is no coldboot INI. The target has `ath12k-firmware-qcn9274`
but no QCN9224-specific firmware and no BE10000/BE18000 calibration policy.

**Gap and plan.** Test the official QCN9274 `firmware-2.bin` on both
hardware profiles with the matching board-2. For BE10000, try the ART
`cal-pci-*` extraction if the standard ART is valid; for BE18000, do not
extract high-band ART and implement/test coldboot. If the official
firmware does not request CALDB on the QCN9224, wrap the QSDK13 QCN9224
AMSS/M3 into a `firmware-2.bin` container as a fallback, or add the fixed
caldb region path. Keep the two calibration strategies separate.

## Round 12: ART, BDF, and caldata layout

**Probe QWRT BE18000 firmware.** The live ART is 0x140000; factory BDFs
at 0x1000 (63,488), 0x33000 (100,352), 0x65000 (100,352); high-band
caldata at 0x58800/0x8A800/0xBC800 are `0xFF` or contain the 0x65000 BDF;
the live/modified BDFs are the working profile; QSDK13 `ftm.conf` maps
1/4/2; live caches are zero.

**Probe QWRT BE10000 firmware.** The README/`board.dts` shows the
standard BE10000 ART caldata at 0x58800/0x8A800/0xBC800 with 0x2d000
(184,320 B) slices, BDFs b01/b04/b02, and the QSDK `caldata_2/3/4`
mapping. The standard BE10000 profile is the origin of the factory ART
BDFs; the modified BE18000 replaced the 6G RF path.

**Compare with OpenWrt.** `11-ath12k-caldata` already extracts exactly
0x58800/0x8A800/0xBC800 for `askey,sbe1v1k`; that makes it a candidate
for the standard BE10000, but **not** for the modified BE18000. The
target has no Xiaomi board case; no per-device caldata policy.

**Gap and plan.** Add a BE10000 `11-ath12k-caldata` case only after
validating that its ART slices are real calibration; add no BE18000
high-band extraction. For BE18000 use coldboot or the live BDFs, never
blank ART. Preserve the ART and do not write it. Record the exact
controller/BDF/caldata order for each device (BE10000 1/4/2, BE18000
1/2/4).

## Round 13: MLO, DCS, and auth behavior

**Probe QWRT BE18000 firmware.** Live QSDK12.2 MLO has 3 chips, one
local link each, `num_adj_chips: 0`; 6G is moved by AWGN DCS from PSC37
to ch129; stale-MLD peers are rejected; QSDK13 turns DCS off by default
and forwards PMF/SAE auth to hostapd with active-MLO peer deletion.

**Probe QWRT BE10000 firmware.** The BE10000 QWRT 25.12.2/QSDK12.5
`qcawifi.sh` and `QCN9224_i.ini` carry the MLO/DCS userspace controls;
the standard BE10000 has 2.4G/5G/5G radios and no 6G, so its MLO pairs
are 2.4G+5G/5G rather than 5G+6G. The BE10000 image is from a newer QSDK
12.5 than the live BE18000 QSDK12.2; do not assume identical defaults.

**Compare with OpenWrt.** Mainline ath12k has WSI/MLO support and the
target has patch 105 (device ID from WSI index); it does not implement
QSDK DCS or the QSDK stale-MLD reject path. The target has no Xiaomi
wireless userspace/board config for either device.

**Gap and plan.** Keep MLO opt-in on both devices; use the sbe1v1k WSI
ring; pin BE18000 6G to PSC ch37/6135 and do not enable QSDK DCS; for
BE10000 use the 5G/5G pair and validate its own WSI graph. Do not copy
the QSDK12.2 reject path; use mainline mac80211/ath12k link removal and
PMF/SAE handling. Test 6G link drop/reconnect on BE18000 and 5G pair
recovery on BE10000.

## Round 14: LEDs, buttons, and PWM

**Probe QWRT BE18000 firmware.** Live gpio LEDs: sys_white 40, sys_orange
41, net_white 42, net_orange 43, sfp_green 62 (netdev trigger); keys
mesh 44 (code 0x109) and reset 45 (KEY_RESTART); PWM RGB channels 3/2/1,
period 0xc738; aliases boot/failsafe = orange, running/upgrade = white.

**Probe QWRT BE10000 firmware.** `board.dts` has the same LEDs 40-43/62
and keys 44/45, PWM 3/2/1 period 0xc738. QWRT's
`qwrt-files/etc/board.d/01_leds` has explicit `xiaomi,be10000` and
`xiaomi,be18000` cases: WAN netdev on `eth4`, SFP netdev on `eth5`;
`etc/config/rgbcontrol` drives the PWM RGB.

**Compare with OpenWrt.** `ipq9570-sbe1v1k.dts` has pwm-leds and
gpio-keys; the target has no Xiaomi `01_leds` and no Xiaomi LED/button
nodes. The default `kmod-leds-gpio`/`kmod-gpio-button-hotplug` are
already in the target packages.

**Gap and plan.** Add common gpio-leds/gpio-keys/pwm-leds nodes and
aliases for both devices; add the Xiaomi `01_leds` cases from QWRT
(WAN `eth4`, SFP `eth5`, `net_white`/`sfp_green`). Add
`kmod-leds-pwm`/`kmod-input-gpio-keys` if not present. Do not add a WPS
key; preserve the live reset code. Use the live period 0xc738 and GPIO
polarities.

## Round 15: I2C, fan, NFC, and thermal

**Probe QWRT BE18000 firmware.** NFC `miwifi,nfc` at i2c1 0x54; LM63 at
i2c3 0x4c; EMC2301 at i2c3 0x2f with `pwm-fan@0`; thermal sensor at
0x4a9000. The live fan is controlled by the EMC2301 hwmon path.

**Probe QWRT BE10000 firmware.** `board.dts` has the same i2c1 NFC,
i2c3 LM63/EMC2301 and SFP i2c4; `qwrt-files/etc/config/fancontrol`
points at `1-002f/hwmon/hwmon0/pwm1`; `rgbcontrol` and `sfp-info.uc`
are QWRT userspace. The BE10000 uses i2c4 for the SFP EEPROM, unlike the
BE18000 QCA SFP PHY.

**Compare with OpenWrt.** The target has I2C/PWM/HWMON/thermal support
and the `kmod-hwmon-emc2305`/`kmod-hwmon-lm63` packages, but no Xiaomi
i2c/fan/NFC nodes and no fancontrol/rgbcontrol defaults. `miwifi,nfc`
has no mainline driver in the target.

**Gap and plan.** Add common i2c1/i2c3 nodes for NFC/LM63/EMC2301;
add the fancontrol/rgbcontrol uci-defaults or a minimal hwmon fan policy.
Keep NFC disabled until a compatible driver exists. Add the packages and
verify `i2cdetect`, `sensors`, fan RPM and EMC2301 reset isolation from
GPIO60. The BE10000 i2c4 SFP node is per-device (Round 8).

## Round 16: MAC source, interface names, and board.d

**Probe QWRT BE18000 firmware.** The live MAC base is the first ART MAC
at 0x0; LAN = WAN+1; the live WAN is `eth4`; the QWRT BE10000
`02_network` has a `xiaomi,be18000` case using `mtd_get_mac_binary 0:ART
0x0`, LAN +1, and LAN `eth0 eth1 eth2 eth3 eth5`, WAN `eth4`.

**Probe QWRT BE10000 firmware.** QWRT `02_network` has a
`xiaomi,be10000` case using `mtd_get_mac_ascii 0:APPSBLENV ethaddr`,
LAN +1, and the same LAN/WAN split. `01_leds` maps WAN to `eth4` and SFP
to `eth5`. The BE10000 and BE18000 thus have different MAC sources even
though the live values happen to match.

**Compare with OpenWrt.** The target `02_network` has no Xiaomi case and
uses `lan1..` names for the existing devices. It has no `01_leds`; the
existing `platform.sh` has no Xiaomi NAND case. The QWRT board.d files
are the exact source for the Xiaomi cases.

**Gap and plan.** Add explicit `xiaomi,be10000` and `xiaomi,be18000`
cases: BE10000 WAN from `0:APPSBLENV ethaddr`, BE18000 WAN from
`0:ART` offset 0; LAN = WAN+1; LAN `lan1..lan4`+SFP and WAN `wan` in
mainline naming, with the DTS port labels matching. Add `01_leds` WAN/
SFP netdev mappings. Keep the QWRT `eth*` names only as documentation.

## Round 17: Kernel config, modules, and packages

**Probe QWRT BE18000 firmware.** QWRT 5.4.250 / QSDK 12.2 loads
`qca_ol`, `qdf`, `umac`, `wifi_3_0`, `qca-ssdk`, `qca-nss-dp`,
`qca-nss-ppe`, `ecm`, and related QSDK modules; its kernel config has
`CONFIG_QCOM_WDT=y`, no `CONFIG_PSTORE`, and no mainline `ath12k`.
The live rootfs has the QSDK WiFi firmware/BDF set.

**Probe QWRT BE10000 firmware.** QWRT 25.12.2 / QSDK 12.5, kernel
5.4.213; `kernel_config` is 153,828 B; the rootfs ships QSDK NSS/ECM/
SSDK and `qca-wifi` 12.5, plus the BE10000 board scripts. The QSDK
modules are not loadable on Linux 6.18.

**Compare with OpenWrt.** The target is Linux 6.18 with upstream
`qcom_ppe`/PCS, QCA8084, AQR, ath12k, SFP and NVMEM. `DEFAULT_PACKAGES`
already has `kmod-qcom-ppe`, `wpad-basic-mbedtls`, `uboot-envtools`;
`config-default` has AQUANTIA/QCA808X/NSSCC. Missing image options:
`kmod-pstore`/`kmod-ramoops`, `kmod-sfp`, `kmod-leds-pwm`,
`kmod-hwmon-emc2305`, `kmod-hwmon-lm63`, `kmod-input-gpio-keys`,
`kmod-i2c-core`.

**Gap and plan.** Define a common Xiaomi package set plus per-device
firmware/board-2 packages; do not copy any QSDK `.ko`. Add the pstore/
ramoops, SFP, LED/PWM, hwmon, GPIO-key and I2C packages; keep AQR/QCA808x
built-in via config-default; use `kmod-ath12k` +
`ath12k-firmware-qcn9274`. Add ramoops reserved memory and validate
image contents (FIT, UBI, board-2 hash, firmware-2.bin).

## Round 18: Existing OpenWrt device support and merge strategy

**Probe QWRT BE18000 firmware.** There is no mainline BE18000 DTS in the
target; the live DT is QSDK vendor data. The closest target templates are
`sbe1v1k` (3 radios/WSI/ART), `rdp433` (PPE/AQR/PCS) and `kiwi` (SFP).

**Probe QWRT BE10000 firmware.** The standard BE10000 extraction includes
`be7000-mainline.dts`, a draft from OpenWrt PR #20604 with QCA8084
package/NSSCC, NAND `qcom,smem-part`, AQR NVMEM and Xiaomi board.d
ideas, but it is not in this target tree. The BE10000 board DTS is QSDK
vendor data, not mainline.

**Compare with OpenWrt.** `target/linux/qualcommbe/image/ipq95xx.mk` has
only kiwi/sbe1v1k/ln6001/rdp433; `dts/` has no Xiaomi; `02_network`,
`platform.sh`, `11-ath12k-caldata` have no Xiaomi cases; `ipq-wifi` has
no Xiaomi board. The BE7000 draft is the only nearly-mainline template
and is not merged.

**Gap and plan.** Create a common `ipq9574-xiaomi.dtsi` for the shared
AP-AL02-C4 hardware (QCA8084, AQR, SFP, PCIe/WSI, LEDs/keys, I2C/fan,
NAND/UBI) and two thin DTS files:
`ipq9574-xiaomi-be10000.dts` and `ipq9574-be18000.dts`. Add two
`Device/` entries, two board-2 packages, `02_network`/`01_leds` cases,
a Xiaomi `platform.sh` NAND case and a per-device caldata policy. Keep
the BE7000 draft as a reference, not as a merged BE10000 device.

## Round 19: OpenWrt driver and binding coverage

**Probe QWRT BE18000 firmware.** The live hardware uses QCA8084 + AQR113C
+ QCA SFP + 3x QCN9224 + NAND/UBI; the QSDK implementation is SSDK/NSS/
qca-wifi. The mainline equivalents are the target's QCA8084 PHY patches,
QCA8084 NSSCC, qcom_ppe/PCS, aquantia NVMEM, ath12k, SFP and UBI.

**Probe QWRT BE10000 firmware.** The standard BE10000 uses QCA8084 +
AQR113C + SFP EEPROM + 3x QCN62xx + NAND/UBI; same mainline driver
families, different BDF/radio/SFP profile. The BE7000 draft is evidence
that QCA8084/NAND/PPE can be expressed in mainline DT.

**Compare with OpenWrt.** Upstream/OpenWrt already covers the generic
drivers: `qcom-ppe`, `pcs-qcom-ipq9574`, QCA8084 PHY/NSSCC, AQUANTIA,
ath12k WSI/MLO, SFP, NVMEM, NAND/UBI. The missing pieces are board data,
device definitions, per-device variants, calibration policy, and
hardware validation. The mainline QCA8084 PHY support is out-of-tree;
the QCN9224 is not a separate upstream hardware entry.

**Gap and plan.** Track a driver/binding checklist per device: DTS
binding, driver built-in/package, firmware/board file, hardware test.
Do not port QSDK SSDK/NSS/qca-wifi. Prioritize the QCA8084 NSSCC/
package probe, AQR NVMEM, ath12k firmware/board-2, and the common
PCIe/WSI graph. Keep the qca8084 split-PHY/OTP and MLO opt-in conditions
explicit.

## Round 20: Final gap matrix and implementation roadmap

**Probe QWRT BE18000 firmware.** The live BE18000 is a modified BE10000:
2.4/5/6 GHz, 3x QCN9224, live BDFs `_live_1/2/4`, Xiaomi AQR firmware,
QCA SFP PHY at 0x1e, blank high-band ART, coldboot, 2 GiB, fixed MIBIB.

**Probe QWRT BE10000 firmware.** The standard BE10000 is 2.4/5/5 GHz,
3x QCN62xx, BDFs `_1/4/2`, Netgear/stock AQR image, SFP EEPROM on i2c4,
ART caldata at 0x58800/0x8A800/0xBC800, QWRT DTB 1 GiB (hardware 2 GiB),
`qcom,smem-part` NAND.

**Compare with OpenWrt.** The target has the generic driver base and
templates but no Xiaomi device. The two devices cannot share one DTS:
radio count/bands, BDF variants, SFP path, memory size, NAND partition
source, and calibration policy differ. The common hardware block is
still worth factoring into a DTSI.

**Gap and plan.**

| Priority | Gap | Plan |
|---|---|---|
| P0 | No Xiaomi device definitions/DTS | Add common DTSI + `be10000`/`be18000` DTS and two `Device/` entries |
| P0 | FIT rootfs `append-bootargs` missing | Extend `mkits`/`fit-its`, add `root=/dev/ubiblock0_1` |
| P0 | No Xiaomi board-2 | Two local `ipq-wifi` packages/files with variants |
| P1 | QCA8084 package/NSSCC not instantiated | Add package/NSSCC nodes; verify 2.5G |
| P1 | AQR NVMEM not in Xiaomi DTS | Add `0:ETHPHYFW` cell + AQR PHY/port5 |
| P1 | BE10000 ART vs BE18000 coldboot | Separate caldata policy and tests |
| P1 | BE10000 5G/5G vs BE18000 5G/6G | Per-device PCIe variants/WSI/MLO |
| P2 | SFP variants | BE10000 `sff,sfp` i2c4; BE18000 QCA SFP 0x1e |
| P2 | Board I/O/I2C/fan/NFC | Common DTSI, packages, uci-defaults |
| P2 | `02_network`/`01_leds`/`platform.sh` | Add Xiaomi cases, MAC source split |
| P2 | sysupgrade/UBI install | `Device/UbiFit`, `ubiformat`, recovery initramfs |
| P3 | MLO/DCS policy | Opt-in MLO, fixed PSC 6G, no QSDK DCS |
| P3 | Validation matrix | Wired, per-band WiFi, SFP, 24h, recovery |

Implementation order: (1) common DTSI and two DTS skeletons; (2) image
definitions, FIT append-bootargs, local board-2; (3) wired QCA8084/AQR
and `02_network`; (4) BE10000 ART/FIT/board-2 and BE18000 coldboot;
(5) SFP/board I/O; (6) MLO/6G and 24h validation. No target source file
was modified by this research; the output is this gap-round document.

## Closing audit

| Check | Result |
|---|---|
| Numbered rounds (`## Round 1` ... `## Round 20`) | **20** |
| BE18000 probe sections | **20** |
| BE10000 probe sections | **20** |
| OpenWrt comparison sections | **20** |
| Gap/plan sections | **20** |
| Markdown fences | **0** |
| Document size | **33,107 bytes** |
| Target source modifications | **none** (`git status --short -- target/linux/qualcommbe package/firmware package/kernel/mac80211` empty) |
| Hardware validation | not performed; no live router/serial session |

The audit is structural: every round contains a BE18000 firmware probe, a
BE10000 firmware probe, an OpenWrt comparison, and a gap/plan. The
evidence is the saved QWRT files and target paths cited in each round; no
claim above should be read as a hardware test.

Remaining hardware-only gates:

- QCA8084 NSSCC/package probe and 2.5G link on both boards.
- BE18000 5G/6G coldboot calibration and QCN9224 firmware/board-2.
- BE10000 ART calibration validity and 5G/5G radio/WSI mapping.
- SFP EEPROM (BE10000) vs QCA SFP PHY (BE18000).
- BE10000 2 GiB memory fixup and NAND `qcom,smem-part` behavior.
- Mainline MLO/6G recovery and sustained 24h validation.
