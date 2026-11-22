# BE18000 mainline port risk research

Research note, 2026-11-17. Read-only. No target source file was modified.
The live BE18000 is not reachable from this PC, so every hardware-dependent
item below is an offline code/data finding, not a boot test.

Scope: mainline `qualcommbe/ipq95xx`, Linux 6.18, backports 7.2, and the
Xiaomi `ap-al02-c4` / BE18000 hardware. The sources are the live QWRT dump,
the QSDK 12.2 and QSDK13 extracts, the target patches, and upstream Linux
v6.18 source.

Evidence classes used below:

- **observed**: read from the live dump, a shipped source file, or upstream
  code;
- **derived**: a direct consequence of the observed code/DT;
- **inferred**: plausible but requires hardware validation.

## 1. Summary

| ID | Risk | Severity | Confidence | Status | Phase |
|---|---|---|---|---|---|
| R1 | QCA8084 external PHY package DT/NSSCC/SerDes | **High** | High provider / medium wiring | Open | 1 |
| R2 | Coldboot CALDB for 5G/6G | **High** | Medium | Open | 2/3 |
| R3 | QCN9224 vs QCN9274 firmware/board-2 | **High** | Medium | Open | 2 |
| R4 | U-Boot FIT/UBI, bootargs, secure boot | Medium-High | High | Partially mitigated | 0/1 |
| R5 | AQR113C NVMEM firmware | Low | High | **Resolved** | 1 |
| R6 | Mainline WSI / multi-device MLO | Medium | Medium | Mitigated by opt-in | 3 |
| R7 | NAND/UBI layout and install/recovery | Medium | Medium | Open | 0/1 |
| R8 | Calibration/BDF mapping and blank ART | Medium | High | Partially mitigated | 2/3 |
| R9 | Board-2 / `ipq-wifi` package override | Low-Medium | Medium | Open | 0 |
| R10 | SFP port 6 | Medium | Medium | Deferred | 4 |
| R11 | Kernel config/package gaps | Low-Medium | High | Open | 0 |
| R12 | PCIe/WSI/board IDs | Low-Medium | High | Partially mitigated | 2/3 |
| R13 | Secure boot, anti-rollback, QCN9224 fuse | Low | High | Mitigated by pre-check | 1 |
| R14 | 6G, DCS, MLO behavior | Medium | High | Mitigated by design | 3 |

The two hardest items are **R1** (QCA8084 PHY/NSSCC/SerDes wiring and
validation) and **R2** (5G/6G calibration without usable high-band ART).
The QCA8084 clock/reset provider exists upstream, so R1 is a DT/wiring and
validation gate rather than a missing-driver dead end; R2 still needs a
firmware/driver answer.

## 2. R1: QCA8084 external PHY package (high)

### What the live board has

The live MDIO bus at `90000` has:

- QCA8084 PHYs at MDIO addresses 1-4;
- AQR113C at C45 address 0;
- SFP port PHY at `0x1e`, reset GPIO64;
- `phy-reset-gpio = <&tlmm 60>`, `phyaddr_fixup = <0xc90f018>`,
  `uniphyaddr_fixup = <0xc90f014>`.

The live QSDK port map is:

| PPE port | Device | MDIO | PCS | QSDK12 mode | QSDK13 mode |
|---|---|---|---|---|---|
| 1-4 | QCA8084 PHY0-3 | 1-4 | UNIPHY0 ch0-3 | `sgmii` | `qusgmii` |
| 5 | AQR113C | 0 (C45) | UNIPHY1 ch0 | `sgmii` | `usxgmii` |
| 6 | SFP+ | `0x1e` | UNIPHY2 ch0 | `sgmii` | `usxgmii` |

Evidence: `QWRT/extracted/live-be18000/dt/live-board.dts` (MDIO, `dp1`-`dp6`),
`QWRT/doc/be18000-live-probe-5.md` (live `qcom,port_phyinfo` and SFP mapping),
`QWRT/extracted/qsdk13-r26.09.05-be18000/be18000-board.dts` (`dp1`-`dp6`).

### The QCA8084 clock/reset provider exists, but the Xiaomi DT does not use it yet

The target carries a QCA8084 PHY/package series (`patches-6.18/0301`-`0312`).
The PHY driver is out-of-tree: upstream Linux v6.18
`drivers/net/phy/qcom/qca808x.c` has **no QCA8084 support**. The clock/reset
side is different: upstream v6.18 **does** have the QCA8084 NSSCC
clock/reset driver in `drivers/clk/qcom/nsscc-qca8k.c`, compatible
`qcom,qca8084-nsscc` (the binding says "QCA8386/QCA8084"). It is an MDIO
device (the binding example is `clock-controller@18`), with a reference
clock and a `reset-gpios`; it supplies the QCA8084 package/per-PHY/PCS/XPCS
clocks and resets. The target enables it with
`CONFIG_IPQ_NSSCC_QCA8K=y` in `ipq95xx/config-default`.

The target QCA8084 driver requires, for every QCA8084 PHY:

