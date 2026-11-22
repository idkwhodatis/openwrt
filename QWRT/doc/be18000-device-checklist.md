# Modified BE10000 / BE18000 device acceptance checklist

Use this on the hardware-converted 6 GHz BE10000 that QWRT identifies as `xiaomi,be18000`. Start with the running vendor system. The first acceptance milestone for the fork is a cold RAM boot with working wired SSH and image validation. The final upgrade milestone is a second build reachable after a persistent upgrade and power cycle.

## 1. First SSH session on running QWRT

Run these from a private capture directory **on the PC**. The outer single quotes pass each command to the router shell, and the redirects save text on the PC. Use a fresh directory per session. Logs can identify clients, SSIDs and MACs. Record the date, PC interface, jack or Wi-Fi band used, room/load conditions and whether the last boot was warm, cold or unknown. Keep the current management link up throughout. Missing commands, attributes or old boot messages are evidence gaps.

### Identity, management path and fault history

```sh
ssh root@10.10.10.1 'date; uptime; uname -a; ubus call system board; for f in model compatible; do echo "$f"; tr "\000" "\n" < "/proc/device-tree/$f"; done; cat /proc/cmdline' > identity.txt
ssh root@10.10.10.1 'echo "$SSH_CONNECTION"; ip addr; ip route; ip -s link; command -v bridge >/dev/null && bridge link; command -v bridge >/dev/null && bridge vlan show; command -v brctl >/dev/null && brctl show' > network.txt
ssh root@10.10.10.1 'dmesg' > dmesg-before.txt
ssh root@10.10.10.1 'logread' > logread-before.txt
ssh root@10.10.10.1 'ls -l /sys/fs/pstore; for f in /sys/fs/pstore/*; do [ -f "$f" ] && { echo "$f"; cat "$f"; }; done' > pstore.txt
```

- [ ] Compare board ID and kernel with the saved 5.4.250 QWRT baseline. Map the SSH client address to its route and bridge. Note which link must stay up.
- [ ] Review full logs for watchdog resets, firmware recovery loops, PCIe/AER errors, repeated PHY resets, NAND ECC errors, UBIFS errors and thermal alarms. An empty pstore or a wrapped log leaves prior failures unknown.

### NAND, UBI and bootloader

```sh
ssh root@10.10.10.1 'cat /proc/mtd; for d in /sys/class/mtd/mtd[0-9]*; do [ -f "$d/name" ] || continue; echo "$d"; for k in name offset size erasesize bad_blocks ecc_failures corrected_bits; do [ -r "$d/$k" ] && { printf "%s " "$k"; cat "$d/$k"; }; done; done' > mtd.txt
ssh root@10.10.10.1 'cat /proc/mounts; df -h; for f in /sys/class/ubi/ubi*/mtd_num; do [ -r "$f" ] && { echo "$f"; cat "$f"; }; done; command -v ubinfo >/dev/null && ubinfo -a' > ubi.txt
ssh root@10.10.10.1 'cat /etc/fw_env.config' > env-layout.txt
```

The shipped QWRT file is wrong for this unit: it reads `/dev/mtd17 0x0
0x40000 0x20000 2`, but the live environment CRC validates only over the
first 64 KiB. Do not use it for `fw_printenv` or `fw_setenv`. The
mainline image generates `/dev/mtd17 0x0 0x10000 0x20000 1` (64 KiB
environment, 128 KiB NAND erase block, one sector). For the read-only
QWRT baseline, use an explicit temporary config; the 64 KiB erase size
is sufficient because only reads are performed.

- [ ] Compare names, offsets, erase sizes and UBI volume IDs against the MAX layout. Expected rootfs size is **199,229,440 bytes**. Record kernel, rootfs and rootfs_data volumes and free/bad-block reserves. A v2 split rootfs/overlay layout stops the MAX first-flash procedure.
- [ ] After confirming that mtd2 is `0:MIBIB`, read only the first 256 KiB. Expected MAX digest is `e482188b9d950fd6fa8375df002f143600911a4472e186c9172d072e0fd034a0`. Check the read count and digest. After matching the environment configuration to APPSBLENV, read the selected boot variables. Save secondary APPSBL separately during the backup stage.

