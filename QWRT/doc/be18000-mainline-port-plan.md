# BE18000 mainline OpenWrt port plan

Planning document, 2026-11-16. This is the implementation plan for the modified
Xiaomi BE18000 on the mainline `qualcommbe/ipq95xx` target, not a flash
procedure. The live router is not currently reachable from this PC (the PC is
disconnected; `10.10.10.1` currently presents a different LuCI host), so the
first phases are offline build/design work. Do not flash without a recovery
path and hardware access.

## 1. Objective and non-goals

**Objective:** boot mainline OpenWrt on the modified BE18000 with working
Ethernet (2.5G + 10G), 2.4/5/6 GHz WiFi, and an opt-in MLO path, while
preserving the stock boot chain and calibration partitions.

**Non-goals for the first milestone:**

- Do not replace U-Boot, MIBIB, CDT, QSEE, DEVCFG or APDP.
- Do not write blank ART/high-band calibration or zero-filled caches.
- Do not enable MLO by default before 6G and calibration are stable.
- Do not port the QSDK 12.2 DCS/random-channel behavior or the QSDK legacy MLO
  reject path.

## 2. Baseline and decisions

### Target

- `target/linux/qualcommbe`, subtarget `ipq95xx`, kernel 6.18.
- Mainline `ath12k` from `package/kernel/mac80211` (backports 7.2).
- `kmod-qcom-ppe`, `qca808x`, `qca8084`, `AQUANTIA_PHY`, NAND/UBI, SFP.
- `Device/FitImage` (gzip FIT) and `Device/UbiFit` (`kernel` in UBI +
  `rootfs`/`rootfs_data` volumes) already exist in
  `target/linux/qualcommbe/image/Makefile`.

### Closest existing reference

The mainline `qcom_rdp433` (AP-AL02-C4) is the same board family as the live
`ap-al02-c4`; use it as the starting point:

- `arch/arm64/boot/dts/qcom/ipq9574-rdp433.dts` and
  `ipq9574-rdp-common.dtsi` (kernel source).
- Target patches `0347`-`0350` add NAND partitions, QCA8075/AQR PPE ports and
  the AQR NVMEM cell. Do **not** copy the RDP433 partition table; the Xiaomi
  MIBIB layout is different.
- `ipq9570-sbe1v1k.dts` is the WSI/PCIe/LED/ART-nvmem template.
- QSDK13 `be18000-board.dts` and the live QSDK12 DT are the Xiaomi-specific
  authority for PCIe/WSI/board IDs/board I/O.

### Key decisions

| Topic | Decision |
|---|---|
| SoC | `ipq9574`, `compatible = "xiaomi,be18000", "qcom,ipq9574"` |
| Image | `Device/FitImage` + `Device/UbiFit` (`factory.ubi` + sysupgrade tar) |
| Kernel load | `0x42080000`, gzip (live working FIT); keep `config@al02-c4` |
| Rootfs | live MIBIB `rootfs` 0x1780000 size 0xbe00000 (190 MiB) |
| UBI | `kernel`, `rootfs`, `rootfs_data`; 0x20000 erase, 2048 page |
| WiFi firmware | official `ath12k-firmware-qcn9274` + Xiaomi board-2 override |
| Board-2 | live BDFs, variants `Xiaomi_BE18000_live_1/_2/_4` |
| Calibration | coldboot CALDB, no blank ART/caches |
| 6G | fixed PSC ch37/6135, no QSDK DCS |
| MLO | opt-in only after 6G/WSI/calibration pass |
| Crash capture | pstore/ramoops + watchdog sysfs |

## 3. Current target gaps

1. No `Device/xiaomi_be18000` and no Xiaomi DTS.
2. `Device/UbiFit` is defined but no device uses it; NAND/UBI install path
   needs a Xiaomi device and `platform.sh` case.
3. `ipq95xx/base-files/etc/board.d/02_network` has no Xiaomi interface/WLAN
   mapping.
4. `ipq95xx/base-files/lib/upgrade/platform.sh` has no Xiaomi NAND upgrade
   case.
5. `ipq95xx/base-files/etc/hotplug.d/firmware/11-ath12k-caldata` only handles
   sbe1v1k; Xiaomi must not extract blank high-band ART caldata.
6. No Xiaomi `ipq-wifi` package/board-2 file in the tree.
7. `ath12k` coldboot CALDB has no fixed DT region: `CALDB_MEM_REGION_TYPE`
   sets paddr=0, although the same path also allocates a DMA chunk. Whether
   the QCN9224 firmware requests CALDB and accepts a DMA paddr is unproven.
8. `config-6.18` lacks pstore/ramoops/SFP/PWM/hwmon/watchdog options needed
   for the full board.
9. QCA8084 package/PPE mapping and AQR113C firmware/NVMEM are new for this
   board; no Xiaomi validation.
10. The feed `kmod-qcom-ppe` (and possibly `kmod-hwmon-*`) must be installed;
    the target already lists `kmod-qcom-ppe` in `DEFAULT_PACKAGES`.
11. The QCA8084 PHY support (`patches-6.18/0301`-`0312`) is out-of-tree, but
    the upstream QCA8084 NSSCC clock/reset driver (`qcom,qca8084-nsscc`,
    `drivers/clk/qcom/nsscc-qca8k.c`) exists and `CONFIG_IPQ_NSSCC_QCA8K=y`
    is already set. The Xiaomi DTS does not instantiate the NSSCC node yet;
    the exact MDIO address/reference clocks/reset GPIO, package/PCS/XPCS
    clock-reset wiring, and QXGMII/SerDes remain the Phase 1 gate. The QSDK
    SSDK `qca8084_phy.c` is the sequence reference.

## 4. Work breakdown

### Phase 0: build harness and image layout (offline)

**Tasks**

1. Add `Device/xiaomi_be18000` to
   `target/linux/qualcommbe/image/ipq95xx.mk`.
2. Add `target/linux/qualcommbe/dts/ipq9574-be18000.dts` skeleton:
   model/compatible, `chosen`, reserved-memory, NAND partitions, UBI, board
   I/O, PCIe nodes (initially `status = "disabled"` for WiFi), PPE/MDIO
   (initially disabled if needed).
3. Add the Xiaomi `ipq-wifi` package/board-2 file.
4. Add kernel config options:
   `CONFIG_PSTORE=y`, `CONFIG_PSTORE_RAM=y`, `CONFIG_PSTORE_CONSOLE=y`,
   `CONFIG_SFP`/`kmod-sfp`, `CONFIG_PWM=y`, `CONFIG_HWMON=y`,
   `CONFIG_QCOM_WDT=y`, `CONFIG_WATCHDOG_SYSFS=y`,
   `CONFIG_SENSORS_EMC2305`/`kmod-hwmon-*`, `CONFIG_LEDS_PWM`/`kmod-leds-pwm`.
5. Build and inspect the image only:
   - `factory.ubi` must contain `kernel`, `rootfs`, `rootfs_data`.
   - FIT must have `config@al02-c4`, load/entry 0x42080000, gzip, and a FIT
     root `append-bootargs` containing `root=/dev/ubiblock0_1`. OpenWrt
     `mkits.sh` does not add this; the live runtime DT gets it from the QSDK
     `chosen/bootargs-append`, which mainline does not consume.
   - board-2 must be the Xiaomi file; firmware files must be present.

**Device definition draft**