- `devm_clk_get_enabled(dev, NULL)` in `qca8084_probe()`;
- `devm_reset_control_get_exclusive(dev, NULL)` in `qca8084_probe()`;
- package clocks and a package reset in `qca8084_phy_package_probe_once()`;
- PCS/XPCS resets and clocks in `qca8084_package_pcs_probe()` and
  `qca8084_package_xpcs_probe()`;
- for 10G-QXGMII, `qca8084_qxgmii_set_mode()` and the SerDes clock-parent
  setup.

Evidence: `patches-6.18/0306` (`qca8084_probe`), `0307` (package clocks and
resets), `0308` (`qca8084_package_clock_init`), `0310` (PCS/XPCS probe),
`0311` (`qca8084_qxgmii_set_mode`), and the binding example in `0301`
(`qca8k_nsscc` clocks, `QCA808X_PCS1_10G_QXGMII_PCS0_UNUNSED`). Upstream
v6.18 `Documentation/devicetree/bindings/clock/qcom,qca8k-nsscc.yaml` and
`drivers/clk/qcom/nsscc-qca8k.c` are the provider reference.

The QSDK handles the same controller from the **SSDK**, not the Linux PHY
framework: `qsdk/qca/src/qca-ssdk/src/hsl/phy/qca8084_phy.c` uses
`ssdk_mht_gcc_clock_init()`, `ssdk_mht_port_clk_reset()`,
`mht_port_speed_clock_set()`, `mht_uniphy_xpcs_speed_set()`,
`ssdk_mht_pinctrl_init()`, and the MHT/UNIPHY registers for the IPQ9574.
The mainline equivalent is the `qcom,qca8084-nsscc` MDIO driver, not a
different hardware model. The live QSDK DT does not describe the NSSCC node;
the Xiaomi mainline DTS must add it.

**Derived:** without the NSSCC node and the per-PHY/PCS/XPCS clock/reset
phandles, `qca8084_probe()`/the package/PCS/XPCS probes return `-ENOENT` and
the QCA8084 PHYs do not bind. With a correct NSSCC node they can bind; the
open issue is the exact Xiaomi wiring (NSSCC MDIO address, reference clocks,
reset GPIO, clock/reset IDs) and the external QCA8084 QXGMII/SerDes
validation.

**Inferred:** a QSGMII (4 x 1G) fallback still needs the per-PHY clocks and
resets, so it does not avoid the NSSCC/package node; it only avoids the
10G-QXGMII SerDes clock-parent path.

### Impact

If the NSSCC/package wiring is wrong, the four 2.5G ports fail to probe; the
AQR113C 10G port is independent and may still work. The provider exists, so
this is a DT/wiring and validation problem, not a missing-driver problem.
Do not schedule the 2.5G ports as a Phase 1 certainty.

### Mitigation

1. **Instantiate the upstream `qcom,qca8084-nsscc` MDIO clock controller** at
   the address used by the QCA8084 package (the binding example uses `0x18`),
   with the IPQ9574 reference/UNIPHY clocks and the NSSCC reset GPIO (verify
   whether it is the live PHY reset GPIO60 or a separate line). Wire the
   QCA8084 package's `clocks`/`resets` and the per-PHY, PCS and XPCS phandles
   to it, following the `0301` binding example.
2. Compare the NSSCC clock/reset IDs and the QSDK SSDK `qca8084_phy.c`
   sequences; the QSDK's MHT/GCC programming is the reference for the
   external package. If a clock/reset ID differs, adapt the DT/driver.
3. Only if the external package cannot be described with the upstream
   provider, add a board-specific clock/reset adaptation or make the
   QCA8084 probes tolerate missing resources as a bring-up fallback.

### Validation

- `dmesg` for `qca8084` probe errors, `-ENOENT` clock/reset messages, the
  NSSCC probe, and PHY addresses 1-4.
- `ethtool ethX` for 10/100/1000/2500 link modes; a 2.5G link is the
  acceptance test.
- `mdio-tools`/`phytool` reads of the QCA8084 package and NSSCC registers if
  the kernel exposes the bus.
- Compare the mainline NSSCC clock tree with the QSDK SSDK clock tree at the
  same link speed.

## 3. R2: Coldboot CALDB for 5G/6G (high)

### What is known

- The live high-band ART slices at `0x58800`, `0x8A800`, `0xBC800` are
  `0xff`; they are not calibration data.
- The live QSDK coldboot-calibrates all three radios; the live log has
  `Coldboot Calibration completed successfully for device 0x1109`.
- The QSDK13 `firmware_rdp_feature.ini` enables cold boot for
  `ap-al02-c4_qcn9224_pci1/2/3`.
- The live QSDK DT gives each QCN9224 a 50 MiB reserved region and a
  `caldb-addr`/`caldb-size` of 8 MiB at offset `0x1e00000` inside it:
  `0x52d00000`, `0x55f00000`, `0x59100000`.

Evidence: `QWRT/extracted/live-be18000/firmware/art.bin` (blank slices),
`QWRT/doc/be18000-live-probe-4.md` (coldboot log), `QWRT/doc/be18000-probe-rounds.md`
(round 24), `QWRT/extracted/qsdk13-r26.09.05-be18000/rootfs/lib/firmware/qcn9224/firmware_rdp_feature.ini`,
`be18000-board.dts` (`qcom,caldb-addr`, `qcom,caldb-size`), and
`QWRT/extracted/live-be18000/dt/live-board.dts` (`reserved-memory`, `qcom,cnss-qcn9224`).

