# BE18000 no-SSH audit after the first flash

Date: 2026-11-22. Second-pass source snapshot:
`b1522ec3ccef68a82feb08531e841bdbe88ec1ad`.

The owner built and flashed the factory image and reported no SSH access.
The factory filename is confirmed; the exact writer, emitted boot log,
client SSH error and resulting overlay have not been observed in this audit.
The intended installation is fresh. Reusing QWRT hardware research and
board data does not import QWRT network or SSH configuration.

Two requested fixes have been pushed to `master`. The second pass found
additional conditional driver failure paths, but cannot establish which
one occurred on the router without runtime evidence. No new firmware was
flashed or hardware boot claimed during this work.

## 1. Fixes already published

| Commit | Change | Result |
| --- | --- | --- |
| [c463915](https://github.com/idkwhodatis/openwrt/commit/c463915128407f3605641aeacd0d535237a679a8) | [0364: PPE unwind and NAPI teardown](../../target/linux/qualcommbe/patches-6.18/0364-net-ethernet-qualcomm-ppe-fix-port-init-unwind.patch) | Track initialized clocks separately from registered ports; preserve the original probe error; unregister before freeing resources; avoid disabling never-enabled or already-disabled NAPI. |
| [b1522ec](https://github.com/idkwhodatis/openwrt/commit/b1522ec3ccef68a82feb08531e841bdbe88ec1ad) | [0365: QCA8084 startup order](../../target/linux/qualcommbe/patches-6.18/0365-net-phy-qca808x-fix-qxgmii-startup-order.patch) | Prepare the external SerDes during PHY attachment, then complete BaseR-dependent XPCS setup from PHY status polling after the host PCS starts. |

### PPE cleanup

The old port error path decremented its signed index to `-1` while
destroying registered ports, then reused it in a clock-cleanup loop. It
could access memory before the port array. Other failure branches leaked
the current port's clocks or skipped earlier registered ports.

The same investigation found that TX NAPI deletion called `napi_disable()`
before NAPI had ever been enabled on setup failure. RX deletion disabled
NAPI a second time after its caller had already disabled it. Those calls
can wait indefinitely. The patch fixes these associated error paths and
keeps resources alive until `ndo_stop` and PHY detachment complete.

### QCA8084 startup

PHY `config_init()` runs during `phylink_of_phy_connect()`, before
`register_netdev()` and before the netdevice's `ndo_open()`. The host PCS
is configured later by `phylink_start()`. Requiring host BaseR readiness
during PHY attachment therefore creates an unsatisfied startup dependency.

The new path prepares and calibrates the receiver at attachment. A valid
BaseR status read with no link reports ordinary link-down and is retried
by polling. Once BaseR locks, it performs the remaining USXGMII/QXGMII,
XPCS reset, channel configuration and package clock sequence. Actual MDIO,
calibration and reset errors remain errors.

Shared preparation/completion flags are protected by a mutex and set only
after success. Failed clock enables are unwound. The FIFO remains asserted
and channel operations are suppressed until shared setup finishes.
QXGMII uses polling because a copper-link interrupt cannot announce host
PCS readiness. Ordinary link loss does not repeat the shared XPCS reset.

The order matters: a related BE7000 implementation reported working TX
but dead RX when its XPCS adaptation/reset ran before BaseR lock. This
patch independently preserves the prerequisite rather than simply
ignoring the early timeout. That related-board observation is not a
BE18000 hardware result. See the author's
[subsequent receive-path fix](https://github.com/timofey-maykov/be7000-openwrt/blob/main/patches/0903-net-phy-qca8084-redo-xpcs-setup-after-baser-lock.patch).

## 2. Validation performed

- Downloaded Linux **6.18.64** and verified SHA-256
  `020d45510c539972e6f14c5c71566878d3b7ef56fb082b3e09134f2ebaade562`, matching
  [the fork's kernel pin](../../target/linux/generic/kernel-6.18).
- Applied all **655** existing generic/qualcommbe patches, then 0364 and
  0365 without fuzz. Independently reviewed port failure branches, NAPI
  ownership, PHY attachment/start ordering, shared state and clock rollback.
- Merged the generic, qualcommbe and ipq95xx kernel configurations, enabled
  `QCOM_PPE=m`, `PCS_QCOM_IPQ9574=m` and `QCA808X_PHY=y`, and compiled the
  actual driver sources for **ARM64 with GCC 14.2.0**. Debug metadata was
  disabled for this focused compilation.
- Compiled the complete PPE directory and linked `qcom-ppe.o`; compiled
  `qca808x.o`, `qca8084_serdes.o`, the Qualcomm PHY directory and
  `pcs-qcom-ipq9574.o`. The final revision completed without compiler
  diagnostics. The resulting objects identify as AArch64 ELF.
- Both patches pass Linux `checkpatch.pl` with **zero errors, warnings or
  checks**. No mock tests were used.
- Compiled the board DTB against the exact patched kernel include tree:
  **45,555 bytes**, successful DTC exit, with the two existing PCI bridge
  `reg` warnings discussed below.
- For the radio audit, reconstructed the exact **backports 7.2** source
  with all **320** mac80211 patches in the package's declared order.

This is driver compilation and source analysis, not a full firmware build,
final module/image validation, or a hardware boot/traffic test. GCC 14.2.0
also differs from the archived build toolchain; see the existing
[build manifest](be18000-phase-a-build-manifest.md) for that distinction.
The fixes take effect on the device only in a newly built and installed image.

## 3. Second pass: where access can still fail

| Stage | Finding | Evidence status |
| --- | --- | --- |
| Kernel/rootfs boot | FIT, MAX partition map, NAND geometry, UBI volume numbering, root argument and built-in root-storage drivers agree. | No new confirmed boot blocker. Actual boot output remains unavailable. |
| Early module loading | A partial multi-radio ath12k startup failure can deadlock cleanup before normal services start. | Definite conditional lock cycle; occurrence on this router unobserved. |
| Ethernet registration | A WAN port initialization failure still unwinds all four previously registered LAN ports. | Certain driver policy; initiating failure unobserved. |
| EDMA initialization | RX-ring allocation failure uses an unsigned index in an always-true cleanup loop. | Definite error-path defect; allocation failure unobserved. |
| Ethernet traffic | Invalid-source RX can reuse a freed skb; TX completion can wake the wrong stopped queue. | Definite conditional runtime defects; weaker explanations for never obtaining first access. |
| Address/firewall/SSH | Fresh LAN generation and Dropbear defaults are present and coherent. | No additional deterministic default-config defect found. |

### 3.1 ath12k can block startup after a partial radio failure

The board enables three PCIe radios. Disabling a wireless interface in UCI
does not prevent their driver modules from loading. The
[boot script](../../package/base-files/files/etc/init.d/boot) synchronously
runs `/sbin/kmodloader` in `S10boot`, before `S19dropbear` and `S20network`.
The pinned [procd rcS implementation](https://github.com/openwrt/procd/blob/fb6116870115a66686709017ecabfd724804bbdf/rcS.c)
runs one boot script at a time; its stop/shutdown timeout does not apply
to boot tasks. A driver returning an error permits progress; a driver
that never returns can prevent both network and SSH startup.

The fully patched ath12k source has this lock cycle:

| Context | State | Wait |
| --- | --- | --- |
| PCI probe / group creation | Holds `ag->mutex`; an earlier radio started, a later radio fails. Cleanup destroys the earlier radio. | `cancel_work_sync(&ab->qmi.event_work)` waits for its running QMI worker. |
| Earlier radio's QMI worker | Has entered the normal `SERVER_ARRIVE` handler. | `mutex_lock(&ag->mutex)` waits for the probe thread. |

Relevant generated-source locations under
`drivers/net/wireless/ath/ath12k/` are:

- `core.c`, `ath12k_core_init()` and `ath12k_core_hw_group_create()`:
  group creation and its error unwind retain the group mutex.
- `core.c`, `ath12k_core_soc_create()`: QMI service/workqueue initialization
  precedes radio power-up.
- `qmi.c`, `ath12k_qmi_event_server_arrive()`: the normal path acquires the
  group mutex before testing whether all radios are ready for host caps.
- `core.c`, `ath12k_core_soc_destroy()`, and `qmi.c`,
  `ath12k_qmi_deinit_service()`: cleanup synchronously cancels the worker.

`mhi_sync_power_up()` waits for the MHI mission state, not for QMI event
completion. An earlier radio can therefore have a running QMI worker
while a later radio is still starting. The worker's mutex wait cannot be
aborted by `cancel_work_sync()`. The create-unwind path neither releases
the group mutex before cancellation nor prevents an already running
worker from waiting for it.

This path does **not** require `cold_boot_cal=1`. With the default value
of zero, `SERVER_ARRIVE` follows the mutex-taking path. The selected module
dependencies also permit QRTR-MHI to be loaded before ath12k: the pinned
[ubox loader](https://github.com/openwrt/ubox/blob/b0635f4227bd12de3445bdfe69653723de300953/kmodloader.c)
queues unnumbered AutoProbe entries, then loads dependency-ready modules
in repeated passes.

**Trigger:** at least one radio has progressed to its QMI event while a
later radio's creation/power-up fails. **Discriminator:** module loading
does not finish; an ath12k/MHI failure precedes a stalled probe, with one
task in work cancellation and a QMI task waiting for the group mutex.
Without a task dump or boot log, this remains a candidate for the incident.

The source package and hash are pinned in
[mac80211/Makefile](../../package/kernel/mac80211/Makefile); its release is
[backports 7.2](https://github.com/openwrt/backports/releases/tag/backports-v7.2).
This second pass reports the defect; it is not included in 0364/0365.

### 3.2 WAN initialization can remove all LAN interfaces

The [board DTS](../../target/linux/qualcommbe/dts/ipq9574-xiaomi-be18000.dts)
lists `lan1` through `lan4`, followed by the AQR113C `wan` on PPE port 5.
`ppe_port_mac_init()` treats them as one transaction. Any failure of the
WAN port's clocks, MAC, PCS acquisition, PHY attachment or registration
destroys the earlier LAN netdevices. 0364 makes that teardown safe; it
preserves the existing all-or-nothing policy.

This means four correctly wired LAN PHYs are insufficient if port 5 fails
attachment. Unplugging the WAN cable does not skip WAN device probing.

The AQR firmware NVMEM cell remains `0:ETHPHYFW + 0x28`, length `0x60002`,
matching the saved evidence. The AQR driver keeps bootloader-loaded
firmware when it is already ready and attempts NVMEM loading after its
ready poll times out. I found no new cell-offset mismatch. A missing
specific PHY driver can also fall back to generic C45 attachment, so
an AQR driver probe error alone does not prove that PPE must fail.

**Discriminator:** LAN attachment messages followed by
`PPE port 5 failed to connect phylink`, `QCOM EDMA port setup failed`, or
`PPE Port MAC initialization failed`, with all LAN devices then absent.

### 3.3 Additional EDMA defects

These are separate from the signed PPE port index repaired in 0364.

**RX allocation cleanup:** `edma_cfg_rx_rings_setup()` declares
`ring_idx` as `u32` and uses `while (--ring_idx >= 0)` on RX-fill and
RX-descriptor allocation failures. Unsigned underflow makes the condition
always true and indexes outside the ring array. The same pattern occurs
in its normally unreachable invalid-queue branch. See
[RX patch 0333](../../target/linux/qualcommbe/patches-6.18/0333-net-ethernet-qualcomm-Add-Rx-Ethernet-DMA-support.patch).
An allocation-error message followed by a cleanup exception would make
this relevant. Successful allocation bypasses it.

**RX drop path:** `edma_rx_reap()` advances `next_rxdesc_pri`, but when
source-device lookup fails it frees `skb` and jumps to the loop tail
without refreshing `next_skb`. If another descriptor remains in the same
poll, the next iteration reuses freed memory. Invalid source metadata,
an out-of-range port, or a NULL `netdev_arr` entry can enter that branch.
Messages such as `Netdev Null`, `Invalid src info_type` or
`Port number error` before an RX/free-skb exception would distinguish it.
EDMA enables RX interrupts before port registration, but PPE reset and
initially disabled MACs mean normal startup traffic has not been proved
to trigger this branch. The code is also in RX patch 0333.

**TX queue recovery:** `edma_port_xmit()` stops the skb-selected queue on
descriptor exhaustion, but `edma_tx_complete()` selects the queue to wake
using the completion CPU's `smp_processor_id()`. The completion CPU need
not equal the queue index, and the driver supplies no matching IRQ-affinity
guarantee. A full queue can therefore remain stopped while another queue
is repeatedly checked. See
[TX patch 0334](../../target/linux/qualcommbe/patches-6.18/0334-net-ethernet-qualcomm-Add-Tx-Ethernet-DMA-support.patch).
This better fits a link that initially works and later stalls under load;
it is weak evidence for a failure before the first SSH connection.

These new error/runtime defects have not been changed in this audit pass.

### 3.4 QCA8084 package probe lifetime needs separate hardening

Package clock references are not consistently released on failed probe.
PCS/XPCS devres belongs to the MDIO devices even though acquisition runs
from a PHY probe, and an exclusive package reset is acquired without
being retained for release. A failure after partial success can leave
resources behind and make a later exclusive-reset request return `-EBUSY`.
Relevant source is introduced by the QCA8084 probe/SerDes patches in
`target/linux/qualcommbe/patches-6.18/0307*` through `0311*`.

However, ordinary initial missing-PCS deferral is not by itself proof of
a poisoned `phy_package_probe_once()` flag. With this DTS, an early failed
PHY probe normally has only one package user. Its devres cleanup calls
`phy_package_leave()` and frees the last shared object and its flags.
The new configuration completion flags in 0365 are a separate issue and
are already fixed. Do not describe the remaining probe-lifetime problem
as an inevitable cold-boot failure.

## 4. Boot checks and lower-priority observations

The source still agrees on FIT `config@al02-c4`, gzip, load/entry
`0x42080000`, 128 KiB NAND eraseblocks, 2048-byte page/VID offset and the
MAX rootfs partition at `0x1780000` with size `0xbe00000`. Factory UBI
contains `kernel`/`rootfs`/`rootfs_data` at IDs 0/1/2. The board's final
root argument selects `/dev/ubiblock0_1`, and the kernel has built-in QPIC
SPI NAND, UBI, ubiblock and squashfs support. See the
[FIT cross-check](be18000-fit-crosscheck.md),
[runbook](be18000-recovery-runbook.md) and
[build manifest](be18000-phase-a-build-manifest.md).

`ubi.mtd=rootfs` must still reach the kernel: this board does not label
the partition `linux,ubi`, and UBI's fallback named-partition search does
not select a partition named `rootfs`. The saved environment already
contains the argument in both `bootargs` and `fsbootargs`, so its absence
is a low-priority conditional check, not an established cause. The actual
`Kernel command line:` and UBI attachment messages settle this. Do not
blindly append another `ubi.mtd` parameter; repeated parameters request
separate attachments.

Three lower-priority observations should not be promoted to incident causes:

- The FIT load address retains a `0x80000` displacement although Linux
  6.18's ARM64 header has `text_offset=0`. This violates the strict boot
  ABI alignment requirement, but the exact kernel enables
  `CONFIG_RELOCATABLE` and incorporates the displacement in its early
  mappings. Its alignment check warns rather than aborts. No speculative
  load-address change was made.
- DTC warns that PCI2/PCI3 bridge `reg` entries have nonzero third address
  cells. This is a description defect. Linux's PCI child-node lookup uses
  the first cell to derive devfn, so these warnings alone do not establish
  failed enumeration or missing radio DT properties. The DTB builds.
- The board sets `IMAGE_SIZE` but not `NAND_SIZE`, while `append-ubi` only
  runs its size guard when both are present. This can fail to reject an
  oversized customized image. The archived factory image is only
  17,432,576 bytes against the 190 MiB partition, so that omission does
  not explain the archived image's no-SSH symptom.

## 5. Fresh-install networking and configuration

The intended fresh management connection is **`root@192.168.1.1` through
one of the four QCA8084 2.5G LAN ports**. The AQR113C 10G copper port is
WAN; the SFP path is disabled.

The [board network script](../../target/linux/qualcommbe/ipq95xx/base-files/etc/board.d/02_network)
supplies `lan1 lan2 lan3 lan4` and `wan`. First-boot
[`config_generate`](../../package/base-files/files/bin/config_generate)
creates `br-lan` with `192.168.1.1/24`. Missing static network/system UCI
files in the source tree are intentional; preinit generates them.

Dropbear is in [the global default package set](../../include/target.mk).
Its [default configuration](../../package/network/services/dropbear/files/dropbear.config)
enables port 22 and root/password authentication without an interface
restriction. Its init script generates missing host keys. The shipped
blank-root-password patch permits initial setup login. No board override
that disables SSH was found.

The exact pinned [firewall4 defaults](https://github.com/openwrt/firewall4/blob/3722eadc088c3ab81389596ca9796112b436583a/root/etc/config/firewall)
accept LAN input and reject WAN input. WAN has an explicit ping exception,
so successful ping through WAN does not imply SSH is permitted there.

The QWRT-derived board-data package installs firmware board data, not
`/etc/config/network`, Dropbear settings, passwords or a saved overlay.
A proper full factory-UBI replacement creates a new `rootfs_data` volume.
Old settings are relevant only if the actual writer preserves that volume
or restores an archive through preinit's existing restore path. Separate
bootloader, environment and ART partitions remain part of the hardware
boot contract; that is distinct from importing QWRT UCI configuration.

## 6. Smallest evidence that locates the failing stage

From the connected PC, record the physical port, link state and DHCP lease,
then capture the exact result of:

```sh
ssh -vv -o ConnectTimeout=5 root@192.168.1.1
```

| Observation | What it establishes |
| --- | --- |
| A `192.168.1.x` lease from this router on LAN | Ethernet/IP/DHCP userspace made progress; a total S10 boot hang is less likely for that boot. |
| SSH host-key warning or authentication exchange | The SSH transport is reachable; focus on host identity or authentication. |
| Connection refused | A responder rejected TCP; check the destination, listening service and firewall. |
| Timeout, no DHCP or no ARP response | Does not distinguish early boot failure, blocked module startup, wrong address/port or broken Ethernet RX by itself. |
| White running LED | Supporting evidence that S95done ran, provided the board LED mapping is correct; it is not a replacement for logs. |

If UART is available, one power-on capture is substantially more useful
than further speculative configuration changes. The critical markers are:

1. Linux banner and `Kernel command line:`.
2. `ubi0: attached mtd24 (name "rootfs", size 190 MiB)`.
3. `ubiblock0_1: created from ubi0:1(rootfs)`.
4. `VFS: Mounted root (squashfs filesystem)`.
5. Completion or stall of kernel-module loading, followed by PPE/PHY and
   ath12k messages.

A serial shell can additionally inspect `ip link show`,
`ip addr show dev br-lan`, `dmesg`, `logread`, and
`ubus call service list '{"name":"dropbear"}'`. Capture the final 30–50
boot-log lines and the exact SSH error before assigning the failure to
boot, LAN or SSH.