```make
define Device/xiaomi_be18000
	$(call Device/FitImage)
	$(call Device/UbiFit)
	DEVICE_VENDOR := Xiaomi
	DEVICE_MODEL := BE18000
	DEVICE_VARIANT := Pro Max
	DEVICE_DTS := ipq9574-be18000
	DEVICE_DTS_CONFIG := config@al02-c4
	DEVICE_DTS_DIR := ../dts
	KERNEL_LOADADDR := 0x42080000
	SOC := ipq9574
	BLOCKSIZE := 0x20000
	PAGESIZE := 2048
	SUBPAGESIZE := 2048
	VID_HDR_OFFSET := 2048
	IMAGE_SIZE := 0xbe00000
	DEVICE_PACKAGES := ath12k-firmware-qcn9274 ipq-wifi-xiaomi_be18000 \
		kmod-ath12k kmod-qcom-ppe kmod-sfp kmod-hwmon-pwmfan \
		kmod-hwmon-emc2305 kmod-hwmon-lm63 kmod-leds-pwm
endef
TARGET_DEVICES += xiaomi_be18000
```

**Acceptance:** image builds for `ipq95xx`; `dumpimage -l` shows the FIT
config; `ubinize`/`ubinfo` inspection shows the three volumes; no hardware
writes.

### Phase 1: boot, UBI, wired networking

**Tasks**

1. NAND partition table exactly matching the live MIBIB (not RDP433):
   SBL1/MIBIB/BOOTCONFIG/QSEE/DEVCFG/APDP/TME/RPM/CDT/APPSBLENV/APPSBL/ART/
   ETHPHYFW/TRAINING/LICENSE/rootfs/bdata/crash/crash_syslog.
2. `0:ART` nvmem layout with `ethaddr@0` (`mac-base`) and `0:ETHPHYFW`
   nvmem `aqr_fw@28` size 0x60002.
3. `&qpic_nand` status okay, ECC 4/512; `Device/UbiFit`.
4. PCIe controllers and PERST GPIOs 26/29/23, lanes 1/2/2; WiFi children
   initially disabled.
5. `&qcom_ppe` ports, `&mdio` QCA8084 package (PHYs 1-4, package mode 0 or the
   mode that enumerates all four 2.5G ports), the `qcom,qca8084-nsscc`
   clock/reset controller at the QCA8084 MDIO address (0x18 example), AQR113C
   at MDIO 0 (C45, NVMEM firmware), SFP at 0x1e/reset GPIO64 initially
   disabled.
6. `02_network`: Xiaomi LAN/WAN mapping; `platform.sh`: `CI_KERNPART=kernel`,
   `CI_ROOTPART=rootfs`, `nand_do_upgrade`.
7. Build `factory.ubi`; install via U-Boot web recovery or TFTP only after
   preserving ART/ETHPHYFW/APPSBL/MIBIB. Keep a serial console at 115200.
8. Validate: boot to OpenWrt, UBI volumes, MACs, 4x2.5G, WAN, 10G AQR; LEDs,
   buttons, fan.

**Acceptance:** serial boot, rootfs on UBI, wired LAN/WAN/10G links, no
unexpected writes to bootloader/ART/ETHPHYFW.

### Phase 2: PCIe WiFi, 2.4G and 5G

**Tasks**

1. Enable `&pcie1`/`&pcie2` (2.4G/5G) with `wifi@0` children:
   `compatible = "pci17cb,1109"`, `qcom,calibration-variant` live variants,
   `qcom,wsi-controller` on 5G, WSI ring ports.
2. Add `memory-region` for the 50 MiB QCN9224 reserved regions. The live QSDK
   caldb is 8 MiB at offset 0x1e00000 (`0x52d00000`, `0x55f00000`,
   `0x59100000`); decide between the QSDK `qcom,caldb-addr`/`size` fixed
   region and the driver's existing DMA CALDB allocation after seeing the
   firmware request.
3. Add the Xiaomi board-2 to `ath12k/QCN9274/hw2.0/board-2.bin`; verify the
   selected variant in dmesg.
4. Treat the coldboot CALDB patch as conditional (Phase 2 or 3): the mainline
   driver already allocates a DMA chunk for `CALDB_MEM_REGION_TYPE`, but it
   sets the fixed-memory paddr to 0 and does not use the QSDK reserved
   region. First test whether the official QCN9274 `firmware-2.bin` requests
   CALDB; if it does not, implement the fixed `qcom,caldb-addr` path and/or a
   QCN9224 firmware/INI path.
5. Do **not** add high-band `cal-pci-*` extraction from blank ART; test whether
   ath12k proceeds with coldboot CALDB. 2.4G may use the live BDF/ART path only
   if its calibration is valid.
6. The official QCN9274 firmware is `firmware-2.bin` (AMSS/M3 IEs), not the
   QSDK13 QCN9224 `amss.bin`/`m3.bin`. Test the official file first; a
   `firmware-2.bin` wrapper around the QCN9224 AMSS/M3 is a fallback, not a
   drop-in copy.
6. Validate 2.4G AP first, then 5G; check QMI target capability, BDF download,
   board-2 variant, txpower, rates.

**Acceptance:** 2.4G and 5G APs up; clients associate; sane txpower/rates;
coldboot calibration succeeds; no missing-caldata probe failure.

### Phase 3: 6G, calibration, WSI, MLO

**Tasks**

1. Enable `&pcie3` (6G, PERST GPIO23, lanes 2), 6G board-2 variant
   `Xiaomi_BE18000_live_4`, 320 MHz on PSC ch37/6135.
2. Keep QSDK DCS off; no random channel selection. Fixed PSC channel.
3. Validate 6E-only client, 6G AP, txpower, rates; compare with the live
   `6135 MHz/320 MHz` baseline.
4. Enable WSI ring graph (2.4G -> 5G -> 6G -> 2.4G, controller on 5G); verify
   `ath12k_core_get_wsi_index` 2/0/1 and `WSI stats` messages.
5. Test MLO 5G+6G as opt-in only; PMF/SAE client; direct 6G probe; 6G link
   drop/re-add; full MLD disconnect/reconnect. Do not copy QSDK 12.2 reject
   behavior; mainline ath12k removes link peers.
6. Add pstore/ramoops, watchdog, persistent logs; 24h stability.

**Acceptance:** 6G AP + 6E client, MLO opt-in client, 6G link recovery, no DCS
channel switch, stable 24h with pstore capture.

### Phase 4: SFP, AQR, board I/O, upgrade

**Tasks**

1. SFP+ port 6: `sfp` node / PHY 0x1e / reset GPIO64; validate module detect
   and 1G/10G.
2. AQR113C firmware: U-Boot `0:ETHPHYFW` NVMEM `aqr_fw@28`; confirm the PHY
   loads the Xiaomi payload; fallback package the extracted Xiaomi cld only if
   the PHY resets and needs Linux reload.
3. NFC optional node (`miwifi,nfc` at i2c0 0x54); LM63/EMC2301 fan; RGB
   PWM3/2/1; sys/net/SFP LEDs; reset/mesh buttons.
4. sysupgrade path: `nand_do_upgrade` with `kernel`/`rootfs`; factory.ubi
   recovery; config preservation; verify bootloader FIT/UBI compatibility.
5. Power/thermal stress, reboot-cause capture, final validation matrix.

**Acceptance:** all ports, SFP, board I/O, sysupgrade/recovery, 24h stability.

## 5. DTS outline

Use `ipq9574.dtsi` and copy the RDP433/sbe1v1k nodes; do not include the
RDP433 reference partition table.

