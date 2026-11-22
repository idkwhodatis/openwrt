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
  `Xiaomi_BE10000_1/4/2`, candidate ART slots at 0x58800/0x8A800/0xBC800,
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
`VID_HDR_OFFSET=2048`, and board-specific `/chosen/bootargs-append` after verifying the generated rootfs volume ID. Then add two device wrappers:
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
this fork's generic 6.18 patch 920 appends the chosen property to the
kernel command line. QSDK U-Boot separately reads FIT-root
`append-bootargs` in `cmd_bootqca.c`.

**Gap and plan.** Use the board DTS for the root argument. Preserve the
leading space and check the generated UBI volume ID before selecting
`root=/dev/ubiblock0_1`. Add a Xiaomi `fw_env.config`/`30_uboot-envtools`
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
stock NAND `0:ethphyfw` is the source. The stock partition header, payload and running version remain unverified. Port 5 is the WAN AQR.

**Compare with OpenWrt.** `config-default` has `CONFIG_AQUANTIA_PHY=y`;
the target patch `0350` adds `nvmem-cells = <&aqr_fw>` /
`nvmem-cell-names = "firmware"`; Linux v6.18 `aquantia_firmware.c` reads
the cell, validates CRC/header, and falls back to `firmware-name`. There
is no Xiaomi/ BE10000 DTS cell.

**Gap and plan.** Add the `0:ETHPHYFW` nvmem layout per device:
BE18000 at 0x28/0x60002 (Xiaomi payload); BE10000 bounds pending a stock partition header. Add the AQR PHY node and port 5 `usxgmii`. Do not
substitute the Netgear VER1990 cld for the live Xiaomi image; do not
package either cld as the primary firmware. Keep the driver built-in
(`CONFIG_AQUANTIA_PHY=y`) and test the 10G link and firmware version.

## Round 8: SFP+ port 6

**Probe QWRT BE18000 firmware.** The SFP+ is ESS port 6, PHY 0x1e,
`phy_i2c_address = 0x1e`, reset GPIO64, `media-type = "sfp"`;
`ethtool -m` says "Not supported"; the live MDIO device at 0x1e binds
`QCA SFP` with `phy_id 0xaaaabbbb`; there is no direct i2c4 EEPROM node.

**Probe QWRT BE10000 firmware.** The BE10000 README says SFP EEPROM is on
`i2c@78b9000` (i2c4), and proposes an `sff,sfp` model. The vendor port node names GPIO64 as PHY reset; QWRT ships `rpcd/ucode/sfp-info.uc` and the SFP LED
GPIO62. `port_phyinfo` still lists PHY 0x1e for the QSDK switch port.

**Compare with OpenWrt.** `kmod-sfp` (`CONFIG_SFP`, `CONFIG_MDIO_I2C`,
`sfp.ko`, `mdio-i2c.ko`) is available; `ipq9570-kiwi-dvk.dts` is the
`sff,sfp` example (`i2c-bus`, `los-gpios`). The target has no Xiaomi SFP
node; `config-6.18` has no `CONFIG_SFP`.

**Gap and plan.** Treat the two SFP implementations separately:
BE10000 gets an `sff,sfp` node on `blsp1_i2c4` as a candidate for module access. Leave TX-disable and polarity unresolved; BE18000 gets the QCA SFP 0x1e path
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
BE10000 candidate ART slots at 0x58800/0x8A800/0xBC800 may be valid, unlike the
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
candidate standard BE10000 ART offsets at 0x58800/0x8A800/0xBC800 with 0x2d000
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
3x QCN62xx, BDFs `_1/4/2`, Netgear AQR file (stock resident image unknown), SFP EEPROM on i2c4,
candidate ART slots at 0x58800/0x8A800/0xBC800, QWRT DTB 1 GiB (hardware 2 GiB),
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
| P0 | Root volume selection | Verify the generated volume ID and set the board DT chosen argument |
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
definitions, board DT root argument, local board-2; (3) wired QCA8084/AQR
and `02_network`; (4) BE10000 ART/FIT/board-2 and BE18000 coldboot;
(5) SFP/board I/O; (6) MLO/6G and 24h validation. No target source file
was modified by this research; the output is this gap-round document.

## BE10000 wired bring-up trace (offline, 2026-11-21)

The extracted [BE10000 DT](../extracted/qwrt-25.12.2-be10000/board.dts)
gives the Xiaomi port numbers and wrapper settings. The local
[SSDK enum](../../qsdk/qca/src/qca-ssdk/include/init/ssdk_init.h)
decodes `switch_mac_mode{,1,2}` as follows. The PCS handles come from
[OpenWrt RDP433 patch 0349](../../target/linux/qualcommbe/patches-6.18/0349-arm64-dts-qcom-Add-IPQ9574-RDP433-port-node.patch)
and describe a candidate SoC-side route for Xiaomi.

| Xiaomi PPE port | Vendor wrapper | Xiaomi endpoint | OpenWrt reference route |
|---|---|---|---|
| 1–4 | 0x15 UQXGMII | QCA8084 PHYs 1–4 | pcs0_ch0 through pcs0_ch3. RDP433 uses qsgmii and PHYs 0x10–0x13. Xiaomi's four-channel wrapper supports investigating 10g-qxgmii. |
| 5 | 0x0d USXGMII | Clause 45 PHY 0, vendor WAN | pcs1_ch0. RDP433 uses PHY 8 here. Patch 0350 attaches a firmware NVMEM cell to its AQR PHYs. |
| 6 | 0x0e 10GBASE-R | SFP, vendor PHY I²C address 0x1e | pcs2_ch0. RDP433 uses USXGMII with a second copper PHY here. |

**Four copper LAN ports.** The Xiaomi MDIO node marks four children for
address fixup. QSDK's [mdio-qca.c](../../qsdk/qca/src/linux-5.4/drivers/net/phy/mdio-qca.c)
packs their reg values into the EPHY register and selects available
addresses for the UNIPHY block. OpenWrt [patch 0306](../../target/linux/qualcommbe/patches-6.18/0306-net-phy-qca808x-Add-QCA8084-probe-function.patch)
instead joins a PHY package, programs the four PHY and three PCS addresses
once from its seven-entry property, then enables each PHY clock and
deasserts reset. Check package discovery on a cold start, NSSCC clocks
and resets, and PCS channel order before diagnosing LAN configuration.

**Copper WAN.** QSDK's [Aquantia loader](../../qsdk/qca/src/u-boot-2016/drivers/net/ipq_common/ipq_aquantia_phy.c)
looks up 0:ETHPHYFW. The Netgear file in the extraction establishes file
availability only. On stock hardware, identify the partition payload
before specifying the Linux firmware cell and record the running PHY
version separately.

**SFP.** When built with IN_PHY_I2C_MODE, the [SSDK parser](../../qsdk/qca/src/qca-ssdk/src/init/ssdk_dts.c)
uses phy_i2c_address for I²C transactions and registers phy_address as a
synthetic MDIO address. Both fields happen to be 0x1e here. A Linux MDIO
PHY node at that address would need independent evidence. Verify module
I²C access, control signals and link independently.

