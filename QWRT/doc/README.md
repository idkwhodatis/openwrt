# Xiaomi BE10000 modified 6 GHz port investigation

These reports cover the hardware investigation, port implementation and
validation status. The recovery runbook is listed separately below.

Read the reports in order; later reports refine earlier unknowns:

1. [Hardware/profile comparison](be10000-hardware-comparison.md)
2. [ART, device tree, and porting implications](be10000-porting-probe-2.md)
3. [Calibration caches and boot handling](be10000-porting-probe-3.md)
4. [Compared file hashes](be10000-comparison-hashes.json)
5. [BE18000 live probe 4: AQR113C, QMI IDs, ART factory BDFs, gain LUT](be18000-live-probe-4.md)
6. [BE18000 live probe 5: bootloader/FIT, PCIe, board I/O, CNSS debugfs](be18000-live-probe-5.md)
7. [BE18000 probe rounds 1-29](be18000-probe-rounds.md)
   · [Device checklist, starting with read-only SSH on QWRT](be18000-device-checklist.md)
8. [BE18000 MLO incident: reboot and slow 6G recovery](be18000-mlo-incident.md)
9. [QSDK DCS research: 6 GHz AWGN channel switch](be18000-qsdk-dcs-research.md)
10. [QSDK13 MLO auth-path research: stale-peer recovery](be18000-qsdk13-mlo-auth-research.md)
11. [BE18000 mainline OpenWrt port plan](be18000-mainline-port-plan.md)
12. [BE18000 mainline port risk research](be18000-port-risk-research.md)
13. [BE10000 vs BE18000 QWRT: 20 OpenWrt gap rounds](be10000-be18000-openwrt-gap-rounds.md)
14. [QWRT U-Boot package analysis (MAX vs v2, live match)](be18000-uboot-package-analysis.md)
15. [OpenWrt FIT vs live QWRT FIT cross-check](be18000-fit-crosscheck.md)
16. [Recovery and first-flash runbook (MAX layout)](be18000-recovery-runbook.md)
17. [No-SSH audit after the first flash: fixes and second-pass findings](be18000-no-ssh-audit.md)