```
/ {
    model = "Xiaomi BE18000";
    compatible = "xiaomi,be18000", "qcom,ipq9574";
    aliases { serial0 = &blsp1_uart2; ... };
    chosen { stdout-path = "serial0:115200n8"; };
    reserved-memory {
        /* QCN9224 50MiB regions: 0x50f00000, 0x54100000, 0x57300000 */
        /* q6_etr_dump, tzapp, optional ramoops (verify /proc/iomem) */
    };
};

&qpic_nand {
    status = "okay";
    nand-ecc-strength = <4>;
    nand-ecc-step-size = <512>;
    partitions { /* live MIBIB table */ };
};

&qcom_ppe { /* QCA8084 ports 1-4, AQR113C port 5, SFP port 6 */ };
&mdio {
    /* QCA8084 package @1: PHYs 1-4, PCS 6/7; qca8084-nsscc @0x18 clock/reset */
    /* AQR113C @0 C45, nvmem firmware */
    /* SFP PHY @0x1e, reset GPIO64 */
};

&pcie1 { perst-gpios = <&tlmm 26 ...>; num-lanes = <1>; wifi@0 { ... WSI ... }; };
&pcie2 { perst-gpios = <&tlmm 29 ...>; num-lanes = <2>; wifi@0 { qcom,wsi-controller; ... }; };
&pcie3 { perst-gpios = <&tlmm 23 ...>; num-lanes = <2>; wifi@0 { ... WSI ... }; };

&tlmm { /* PCIe PERST, LEDs, buttons, SFP reset, fan/NFC pinctrl */ };
/* gpio-keys mesh GPIO44/reset GPIO45 */
/* leds-gpio sys 40/41, net 42/43, sfp 62 */
/* pwm-leds red PWM3, green PWM2, blue PWM1, period 51000 */
/* i2c0 nfc@54; i2c1 lm63@4c, emc2301@2f, pwm-fan */
```

## 6. Firmware, board-2 and calibration

### Firmware

- `ath12k-firmware-qcn9274` is provided by
  `package/firmware/linux-firmware/qca_ath12k.mk` and installs
  `ath12k/QCN9274/hw2.0/*`.
- Test the official QCN9274 firmware with the QCN9224 endpoints. If it is
  incompatible, fall back to the QSDK13 `amss.bin`/`m3.bin` (WBE.1.5) only
  after checking the mainline ath12k API/board-2 compatibility.
- Do not use QSDK `caldata_2/3/4` as calibration; they are BDF copies.

### Board-2

- Use `board-live-be18000.qcn9274` (live BDFs + live regdb) as the candidate.
- Variants: `Xiaomi_BE18000_live_1` (2.4G), `_live_2` (5G), `_live_4` (6G).
- Add a local `ipq-wifi-xiaomi_be18000` package/file; install to
  `/lib/firmware/ath12k/QCN9274/hw2.0/board-2.bin`.
- Verify the final image's board-2 hash; the official firmware package also
  installs a board-2 and must not win.

### Calibration

- 2.4G: live BDF/ART may be usable; test.
- 5G/6G: high-band ART blank; use coldboot CALDB:
  - reserve the three 50 MiB QCN9224 regions;
  - add `qcom,caldb-offset = <0x1e00000>` (8 MiB caldb inside each region);
  - patch ath12k `CALDB_MEM_REGION_TYPE` to use the host region base + offset
    instead of 0.
- Do not install blank ART slices, zero cache files, or the unused 6G gain LUT.

## 7. Install and recovery

1. Preserve `0:ART`, `0:ETHPHYFW`, `0:APPSBL`, `0:MIBIB`, `0:CDT`,
   `0:QSEE`, `0:DEVCFG`, `0:APDP`.
2. Build `factory.ubi` with `kernel`/`rootfs`/`rootfs_data`; write only the
   `rootfs` mtd partition (mtd24, 0xbe00000) via U-Boot web recovery/TFTP or
   `ubiformat` from a recovery initramfs.
3. Keep a serial console at 115200 and the U-Boot web recovery as the fallback.
4. FIT: `config@al02-c4`, gzip, load/entry 0x42080000. If the stock U-Boot
   rejects it, test 0x42200000/lzma only as a separate change.
5. `sysupgrade`: add a Xiaomi `platform_do_upgrade` case with
   `CI_KERNPART="kernel"`, `CI_ROOTPART="rootfs"`, `nand_do_upgrade`.
6. UBI parameters: 0x20000 erase, 2048 page/subpage, VID header 2048; verify
   against the stock live UBI before first write.

## 8. Validation matrix

| Area | Test | Pass criteria |
|---|---|---|
| Boot | serial, UBI attach, rootfs | OpenWrt login, 3 UBI volumes |
| NAND | `ubiattach`/`ubinfo`, MACs | no ECC/UBI errors; MACs match live |
| Ethernet | 4x2.5G, WAN, 10G AQR | link + DHCP + throughput |
| SFP | module detect, 1G/10G | link, EEPROM/`ethtool -m` as applicable |
| 2.4G | AP, client | BDF variant, txpower, association |
| 5G | AP, client | BDF variant, 160 MHz, association |
| 6G | AP, 6E client | ch37/6135 320 MHz, txpower, association |
| MLO | 5G+6G client, link drop | opt-in, PMF/SAE, recovery, no stale reject |
| Calibration | coldboot CALDB | per-radio cal success, sane txpower/rates |
| Board I/O | LEDs, buttons, fan, NFC | all match live behavior |
| Stability | 24h, pstore | no reboot, captured logs if any |
| Upgrade | factory.ubi, sysupgrade | recovery path works; config preserved |

## 9. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| **QCA8084 external package NSSCC/SerDes** | **no 2.5G ports** | instantiate the upstream `qcom,qca8084-nsscc` MDIO clock/reset controller (0x18 example, reference clocks, reset GPIO60), wire the package/per-PHY/PCS/XPCS phandles, validate 10G-QXGMII; AQR/10G first |
| QCA8084 package mode/PPE mapping | wrong port/PCS mapping | use 10G-QXGMII package mode 0, `pcs0_ch0..3`, live MDIO 1-4; test 2.5G |
| AQR113C firmware/MBN | no 10G | use `0:ETHPHYFW` NVMEM `aqr_fw@28`/0x60002; mainline driver validates the payload; U-Boot already loads it |
| High-band calibration | no 5G/6G | coldboot CALDB; do not use blank ART; test whether firmware requests CALDB before adding a fixed region patch |
| QCN9224 vs QCN9274 firmware | WiFi probe fail | official QCN9274 `firmware-2.bin` first; wrap QSDK13 QCN9224 AMSS/M3 only as a fallback |
| U-Boot FIT/UBI | no boot / no rootfs | live 0x42080000/gzip/config@al02-c4 **and** FIT `append-bootargs` for `root=/dev/ubiblock0_1`; web recovery |
| NAND/UBI params | corrupt rootfs | verify stock UBI; back up ART/ETHPHYFW; recovery initramfs + `ubiformat` |
| Install path | bricked rootfs | do not assume the web recovery accepts raw `factory.ubi`; use serial/TFTP recovery initramfs |
| SFP port 6 | no SFP | defer; `sfp` node/PHY 0x1e/reset GPIO64/`pcs2_ch0` |
| MLO/WSI | slow 6G recovery | opt-in; sbe1v1k WSI graph; fixed PSC; mainline ath12k lifecycle; test |
| Secure boot/DPR | image rejected | verify fuse status before flashing; preserve QSEE/DEVCFG/APDP |

## 10. Immediate next actions

1. Read `QWRT/doc/be18000-port-risk-research.md` first; it changes the
   QCA8084 and CALDB assumptions.
2. Create `Device/xiaomi_be18000` and the DTS skeleton; build offline.
3. Add the local `ipq-wifi-xiaomi_be18000` board-2 package and verify the
   image's `board-2.bin` hash.
4. Add the FIT `append-bootargs` handling, the config options, and the
   conditional coldboot CALDB patch draft.
5. Add the Xiaomi `02_network`/`platform.sh` cases.
6. Prepare the U-Boot recovery/serial procedure and a recovery initramfs with
   `ubiformat`; do not rely on the web recovery for a raw `factory.ubi`.
7. Only after hardware access returns: validate AQR/10G and the QCA8084
   package probe first, then 2.4G/5G, then 6G/MLO.

## 11. References