**Network defaults.** The [ipq95xx board script](../../target/linux/qualcommbe/ipq95xx/base-files/etc/board.d/02_network)
falls through to unsupported hardware for Xiaomi. Once the netdevices
exist, map the four copper LAN ports and SFP to LAN and port 5 to WAN
using verified Linux labels. Vendor eth4 identifies the intended WAN
role only. Verify physical jack order and negotiated speeds individually.

**Calibration cross-check.** The Askey hotplug case reads three MMC slices
of 0x2d000 bytes and assigns them by PCI domain. A stock BE10000 case
needs NAND/MTD extraction, validated slot contents and a verified
domain-to-radio mapping.

### Owner's modified BE10000 (BE18000 firmware profile)

The port target is the owner's hardware-modified BE10000. The installer
reported RF path and FEM/filter changes using SKY85798. The exact suffix
and component population remain unknown. The saved custom QWRT runtime
is the working 6 GHz baseline. Its capture shows a client link on PCI3's
6 GHz radio at channel 37 and 320 MHz. The installer-supplied BE18000
QSDK13 image is a separate offline reference. Its SHA-256 was rechecked
as `88c851b6f8a9103cad3b2540adc9e666f97f5fd6baee61a0c93798e1441a7f24`.
[Installer account](be18000-sky85798-qsdk13.md) ·
[Saved link capture](../extracted/live-be18000/probes/round22-mlo-runtime.txt)

**Ethernet cold boot on this unit.** The saved live DT and BE18000 QSDK13
DT both specify GPIO60, EPHY/UNIPHY registers 0x0c90f018/0x0c90f014,
`mdio_clk_fixup`, and wrapper modes 0x15/0x0d/0x0e. This supports using
the QCA8084 trace below for this unit. One difference matters when
translating reset sequencing: the GPIO flags cell is 0 in the live DT
and 1 in QSDK13. The local QSDK 5.4 helper gets a numeric GPIO and
drives low then high explicitly. The flags difference alone cannot
establish a wiring change or the sequence executed by the 6.6 image.
[Live DT](../extracted/live-be18000/dt/live-board.dts) ·
[QSDK13 DT](../extracted/qsdk13-r26.09.05-be18000/be18000-board.dts) ·
[QSDK 5.4 reset helper](../../qsdk/qca/src/linux-5.4/drivers/net/phy/mdio-qca.c)

**Radio selection and calibration.** The modified mapping is PCI1/1
(2.4 GHz), PCI2/2 (5 GHz), PCI3/4 (6 GHz). The number after the slash
is the vendor board-profile selector. All three live board-2 entries
use QMI chip ID 0 and board ID 255, so the per-radio variant distinguishes
them. The QSDK13 DT agrees on 1/2/4, but its AL02-C4 FTM rows list
1/4/2. Using those rows by controller would exchange the two high-band
profiles. That is an offline mapping conflict; the image's runtime
selection remains unobserved. A fresh count of the saved modified ART
found all 184,320 bytes erased in **each** slot at 0x8a800 and 0xbc800.
Neither slot supplies usable per-unit high-band calibration.
[Live variants](../extracted/live-be18000/wifi/board-2-live.json) ·
[QSDK13 FTM rows](../extracted/qsdk13-r26.09.05-be18000/wifi/ftm.conf) ·
[Controller download trace and ART analysis](be18000-live-probe-4.md)

**Firmware provenance.** Rehashed the extracted live and QSDK13 files.
All three BDFs and the regulatory database differ. On PCI3 the two
b0004 files are both 102,400 bytes, with SHA-256 prefixes
`bd911abb719fbcae` (live) and `eb488f7753d61ba4` (QSDK13).
The 6,244-byte Skyworks-named gain table is byte-identical. The saved
live host download trace shows no matching LUT request. For an OpenWrt
probe, record the selected PCI3 variant and BDF before interpreting
6 GHz association, bandwidth or MLO results. A successful board-file
lookup alone leaves per-unit calibration unresolved.
[QSDK13 variants](../extracted/qsdk13-r26.09.05-be18000/wifi/board-2.json) ·
[Gain-table and BDF comparison](be18000-sky85798-qsdk13.md)

### PCI3 6 GHz board selection and cold-boot calibration

**Working QWRT.** The saved module parameters include `bdf_pci3=0`.
In the local CNSS source the QCN9224 case first checks the per-slot module
parameter, then reads the CNSS node's unprefixed `board_id` when that
parameter is zero. PCI3 has selector 4. The filename formatter uses two
bytes (four hex digits), so the effective override explains the observed
`qcn9224/bdwlan.b0004` even though firmware reports QMI board ID 255.
The recorded download order is `regdb.bin`, then `bdwlan.b0004`, then
`caldata_4.bin`. The final 4 has a different origin: PCI calibration
filenames use the slot index plus one. Equal suffixes on PCI3 are
coincidental. The local CNSS source explains the capture but is a
different release from the running module.
[Live parameters](be10000-porting-probe-3.md) ·
[Live download sequence](be18000-live-probe-4.md) ·
[Override selection](../../qsdk/qca/src/qca-cnss/main.c) ·
[Filename construction](../../qsdk/qca/src/qca-cnss/qmi/qmi.c)

**What supplied calibration on that boot?** A byte comparison confirms
that live caldata_4.bin equals ART at 0xbc800 for all 184,320 bytes:
every byte is 0xff. The Wi-Fi startup script passes the board-specific
cold-boot feature to CNSS. The saved probe reports firmware calibration
on all three radios. Its timestamped excerpt shows mode 7, completion
and report handling for the earlier radios; it does not give a PCI3
duration. The PCI3 DT assigns an 8 MiB CALDB at 0x59100000, and the
saved PCI3 cache was 5,153,776 zero bytes. The CNSS completion handler
requests a report upload and marks calibration done. A successful status
establishes firmware completion; neither the erased input nor the zero
cache yields reusable coefficients. The saved material does not reveal
the coefficients retained internally by firmware.
[Boot capture and memory layout](../extracted/live-be18000/probes/round24-coldboot.txt) ·
[CNSS completion handler](../../qsdk/qca/src/qca-cnss/main.c)

**Installer QSDK13.** Its PCI3 DT retains board_id 4 and the same CALDB
range. Its QCN9224 feature INI enables PCI3 cold boot for ap-al02-c4.
Direct comparison of the extracted files gives the following result:

| File | Saved live QWRT | Installer QSDK13 |
|---|---|---|
| bdwlan.b0004 | Modified-unit 6 GHz board data, SHA-256 prefix bd911abb719fbcae | Different board data, prefix eb488f7753d61ba4 |
| caldata_4.bin | 184,320 erased bytes | 100,352 bytes identical to QSDK13 bdwlan.b0002 |
| caldata_3.bin in QSDK13 | — | 102,400 bytes identical to QSDK13 bdwlan.b0004 |