### The mainline driver is only half-ready

Upstream Linux v6.18 `ath12k/qmi.c` has a `CALDB_MEM_REGION_TYPE` case that
sets `paddr = 0` with this comment:

> Cold boot calibration is not enabled in Ath12k. Hence, assign paddr = 0.
> Once cold boot calibration is enabled add support to assign reserved memory
> from DT.

However, the same file also calls `ath12k_qmi_alloc_chunk()` for
`CALDB_MEM_REGION_TYPE`; that allocates a DMA coherent chunk and sets
`chunk->paddr`. So the firmware **can** receive a host buffer if it requests
CALDB. The missing pieces are:

- no `qcom,caldb-addr`/`qcom,caldb-size` or reserved-memory path in the
  mainline driver;
- no mainline use of the QSDK `firmware_rdp_feature.ini` coldboot flag;
- no proof that the official QCN9274 `firmware-2.bin` requests CALDB on the
  QCN9224 or that it accepts an arbitrary DMA address.

**Derived:** the plan's "add a coldboot CALDB patch that sets paddr from a
reserved region" is not the whole change. The driver already allocates a CALDB
chunk; the open question is whether the QCN9224 firmware asks for it and
whether it needs the fixed QSDK address.

### Impact

Without CALDB, 2.4G may work from its valid ART/BDF, but 5G and 6G have no
usable calibration and will fail or run with invalid txpower/rates. This is
a blocker for the Wi-Fi 7 milestone, not just a warning.

### Mitigation

1. Test the official QCN9274 `firmware-2.bin` first and capture the QMI
   target-memory request types. If CALDB is requested, confirm the DMA chunk
   allocation and the coldboot completion message.
2. If the firmware does not request CALDB, implement the QSDK-style fixed
   region: add the 50 MiB reserved regions and the `qcom,caldb-addr`/size
   properties, then patch `ath12k_qmi_assign_target_mem_chunk()` to map
   `CALDB_MEM_REGION_TYPE` to the reserved address instead of `paddr=0`.
3. If the QCN9274 firmware cannot enable coldboot for the QCN9224, the
   fallback is the QCN9224 QSDK firmware/INI path (see R3), not blank ART.

### Validation

- `dmesg` for QMI memory allocation types (`CALDB`, `HOST_DDR`, `BDF`,
   `M3_DUMP`), `Coldboot Calibration` and per-radio calibration success.
- `iw phy` txpower/rate sanity on 5G/6G; a 6E client association.
- Do not treat a firmware boot as calibration success; check the
  per-radio calibration completion.

## 4. R3: QCN9224 vs QCN9274 firmware and board-2 (high)

### What is known

- The live PCI endpoints are vendor `0x17cb`, device `0x1109`; the live QMI
  target reports `chip_id 0`, `board_id 0xff`, firmware `0x110d8016`
  (2023-10-27).
- Upstream ath12k supports `QCN9274 hw2.0` (and WCN7850), with firmware
  `ath12k/QCN9274/hw2.0/firmware-2.bin` and a split-PHY `amss_dualmac`
  image IE. The QCN9224 is not a separate upstream hardware entry.
- The QSDK13 QCN9224 firmware is `WLAN.WBE.1.5-01577`, with separate
  `amss.bin` (7,237,632 B) and `m3.bin` (421,888 B), and the variant string
  `9224.wlanfw.eval_v2Q`. The live QCN9224 `amss.bin` is 7,319,552 B.
- The mainline QCN9274 firmware is a single `firmware-2.bin` (15-16 MB)
  containing AMSS/M3 (and AMSS dual-MAC) IEs, not the QSDK raw `amss.bin`/
  `m3.bin` pair.

Evidence: `QWRT/doc/be18000-live-probe-4.md` (QMI/PCI/firmware), round 16
(`amss.bin` hashes/versions), upstream v6.18 `ath12k/hw.c` (`qcn9274 hw2.0`,
`dir = "QCN9274/hw2.0"`), `pci.c` (`QCN9274_DEVICE_ID 0x1109`), `fw.c`
(`ATH12K_FW_IE_AMSS_IMAGE`, `M3_IMAGE`, `AMSS_DUALMAC_IMAGE`), and the
linux-firmware QCN9274 `firmware-2.bin` history.

**Derived:** the mainline driver will treat the QCN9224 endpoint as a
QCN9274 hw2.0 device. That is plausible because the PCI ID and QMI chip ID
match, but the firmware is a different build (`9224` vs `9274`). The QSDK
`amss.bin`/`m3.bin` cannot be dropped into `ath12k/QCN9274/hw2.0/`; the
mainline loader expects `firmware-2.bin` with the ath12k IE container.

### Impact

If the official QCN9274 firmware does not support the QCN9224 RF/PHY
topology, the radios fail at MHI/firmware load or later at QMI/WMI. This
would block all three bands, independent of calibration.

### Mitigation

1. Test the official `ath12k-firmware-qcn9274` `firmware-2.bin` first. Keep
   the Xiaomi board-2 override; the firmware and board data are separate.