- `QWRT/doc/be18000-port-risk-research.md` (risk audit and evidence)
- `QWRT/doc/be18000-live-probe-4.md`, `be18000-live-probe-5.md`
- `QWRT/doc/be18000-probe-rounds.md`
- `QWRT/doc/be18000-mlo-incident.md`
- `QWRT/doc/be18000-qsdk-dcs-research.md`
- `QWRT/doc/be18000-qsdk13-mlo-auth-research.md`
- `target/linux/qualcommbe/image/ipq95xx.mk`
- `target/linux/qualcommbe/dts/ipq9570-sbe1v1k.dts`
- `target/linux/qualcommbe/patches-6.18/0347..0350`
- `package/firmware/linux-firmware/qca_ath12k.mk`
- `package/firmware/ipq-wifi/Makefile`

## 12. Granular research cycles (20 cycles)

This section is the cycle log for the 20-cycle research pass. Each cycle has
three steps: (1) probe OpenWrt and QWRT, (2) probe OpenWrt against QSDK or
other tools/binaries, (3) record the plan delta and commit the plan. The
earlier sections remain the implementation plan; the cycle log supplies the
granular evidence and corrections.

### Cycle 1: Board identity and device naming

**Step 1 — OpenWrt + QWRT probe**

- OpenWrt DTS convention in this target is `model = "<vendor> <board>"` and
  `compatible = "<vendor>,<board>", "qcom,ipq9574"`:
  `ipq9570-sbe1v1k.dts` has `Askey SBE1V1K` / `askey,sbe1v1k`,
  `ipq9570-kiwi-dvk.dts` has `8devices Kiwi-DVK` / `8devices,kiwi-dvk`,
  `ipq9554-linksys-ln6001.dts` has `Linksys LN6001` /
  `linksys,ln6001`.
- The live QWRT root is:
  `model = "Xiaomi Router BE18000 Pro Max (Wi-Fi 7 320Mhz)"`;
  `compatible = "xiaomi,be18000", "qcom,ipq9574-ap-al02-c4",
  "qcom,ipq9574-al02", "qcom,ipq9574"`.
- The QSDK13 root is:
  `model = "Xiaomi Router BE18000 ( Wi-Fi 7 320MHZ )"`;
  `compatible = "xiaomi,be18000", "qcom,ipq9574-ap-al02-c4",
  "qcom,ipq9574"`.

**Step 2 — OpenWrt vs QSDK/U-Boot identity**

- Live `0:APPSBLENV` has `model=RC01`, `machid=8050301`,
  `bootcmd=bootipq`, `soc_version_major=1`, `soc_version_minor=1`,
  `flash_type=11`. The U-Boot model is a manufacturing code, not the Linux
  model string; do not use `RC01` for `board_name`.
- OpenWrt `board_name` is derived from the first DTS compatible. The scripts
  must use `xiaomi,be18000`, not the QSDK model or `RC01`.
- `DEVICE_DTS` must be `ipq9574-be18000`, `SOC` `ipq9574`, and
  `DEVICE_DTS_CONFIG` `config@al02-c4`; the live FIT config is
  `config@al02-c4`, not the target default `config@1`.

**Step 3 — Plan delta**

- Fix the DTS root identity to:
  `model = "Xiaomi BE18000";`
  `compatible = "xiaomi,be18000", "qcom,ipq9574-ap-al02-c4", "qcom,ipq9574";`
  The AP-AL02-C4 string is retained for board-family matching; the first
  string is the OpenWrt board name.
- Fix `DEVICE_VENDOR := Xiaomi`, `DEVICE_MODEL := BE18000`,
  `DEVICE_VARIANT := Pro Max`, `DEVICE_DTS := ipq9574-be18000`,
  `DEVICE_DTS_CONFIG := config@al02-c4`, `SOC := ipq9574`.
- Use `xiaomi,be18000` in `02_network`, `platform.sh`, `11-ath12k-caldata`,
  and any board-specific hotplug/uci-defaults case.
- Do not use `RC01`, `machid=8050301`, or the QSDK model string as a board
  key. They are bootloader/manufacturing identifiers only.

### Cycle 2: Reserved memory, caldb, and MLO regions

**Step 1 — OpenWrt + QWRT probe**

- OpenWrt `ipq9570-sbe1v1k.dts` has only a `tzapp` reserved-memory node and
  no WiFi `memory-region`; its `wifi@0` nodes only set
  `qcom,calibration-variant` and the 5G `qcom,wsi-controller`. There is no
  existing Xiaomi-style 50 MiB reservation in the target.
- The target's ath12k patches contain no `memory-region` or `caldb`
  properties; patch 105 only assigns `device_id` from the WSI index, 109
  adds `qcom,split-phy`, and 700 reads `qcom,calibration-variant`.
- The live QWRT DT reserves `qcn9224_pcie1@50f00000`,
  `qcn9224_pcie2@54100000`, and `qcn9224_pcie3@57300000`, each
  `0x3200000` (50 MiB), `no-map`; the disabled `qcn9224_pcie0@4dd00000`
  is the same size. It also has `m3_dump@4d600000` (`0x100000`),
  `q6_etr_dump@1` at 0x4d700000 (`0x100000`), and a disabled
  `q6_caldb_region@4d800000` (`0x500000`).

**Step 2 — OpenWrt vs QSDK13/QCN9224.ini**

- QSDK13 uses the same 50 MiB regions and adds absolute caldb addresses:
  `0x52d00000`, `0x55f00000`, `0x59100000`, each `0x800000` (8 MiB).
  These are exactly `region_base + 0x1e00000` (30 MiB).
- `QCN9224.ini` sets `enable_mlo=1`, `max_ml_peer_count=145`,
  `max_mlo_links=3`, `mlo_mem_size=0x1200000` (18 MiB). The 50 MiB region
  has room for 18 MiB MLO plus 8 MiB caldb at +30 MiB; the live DT does not
  state the MLO offset, so the driver/QMI request must confirm it.
- QSDK13 `memory-region = <0x20 0x21>` for wifi1, `<0x25 0x26>` for wifi3,
  `<0x29 0x2a>` for wifi2: index 0 is the per-radio 50 MiB region, index 1
  is a second phandle (a `dma_pool` in QSDK, not necessarily `m3_dump`).
  Mainline ath12k uses index 0 for HOST_DDR/BDF and index 1 for M3 dump, so
  the second phandle must be chosen deliberately, not copied by number.

**Step 3 — Plan delta**

- Add the three active 50 MiB reserved-memory nodes with `no-map`, size
  `0x3200000`; keep the disabled `qcn9224_pcie0` out of the active map (or
  include it with `status = "disabled"`). Keep `m3_dump`/`q6_etr_dump`
  available for the mainline `M3_DUMP` index.
- For each `wifi@0`: `memory-region = <&qcn9224_pcieN>, <&m3_dump>;`.
  Index 0 is the 50 MiB HOST_DDR/BDF region; index 1 is the M3 dump. Do not
  use the QSDK `dma_pool` phandle blindly; verify the QMI request types.
- Add `qcom,caldb-addr = <0x52d00000>` / `<0x55f00000>` / `<0x59100000>`
  and `qcom,caldb-size = <0x800000>` to wifi1/wifi2/wifi3 respectively, or
  a `qcom,caldb-offset = <0x1e00000>` if the driver patch is written
  relative to the 50 MiB base. The absolute form matches QSDK13.
- Do not use `q6_caldb_region@4d800000` (0x500000); it is the disabled
  integrated-WiFi caldb, not the QCN9224 caldb.
- Treat the 18 MiB `mlo_mem_size` as a QMI/MLO reservation inside the 50 MiB
  region; the exact offset is a validation item, not a fixed DT value yet.

### Cycle 3: NAND, MIBIB, UBI geometry, and volumes

**Step 1 — OpenWrt + QWRT probe**

- OpenWrt `Device/UbiFit` is defined at
  `target/linux/qualcommbe/image/Makefile:33-37`: `KERNEL_IN_UBI := 1`,
  `IMAGES += factory.ubi`, `IMAGE/factory.ubi := append-ubi`. No current
  device uses it.