The owner's router is the 6 GHz hardware conversion identified by QWRT as
`xiaomi,be18000`. Start with the [modified-unit source comparison](be10000-be18000-openwrt-gap-rounds.md#owners-modified-be10000-be18000-firmware-profile)
for the Ethernet reset and radio-profile differences between the saved
working system and the installer-supplied QSDK13 image.

## Current conclusions

- The owner has reported no SSH after flashing a factory image. PPE
  cleanup/NAPI teardown and QCA8084 startup-order fixes are on `master`
  (`c463915`, `b1522ec`) and passed actual ARM64 driver compilation against
  the fully patched Linux 6.18.64 source. A second source audit identified
  conditional ath12k and EDMA failure paths; none has yet been matched to
  a runtime log from the failed boot. See the
  [no-SSH audit](be18000-no-ssh-audit.md) for evidence, limits and stage
  discriminators. These changes need a rebuilt image for device validation.
- Phase A/B/C/D-G has an offline `qualcommbe/ipq95xx` image for
  `xiaomi,be18000`: FIT `config@al02-c4`, gzip `0x42080000`, UBI
  `kernel`/`rootfs`/`rootfs_data`, the live 292,256-byte Xiaomi board-2,
  and the live MIBIB partition table. The DTB also stages the live
  `tzapp` reservation, QCA8084 package/NSSCC, QCA8084 PHYs 1-4,
  PCS/XPCS, AQR113C and PPE ports `lan1`-`lan4`/`wan`, plus
  pcie1/2/3 QCN9224 nodes with the `_live_1/_2/_4` variants and the
  three-node WSI ring. SFP port 6 is staged disabled. Phase E
  coldboot is implemented behind `ath12k.cold_boot_cal=1` (default off)
  and still needs hardware validation. Full hashes and inspection
  output are in the
  [offline build manifest](be18000-phase-a-build-manifest.md).
  This is not yet a hardware result; serial/RAM boot, PCIe enumeration
  and PHY probe are next.
- The installed U-Boot is the exact QWRT package in `QWRT/UBoot` (MAX MIBIB,
  byte-identical to the live `0:APPSBL` prefix). The built FIT matches its
  boot contract, and `root=/dev/ubiblock0_1` comes from the DTB
  `chosen/bootargs-append` plus kernel hack 920. See the
  [U-Boot package analysis](be18000-uboot-package-analysis.md),
  [FIT cross-check](be18000-fit-crosscheck.md) and
  [recovery runbook](be18000-recovery-runbook.md).
- The custom radio mapping is PCI1/BDF1 (2.4G), PCI2/BDF2 (5G), PCI3/BDF4
  (6 GHz); PCI3 currently operates at 6135 MHz/320 MHz. The live unit was later
  moved to ch129/6595 by AWGN DCS; the port intentionally pins ch37/6135.
- ART offsets are verified. Both high-band 184,320-byte slots are erased
  (`0xFF`), not valid shared calibration records. The ART also contains factory
  BDF containers at 0x1000/0x33000/0x65000; these match the original BE10000
  profile, not the modified SKY85798 profile.
- QWRT runs cold-boot calibration. The three `/data/vendor/wifi` cache files are
  zero-filled placeholders, not calibration. Backports 7.2 ath12k does **not**
  implement the verified QSDK PCI mode-7 sequence by default; mac80211 patch
  701 adds it behind `ath12k.cold_boot_cal=1`, and its PCI path retains the DMA
  address for the requested CALDB segment across the reset. See the
  [mode and memory trace](be10000-be18000-openwrt-gap-rounds.md#pci3-mode-7-caldb-handoff-and-return-to-service)
  and [Phase E status](be18000-phase-e-coldboot.md).
  See the [PCI3 board selection and calibration trace](be10000-be18000-openwrt-gap-rounds.md#pci3-6-ghz-board-selection-and-cold-boot-calibration).
- The live 10G PHY is **Aquantia AQR113C**. `0:ETHPHYFW` is an MBN-wrapped Xiaomi
  AQR v5.6.7 firmware image loaded by U-Boot; the 0x28/0x60002 nvmem slice is
  valid. RTL8261N is not the live PHY.
- The live QCN9224 QMI IDs are `chip_id 0x0`, `board_id 0xff`, matching the
  generated board-2 entries.
- `rxgainlutSKY_6G.bin` is **not loaded** by cnss2; the loader expects
  `rxgainlut.b<boardid>`/`.bin`/`.b%02x`.
- The QSDK13 image's `ftm.conf`/`caldata_3/4` are the standard 1/4/2 mapping,
  while its DTS uses 1/2/4; the 5G/6G BDF copies are swapped relative to the
  live controllers.
- Live MLO is the stock QSDK `load_cnss2` default, not recent user work.
  MLO logs show some partner-peer failures and "WSI stats support is not enabled";
  treat it as a separate validation item.
- The live FIT is `config@al02-c4`, gzip, load/entry **0x42080000**; the QSDK13
  FIT uses the same config but lzma at **0x40000000**. The live U-Boot proves the
  config name; the load-address choice is an install test.
- The live unit has **NFC** at i2c0 0x54 (`miwifi,nfc`) and a **reset** button on
  GPIO45 (the QSDK13 DTS says wps). The SFP+ is ESS port6/PHY 0x1e/reset GPIO64,
  not a direct i2c4 EEPROM.
- PCIe links are 8 GT/s x1 for PCI1/2.4G and x2 for PCI2/PCI3; endpoint BAR0 is
  2 MiB.
- The U-Boot contains AQR/ETHPHYFW loading, a web recovery UI, QCN9224
  detect/fuse commands, and generic secure-boot strings. `qcn9224_version` is
  set by `detect_qcn9224` from the TCSR SoC HW version, not an anti-rollback
  check. Verify secure boot/anti-rollback before flashing; do not touch
  QSEE/DEVCFG/APDP.
- The installer has identified SKY85798 and RF/FEM-filter changes. Exact suffix,
  filters, component count and wiring remain unverified; see the latest report.
- The historical read-only probes did not change the router. Subsequent
  port implementation, offline builds and the post-flash audit are documented
  in the later reports linked above.

The initial report used previously extracted files. Probe 2 independently
compared the supplied factory image's embedded DTB against the live DTB, but did
not independently re-extract every supplied rootfs file.

## Installer update - 2026-11-16

[SKY85798 confirmation and QSDK13 comparison](be18000-sky85798-qsdk13.md)
supersedes the earlier unknown-FEM status and adds verified gain-table and
packaged-calibration comparisons.

[BE18000 live probe 4](be18000-live-probe-4.md) adds the live AQR113C/MBN
identification, QMI IDs, ART factory BDFs, gain-LUT non-use, and the QSDK13
caldata mapping inconsistency. Raw read-only dumps are in
`QWRT/extracted/live-be18000/`.

[BE18000 live probe 5](be18000-live-probe-5.md) adds the FIT/load-address
comparison, U-Boot/secure-boot strings, PCIe widths/BARs, NFC/reset-button/SFP
corrections, and CNSS debugfs/QMI/MLO caveats.

[BE18000 probe rounds 1-29](be18000-probe-rounds.md) is the consolidated round
log. Rounds 1-11 are live read-only probes; rounds 12-21 are offline analysis
after `10.10.10.1` became unreachable; rounds 22-29 are the MLO/reboot/DCS/
QSDK-source investigation after the router came back.

[BE18000 MLO incident](be18000-mlo-incident.md) explains the unclean reboot
(no persistent crash log), the QSDK stale-MLD-peer auth rejects, the direct-6G
probe MLDID drops, the 6G AWGN DCS channel switch from ch37 to non-PSC ch129,
and the mainline port fixes (WSI ring graph, MLO opt-in, mainline ML station
lifecycle, fixed PSC 6G channel, coldboot calibration, pstore/reset-reason
capture).

[QSDK DCS research](be18000-qsdk-dcs-research.md) adds the QSDK 12.5 source
analysis (DCS type mask, AWGN/AFC path, PCL/bandwidth-reduction algorithm) and
the key QSDK13 finding: the BE18000 image explicitly disables DCS in
`bootcount`, the generated wireless config, and `performance_configs.sh`, while
the live QSDK 12.2 image leaves it enabled.

[QSDK13 MLO auth-path research](be18000-qsdk13-mlo-auth-research.md) adds the
QSDK13 `umac.ko` finding: PMF/SAE stale peers are forwarded to hostapd (with an
active-MLO peer delete path) instead of rejected; the live QSDK 12.2 image only
has the reject path.

[BE18000 mainline OpenWrt port plan](be18000-mainline-port-plan.md) is the
implementation plan: device definition, NAND/UBI `Device/UbiFit`, live MIBIB
partitions, QCA8084/AQR113C wired networking, PCIe/WSI WiFi, board-2 and
coldboot CALDB, fixed-PSC 6G, opt-in MLO, pstore/ramoops, install/recovery and
validation matrix.

[BE18000 mainline port risk research](be18000-port-risk-research.md) audits the
plan's top risks. The two hardest items are the QCA8084 PHY/NSSCC/SerDes
wiring (the upstream `qcom,qca8084-nsscc` clock/reset driver exists and is
enabled, but the Xiaomi DTS does not instantiate it yet) and 5G/6G coldboot
calibration (the mainline driver allocates a CALDB chunk but does not use the
QSDK fixed region or coldboot INI). The [BE10000 offline wired trace](be10000-be18000-openwrt-gap-rounds.md#be10000-wired-bring-up-trace-offline-2026-11-21) corrects the earlier FIT tooling recommendation and follows the six PPE ports through QSDK and OpenWrt. The risk research also covers the QCN9224-vs-QCN9274
`firmware-2.bin` format gap, and the install/recovery caveat for a raw
`factory.ubi`.