2. If it fails, build a `firmware-2.bin` container from the QSDK13 QCN9224
   `amss.bin`/`m3.bin` (and the dual-MAC image if required), using the
   upstream QCN9274 container as the IE/timestamp/feature template. Test only
   after recording the exact IE layout and hashes.
3. Do not mix the QSDK `caldata_2/3/4` (BDF copies) with the mainline
   `cal-pci-*` mechanism; the live BDFs are already in the board-2 container.
4. Keep the QSDK13 `amss.bin`/`m3.bin` as a fallback artifact, not as a
   primary firmware, and record the license/provenance.

### Validation

- `dmesg` for `qmi chip_id/board_id`, firmware version, MHI load, QMI
  `TGT_CAP_RESP`, and per-radio `fw_version`.
- `iw phy`/`iw dev` for each radio; a QMI capability failure is not a
  successful probe.

## 5. R4: U-Boot FIT/UBI, bootargs, secure boot (medium-high)

### FIT config and load address

The live FIT is `config@al02-c4`, gzip, load/entry `0x42080000`. The live
U-Boot is `bootcmd=bootipq` and boots that FIT from the UBI `kernel` volume
inside the `rootfs` mtd partition. The QSDK U-Boot `ipq9574-al02-c4.dts`
declares `config@al02-c4`; the live boot proves the runtime U-Boot accepts
it. The string list extracted from the ELF is not the runtime control DTB
list (the control DTB is separate), so it does not contradict the live
evidence.

Evidence: `QWRT/extracted/live-be18000/firmware/live-kernel.fit`,
`QWRT/doc/be18000-live-probe-5.md`, `qsdk/qca/src/u-boot-2016/arch/arm/dts/ipq9574-al02-c4.dts`,
`qsdk/qca/src/u-boot-2016/board/qca/arm/common/cmd_bootqca.c`.

**Confidence: high** that `config@al02-c4` is the right name and
`0x42080000`/gzip is the proven load layout. Keep both.
### Installed bootloader identity (verified)

The installed QWRT U-Boot is byte-identical to the package in `QWRT/UBoot`:
the first 549,912 bytes of the live `0:APPSBL` dump equal `uboot.bin`
(SHA-256 `a82b5476...`), version `U-Boot 2016.01 (Jan 01 2024 ...)`, web UI
`uboot2.0 version:24.01.02`. It is a Thumb-2 ARM32 QSDK fork with `bootipq`,
`ubi`, `tftpboot`, `httpd`/web recovery and the QCA `flash` command. The
checked-in `qsdk/qca/src/u-boot-2016` tree cannot rebuild it:
`ipq9574_defconfig` has `CONFIG_CMD_NAND`/`CONFIG_CMD_SPI` off and the web UI
source is absent. Upstream `qcom_ipq9574_mmc_defconfig` is eMMC-only. Keep the
installed bootloader; replacing it is a separate project. See
`be18000-uboot-package-analysis.md`.

### The rootfs bootarg is missing from the mainline FIT

The live runtime DT has:

```
chosen {
    bootargs = "... root=mtd:ubi_rootfs ... rootwait ...";
    bootargs-append = " root=/dev/ubiblock0_1 cnss2.enable_mlo_support=0 swiotlb=1 coherent_pool=2M";
};
```

The QSDK13 board DTS has the same `chosen/bootargs-append`. The live FIT root,
however, has **no** `append-bootargs` property; the live ubiblock arg comes
from the QSDK `bootargs-append` mechanism, not from the OpenWrt FIT root.

The stock U-Boot `update_bootargs()` reads `append-bootargs` from the **FIT
root** and appends it to the env `bootargs` plus `rootwait`. If the FIT lacks
it, U-Boot falls back to `fsbootargs`, which on the live unit still says
`root=mtd:ubi_rootfs` and does **not** contain `root=/dev/ubiblock0_1`.
OpenWrt `scripts/mkits.sh` does not add `append-bootargs` either. Note: the
installed QWRT binary contains neither `append-bootargs` nor
`bootargs-append` as a string, so the `fsbootargs` fallback is the only
certain U-Boot path.

**Verified (offline):** the blocker is closed on the kernel side. The FIT
root still has no `append-bootargs`, but the board DTB
`chosen/bootargs-append` is consumed by OpenWrt's generic
`target/linux/generic/hack-6.18/920-device_tree_cmdline.patch`, which appends
it to the cmdline after the bootloader arguments. The built 6.18.60 kernel
contains the `bootargs-append` string (offset 12606288 of the decompressed
`factory.ubi` kernel) and the DTB carries
`chosen/bootargs-append = " root=/dev/ubiblock0_1"`. The last `root=` wins,
so the squashfs mounts. See `be18000-fit-crosscheck.md`.

A FIT-root `append-bootargs` is therefore optional. It is only required if
the kernel hack or the DTB property is removed, or for a U-Boot that replaces
the DTB cmdline. The fallback is the U-Boot env `fsbootargs`.

### Secure boot and authentication