- `scripts/ubinize-image.sh` emits a `kernel` volume, a `rootfs` volume, and
  a `rootfs_data` volume with `vol_flags=autoresize`; the kernel volume is
  only created when `--kernel` is passed (i.e. `KERNEL_IN_UBI=1`).
- OpenWrt config has `CONFIG_MTD_NAND_QCOM=y`, `CONFIG_MTD_RAW_NAND=y`,
  `CONFIG_MTD_UBI=y`, `CONFIG_MTD_UBI_BLOCK=y`, `CONFIG_UBIFS_FS=y`,
  `CONFIG_UBIFS_FS_ADVANCED_COMPR=y`.
- The live `mibib.bin` (28 entries, magic `0x55ee73aa`/`0xe35ebddb`,
  version 4, entry size 28) and the live DT partition nodes agree exactly.
  The live UBI has 1,520 LEBs of 126,976 bytes: `kernel` 44 LEB,
  `rootfs` 407 LEB, `rootfs_data` 1,025 LEB. NAND is QPIC, ECC 4/512,
  8-bit, with `qcom,training_offset = <0x16c0000>`.

**Step 2 — OpenWrt vs QSDK13/U-Boot**

- QSDK13 does not carry a separate NAND partition table in
  `be18000-board.dts`; it relies on the bootloader/MIBIB. The live DT and
  `mibib.bin` are therefore the only authoritative partition source.
- U-Boot `bootipq` reads the FIT from the UBI `kernel` volume inside the
  `rootfs` mtd partition (`ubi part fs && ubi read ... kernel`). The live
  U-Boot strings confirm `ubi part fs` and `ubi read 0x%x kernel`.
- The `rootfs` mtd partition is 190 MiB but the live rootfs UBI volume is
  49.2 MiB; sysupgrade removes/recreates the volumes and resizes them, so
  the factory image must not assume the live 49.2 MiB volume size.

**Step 3 — Plan delta**

- Use exactly this live MIBIB table (offset/size):

| MTD | Offset | Size |
|---|---:|---:|
| `0:SBL1` | 0x0 | 0x180000 |
| `0:SBL1_1` | 0x180000 | 0x180000 |
| `0:MIBIB` | 0x300000 | 0x100000 |
| `0:BOOTCONFIG` | 0x400000 | 0x80000 |
| `0:BOOTCONFIG1` | 0x480000 | 0x80000 |
| `0:QSEE` | 0x500000 | 0x380000 |
| `0:QSEE_1` | 0x880000 | 0x380000 |
| `0:DEVCFG` | 0xc00000 | 0x80000 |
| `0:DEVCFG_1` | 0xc80000 | 0x80000 |
| `0:APDP` | 0xd00000 | 0x80000 |
| `0:APDP_1` | 0xd80000 | 0x80000 |
| `0:TME` | 0xe00000 | 0x80000 |
| `0:TME_1` | 0xe80000 | 0x80000 |
| `0:RPM` | 0xf00000 | 0x80000 |
| `0:RPM_1` | 0xf80000 | 0x80000 |
| `0:CDT` | 0x1000000 | 0x80000 |
| `0:CDT_1` | 0x1080000 | 0x80000 |
| `0:APPSBLENV` | 0x1100000 | 0x80000 |
| `0:APPSBL` | 0x1180000 | 0x180000 |
| `0:APPSBL_1` | 0x1300000 | 0x180000 |
| `0:ART` | 0x1480000 | 0x140000 |
| `0:ETHPHYFW` | 0x15c0000 | 0x100000 |
| `0:TRAINING` | 0x16c0000 | 0x80000 |
| `0:LICENSE` | 0x1740000 | 0x40000 |
| `rootfs` | 0x1780000 | 0xbe00000 |
| `bdata` | 0xd580000 | 0x40000 |
| `crash` | 0xd5c0000 | 0x40000 |
| `crash_syslog` | 0xd600000 | 0x40000 |

- Use `BLOCKSIZE=0x20000`, `PAGESIZE=2048`, `SUBPAGESIZE=2048`,
  `VID_HDR_OFFSET=2048`, `IMAGE_SIZE=0xbe00000`, `KERNEL_IN_UBI=1`; the
  factory image must contain `kernel`, `rootfs`, `rootfs_data`.
- Add `platform.sh` Xiaomi case with `CI_KERNPART="kernel"`,
  `CI_ROOTPART="rootfs"`, `CI_DATAPART="rootfs_data"`, `nand_do_upgrade`.
- Do not copy the RDP433 partition patch `0348`; the Xiaomi MIBIB table is
  different. Do not write `0:SBL1`, `0:MIBIB`, `0:APPSBL`, `0:CDT`,
  `0:QSEE`, `0:DEVCFG`, `0:APDP`, `0:ART`, or `0:ETHPHYFW`.

### Cycle 4: FIT build, config, load address, and rootfs bootargs

**Step 1 — OpenWrt + QWRT probe**

- `Build/fit-its` invokes `scripts/mkits.sh` with `-C`, `-a`, `-e`, `-c`
  and the kernel/DTB; `mkits.sh` emits `configurations { default = ...; }`,
  the kernel `compression/load/entry`, and the DTB node. It has **no**
  `append-bootargs` option and does not emit the property.
- The live FIT root contains only `timestamp`, `description`,
  `#address-cells`, and `/configurations default = "config@al02-c4"`.
  It has no `append-bootargs`.
- The live runtime `/sys/firmware/fdt` `chosen` node has
  `bootargs = "... root=mtd:ubi_rootfs ... rootwait ..."` and
  `bootargs-append = " root=/dev/ubiblock0_1 ..."`.
- The live FIT `kernel@1` is gzip, load/entry `0x42080000`; `fdt@1` is
  `xiaomi_be18000`; the config is `config@al02-c4`.
- QSDK13 has the same `chosen/bootargs-append = " root=/dev/ubiblock0_1
  cnss2.enable_mlo_support=1 swiotlb=1 coherent_pool=2M"`.

**Step 2 — U-Boot path**

- U-Boot defines `FIT_BOOTARGS_PROP "append-bootargs"`.
  `update_bootargs()` reads that property from the FIT root; if present it
  appends it to the env `bootargs` (+ `rootwait`), otherwise it appends
  `fsbootargs`.
- The live env `fsbootargs` is
  `ubi.mtd=rootfs root=mtd:ubi_rootfs rootfstype=squashfs
  cnss2.enable_mlo_support=1` and does **not** contain
  `root=/dev/ubiblock0_1`. The live ubiblock arg comes from the QSDK
  `bootargs-append` consumer, not from the OpenWrt FIT root.
- `do_bootipq()` checks the QFPROM secure-boot fuse: fuse clear =>
  `do_boot_unsignedimg()`; fuse set => `do_boot_signedimg()` and
  `qca_scm_auth_kernel()`. The live plain FIT boots through the unsigned
  path.

**Step 3 — Plan delta**

- Extend `Build/fit-its`/`mkits.sh` with a device variable such as
  `DEVICE_FIT_APPEND_BOOTARGS` (or a `-b` option) that emits
  `append-bootargs = " root=/dev/ubiblock0_1";` at the FIT root. Add
  `swiotlb=1 coherent_pool=2M` only if the mainline kernel needs them; omit
  `cnss2.*`.
- Do not rely on `chosen/bootargs-append`: it is a QSDK-side property and
  mainline does not consume it. A DTB `chosen` property is not the FIT root
  `append-bootargs`.
- Keep `DEVICE_DTS_CONFIG := config@al02-c4`, gzip, `0x42080000`, and the
  live FIT `kernel@1`/`fdt@1` node names. If config selection fails in a
  test, set the U-Boot env `config_name=config@al02-c4` as a debug step.
- Before flashing, read the secure-boot fuse status in the U-Boot console;
  do not flash an unsigned mainline FIT on a fuse-set unit.