```sh
ssh root@10.10.10.1 'dd if=/dev/mtd2 bs=256k count=1 | sha256sum' > mibib-prefix.txt
ssh root@10.10.10.1 'echo "/dev/mtd17 0x0 0x10000 0x10000 1" > /tmp/fw_env.test; fw_printenv -c /tmp/fw_env.test bootcmd bootargs fsbootargs bootdelay ipaddr serverip flag_boot_rootfs flag_boot_type flag_boot_success' > boot-env.txt
```

### Ethernet, PCIe, radio calibration and board health

```sh
ssh root@10.10.10.1 'ls -l /sys/bus/mdio_bus/devices; for p in /sys/bus/mdio_bus/devices/*; do [ -e "$p" ] || continue; echo "$p"; readlink "$p/driver"; [ -r "$p/phy_id" ] && cat "$p/phy_id"; done; for n in /sys/class/net/dp* /sys/class/net/eth*; do [ -d "$n" ] || continue; echo "$n"; cat "$n/address"; command -v ethtool >/dev/null && ethtool "${n##*/}"; done' > ethernet.txt
ssh root@10.10.10.1 'for d in /sys/bus/pci/devices/*; do [ -r "$d/vendor" ] || continue; echo "$d"; cat "$d/vendor" "$d/device"; readlink "$d/driver"; for k in current_link_speed current_link_width; do [ -r "$d/$k" ] && cat "$d/$k"; done; done; command -v iw >/dev/null && iw dev; command -v iw >/dev/null && iw reg get' > radio.txt
ssh root@10.10.10.1 'cat /sys/module/ipq_cnss2/parameters/soft_switch; ls -l /sys/kernel/debug/*cnss*; dmesg | grep -Ei "QCN9224|b000[124]|bdwlan|CALDB|CAL_DONE|coldboot|HOST_CAP|59100000|AQR113|QCA8084"' > vendor-trace.txt
ssh root@10.10.10.1 'cat /proc/iomem /proc/meminfo; for f in /sys/class/thermal/thermal_zone*/type /sys/class/thermal/thermal_zone*/temp /sys/class/hwmon/hwmon*/name /sys/class/hwmon/hwmon*/temp*_input /sys/class/hwmon/hwmon*/fan*_input /sys/class/hwmon/hwmon*/pwm[0-9] /sys/class/watchdog/watchdog*/identity /sys/class/leds/*/brightness; do [ -r "$f" ] && { echo "$f"; cat "$f"; }; done' > board-health.txt
```

- [ ] Correlate the occupied copper jacks with vendor interfaces, MACs, rates, counters and probe logs. Look for the AQR113C at Clause 45 address 0 and the four QCA8084 PHYs. Save the AQR firmware version if reported. Leave unplugged jacks untested.
- [ ] Correlate the three `17cb:1109` endpoints with driver, link width/speed, firmware version and BDF. Prior QWRT evidence maps PCI1/2/3 to b0001/b0002/b0004 (2.4/5/6 GHz). Save the actual operating frequency and peer association per active interface; where supported, use `iw dev IFACE station dump` with the name from `iw dev`.
- [ ] On PCI3, look for service 0x3a, mode 7, CAL_DONE (0x3e), OFF/subsystem restart, a second HOST_CAP, mission readiness and CALDB at 0x59100000. Record the source of each observation. On the saved build reading CNSS debugfs `qmi_record` **prints into the kernel log**. Preserve the original dmesg first; leave that trigger untouched for a strictly passive capture. A reused address or HOST_CAP success alone cannot establish TLV contents or firmware consumption. [Saved PCI3 trace](be10000-be18000-openwrt-gap-rounds.md)
- [ ] Compare idle readings with a second capture during ordinary traffic. Look for plausible temperature and fan response, persistent memory pressure, and new errors. For watchdog inventory use sysfs only; opening the watchdog character device can arm it.

## 2. Before any NAND write — serial bench session