The live U-Boot `do_bootipq()` checks the QFPROM secure-boot fuse. If the
fuse is not set, it uses `do_boot_unsignedimg()` and skips
`qca_scm_auth_kernel()`. The live FIT is a plain FIT, not an MBN-wrapped
signed image, so the live unit is on the unsigned path. If the fuse were
set, `do_boot_signedimg()` would authenticate the kernel and the plain FIT
would fail.

**Confidence: high** that the live unit does not enforce secure boot; **not
proven** for any other unit. Check the fuse status in the U-Boot console
before flashing an unsigned image.

### Mitigation

1. Optional hardening: add a FIT root `append-bootargs = " root=/dev/ubiblock0_1"` (and any
   `swiotlb`/`coherent_pool` options) to the Xiaomi image. Extend
   `scripts/mkits.sh`/`Build/fit-its` with a device variable, or post-process
   the FIT with `fdtput`; do not rely on the QSDK `bootargs-append` property.
2. Alternatively, set the U-Boot env `fsbootargs` (or `bootargs`) to include
   `root=/dev/ubiblock0_1`; but that changes APPSBLENV and is less clean than
   the FIT property.
3. Keep `config@al02-c4`; if the config select fails, set the U-Boot
   `config_name` env to `config@al02-c4` as a one-time debug step.
4. Check the secure-boot fuse before flashing; if it is set, stop and use a
   signed/QSDK image or the stock recovery, not a mainline unsigned FIT.
5. Keep `bootcmd=bootipq` and the UBI `kernel` volume; do not replace U-Boot.

### Validation

- U-Boot console `printenv bootargs fsbootargs` and the `bootipq debug`
  output.
- Kernel cmdline contains `root=/dev/ubiblock0_1` after `root=mtd:ubi_rootfs`.
- Rootfs mounts; `ubiattach`/`ubinfo` show `kernel`, `rootfs`, `rootfs_data`.

## 6. R5: AQR113C NVMEM firmware (low, resolved)

The live `0:ETHPHYFW` partition is an MBN image: 0x28-byte header,
`image_type 0x13`, size `0x60002`, followed by the Xiaomi
`aqr-xiaomi-v5.6.7.cld` payload. The payload is 393,218 bytes and its
CRC-16/CCITT (init 0) over the first `size-2` bytes is `0x8ac4`, matching
the stored trailing big-endian CRC `0x8ac4`.

Upstream Linux v6.18 `drivers/net/phy/aquantia/aquantia_firmware.c` supports
exactly this:

- `aqr107_probe()` calls `aqr_firmware_load()`;
- if `VEND1_GLOBAL_FW_ID` is already non-zero, it does nothing (the live
  U-Boot already loaded the firmware);
- otherwise it reads the NVMEM cell named `firmware`, validates the AQR
  header/CRC/version, and boots the image; if the cell is missing/invalid it
  falls back to `firmware-name` from the filesystem.

The target patch `0350` already adds `nvmem-cells = <&aqr_fw>` /
`nvmem-cell-names = "firmware"` to the AQR PHY. The Xiaomi cell must be:

```
aqr_fw: aqr-fw@28 {
    reg = <0x28 0x60002>;
};
```

inside an nvmem-layout on the `0:ETHPHYFW` partition. Do not use the
Netgear VER1990 `cld` and do not include the 0x28 MBN header in the cell.

**Confidence: high.** This risk is resolved unless the PHY resets after
Linux probe and the NVMEM cell is wrong; test `ethtool -m`/link on the 10G
port and `dmesg` for the AQR firmware version.

## 7. R6: Mainline WSI and multi-device MLO (medium)

Upstream ath12k v6.18 has WSI discovery through the `of_graph` and
`qcom,wsi-controller`, plus MLO group setup, partner links, and per-device
IDs. The target adds `105-wifi-ath12k-assign-device-id-from-the-WSI-index.patch`
to make the device ID deterministic.

The Xiaomi QSDK DT uses QSDK-specific properties, not the mainline graph:

- `wsi { id = 0; num_chip = 3; chip_info = ...; }`;
- per-`wifi@N`: `qcom,wsi = <&wsi>`, `qcom,wsi_index = <2/0/1>`;
- live MLO config: 3 chips, one local link each, no WSI adjacency.

The sbe1v1k DTS has the mainline template: endpoint pairs between the three
radios and `qcom,wsi-controller` on the 5G (pcie2) radio. The QSDK13 WSI
indices are 2 (2.4G), 0 (5G controller), 1 (6G); the mainline graph should
reproduce that order.

**Impact:** a wrong graph can prevent the 5G controller from becoming the
WSI controller, leave `ath12k_core_get_wsi_index()` without an index, or
break MLO partner setup. Single-radio operation should survive if MLO is
left disabled.

**Mitigation:** use the sbe1v1k graph, keep MLO opt-in, verify
`wsi group-id ... num-devices ... index ...` in dmesg, and test 2.4G/5G/6G
individually before enabling MLO. Do not copy the QSDK 12.2 stale-MLD reject
path or the QSDK DCS behavior.

**Confidence: medium** for the graph; **high** that MLO is not needed for the
first wired/2.4G/5G/6G milestones.

## 8. R7: NAND/UBI layout and install/recovery (medium)

The live MIBIB table is the only valid partition source:

```
0:ART      0x1480000 0x140000
0:ETHPHYFW 0x15c0000 0x100000
rootfs     0x1780000 0xbe00000 (190 MiB)
```

NAND is QPIC, ECC 4/512, 8-bit. The live UBI has 1,520 LEBs of 126,976
bytes: `kernel` 44 LEB, `rootfs` 407 LEB, `rootfs_data` 1,025 LEB. The
`Device/UbiFit` definition (kernel in UBI, `factory.ubi`) is the right
shape, but no existing device uses it and `platform.sh` has no Xiaomi case.

**Derived:** `Device/UbiFit` can create `kernel`, `rootfs`, `rootfs_data`
with `BLOCKSIZE=0x20000`, `PAGESIZE=2048`, `SUBPAGESIZE=2048`,
`VID_HDR_OFFSET=2048`, `IMAGE_SIZE=0xbe00000`. `nand_do_upgrade` with
`CI_KERNPART=kernel`, `CI_ROOTPART=rootfs` is the expected sysupgrade path.
The `rootfs` partition is 190 MiB; the live rootfs volume is only 49.2 MiB,
so the sysupgrade resizes the volumes (expected).

**Install risk:** the stock U-Boot web recovery "Firmware" page may expect a
vendor sysupgrade/full image, not a raw `factory.ubi`. The safe first install
is a recovery initramfs booted over TFTP/serial, with `ubiformat` of the
`rootfs` mtd partition and a verified backup of ART/ETHPHYFW/APPSBL/MIBIB.
Do not use `nand write` for a raw UBI image; it does not handle bad blocks.

**Mitigation:** build a recovery initramfs with `ubiformat`, `ubiattach`,
`ubinfo`, `nanddump`; preserve `0:ART`, `0:ETHPHYFW`, `0:APPSBL`,
`0:MIBIB`, `0:CDT`, `0:QSEE`, `0:DEVCFG`, `0:APDP`; add a Xiaomi
`platform.sh` case and validate `sysupgrade` only after a serial recovery
path exists.
**Verified from the QWRT package (2026-11-22):** the live `0:MIBIB` matches
`BE10000_Uboot_MIBIB_MAX.zip` exactly (first 256 KiB hash `e482188b...`), not
the v2 package. v2 splits the same 190 MiB into a 120 MiB `rootfs` plus a
70 MiB `overlay` mtd and moves bdata/crash; never flash it. The readme's
`mtd write uboot.bin /dev/mtd18` touches only the primary APPSBL; the web
U-Boot page runs `flash 0:APPSBL; flash 0:APPSBL_1`. Full backup and
first-flash commands are in `be18000-recovery-runbook.md`.

## 9. R8: Calibration/BDF mapping and blank ART (medium)

The live mapping is board IDs 1/2/4 for PCI1/2/3 = 2.4G/5G/6G. The live
board-2 variants are `Xiaomi_BE18000_live_1/_2/_4`; the BDFs are the live
`bdwlan.b0001/2/4`. The QSDK13 `ftm.conf` maps `ap-al02-c4` as 1/4/2 (2.4G,
6G, 5G) and its `caldata_3/4` are swapped relative to the live controllers;
that is a QSDK mapping, not the mainline variant mapping.

The `0:ART` high-band slices at 0x58800/0x8A800/0xBC800 are `0xff`; the
current `11-ath12k-caldata` script only handles sbe1v1k and extracts those
offsets. Adding the same cases for Xiaomi would install blank calibration.
The live `caldata_1..4` are 184,320-byte QSDK containers, not raw ART
slices: `caldata_1` embeds the factory `art-0x33000-b04` at 0xC800,
`caldata_2` embeds `art-0x65000-b02` at 0xC800, and `caldata_3/4` are
identical all-nonzero copies. The live driver maps PCI1/2/3 to
`caldata_2/3/4`, but that is a QSDK controller order, not a mainline
calibration-variant mapping. The `wlfw_cal_01_QCN9224_PCI*.bin` cache files
are zero-filled placeholders.

Use the live BDFs (`bdwlan.b0001/2/4`) as the board-2 data; do not derive
mainline calibration from the QSDK `caldata_*` containers.

**Mitigation:** use the live BDFs and the `Xiaomi_BE18000_live_1/_2/_4`
variants; do not add high-band `caldata_extract_mmc` cases; if the 2.4G ART
BDF is valid, use only that low-band artifact; rely on coldboot CALDB for
5G/6G (R2). Verify the selected variant in dmesg.

## 10. R9: Board-2 / `ipq-wifi` package override (low-medium)

Both `ath12k-firmware-qcn9274` and a Xiaomi `ipq-wifi` package install
`/lib/firmware/ath12k/QCN9274/hw2.0/board-2.bin`. The final file must be the
Xiaomi container (292,256 bytes, SHA256 `0fcbb66e...` for the live build),
not the official 2.6 MB board-2. The package install order is not a strong
guarantee.

**Mitigation:** add a local `ipq-wifi-xiaomi_be18000` package/file, list it
after `ath12k-firmware-qcn9274` in `DEVICE_PACKAGES`, and verify the built
image's `board-2.bin` hash. Keep the official firmware package for
`firmware-2.bin`/`regdb`, but override only `board-2.bin`.