- `CONFIG_MTD_UBI_BLOCK=y` is required for the `ubiblock0_1` rootfs path; it
  is already present in `config-6.18`.

### Cycle 5: QCA8084 package and NSSCC clock/reset

**Step 1 — OpenWrt + QWRT probe**

- Target binding `0301` defines the QCA8084 package at `ethernet-phy-package@1`
  with `qcom,package-mode = <QCA808X_PCS1_10G_QXGMII_PCS0_UNUNSED>`
  (= 0), `qcom,phy-addr-fixup = <1 2 3 4 5 6 7>`, per-PHY clocks/resets for
  PHY0-PHY3, `pcs-phy@6`, and `xpcs-phy@7`.
- Target `0306` `qca8084_probe()` requires a per-PHY unnamed clock
  (`devm_clk_get_enabled`) and a per-PHY reset
  (`devm_reset_control_get_exclusive`). Target `0307` requires package clocks
  by name and a package reset. Target `0310` requires PCS/XPCS resets and
  clocks, including per-channel XPCS clock arrays.
- `ipq95xx/config-default` already enables `CONFIG_IPQ_NSSCC_QCA8K=y` and
  `CONFIG_NET_DSA_QCA8K=y`.
- The live MDIO bus is at `90000` with `phy-reset-gpio = <&tlmm 60>`,
  `phyaddr_fixup = <0xc90f018>`, `uniphyaddr_fixup = <0xc90f014>`, and
  QCA8084 PHYs at addresses 1-4. The live driver uses `sgmii` (QSDK12) or
  `qusgmii` (QSDK13) for the four ports.

**Step 2 — OpenWrt vs QSDK SSDK/upstream**

- Upstream v6.18 has `drivers/clk/qcom/nsscc-qca8k.c` with compatible
  `qcom,qca8084-nsscc`; the binding title is "QCA8386/QCA8084" and the
  example is `clock-controller@18` with `reset-gpios`. The clock/reset IDs
  include `NSS_CC_GEPHY0_SYS_CLK`, `NSS_CC_GEPHY0_SYS_ARES`,
  `NSS_CC_GEPHY_FULL_ARES`, `NSS_CC_SRDS1_SYS_CLK`, `NSS_CC_XPCS_ARES`.
- The QSDK SSDK `qca8084_phy.c` uses the equivalent MHT/GCC programming:
  `ssdk_mht_gcc_clock_init(dev_id, MHT_PHY_UQXGMII_MODE, 0)`,
  `ssdk_mht_pinctrl_init`, `mht_port_speed_clock_set`,
  `mht_uniphy_xpcs_speed_set`, and `ssdk_mht_port_clk_reset`. That is the
  sequence reference for the external package.
- The upstream NSSCC driver is an MDIO device; the QCA8084 package node's
  clocks/resets can be wired to it. Without that node, the target
  `qca8084_probe`/PCS/XPCS probes fail with `-ENOENT`.

**Step 3 — Plan delta**

Add the following `&mdio` shape (addresses/clock IDs from the binding
example; verify the NSSCC address and reference-clock wiring against the
QSDK SSDK):

```dts
&mdio {
	#address-cells = <1>;
	#size-cells = <0>;
	reset-gpios = <&tlmm 60 GPIO_ACTIVE_LOW>;
	clock-frequency = <6250000>;

	qca8084_nsscc: clock-controller@18 {
		compatible = "qcom,qca8084-nsscc";
		reg = <0x18>;
		reset-gpios = <&tlmm 60 GPIO_ACTIVE_LOW>;
		clocks = <&pcs0_pll>, <&qca8k_uniphy0_rx>,
			 <&qca8k_uniphy0_tx>, <&qca8k_uniphy1_rx>,
			 <&qca8k_uniphy1_tx>, <&qca8k_uniphy1_rx312p5m>,
			 <&qca8k_uniphy1_tx312p5m>;
		#clock-cells = <1>;
		#reset-cells = <1>;
		#power-domain-cells = <1>;
	};

	ethernet-phy-package@1 {
		compatible = "qcom,qca8084-package";
		reg = <1>;
		#address-cells = <1>;
		#size-cells = <0>;
		qcom,package-mode = <QCA808X_PCS1_10G_QXGMII_PCS0_UNUNSED>;
		qcom,phy-addr-fixup = <1 2 3 4 5 6 7>;
		clocks = <&qca8084_nsscc NSS_CC_APB_BRIDGE_CLK>,
			 <&qca8084_nsscc NSS_CC_AHB_CLK>,
			 <&qca8084_nsscc NSS_CC_SEC_CTRL_AHB_CLK>,
			 <&qca8084_nsscc NSS_CC_TLMM_CLK>,
			 <&qca8084_nsscc NSS_CC_TLMM_AHB_CLK>,
			 <&qca8084_nsscc NSS_CC_CNOC_AHB_CLK>,
			 <&qca8084_nsscc NSS_CC_MDIO_AHB_CLK>;
		clock-names = "apb_bridge", "ahb", "sec_ctrl_ahb", "tlmm",
			      "tlmm_ahb", "cnoc_ahb", "mdio_ahb";
		resets = <&qca8084_nsscc NSS_CC_GEPHY_FULL_ARES>;

		ethernet-phy@1 {
			compatible = "ethernet-phy-id004d.d180";
			reg = <1>;
			clocks = <&qca8084_nsscc NSS_CC_GEPHY0_SYS_CLK>;
			resets = <&qca8084_nsscc NSS_CC_GEPHY0_SYS_ARES>;
			qcom,xpcs-channel = <0>;
		};
		/* PHY@2/3/4 use GEPHY1/2/3 and channels 1/2/3 */
		pcs-phy@6 {
			compatible = "qcom,qca8k-pcs-phy";
			reg = <6>;
			clocks = <&qca8084_nsscc NSS_CC_SRDS1_SYS_CLK>,
				 <&qca8k_uniphy1_tx312p5m>,
				 <&qca8k_uniphy1_rx312p5m>;
			clock-names = "pcs", "pcs_rx_root", "pcs_tx_root";
			resets = <&qca8084_nsscc NSS_CC_SRDS1_SYS_ARES>;
		};
		xpcs-phy@7 {
			compatible = "qcom,qca8k-xpcs-phy";
			reg = <7>;
			#address-cells = <1>;
			#size-cells = <0>;
			resets = <&qca8084_nsscc NSS_CC_XPCS_ARES>;
			channel@0 { reg = <0>; /* NSS_CC_MAC1_* clocks/resets */ };
			channel@1 { reg = <1>; /* NSS_CC_MAC2_* */ };
			channel@2 { reg = <2>; /* NSS_CC_MAC3_* */ };
			channel@3 { reg = <3>; /* NSS_CC_MAC4_* */ };
		};
	};
};
```

- Use `phy-mode = "10g-qxgmii"` on PPE ports 1-4; QSDK13's `qusgmii` is
  the vendor name for the same 2.5G quad-PHY mode. Package mode 0 means
  PCS1 10G-QXGMII for PHY0-PHY3 and PCS0 unused.
- Keep the MDIO bus `reset-gpios` and the NSSCC `reset-gpios` explicit;
  verify whether they share GPIO60 or use separate lines. The QSDK uses
  GPIO60 for the QCA8084 package reset.
- The `pcs-phy@6`/`xpcs-phy@7` children are required for the 10G-QXGMII
  SerDes path; without them the package probe can bind but link-up fails.
- Do not describe the QCA8084 PHYs as simple `ethernet-phy@1..4` nodes:
  the target driver requires the package join and per-PHY clocks/resets.
- If `dmesg` shows `-ENOENT` clock/reset failures, compare the NSSCC
  address/reference clocks and the QSDK SSDK `qca8084_phy.c` sequence first,
  before adding a driver workaround.

### Cycle 6: PPE ports, PCS channels, and MAC mapping

**Step 1 — OpenWrt + QWRT probe**