- [ ] Identify the candidate commit and build fresh matching initramfs FIT, factory UBI and sysupgrade artifacts. Record their hashes and the owner-supplied board-2 hash. The archived pre-merge images establish an earlier baseline.
- [ ] Interrupt U-Boot over serial, TFTP the candidate into RAM, reach a serial shell, then demonstrate a return to the original QWRT by power cycle. Capture both boots.
- [ ] Before the first write, verify the QWRT rootfs UBI backup (`mtd24.bin`, 190 MiB) and read the section 6 restore procedure. A power-cycle return to QWRT is not a substitute for a tested restore of a corrupt rootfs; do not start the first write until the serial/TFTP path and the restore image are both ready.
- [ ] Confirm RAM root, UBI attachments/mounts and tmpfs headroom. From the RAM boot, follow the MAX runbook for a consistent backup of MIBIB, APPSBLENV, **both** APPSBL copies, ART, ETHPHYFW, bdata and the complete rootfs UBI partition. Extract the transferred archive on the PC, verify every source checksum and independently verify rootfs length. Keep recovery files available offline. [Recovery and first-flash procedure](be18000-recovery-runbook.md)

## 3. OpenWrt RAM-boot acceptance

- [ ] Verify board identity, usable RAM, TrustZone/radio/dump/ramoops reservations and early boot logs, including the inherited WCSS reservation state. Investigate overlaps, persistent deferred probes or unexplained resets.
- [ ] On a genuine cold power-on verify QCA8084 package/NSSCC/PCS bring-up and read Clause 22 registers 2 and 3 at each address 1–4 with a supported read-only MDIO tool. Expect combined ID 0x004dd180. DT-supplied IDs in sysfs alone do not show a hardware response.
- [ ] With serial connected, cable-test each jack. Match lan1–lan4 to labels, carrier, DHCP, bidirectional traffic and error-counter deltas; exercise 1G and 2.5G with capable peers. LAN ports intentionally share ART base +1. Test the AQR WAN at ART base +0 with separate upstream DHCP, DNS, routing and forwarded traffic; exercise 10G with a suitable peer.
- [ ] Verify LAN/WAN isolation and DHCP direction after a link flap. From a separate wired PC, establish SSH and copy files both ways with matching hashes. Repeat across warm and cold boots. Keep traffic and SSH active while ath12k initializes. Check temperatures, memory and counters over sustained load.
- [ ] Upload the matching sysupgrade image and run `sysupgrade -T /tmp/<candidate-sysupgrade.bin>`. Expect acceptance. In test mode the raw factory UBI should be rejected. Record the exit codes. First-flash gate: demonstrated serial/TFTP recovery, verified off-device backup, repeatable cold wired SSH, and successful validation.

## 4. Radios and board peripherals

- [ ] Verify OpenWrt domains 1/2/3, calibration variants Xiaomi_BE18000_live_1/_2/_4 and ART MAC offsets +2/+3/+4. Check actual variant selection, QMI/MHI stability, supported channels and client traffic per band, including observed 6 GHz frequency.
- [ ] Start with default mission mode. Once individual bands work, check the WSI ring/controller on PCI2, peer link IDs and traffic counters with an MLO-capable client. Record partial success per link.
- [ ] Test opt-in cold calibration in a separate serial/wired session. Track mode-7 acceptance, CALDB request/backing, CAL_DONE, OFF/power cycle, mission HOST_CAP and firmware readiness per radio. The OpenWrt DMA address may differ from QWRT's fixed window; verify the retained allocation and distinguish an observed TLV from an inferred value. Exercise fallback/recovery as a separate experiment. [Phase E evidence and acceptance](be18000-phase-e-coldboot.md)
- [ ] Check LM63/EMC230x temperature, fan RPM and response to load, watchdog registration, pstore availability, status/network/RGB LEDs and short reset/mesh button events under serial supervision. Keep SFP port 6 disabled for this image; confirm copper remains usable. [Board mappings and staged features](be18000-phase-a-build-manifest.md)

## 5. Persistent install and network upgrade

- [ ] On the serial-supervised first NAND boot, verify kernel volume 0, squashfs root volume 1, writable rootfs_data volume 2, overlay capacity and NAND/ECC/UBI logs. Preserve a test setting or SSH key and reconnect over Ethernet after reboot and cold power-on.
- [ ] Rehearse one real upgrade to a distinguishable second build with stable power and serial attached. Record both build IDs, verify the transferred digest, pass `sysupgrade -T`, and explicitly select the intended settings-preservation behavior. The fork updates active UBI volumes in place.
- [ ] From a separate wired PC open a fresh SSH connection after the upgrade. Verify the new build ID, LAN settings/key, mounts, error counters and traffic. Repeat after cold power-on and save both serial logs. This is the acceptance test for subsequent network upgrades.