The QSDK13 mount script creates the QCN9224 ath12k calibration links
only inside its board-2.bin branch. On ap-al02-c4 it uses the FTM rows
for controllers 1–3. Thus the package contains a consistent explanation
for a *potential* 5/6 GHz caldata swap, alongside a correct PCI3 DT
board selector. No installer-image boot log here establishes which
calibration bytes its firmware actually consumed.
[Installer DT](../extracted/qsdk13-r26.09.05-be18000/be18000-board.dts) ·
[Feature INI](../extracted/qsdk13-r26.09.05-be18000/rootfs/lib/firmware/qcn9224/firmware_rdp_feature.ini) ·
[Mount script](../extracted/qsdk13-r26.09.05-be18000/rootfs/etc/init.d/wifi_fw_mount)

**OpenWrt ath12k.** During target-capability handling, patch 700 reads
`qcom,calibration-variant` from the radio's device node into
`bdf_ext`. The saved board-2 container has the PCI3 key
`bus=pci,qmi-chip-id=0,qmi-board-id=255,variant=Xiaomi_BE18000_live_4`
with a 102,400-byte payload. This supplies an exact board lookup target.
It does not select the separate calibration file: the backports 7.2
trace shows an EEPROM capability branch and a file path that tries
`cal-<bus>-<id>.bin` followed by `caldata.bin`. The same source shows
two CALDB paths: one allocates a chunk, while the target-memory
assignment path records address zero. Neither excerpt demonstrates a
mode-7 request, a PCI3 completion indication or a return to normal
operation on this hardware. Assigning a reserved address alone is
therefore an untested proposal. For a future boot trace, record the
actual PCI endpoint, selected variant/payload, calibration file request,
CALDB response address and size, firmware mode transition and completion
before interpreting a 6 GHz link as evidence of cold calibration.
[Variant patch](../../package/kernel/mac80211/patches/ath12k/700-ath12k-read-calibration-variant-from-dt.patch) ·
[Decoded board container](../extracted/live-be18000/probes/round19-board2.txt) ·
[Backports 7.2 source excerpts](../extracted/live-be18000/probes/round20-calibration-source.txt)

#### PCI3 mode 7, CALDB handoff and return to service

**QSDK startup.** In the local CNSS implementation the host makes the mode
decision. In probe order, an enumerated PCI target with cold_boot_support
set and cal_done clear gets cal_in_progress set. CNSS registers its
subsystem and waits for firmware readiness. With the observed driver_mode
of 0, the calibration pass calls __cnss_wlan_enable with CNSS_CALIBRATION
(7). FTM takes a different branch (10). Calibration skips ordinary WLAN
configuration, sets CNSS_COLD_BOOT_CAL, sends the WLAN mode request and
schedules per-device calibration work. The supplied QSDK13 feature INI
enables the PCI3 support flag. Its presence establishes configuration,
while the call sequence here is from the local comparison source.
[Probe and mode sender](../../qsdk/qca/src/qca-cnss/main.c) ·
[Mode enum](../../qsdk/qca/src/qca-cnss/include/cnss2.h) ·
[Installer feature flags](../extracted/qsdk13-r26.09.05-be18000/rootfs/lib/firmware/qcn9224/firmware_rdp_feature.ini)

**CALDB is negotiated during firmware memory setup.** Firmware requests a
typed segment and length. On the IPQ reserved-memory path, CNSS PCI handles
QMI_WLFW_MEM_CAL_V01 when cold boot is enabled, checks the requested length
against caldb-size, assigns caldb-addr as the physical address and maps
the requested extent for the host. PCI3's DT supplies 0x59100000 and an
8 MiB ceiling. The request-memory event calls the bus allocator then
cnss_wlfw_respond_mem_send_sync. The response to firmware carries the
address, **requested length** and type for each segment (QMI message
0x0036). This is separate from the later mode-7 command and from the
optional calibration-report upload size. The 5,153,776-byte cache cannot
establish the length that PCI3 requested on the wire.
[PCI memory assignment](../../qsdk/qca/src/qca-cnss/pci/pci.c) ·
[Event dispatch](../../qsdk/qca/src/qca-cnss/main.c) ·
[QMI memory response](../../qsdk/qca/src/qca-cnss/qmi/qmi.c)

**Completion and return.** The CAL_DONE indication can carry an upload
size. The callback posts a completion event. On success the handler
requests report upload, sets cal_done, signals completion and clears the
cold-calibration bit. The per-device worker waits for that bit to clear,
then sends OFF (4). With soft_switch enabled it clears cal_in_progress
and directly calls the WLAN driver's probe. The default-zero branch puts
the subsystem, clears cal_in_progress, waits for the preceding target
where applicable, and gets the subsystem again. The worker marks the
device initialized and decrements the outstanding count. The completion
callback itself does not issue a mission-mode command. The saved round
24 transcript prints mode 7 and OFF for PCI1 and calibration completion
for PCI2. It summarizes the PCI3 calibration; the later client capture
establishes PCI3 service. Neither capture identifies the worker branch,
the PCI3 OFF transaction, or a timestamped PCI3 mission-mode request.
[Completion callback](../../qsdk/qca/src/qca-cnss/qmi/qmi.c) ·
[cnss_driver_cal_work](../../qsdk/qca/src/qca-cnss/main.c) ·
[Saved boot excerpt](../extracted/live-be18000/probes/round24-coldboot.txt) ·
[Subsequent client link](../extracted/live-be18000/probes/round22-mlo-runtime.txt)

**OpenWrt PCI path.** Checked the backports-7.2 release archive against
the fork's package SHA-256 (6ec76a4c…3badb9454). In qmi.c the request
callback selects assign_target_mem_chunk only with
ATH12K_FLAG_FIXED_MEM_REGION. The base source sets this flag in ahb.c;
pci.c initializes fw_mode to NORMAL. The ordinary PCI allocation branch
can allocate coherent DMA memory for CALDB type 4, or reuse a chunk with
matching size and type. Its populated memory response carries the DMA
address, length and type. The fixed branch's zero CALDB address is a
different path. Whether the candidate PCI firmware requests type 4 and
accepts that response on this unit remains unobserved.