## 11. R10: SFP port 6 (medium, deferred)

The live SFP+ is ESS port 6, PHY address `0x1e`, reset GPIO64, not a direct
i2c4 EEPROM. QSDK12 uses `sgmii`, QSDK13 uses `usxgmii`; mainline should
use `usxgmii` (or the module-appropriate mode) and `pcs2_ch0`. The live
`mdio` node does not list the SFP PHY, so the DTS must add it and the `sfp`
framework separately.

**Mitigation:** defer SFP until wired 2.5G/10G is stable. Use the mainline
`sfp` node, `reset-gpios = <&tlmm 64 GPIO_ACTIVE_LOW>`, and the `pcs2_ch0`
port 6; validate module detect, EEPROM, and 1G/10G links.

## 12. R11: Kernel config/package gaps (low-medium)

The target already has `CONFIG_AQUANTIA_PHY=y`, `CONFIG_QCA808X_PHY=y`,
`CONFIG_PHY_PACKAGE=y`, NAND/UBI, `CONFIG_WATCHDOG_SYSFS=y`, and the
`kmod-qcom-ppe`/`kmod-pcs-qcom-ipq9574` package dependencies. Still needed:

- `kmod-pstore` + `kmod-ramoops` (the current `config-6.18` has no
  `CONFIG_PSTORE`/`CONFIG_PSTORE_RAM`; the MLO reboot had no crash log);
- `kmod-sfp` (`CONFIG_SFP`, `CONFIG_MDIO_I2C`);
- `kmod-leds-pwm` (`CONFIG_LEDS_PWM`);
- `kmod-hwmon-emc2305`, `kmod-hwmon-lm63` for the fan/temperature;
- `kmod-input-gpio-keys`/`kmod-gpio-button-hotplug` for reset/mesh;
- `kmod-i2c-core` for NFC/fan/SFP;
- a ramoops reserved-memory node (the live DT has no pstore reservation);
- `kmod-qcom-ppe` and `kmod-pcs-qcom-ipq9574` (the latter is a dependency;
  the `config-6.18` has `# CONFIG_QCOM_PPE is not set` because the driver is
  a module, not because it is unavailable).

The `CONFIG_QCA808X_PHY=y` built-in path is good, but the QCA8084 package
support still has R1; enabling the driver does not solve the clock/reset
model.

## 13. R12: PCIe/WSI/board IDs (low-medium)

The live mapping is:

| Controller | PERST | Lanes | Board ID | WSI index | Band |
|---|---|---|---|---|---|
| `pci@10000000` | GPIO26 | 1 | 1 | 2 | 2.4G |
| `pci@20000000` | GPIO29 | 2 | 2 | 0 | 5G (controller) |
| `pci@18000000` | GPIO23 | 2 | 4 | 1 | 6G |

The QSDK13 DTS uses the same board IDs 1/2/4; the 1/4/2 mismatch is only in
`ftm.conf`/caldata, not the DTS. Mainline uses `qcom,calibration-variant`
(patch 700) and the `of_graph` WSI graph, not `qcom,board_id`/`wsi_index`.
The live PCIe links are 8 GT/s, x1 for 2.4G, x2 for 5G/6G; the endpoint BAR0
is 2 MiB with 32 MSI IRQs.

**Mitigation:** use the sbe1v1k WSI graph and the live board IDs only as
calibration variants; do not copy the QSDK `qcom,board_id`/`wsi_index`
properties into mainline. Verify the PCIe link state and the WSI index in
dmesg.

## 14. R13: Secure boot, anti-rollback, QCN9224 fuse (low)

The U-Boot has `secure_authenticate`, `qca_scm_auth_kernel`,
`Partition info authentication failed`, and QCN9224 `detect_qcn9224`/
`fuse_qcn9224` commands. The QCN9224 commands are manufacturing detection/
fuse helpers; `detect_qcn9224` reads TCSR and sets an env, and `fuse_qcn9224`
skips V1. They are not an automatic anti-rollback check.

The live plain FIT proves the secure-boot fuse is not enforced on this unit.
The risk is for a different unit or a fuse state change. **Mitigation:** read
the secure-boot fuse status in the U-Boot console before any flash; do not
blow QCN9224 fuses; preserve QSEE/DEVCFG/APDP.

## 15. R14: 6G/DCS/MLO behavior (medium, design-mitigated)

The live unit was moved from PSC ch37/6135 to ch129/6595 by QSDK AWGN DCS;
the laptop 6G link fell to 6/17 Mbps. The port intentionally pins ch37/6135
and does not copy QSDK DCS. QSDK12 has a stale-MLD reject path and
`num_adj_chips: 0`; QSDK13 forwards PMF/SAE auth to hostapd and deletes
active-MLO peers. Mainline mac80211/ath12k handles the MLO lifecycle
differently; keep MLO opt-in and test 6G link drop/reconnect.

**Mitigation:** fixed PSC 37/6135, 320 MHz; no QSDK DCS; MLO off by default;
validate 6E-only client first; then opt-in 5G+6G MLO with PMF/SAE and test
link removal/re-add and full MLD reconnect.

## 16. What this changes in the port plan