- Target `0349` gives the exact RDP433 `qcom_ppe` port pattern:
  `port@1..4` use `pcs0_ch0..3` with `phy-handle` and per-port
  `NSS_CC_PORTn_MAC_CLK`/`NSS_CC_PORTn_RX_CLK`/`NSS_CC_PORTn_TX_CLK` plus
  `PORTn_MAC/RX/TX_ARES`; `port@5` uses `pcs1_ch0`; `port@6` uses
  `pcs2_ch0`. All use `managed = "in-band-status"`.
- Target `0324` provides `pcs0_ch0..3`, `pcs1_ch0`, and `pcs2_ch0`.
  `pcs0` is the UNIPHY0 quad channel block; `pcs1` is UNIPHY1; `pcs2` is
  UNIPHY2.
- The live `qcom,port_phyinfo` is:
  port@0..3 => port_id 1..4, PHY 1..4 (QCA8084 2.5G);
  port@4 => port_id 5, PHY 0, C45 (AQR113C);
  port@5 => port_id 6, PHY 0x1e, reset GPIO64, `media-type = "sfp"`.
- Live `dp1..dp6` use `qcom,id 1..6`, `phy-mdio-addr 1/2/3/4/0/0x1e`, and
  QSDK12 `sgmii` (QSDK13 `qusgmii` for dp1-4, `usxgmii` for dp5/6).
- QSDK12 `dp1..dp4` are at `0x3a001000..0x3a001600`; QSDK13 moves them to
  `0x3a500000..0x3a50c000`. These are vendor DP register addresses; mainline
  `qcom_ppe` ports are addressed by `reg = <1..6>`, not those addresses.

**Step 2 — OpenWrt vs QSDK mapping**

- QSDK's `port_id 1..6` matches mainline `port@1..6`; the QCA8084 ports are
  PCS0 channels 0-3, the AQR is PCS1 channel 0, and the SFP is PCS2 channel 0.