In core.c, firmware startup passes ab->fw_mode to the QMI start routine,
which sends INI, WLAN configuration, then that mode. qmi.c advertises a
cal_done indication interest and reports a cal_done capability field.
Those fields alone do not drive a calibration session. No corresponding
PCI startup sequence selecting 7, handling completion and re-entering
ordinary service was found in this release and the fork's ath12k patches.
For a future capture, correlate the per-PCI3 memory request/response,
FW_READY, WLAN mode, CAL_DONE, OFF and subsequent probe/service. A missing
CALDB request cannot be corrected by changing a response address alone.
[OpenWrt package pin](../../package/kernel/mac80211/Makefile) ·
[Backports 7.2 source archive](https://github.com/openwrt/backports/releases/download/backports-v7.2/backports-7.2.tar.zst) ·
[Fork patches](../../package/kernel/mac80211/patches/ath12k/)

#### Installer module evidence for soft_switch and mission mode

The following offsets are relative to the ELF sections in the installer
image's 6.6.47 AArch64 modules. Calls were resolved using ELF relocations.
Module SHA-256 prefixes are 68efb39f1644665b (ipq_cnss2.ko) and 6daf5fe1b1fde751
(qca_ol.ko).

**Which setting ships?** ipq_cnss2.ko declares soft_switch as an unsigned
module parameter. Its __param entry at 0x28 references param_ops_uint and
points to .bss+0x94, giving it an initial value of zero. The loader
collects cnss2-prefixed arguments from /proc/cmdline. The packaged DT
appends cnss2.enable_mlo_support=1 and supplies no soft_switch value.
No explicit override surfaced in the readable etc, lib/wifi or ini
configuration examined. Zero is consequently the image-backed expectation.
Bootloader arguments or runtime configuration can still change it.
[Installer loader](../extracted/qsdk13-r26.09.05-be18000/rootfs/etc/init.d/load_cnss2) ·
[Installer DT](../extracted/qsdk13-r26.09.05-be18000/be18000-board.dts)

**What follows calibration in the shipped binary?** In ipq_cnss2.ko
the worker calls cnss_wait_for_cold_boot_cal_done at .text+0x6364 and
passes 4 to cnss_wlfw_wlan_mode_send_sync at 0x6370. Only the successful
OFF path reads .bss+0x94 at 0x63a0. A nonzero value clears the in-progress
byte and calls the driver callback indirectly at 0x63bc. Zero branches
to 0x63e4: depending on another per-device field, the code calls either
__cnss_hif_put/get or __cnss_subsystem_put/get. Between put and get it
clears the in-progress byte and, when applicable, waits for the previous
target's initialized status. Both successful paths converge on setting
initialized and decrementing the outstanding counter. The binary therefore
narrows the earlier description: soft_switch=0 selects a release/reacquire
path, but by itself does not identify the reset mechanism used by PCI3.
[CNSS module](../extracted/qsdk13-r26.09.05-be18000/rootfs/lib/modules/6.6.47/ipq_cnss2.ko)

**Where mission mode can be sent.** qca_ol.ko has a normal driver-enable
path from hif_wlan_enable (call at 0xd8dec) through pld_wlan_enable
(PCI dispatch at 0x7ad34) and pld_pcie_wlan_enable to cnss_wlan_enable
(0x7c06c). The PCI wrapper maps input mode zero to CNSS mode zero
at 0x7c040–0x7c060. In ipq_cnss2.ko the internal enable routine calls
the QMI WLAN mode sender at 0x2f34. This gives a concrete mission-mode
path on driver bring-up, separate from the worker's OFF call. A static
call path does not identify a particular execution. The saved record
does not show this installer image sending mode zero on PCI3.
[WLAN module](../extracted/qsdk13-r26.09.05-be18000/rootfs/lib/modules/6.6.47/qca_ol.ko) ·
[CNSS mode enum in comparison source](../../qsdk/qca/src/qca-cnss/include/cnss2.h)

**Mapping to OpenWrt backports 7.2.** These are implementation requirements
inferred from the vendor sequence. Firmware support on the modified radio
still requires a cold-power-on trace.

| Phase | Existing ath12k entry point | What the PCI3 port would need |
|---|---|---|
| First firmware boot | qmi.c handles REQUEST_MEM, FW_MEM_READY and FW_READY separately. PCI can return a DMA segment for CALDB type 4. | Track a per-radio calibration phase. Verify the PCI3 BDF and the accepted CALDB address and length before selecting mode 7. |
| Calibration start | FW_READY normally calls ath12k_core_qmi_firmware_ready, which starts firmware using ab->fw_mode. | At first readiness, issue the firmware-supported calibration request and defer ordinary datapath and MAC registration. Keep ordinary and factory-test boots distinct. |
| Completion and OFF | The QMI layer advertises calibration-done interest. ath12k_qmi_firmware_stop issues OFF and returns void. | Handle the completion indication on the correct radio, bound the wait, and observe OFF success before advancing. On timeout or transport loss, clear pending work without declaring the radio ready. |
| Second bring-up | The normal firmware-ready path already starts the radio. MAC registration is coordinated for the hardware group. | Use a firmware-supported restart or in-place transition, retain the required CALDB state, and track completion across the second readiness event. Enter NORMAL once and join group bring-up after successful mission startup. Which transition preserves this firmware's calibration is still open. |

The decision point for a hardware capture is immediately after PCI3's
CAL_DONE: capture OFF acknowledgement, HIF/subsystem teardown or direct
probe, any second memory/ready handshake, and the mode-zero request and
response on that same service instance.
[Package pin](../../package/kernel/mac80211/Makefile) ·
[Verified release source](https://github.com/openwrt/backports/releases/download/backports-v7.2/backports-7.2.tar.zst)

#### PCI3 bus selector and CALDB lifetime across OFF

**The selector is the CNSS bus type.** In the installer ipq_cnss2.ko
platform initialization compares the device ID with 0x1109 (QCN9224)
at .text+0x80d8 and takes the branch at 0x80e0. That path stores zero at
platform-context offset 0x70 (0x8200). The subsequent dispatch selects
cnss_pci_get_ops at 0x82e0 for zero. Independently, cnss_get_bus_type
at 0x16d64 returns zero for 0x1109. The comparison source names this
field bus_type and assigns CNSS_BUS_PCI in the QCN9224 case. The installer
DT identifies PCI3 as qcom,cnss-qcn9224. Thus the default-zero soft_switch
path for this radio selects **HIF put/get**. This is a device-specific
prediction from the shipped code; the installer image has no saved PCI3
execution trace here.
[Installer module](../extracted/qsdk13-r26.09.05-be18000/rootfs/lib/modules/6.6.47/ipq_cnss2.ko) ·
[Installer PCI3 DT](../extracted/qsdk13-r26.09.05-be18000/be18000-board.dts) ·
[Comparison source](../../qsdk/qca/src/qca-cnss/main.c)

| Return path after successful OFF | What the shipped code establishes | CALDB consequence |
|---|---|---|
| soft_switch=0, PCI3 | Worker reads +0x70 at 0x63e4 and 0x6460, calls __cnss_hif_put at 0x63f0 and __cnss_hif_get at 0x646c. For device 0x1109, shutdown dispatches through 0x12d1c to the helper at 0x12944. On ordinary shutdown that helper calls cnss_power_off_device at 0x12afc and cnss_pci_remove at 0x12b6c. | Device power and host reserved DDR have separate lifetimes. On a subsequent reserved CALDB request the same DT base is available. No pre/post bytes or mission-pass read were captured. |
| soft_switch nonzero | The direct callback at 0x63bc bypasses the worker's put/get pair. Firmware has already acknowledged OFF. | The worker itself issues no unmap or erase on this branch. The effect of OFF, firmware and the next probe on the contents remains unknown. |
| soft_switch=0, non-PCI subsystem branch | The worker's alternate callees reach rproc_shutdown at 0x62a4 and rproc_boot at 0x61a0. The QCN9224 initialization above excludes this branch for PCI3. | This branch supplies no evidence about retention in PCI3's window. Retention for an AHB target would require that target's memory layout and loader behavior. |

**Physical reservation, host mapping and usable calibration are three
different observations.** In the shipped allocator the caldb-size and
caldb-addr property references lead to the physical-address store at
0xd1e0, ioremap_prot at 0xd1fc and the virtual-address store at 0xd200.
For this radio the base is 0x59100000 and the maximum length is 8 MiB.
The reserved-memory cleanup code has an iounmap at 0xe50c followed by
clearing descriptor fields. In the comparison PCI source, reserved CAL
takes the ordinary unmap branch; explicit memory clearing belongs to
AFC. Unmapping releases CPU access to the range. It does not zero the
backing DDR. The installer call chain below establishes when normal HIF shutdown reaches
this cleanup; the saved captures do not show a live unmap.
[PCI allocator and cleanup](../../qsdk/qca/src/qca-cnss/pci/pci.c)

**File restoration is unverified for the installer.** The comparison
source compiles the CALDB report upload helper and firmware-memory-ready
download helper as empty functions on kernel 6.1 and later. The
zero-filled cache captured from the working 5.4 image cannot demonstrate
that the installer 6.6 module restores coefficients from disk. The
offline evidence establishes a reusable physical address, not byte or
firmware-state continuity across either applicable PCI3 return path.
[Version-dependent upload](../../qsdk/qca/src/qca-cnss/main.c) ·
[Version-dependent download](../../qsdk/qca/src/qca-cnss/qmi/qmi.c)

For ath12k, retain the per-radio CALDB allocation through the intended
transition and observe the address and requested length on both boots
if firmware renegotiates memory. To distinguish retention from firmware
reinitialization, compare a digest over the same requested extent after
CAL_DONE and before mission firmware can write it, with CPU/device
access synchronized. Record firmware's subsequent use or reported
calibration status separately. Equal addresses alone cannot answer
either question.

#### PCI3 HIF shutdown, CALDB unmap and the next memory request

**Shutdown reaches PCI removal.** In the installer ipq_cnss2.ko,
cnss_pci_dev_shutdown subtracts 0x1101 from the device ID and tests
mask 0x10d. QCN9224 (0x1109) selects bit 8 and calls the helper at
.text+0x12944 via 0x12d1c. The earlier power-off site at 0x12cd4
belongs to the 0x3e device branch. On the ordinary 0x1109 route, the
helper calls cnss_power_off_device at 0x12afc and cnss_pci_remove at
0x12b6c. Pending dump collection can exit this helper early. This
distinction matters: the WLAN driver's remove callback alone would
not establish that CNSS releases its firmware memory.
[Installer module](../extracted/qsdk13-r26.09.05-be18000/rootfs/lib/modules/6.6.47/ipq_cnss2.ko) ·
[Comparison PCI shutdown and remove](../../qsdk/qca/src/qca-cnss/pci/pci.c)

**What gets unmapped.** cnss_pci_remove tests bit 0 at platform offset
0xf8c (0x12840–0x12848). The comparison source calls this
dma_alloc_supported. When clear, it calls cnss_bus_free_fw_mem at
0x1284c. In reserved-memory cleanup, a descriptor with no VA is skipped
at 0xe484. For a mapped CALDB segment (type 4), the type checks at
0xe4a8 and 0xe500 route it to iounmap at 0xe50c, then clear the VA
and size. Type 10 takes the explicit AFC clear and type 8 skips the
unmap. Thus **ordinary HIF put releases the active CPU mapping when
PCI3 is using the reserved CALDB path**. A DMA-backed target skips that
cleanup at removal. The installer DT provides the reserved window and
the compiled allocator can use it; the capture does not expose the
runtime flag or a type-4 mapping for this installer boot. Clearing
descriptor fields does not establish erasure of the physical bytes.
[PCI allocator and cleanup](../../qsdk/qca/src/qca-cnss/pci/pci.c) ·
[Installer DT](../extracted/qsdk13-r26.09.05-be18000/be18000-board.dts)

**HIF get and mission memory setup.** After OFF and put, the calibration
worker clears cal_in_progress before HIF get. The HIF power-up path
calls cnss_pci_probe and cnss_bus_dev_powerup (0xde4 and 0xe24).
A fresh CALDB assignment depends on what that firmware boot requests.
WLFW REQUEST_MEM (0x35) supplies segment types and lengths. The host
request event calls cnss_bus_alloc_fw_mem at 0x5738 and, on success,
cnss_wlfw_respond_mem_send_sync at 0x5748. On the reserved CAL branch
the allocator reads caldb-size and caldb-addr, maps the requested extent
at 0xd1fc and stores the new VA at 0xd200. With cold_boot_support still
enabled, a second type-4 request fitting PCI3's 8 MiB window would
therefore receive **the same physical base, 0x59100000**. The requested
length could differ. Firmware asks for a type and size; the host chooses
the physical address. HIF get alone does not trigger a CALDB request.
[CNSS memory indication](../../qsdk/qca/src/qca-cnss/qmi/qmi.c) ·
[Memory event dispatch](../../qsdk/qca/src/qca-cnss/main.c)

**Offline limit.** The saved working-QWRT excerpt supplies the PCI3 DT
address, but contains no pair of decoded PCI3 type-4 requests and
responses spanning calibration and mission startup. The separate
installer image supplies executable paths only. To resolve reuse, match
PCI3's service instance across OFF, HIF put/get and the next FW_READY;
inspect the second 0x35 segment list and its 0x36 response. A type-4
entry with base 0x59100000 establishes address reuse. Content retention
and firmware consumption require independent evidence.
[Saved cold-boot excerpt](../extracted/live-be18000/probes/round24-coldboot.txt)

#### Live PCI3 QMI history after SSH access returned

The running router reports xiaomi,be18000, kernel 5.4.250 and
/sys/module/ipq_cnss2/parameters/soft_switch = 0. Reading the CNSS
debugfs qmi_record entry printed its retained history to dmesg. The
following entries are for service 0x3a (QCN9224_3), ordered by embedded
tstamp because the ring wrapped. These are readings from the working
QWRT system. The installer 6.6.47 image remains a separate baseline.

| Embedded tstamp | Recorded PCI3 events |
|---|---|
| 49681–49827 | FW_MEM_REQ_IND (0x35), MEM_INFO request/response (0x36), FW_MEM_RDY_IND (0x37) |
| 49994–51325 | WLAN mode request/response, then CAL_DONE_IND (0x3e) at 51325 |
| 51569–51570 | Another WLAN mode request/response immediately following calibration completion |
| 56511–56555 | Fresh indication registration, host capability exchange, FW_MEM_REQ_IND at 56551, successful MEM_INFO exchange and FW_MEM_RDY_IND at 56555 |
| 56751–58055 | WLAN configuration request/response followed by WLAN mode request/response |

**Confirmed live:** PCI3 negotiated firmware memory again after completing
calibration. Its current CNSS state is 0x20107 (QMI connected, firmware
memory ready, firmware ready, driver probed, QDSS started). The live PCI3
DT contains 0x59100000 and 0x00800000 for CALDB base and maximum length.
At inspection ath2 was operating as a 6 GHz AP on channel 93 at 320 MHz.

**Still unresolved:** this history records message IDs and result codes,
without the segment list or mode argument. The sequence is consistent
with calibration, OFF and normal startup. It cannot identify a type-4
segment in the second request, its returned address, or the contents of
the CALDB. No reboot, radio restart or configuration change was used.

#### Live verification of the PCI3 return path and CALDB mapping

**The two kernel builds take different return paths.** Read the running
router's /lib/modules/5.4.250/ipq_cnss2.ko over SSH and matched its GNU
build-ID note byte-for-byte to /sys/module/ipq_cnss2/notes/.note.gnu.build-id.
Module SHA-256: f01268d60a0705a95e955518385c086dd3b739dee69845bcd80c266d6c8a4920.
In this build the calibration worker waits at .text+0x8cb8 and calls the
WLAN mode sender with OFF (4) at 0x8cc4. After a successful return it
tests .bss+0xf8, the ELF parameter backing soft_switch. Zero branches to
__cnss_subsystem_put at 0x8d44 and __cnss_subsystem_get at 0x8de4.
Those routines contain rproc_shutdown (0x8bfc) and rproc_boot (0x8974).
The current live parameter is zero. This identifies the compiled path
selected by that setting; the parameter reading alone cannot establish
that nobody changed it since boot. The QSDK13 PCI HIF conclusion above
applies to the installer 6.6.47 module.

**PCI3 CALDB has an active CPU mapping during normal Wi-Fi service.**
/proc/vmallocinfo showed phys=0x59100000, ioremap, allocation span
8,048,640 bytes, caller cnss_pci_alloc_fw_mem+0x394/0xc60. In the
build-ID-matched module this is exactly the return site of __ioremap
(+0x390) after the caldb-addr property lookup (+0x378). The live PCI3 DT
specifies an 8 MiB maximum. PCI1 and PCI2 had mappings from the same
call site at 0x52d00000 and 0x55f00000. The vmalloc span includes kernel
mapping accounting and cannot substitute for the exact WLFW segment
length. This snapshot establishes a CALDB mapping while PCI3 is in
service. It cannot date the allocation to a particular handshake,
demonstrate an earlier unmap or recover the wire payload.

**Radio and file identity.** The AP ath2 reported parent wifi2. Its PCI
endpoint was 0004:01:00.0, vendor/device 17cb:1109, bound to cnss_pci.
This is the live Linux domain for the logical PCI3 radio. Its CNSS DT
board_id was 4 and bdf_pci3 was zero. The resolved board file SHA-256
started bd911abb719fbcae, matching the saved live profile. A full hash
of caldata_4.bin matched 184,320 bytes of 0xff; the PCI3 cache hash
matched 5,153,776 bytes of zero. Neither file reveals the live CALDB
contents. The read-only inspection also found QCA808X PHY ID 0x004dd180
at MDIO addresses 1–4, AQR113C bound at 0 and QCA SFP at 0x1e. Those
are current bindings; their cold-start order remains source-derived.

#### Live 5.4.250 subsystem teardown and CALDB retention

**Shutdown call chain.** The live module passes the operations table at
.rodata+0xee8 to rproc_alloc. Its stop callback at .text+0x20b8 calls
cnss_bus_dev_shutdown at 0x2100. The PCI dispatch at 0x20c2c reaches
cnss_pci_dev_shutdown; device 0x1109 selects the helper at 0x15628.
On the ordinary teardown path that helper calls cnss_pci_remove at
0x15820. Removal tests the DMA-allocation flag at platform offset
0x1764. For the reserved-memory case it calls cnss_bus_free_fw_mem
at 0x155f8, which calls cnss_pci_free_fw_mem at 0x20664. Its mapped
type-4 descriptor takes iounmap at 0x13830 and clears the saved VA and
size. These offsets are for the build-ID-matched live module identified
above. The installer module has a different layout.

**Recreation on the next request.** After subsystem put, the worker
clears cal_in_progress at 0x8d50 before subsystem get at 0x8de4. The
retained PCI3 QMI history shows another memory negotiation. The
request event calls the bus allocator at 0x3dec and sends the memory
response at 0x3dfc on success. For reserved CALDB, the allocator reads
caldb-addr and calls __ioremap again. A fresh SSH check found PCI3
remoteproc running, FW_READY and DRIVER_PROBED set, and the CALDB
ioremap still present at 0x59100000 (span 8,048,640 bytes, caller
cnss_pci_alloc_fw_mem+0x394). Taken together, the normal code path and
the before/after protocol events support an unmap followed by a new
mapping at the same physical base. Only the final mapping was observed
directly. The retained events omit individual segment descriptors and
the kernel log yielded no timestamped PCI3 unmap or remap.

**Evidence about bytes.** The CALDB cleanup clears host bookkeeping.
The explicit payload-clear branch is for type 10 (AFC); type 4 bypasses
it. Mapping the same reserved DDR again permits its contents to survive.
The live module also gates the file-to-memory call at 0x19d28 on both
cold-boot support and the in-progress flag (0x19d08–0x19d1c). Since
the worker clears that flag before the second boot, this handler does
not normally restore the zero-filled PCI3 cache on the mission pass.
These findings support a possible RAM handoff. They cannot establish
that firmware preserved, read or applied the same calibrated bytes.
A current memory digest alone would have no calibration-time baseline
to compare against. The radio and its mappings were left running.

#### Does PCI3 mission firmware report consuming CALDB?

**Firmware-side evidence.** A read-only SSH copy of the running image's
qcn9224/amss.bin was 7,319,552 bytes, SHA-256
b03dbb1a46639aebb42ff03ee9b7dacb9c7735957ad728ace680f34c8278497b.
Its printable diagnostics include an assertion comparing
remote_ddr_mem_req->mem_seg[caldb_idx].size with platform_get_cal_db_size().
It also contains rxdcoHandleSaveRxdcoLutToCalDB, the literally named
rxdcoHandleRestroreRxdcoLutFromCalDB, and an RXDCO beamforming restore
message with bandwidth, chain and home-channel fields. This gives two
firmware-side clues: a defined size for an external CALDB segment, and
PHY code that can restore calibration tables. Strings alone cannot tie
that particular restore routine to the external segment, this PCI3 boot,
or the coefficients produced during the preceding mode-7 pass.

**What mission startup reported.** In PCI3's retained second handshake
(instance 0x3a), firmware acknowledged MEM_INFO and emitted FW_MEM_RDY
at tstamp 56555. FW_INIT_DONE followed at 56700. WLAN_CFG and WLFW_MODE
then completed. The earlier pass contains CAL_RPRT and CAL_DONE; the
retained second pass has no indication identifying a restored table,
its address, checksum, band or chain. The QDSS memory-ready indication
in the second pass belongs to tracing. The current CNSS stats still show
FW_READY and DRIVER_PROBED and the host still maps 0x59100000. Searches
of the available dmesg and logread buffers found none of the identified
restore diagnostics. Boot logs are bounded and firmware debug messages
need not reach these buffers. **Mission startup succeeded; actual reuse
of the mode-7 bytes remains unobserved.**

**OpenWrt consequence.** Treat the host's report of prior calibration as
part of the handoff. The comparison CNSS host-capability request sets
cal_done_valid and copies plat_priv->cal_done; its success handler sets
that state after firmware CAL_DONE. Both PCI3 passes include HOST_CAP in
the live ring, but the ring omits the field values. In the hash-verified
OpenWrt backports 7.2 ath12k source, qmi.c:2222 already serializes
ab->qmi.cal_done. A source search found the read and no assignment to
that field in the base driver or fork's ath12k patches. A port would
need to set it on genuine per-radio completion, carry that state and
the corresponding allocation through the deliberate restart, and
invalidate them together if the allocation or firmware session can no
longer reuse the data. Verify the candidate firmware's requested CALDB
length and mission-pass host-capability value. Those are host-side
checks; a firmware restore event or equivalent firmware telemetry
identifying the retained data would test consumption. The vendor AMSS
diagnostics describe this firmware build, not a guaranteed interface
of the candidate ath12k firmware.
[CNSS QMI fields](../../qsdk/qca/src/qca-cnss/qmi/qmi.c) ·
[OpenWrt package pin](../../package/kernel/mac80211/Makefile) ·
[Backports source](https://github.com/openwrt/backports/releases/download/backports-v7.2/backports-7.2.tar.zst)

#### PCI3 cal_done from completion to mission HOST_CAP

**Live 5.4.250 writer.** The running CNSS module's GNU build ID is
e0b148966c2b1922cc5033ea3f0ce6e7345ffed0. In its successful
cold-calibration event path, the store at .text+0x4448 writes byte 1
at platform-context offset 0x1388. The event worker uses a biased
pointer: x22 is the platform base, x26 is x22 minus 0x120, and the
store uses x26 + 0x1120 + 0x388. It then signals completion at 0x4250
and clears the cold-calibration-in-progress state bit. This ordering
makes the result available before the waiting worker continues. The
worker's separate byte clear at 0x8d50 is cal_in_progress, not cal_done.
[Earlier live worker trace](#live-54250-subsystem-teardown-and-caldb-retention)

**Live serializer.** In the HOST_CAP builder, x20 is the platform context
and x26 is x20 + 0x1000. The load at 0x18258 reads byte +0x388 from x26:
the same platform offset 0x1388. Instructions 0x18260–0x18274 write 1
to request offset 0xa6 and the loaded value to 0xa7. The module's own
wlfw_host_cap_req_msg_v01_ei table maps those offsets to the optional
presence flag and one-byte value of TLV 0x1a. Its QMI send sites use
HOST_CAP message ID 0x34. This verifies the sender and field encoding
against the live binary independently of the comparison source.

**What was sent on this boot?** PCI3 service 0x3a recorded the initial
HOST_CAP at 49666, CAL_DONE_IND at 51325, and the next HOST_CAP at
56543 with a successful response at 56544. The code and those events
support a mission-pass cal_done value of 1 on the normal success path.
The retained history omits TLV bytes. No independent payload capture
or flag-value log was found, and a successful HOST_CAP response does
not acknowledge a particular TLV or prove use of CALDB coefficients.

**Where to change ath12k.** In the pinned backports 7.2 qmi.c, the
existing HOST_CAP builder already sets cal_done_valid and reads
ab->qmi.cal_done (lines 2221–2222). Indication registration sets
cal_done_enable (2365–2366). The missing work is ownership of the value
and its associated per-radio CALDB. The following are proposed port
semantics, not behavior observed in ath12k:

| Transition | Placement and value |
|---|---|
| New radio or new calibration attempt | Keep the per-ab value zero before the first HOST_CAP. Invalidate any older result when beginning a replacement attempt. |
| Successful firmware completion | Decode CAL_DONE on the same QMI instance and process it on the serialized event path. Require an active calibration attempt with its retained CALDB. Set cal_done to 1 before waking the worker that sends OFF. Ignore stale or duplicate indications. |
| Deliberate OFF and second service arrival | Preserve the bit and matching memory through this transition. The next HOST_CAP then advertises 1 before the new memory negotiation. Do not clear it solely because a service-exit event arrived. If mission firmware subsequently asks for incompatible backing, abort this handoff rather than completing startup with a stale claim. |
| Timeout, failed or abandoned handoff, or loss of backing | Clear the bit before another HOST_CAP can be sent. Cover the CALDB replacement path in ath12k_qmi_alloc_chunk (2584 onward), bulk release in ath12k_qmi_free_target_mem_chunk (2551 onward), and final QMI teardown (4076 onward). On recovery, reuse needs explicit evidence that the backing and result remain valid. |

For validation, check PCI3's outgoing TLV 0x1a on both HOST_CAP requests:
expect 0 before calibration and 1 after completion with retained backing.
Exercise a timeout or invalidated allocation separately and expect the
next advertisement to be 0. Keep the firmware-use test separate.
[OpenWrt package pin](../../package/kernel/mac80211/Makefile) ·
[Backports 7.2 source](https://github.com/openwrt/backports/releases/download/backports-v7.2/backports-7.2.tar.zst)

#### Can the existing live traces recover the two cal_done TLVs?

**CNSS history.** On live 5.4.250, PCI3 instance 0x3a has HOST_CAP
request/response pairs at embedded timestamps 49666/49667 and
56543/56544, with CAL_DONE_IND at 51325. The loaded module's qmi_log
symbol occupies 3,072 bytes. Its qmi_record writer (.text+0x17bf0)
wraps the index with 0x7f: 128 records of 24 bytes. It records message
identity, instance, result/error information and a timestamp. It receives
no encoded QMI payload. The table therefore cannot recover the value of
TLV 0x1a for either request, even while both records remain in the ring.
The expected initial 0 and mission 1 come from the driver trace above.
[Comparison history definition](../../qsdk/qca/src/qca-cnss/qmi/qmi.h) ·
[History writer and printer](../../qsdk/qca/src/qca-cnss/qmi/qmi.c)

**Other existing traces.** The running kernel has FTRACE disabled and
neither tracefs location exists. PCI3's remoteproc debugfs directory
exposes no trace file. CoreSight exists, but ETF and ETR both reported
curr_sink=0 at inspection (ETR out_mode=mem). DIAG DCI reported zero
clients and USB disconnected. The live system does retain QDSS control
messages: on the mission pass the QDSS memory request at 58076 and ready
indication at 58077 follow HOST_CAP at 56543. They establish QDSS setup,
without exposing earlier QMI bytes. A read-only filename search under
/tmp, /data, /overlay/upper and /mnt found no matching packet, QDSS or
firmware-log capture. Current sink and client status cannot reconstruct
historical capture settings. No trace session was started or drained.

**Firmware-use result.** The retained mission messages acknowledge
HOST_CAP and the memory exchange, then report firmware initialization
and WLAN startup. The accessible logs contained no decoded cal_done
value or firmware event identifying consumption of PCI3's retained
calibration. A future payload capture could test the host's 0/1 values;
even a confirmed 1 would still require a separate firmware restore
indication to establish that the retained coefficients were applied.

### QCA8084 cold boot and first PHY discovery

**QSDK.** The four BE10000 DT children carry `fixup` and `reg` values
1–4. Their node names end in 0–3. The MDIO driver reads `reg` when
constructing the address map. The fifth child is the Clause 45 AQR at 0.
[Extracted BE10000 DT](../extracted/qwrt-25.12.2-be10000/board.dts)

1. QSDK U-Boot has an earlier, conditional Ethernet path. With QCA8084
   support and the matching board PHY type, IPQ9574 EDMA runs
   `ipq_phy_addr_fixup()` and `ipq_clock_init()` before reading the two
   PHY ID registers. Whether Xiaomi's installed loader executed Ethernet
   initialization on a given boot remains unknown.
   [IPQ9574 EDMA](../../qsdk/qca/src/u-boot-2016/drivers/net/ipq9574/ipq9574_edma.c)
2. QSDK Linux performs its own initialization. `qca_mdio_probe()` sets
   up the common clock, drives the MDIO node's GPIO60 low for 100–110 ms
   and high for another 100–110 ms, then sets the rate and enables
   `gcc_mdio_ahb_clk` when available. With the bus accessors installed,
   it calls `qca_mht_preinit()` **before** `of_mdiobus_register()`.
   [QSDK MDIO probe and reset](../../qsdk/qca/src/linux-5.4/drivers/net/phy/mdio-qca.c)
3. Preinit accesses the package registers through the controller. It
   writes EPHY addresses 1–4 into 0x0c90f018. For this child order, the
   allocator starts at 4, skips occupied slots and selects 5–7 for the
   three UNIPHY fields in 0x0c90f014. These are values derived from the
   source and DT. With the board's `mdio_clk_fixup`, it then enables and
   resets both SerDes system clocks, gates EPHY GMII clocks, enables and
   resets all four EPHY system clocks, releases DSP reset and applies
   analog initialization. Ordinary PHY enumeration follows this work.
   [QSDK address and clock routines](../../qsdk/qca/src/linux-5.4/drivers/net/phy/mdio-qca.c)

**OpenWrt.** The BE7000 draft illustrates how the fork's QCA8084 driver
can start from a declared identity. This is a candidate for BE10000.

1. Linux 6.18 masks automatic scanning, walks the package children and
   takes each address from `reg`. The draft supplies
   `ethernet-phy-id004d.d180` on all four. For this Clause 22 form,
   phylib creates the PHY device with the supplied ID, bypassing the
   initial hardware ID read. This allows the QCA8084 driver to match
   before a copper PHY responds at its final address. A sysfs PHY ID
   alone therefore cannot validate cold discovery.
   [OF package enumeration](https://github.com/torvalds/linux/blob/v6.18/drivers/net/mdio/of_mdio.c#L132-L169) ·
   [PHY creation](https://github.com/torvalds/linux/blob/v6.18/drivers/net/mdio/fwnode_mdio.c#L124-L132) ·
   [Draft PHY nodes](../extracted/qwrt-25.12.2-be10000/be7000-mainline.dts)
2. On the first package probe, patches 0305–0306 use the parent MDIO bus
   and the package's indirect register window to program the two address
   registers. Those accesses use addresses derived from the internal
   register number. They do not require a successful Clause 22 read at
   the new copper address. The seven-entry DT property selects 1–7;
   omission selects the driver's 0–6 defaults, overlapping the Xiaomi
   AQR at 0. [Register access](../../target/linux/qualcommbe/patches-6.18/0305-net-phy-qca808x-Add-register-access-support-routines.patch) ·
   [Address fixup](../../target/linux/qualcommbe/patches-6.18/0306-net-phy-qca808x-Add-QCA8084-probe-function.patch)
3. The draft places the active-low GPIO60 reset on the MDIO bus.
   Its sibling NSSCC MDIO device at 0x18 takes the common PLL's 50 MHz
   reference and supplies clocks and resets to the package and its PHYs.
   The NSSCC driver enables its input clock and can pulse a reset GPIO
   if specified on its own node. The draft has no GPIO there. Its bus
   node also omits explicit reset delays: Linux OF defaults to a 10 µs
   pulse and zero post-delay, much shorter than the QSDK sequence.
   Board reset timing is an independent cold-start variable.
   [Draft MDIO tree](../extracted/qwrt-25.12.2-be10000/be7000-mainline.dts) ·
   [Bus timing](https://github.com/torvalds/linux/blob/v6.18/drivers/net/mdio/of_mdio.c#L198-L214) ·
   [NSSCC probe](https://github.com/torvalds/linux/blob/v6.18/drivers/clk/qcom/nsscc-qca8k.c#L2046-L2074)
4. After address writes, package probe acquires shared clock handles,
   sets up PCS/XPCS resources and deasserts the package reset
   (`NSS_CC_GEPHY_FULL_ARES` in the draft). Each PHY's probe enables
   its own GEPHY system clock and deasserts its system reset. Later,
   `config_init` selects the package mode, enables analog efuse loading,
   waits 10–11 ms and enables the shared operational clocks. These are
   separate failure points after a DT-created PHY can already exist.
   See target patches 0306, 0307, 0308 and 0310 in the
   [qualcommbe series](../../target/linux/qualcommbe/patches-6.18/).

**First hardware check.** On a power-on boot, capture GPIO60 timing and
MDIO/NSSCC probe results, then verify actual Clause 22 ID-register
reads at 1–4 after fixup, alongside the Clause 45 AQR at 0. Record
package/child clock or reset errors before testing carrier and speed on
each jack. A warm reboot can preserve bootloader setup. The source trace
does not establish Xiaomi's minimum reset timing or power-on register
contents.

**Resolution in the board port.** The NSSCC node sets
`reset-post-delay-us = <100000>` and target patch 0363 sleeps after
deasserting GPIO60, preserving the observed 100–110 ms assert and
100–110 ms settle sequence.  The 50 MHz parent is retained because the
QCA8084 binding requires a 50 MHz package reference, the live QSDK MDIO
node covers the CMN PLL block at `0x9b000` and uses `mdio_clk_fixup`,
and the working QWRT mainline reference uses the same parent.  The
physical source still needs a board-level scope check.

## Closing audit (original twenty rounds)

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