1. **Phase 0:** add a FIT root `append-bootargs` for
   `root=/dev/ubiblock0_1`; without it the kernel may not mount the squashfs
   root. The current `Device/FitImage`/`mkits.sh` does not add it.
2. **Phase 1:** do not assume the QCA8084 PHYs probe. Instantiate the
   upstream `qcom,qca8084-nsscc` node and wire the package/per-PHY/PCS/XPCS
   clocks/resets first; the AQR/10G path is independent and should be brought
   up first. A 1G QSGMII fallback still needs the NSSCC/package node, but it
   avoids the 10G-QXGMII SerDes clock-parent path.
3. **Phase 2:** test the official QCN9274 `firmware-2.bin` with the Xiaomi
   board-2 and check the QMI CALDB request. The QSDK13 `amss.bin`/`m3.bin`
   are not a drop-in mainline firmware; a `firmware-2.bin` wrapper is the
   fallback (R3).
4. **Phase 2/3:** the coldboot CALDB path is not just a DT property; the
   driver already allocates a DMA CALDB chunk, but the firmware must request
   it and may need the QSDK fixed `caldb-addr` region. Plan for both outcomes.
5. **Phase 0/1:** add the Xiaomi `platform.sh`/`02_network` cases and a
   recovery initramfs with `ubiformat`; do not rely on the U-Boot web
   recovery accepting a raw `factory.ubi`.
6. **Phase 0:** add `kmod-pstore`/`kmod-ramoops`, `kmod-sfp`,
   `kmod-leds-pwm`, `kmod-hwmon-emc2305`, `kmod-hwmon-lm63`,
   `kmod-input-gpio-keys`, and `kmod-i2c-core`; add a ramoops
   reserved-memory node.
7. **Phase 2/3:** use the sbe1v1k WSI graph and the live calibration
   variants; do not copy `qcom,board_id`/`qcom,wsi_index` into mainline.
8. **Calibration:** never extract the blank 0x58800/0x8A800/0xBC800 ART
   slices; the current sbe1v1k-only hotplug rule is correct in that respect.
9. **Board-2:** verify the Xiaomi board-2 wins over the official 2.6 MB
   board-2; check the image hash.

## 17. Open questions that need hardware

1. Does a `qcom,qca8084-nsscc` node at the correct MDIO address/reference
   clocks/reset GPIO (live GPIO60) make the package/per-PHY/PCS/XPCS probes
   work, and does 10G-QXGMII link up at 2.5G?
2. Does the official QCN9274 `firmware-2.bin` load on the QCN9224 and request
   CALDB? If yes, does the DMA paddr work, or must it be the fixed QSDK
   `caldb-addr`?
3. Does the mainline WSI graph with the sbe1v1k topology produce indices
   2/0/1 and form the 3-chip MLO group on the QCN9224?
4. Does the stock U-Boot accept the mainline `factory.ubi` via the web
   recovery, or is a recovery initramfs + `ubiformat` required?
5. Does a 2.5G link negotiate on the QCA8084 ports with the mainline
   `10g-qxgmii` PCS/PHY, or does it fall back to 1G QSGMII?
6. Does the 6G PSC 37/6135 link recover after a client drop without the QSDK
   stale-MLD reject path?

Until the router is reachable with serial/recovery, these remain inferred.
The offline build can still resolve the FIT `append-bootargs`, the DTS shape,
the package/config list, the board-2 hash, and the AQR NVMEM cell.

## 18. References

- Live dump: `QWRT/extracted/live-be18000/` (`firmware/`, `dt/`, `wifi/`,
  `probes/`).
- QSDK13: `QWRT/extracted/qsdk13-r26.09.05-be18000/` (`be18000-board.dts`,
  `rootfs/lib/firmware/qcn9224/`, `rootfs/lib/firmware/ftm.conf`).
- Live findings: `QWRT/doc/be18000-live-probe-4.md`,
  `be18000-live-probe-5.md`, `be18000-probe-rounds.md`,
  `be18000-mlo-incident.md`, `be18000-qsdk-dcs-research.md`,
  `be18000-qsdk13-mlo-auth-research.md`.
- Mainline target: `target/linux/qualcommbe/image/Makefile`,
  `image/ipq95xx.mk`, `dts/ipq9570-sbe1v1k.dts`, `config-6.18`,
  `ipq95xx/config-default`, `patches-6.18/0301`-`0312`, `0347`-`0350`,
  `ipq95xx/base-files/`.
- Upstream: Linux v6.18 `drivers/net/phy/aquantia/*`,
  `drivers/net/wireless/ath/ath12k/{qmi,core,fw,hw,pci}.c`,
  `drivers/net/phy/qcom/qca808x.c` (no QCA8084),
  `drivers/clk/qcom/nsscc-qca8k.c` and
  `Documentation/devicetree/bindings/clock/qcom,qca8k-nsscc.yaml`,
  `scripts/mkits.sh`, U-Boot `cmd_bootqca.c`.
- QSDK: `qsdk/qca/src/u-boot-2016/`, `qsdk/qca/src/qca-ssdk/src/hsl/phy/qca8084_phy.c`,
  `qsdk/qca/src/linux-5.4/drivers/net/phy/aquantia_main.c`.