- QSDK12 `sgmii` on dp1-4 is only 1G; QSDK13 `qusgmii` is the 2.5G quad
  mode. Mainline must use `10g-qxgmii` for the QCA8084 ports (the target PCS
  driver's 4 x 2.5G mode), not `sgmii`.
- QSDK `dp1` carries the WAN/base MAC `a4:a9:30:19:a8:dc`; the live ART
  first MAC matches. QSDK `dp4..dp6` share `92:43:49:95:cb:ce`, a placeholder
  that must not be copied into mainline.

**Step 3 — Plan delta**

- Add the `&qcom_ppe` shape with six ports:

| Port | Device | `phy-mode` | `pcs-handle` | `phy-handle` |
|---|---|---|---|---|
| 1 | QCA8084 PHY1 @1 | `10g-qxgmii` | `pcs0_ch0` | `qca8084_phy1` |
| 2 | QCA8084 PHY2 @2 | `10g-qxgmii` | `pcs0_ch1` | `qca8084_phy2` |
| 3 | QCA8084 PHY3 @3 | `10g-qxgmii` | `pcs0_ch2` | `qca8084_phy3` |
| 4 | QCA8084 PHY4 @4 | `10g-qxgmii` | `pcs0_ch3` | `qca8084_phy4` |
| 5 | AQR113C @0 (C45) | `usxgmii` | `pcs1_ch0` | `aqr113c` |
| 6 | SFP+ @0x1e | `usxgmii` | `pcs2_ch0` | `sfp_phy` (deferred) |

- Each port node needs the RDP433 clock/reset triple from `0349`
  (`NSS_CC_PORTn_MAC/RX/TX_CLK`, `PORTn_MAC/RX/TX_ARES`) and
  `managed = "in-band-status"`. Use `&nsscc` (IPQ9574 NSSCC), not a QCA8K
  switch node.
- Use MACs from `0:ART` (`mac-base`, offset 0): WAN/base = first MAC,
  LAN = +1, WiFi = +2/+3/+4; do not copy the QSDK placeholder
  `92:43:49:95:cb:ce`. Add `nvmem-cells`/`nvmem-cell-names = "mac-address"`
  to each port or set them in `02_network`.
- Keep the QCA8084 ports on `pcs0` channels 0-3; do not put the QCA8084
  package's internal PCS on `pcs1`/`pcs2`. The QCA8084 package's own
  PCS1/XPCS is the PHY-side 10G-QXGMII block; the SoC `pcs0` is the MAC-side
  block.
- Port 5/6 `usxgmii` matches the QSDK13 modes and the target PCS driver's
  USXGMII support; the SFP port is deferred until the wired ports are
  stable.

### Cycle 7: AQR113C NVMEM firmware and 10G port

**Step 1 — OpenWrt + QWRT probe**

- OpenWrt `ipq95xx/config-default` has `CONFIG_AQUANTIA_PHY=y` (built-in).
  Target `0350` adds `nvmem-cells = <&aqr_fw>` and
  `nvmem-cell-names = "firmware"` to the AQR C45 PHY nodes; target `0348`
  defines an `aqr_fw` cell on the RDP433 `0:ethphyfw` partition.
- The live `0:ETHPHYFW` is at 0x15c0000, size 0x100000. Its first 0x28 bytes
  are an MBN header (`image_type 0x13`, `image_size 0x60002`), followed by
  the Xiaomi AQR v5.6.7 payload.
- The payload is 393,218 bytes (`0x60002`); its last two bytes are
  `0x8ac4` (big-endian), and `crc_itu_t(init 0)` over the first
  `size - 2` bytes is also `0x8ac4`. The live 10G device binds to the
  `Aquantia AQR113C` driver at MDIO C45 address 0 with `usxgmii`.

**Step 2 — OpenWrt vs QSDK/U-Boot**

- Mainline v6.18 `aquantia_firmware.c` `aqr_firmware_load()` first polls
  `VEND1_GLOBAL_FW_ID`; if firmware is already loaded it does nothing.
  Otherwise it reads the NVMEM cell named `firmware`, validates the AQR
  header/CRC/version, and boots the image; if the cell is missing/invalid it
  falls back to the `firmware-name` filesystem property.
- U-Boot loads the same payload from `0:ETHPHYFW`; its strings include
  `0:ETHPHYFW`, `ETHPHYFW Loading failed`, `bad magic on ETHPHYFW partition`,
  and `aquantia_phy_reset_init_done`. The live boot already loads it, so the
  Linux NVMEM path is a recovery path, not the normal path.
- QSDK's `aquantia_main.c` is older and has no NVMEM loader; the live QSDK
  relies on U-Boot. Mainline is the better path and does not need a driver
  patch.

**Step 3 — Plan delta**

- Add the `0:ETHPHYFW` partition node under the NAND controller:

```dts
partition@15c0000 {
	label = "0:ETHPHYFW";
	reg = <0x15c0000 0x100000>;
	read-only;

	nvmem-layout {
		compatible = "fixed-layout";
		#address-cells = <1>;
		#size-cells = <1>;

		aqr_fw: aqr-fw@28 {
			reg = <0x28 0x60002>;
		};
	};
};
```

- Add the AQR PHY node:

```dts
aqr113c: ethernet-phy@0 {
	compatible = "ethernet-phy-ieee802.3-c45";
	reg = <0>;
	nvmem-cells = <&aqr_fw>;
	nvmem-cell-names = "firmware";
};
```

and use it on PPE port 5 with `phy-mode = "usxgmii"` and
`pcs-handle = <&pcs1_ch0>`.
- Use `0x28/0x60002`, not the RDP433 `0x0/0x5fc02` cell: the Xiaomi
  partition has the 0x28-byte MBN header and a 0x60002 payload.
- Do not install the Netgear `AQR-G4...VER1990.cld` or the Marvell
  `VER1922` file as the primary firmware. Do not overwrite `0:ETHPHYFW`.
- Keep `CONFIG_AQUANTIA_PHY=y`; if `kmod-phy-aquantia` is added for
  dependency clarity, ensure it does not force the built-in driver to `m`
  in a way that changes the NVMEM probe timing.
- The AQR `phy_id` may read as zero via the C45 sysfs path; the driver
  binding name and the MDIO C45 address are the reliable identifiers.

### Cycle 8: SFP+ port 6 and QCA SFP PHY

**Step 1 — OpenWrt + QWRT probe**

- OpenWrt has `KernelPackage/sfp` in `package/kernel/linux/modules/netdevices.mk`
  with `CONFIG_SFP` and `CONFIG_MDIO_I2C`, installing `sfp.ko` and
  `mdio-i2c.ko`. The target `config-6.18` has I2C core/QUP but no
  `CONFIG_SFP`/`CONFIG_MDIO_I2C`; `kmod-sfp` must be added.
- `ipq9570-kiwi-dvk.dts` has the only target `sff,sfp` example:
  `i2c-bus = <&blsp1_i2c1>`, `los-gpios = <&tlmm 46 ...>`, plus
  `managed = "in-band-status"` on the PPE port.
- The live SFP is **not** a direct i2c4 EEPROM. `port_phyinfo` says
  port_id 6, PHY address `0x1e`, `phy_i2c_address = 0x1e`,
  `phy-reset-gpio = <&tlmm 64 0>`, `media-type = "sfp"`. The live MDIO
  device `90000.mdio:1e` binds `QCA SFP`, `phy_interface sgmii`,
  `phy_id 0xaaaabbbb`. `ethtool -m` reports "Not supported"; no module
  EEPROM was confirmed.
- The SFP LED is `sfp_green` on GPIO62 with `linux,default-trigger =
  "netdev"`; the live QSDK `dp6` is `usxgmii` at PHY `0x1e`.

**Step 2 — OpenWrt vs QSDK13/SSDK**

- QSDK13 keeps `dp6` at `qcom,phy-mdio-addr = <0x1e>`,
  `phy-mode = "usxgmii"`, `media-type = "sfp"`, reset GPIO64.
- QSDK SSDK has `IN_SFP_PHY`/`PHY_I2C_ACCESS`, `hsl_port_is_sfp()`, and
  `SFP_PHY_CHIP`; the QCA SFP PHY is a vendor driver accessed over the
  MDIO/I2C path. Mainline has no equivalent `QCA SFP` PHY driver in the
  target; the generic `sff,sfp` framework expects an EEPROM/I2C cage.
- **Derived:** port 6 can be described as `pcs2_ch0` + `usxgmii` + a
  `phy-handle` to the `0x1e` MDIO device, but the generic `sfp` framework
  may not bind if the cage has no EEPROM. Do not claim `ethtool -m` support
  without a module/EEPROM test.

**Step 3 — Plan delta**

- Keep SFP in Phase 4, after the QCA8084 2.5G and AQR 10G ports are stable.
- Add `kmod-sfp` to the device packages and `CONFIG_SFP`/`CONFIG_MDIO_I2C`
  via the package; do not add a bare `CONFIG_SFP=y` without `mdio-i2c`.
- Port 6 node: `reg = <6>`, `phy-mode = "usxgmii"`,
  `pcs-handle = <&pcs2_ch0>`, `managed = "in-band-status"`, and a
  `phy-handle` to an `ethernet-phy@1e` node. The `1e` node is a QCA SFP
  device, not a generic C45 PHY; keep its reset GPIO64.
- If a module EEPROM is present, add an `sff,sfp` node with the actual I2C
  bus, `los-gpios`, `tx-fault-gpios`, `tx-disable-gpios`, and
  `mod-def0-gpios`; do not reuse the i2c4 assumption. The live unit has no
  confirmed EEPROM bus.
- Add the `sfp_green` LED on GPIO62 with `linux,default-trigger = "netdev"`;
  keep the SFP reset GPIO64 separate from the MDIO bus reset GPIO60.
- Validation must include module detect, 1G and 10G links, and `dmesg` for
  `sfp`/`mdio-i2c` probe errors. Do not promise `ethtool -m` unless the
  module EEPROM is proven.

### Cycle 9: PCIe controllers, PERST, lanes, and domains

**Step 1 — OpenWrt + QWRT probe**

- `ipq9570-sbe1v1k.dts` is the mainline template: `pcie1` PERST GPIO26,
  wake GPIO27; `pcie2` PERST GPIO29, wake GPIO30; `pcie3` PERST GPIO32,
  wake GPIO33. Each has a `pcie@N` child with a `wifi@0`
  (`pci17cb,1109`), calibration variant, MAC NVMEM, and WSI `ports`.
- The Xiaomi live/Qsdk13 PERST map is different from sbe1v1k:
  `pci@10000000` GPIO26/x1, `pci@20000000` GPIO29/x2,
  `pci@18000000` GPIO23/x2; `pci@28000000` GPIO23/x1 is disabled.
- Live domains are 2/3/4 for `10000000`/`20000000`/`18000000`; QSDK13
  domains are 1/2/3; the disabled `pci@28000000` is domain 1 (live) or
  domain 0 (QSDK13). The target `02_network` paths assume pcie1=domain1,
  pcie2=domain2, pcie3=domain3.
- Live link state is 8 GT/s, x1 for 2.4G, x2 for 5G/6G; endpoint BAR0 is
  2 MiB with 32 MSI IRQs. The QSDK13 board IDs are 1/2/4 for
  pcie1/pcie2/pcie3; WSI indices are 2/0/1.

**Step 2 — OpenWrt vs QSDK domain/board mapping**

- Mainline `ipq9574.dtsi` owns `linux,pci-domain`; do not copy the live
  QSDK domains 2/3/4. The target `DEV_PATH_PCIE0/1/2` strings assume
  pcie1=domain1, pcie3=domain3, pcie2=domain2, matching QSDK13.
- The QSDK `qcom,board_id` is a calibration/BDF selector, not a PCI
  property. Mainline uses `qcom,calibration-variant =
  "Xiaomi_BE18000_live_1/_2/_4"` on pcie1/pcie2/pcie3.
- `pcie@0` child `reg` values in sbe1v1k are 0/1/2 for pcie1/pcie2/pcie3;
  keep that pattern and use the mainline SoC unit addresses. Do not copy the
  QSDK `pcie1_rp`/`pcie3_rp` node names.

**Step 3 — Plan delta**

- Add `&pcie1` (2.4G): `perst-gpios = <&tlmm 26 GPIO_ACTIVE_LOW>`,
  one lane (from the SoC DTSI), `pcie@0` child with `wifi@0`
  (`pci17cb,1109`), `qcom,calibration-variant = "Xiaomi_BE18000_live_1"`,
  WSI tx/rx ports, and `status = "okay"`.
- Add `&pcie2` (5G): `perst-gpios = <&tlmm 29 GPIO_ACTIVE_LOW>`, two
  lanes, `qcom,wsi-controller` on `wifi@0`, variant `_live_2`, WSI ports.
- Add `&pcie3` (6G): `perst-gpios = <&tlmm 23 GPIO_ACTIVE_LOW>`, two
  lanes, `pcie@0,0` child (or the mainline unit address), variant
  `_live_4`, WSI ports.
- Keep `pcie4`/`pci@28000000` disabled. Do not add `wake-gpios` 27/30/33
  unless the Xiaomi board is verified to use them; the QSDK13 nodes only
  show PERST.
- Enable `&pcie1_phy`, `&pcie2_phy`, `&pcie3_phy` and their `pinctrl-0`
  default states; the exact pinctrl groups are cycle 15/16 material.
- Verify the built DTB's `linux,pci-domain` values against the
  `02_network` `DEV_PATH_PCIE*` strings; if mainline uses different
  domains, fix the paths rather than forcing QSDK numbers.
- Do not use `qcom,board_id` or `qcom,wsi_index` in the mainline DTS; the
  variants and the WSI graph carry the same information.
