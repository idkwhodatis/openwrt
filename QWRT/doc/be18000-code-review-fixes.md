# BE18000 follow-up code review and repairs

Date: 2026-11-22. Review base: `490a34c420b630faa3c20f83c67b444d4942f79b`.

The owner requested another code review, fixes, and publication to `master`
after flashing a factory image and reporting no SSH access. This review
continues the [first-flash audit](be18000-no-ssh-audit.md), concentrating on
early module startup, Ethernet initialization and packet ownership. The
reported symptom is still not matched to a serial log or an exact SSH
error. The defects below are established from source; their occurrence on
the router remains unobserved.

## Repairs

| Area | Defect | Repair |
| --- | --- | --- |
| ath12k group startup | Partial multi-radio startup could cancel a QMI worker while holding the mutex that worker needed. | [702: defer QMI events until group creation completes](../../package/kernel/mac80211/patches/ath12k/702-ath12k-defer-qmi-events-until-group-creation-completes.patch). |
| EDMA receive | Unsigned allocation unwinds, a stale skb after a drop, a double free, and checksum access after freeing a fragment skb. | [0366: RX cleanup and skb ownership](../../target/linux/qualcommbe/patches-6.18/0366-net-ethernet-qualcomm-ppe-fix-rx-cleanup-and-skb-ownership.patch). |
| EDMA transmit queues | Unsigned allocation unwinds, waking the completion CPU's queue, a missed stop/wake race, and treating DMA errors as descriptor exhaustion. | [0367: TX cleanup and queue wakeup](../../target/linux/qualcommbe/patches-6.18/0367-net-ethernet-qualcomm-ppe-fix-tx-cleanup-and-queue-wakeup.patch). |
| EDMA transmit buffers | Partial SG chains submitted after a mapping failure, incorrect/incomplete unmapping, nested payload omission, and skb access after submission. | [0369: TX DMA ownership](../../target/linux/qualcommbe/patches-6.18/0369-net-ethernet-qualcomm-ppe-track-tx-dma-ownership.patch). |
| QCA8084 package | Shared handles leaked on failed probe or were released on the first member's removal; repeated notifications accumulated clock enables. | [0368: package resource lifetime](../../target/linux/qualcommbe/patches-6.18/0368-net-phy-qca808x-fix-package-resource-lifetime.patch). |
| Board description | PCI2/PCI3 bridge configuration-space addresses had nonzero low address cells. | Corrected the two bridge `reg` values in the [board DTS](../../target/linux/qualcommbe/dts/ipq9574-xiaomi-be18000.dts). |
| Factory image | `IMAGE_SIZE` did not activate `append-ubi`'s size guard without `NAND_SIZE`. | Added an explicit final `check-size` to this board's factory image pipeline in [ipq95xx.mk](../../target/linux/qualcommbe/image/ipq95xx.mk). |

### ath12k: allow failed group creation to return

The initial group creation holds `ag->mutex` while powering the radios
sequentially. An earlier radio's QMI `SERVER_ARRIVE` worker could wait for
that mutex while a later radio failed. The rollback then called
`cancel_work_sync()` on the earlier worker without releasing the mutex.
Neither task could progress. Because `S10boot` runs module loading
synchronously, this conditional failure can prevent network and Dropbear
startup. It does not require opt-in coldboot calibration.

The repair gives the QMI event path three states:

- **PREPARED:** initialize the handle and retain discovery events; do not
  execute event handlers or coldboot work.
- **RUNNING:** activate each service only after every radio's fallible
  creation and power-up step succeeds. Activation is the final step of
  group creation and cannot fail.
- **STOPPING:** reject new posts, cancel workers while their QMI handle
  remains usable, release receive callbacks, then free retained events.

The direct firmware memory-request callback is gated as well: it can
acquire the group mutex without going through the event worker. The
initialization paths now release a successfully created QMI handle on
workqueue or lookup failure. A full service initialization clears the
entire target-memory array, its count and delayed-allocation state, and
resets the PHY-capability readiness sentinel. Ordinary firmware recovery
continues using the active service and its existing memory-reuse path.

This ordering relies on the exact kernel's MHI power-up waiting for
mission mode independently of QMI event execution. It was checked in the
pinned source. The mac80211 package release is incremented from 17 to 18
to identify the changed package source.

### EDMA: bound cleanup and retain one owner for each skb

Five RX/TX allocation-error loops used an unsigned index with a
decrement-and-`>= 0` condition. They could underflow and walk outside the
ring arrays. Cleanup now visits only earlier successfully allocated
rings; the current ring's allocation helper already frees its partial
allocation.

On receive, the cached next skb advances together with the next
descriptor, including when invalid source metadata drops a packet. The
linear page-mode handler leaves a failed skb for its caller to free once.
Scatter receive records checksum status on the packet head delivered to
the stack, avoiding access through an already freed page-fragment skb.

On transmit, each completion ring records its actual netdevice queue.
Completion checks and wakes that queue under the same TX lock used by
transmit, closing the race in which the last completion checks an active
queue immediately before transmit stops it. Cleanup skips queue access
after NAPI deletion, when its associated netdevice may already be gone.
A failed DMA mapping is a packet failure, not a reason to stop a queue
waiting for a completion that was never submitted.

### EDMA: keep DMA records with the transmitted packet

The SG path added a helper's zero failure result to a count that already
included the first descriptor. Its failure test could therefore never
detect that case, allowing an incomplete `MORE` chain to reach hardware.
Unmapping also reconstructed addresses from fragment metadata instead of
retaining the DMA API's returned address, used the wrong length, and
reclaimed only one mapping on normal completion.

0369 retains the actual DMA address, length and mapping type for every
successful segment. The first record lives in `skb->cb`; only packets
requiring additional mappings allocate an exact-size record array. The
records remain with the skb when hardware reuses a descriptor before
packet completion. A common builder counts and maps nonempty skb heads,
page fragments and direct frag-list children. Nested frag lists are
linearized first, preserving payload that the old one-level walker omitted.

Only a successful mapping advances ownership. The builder sets `MORE`
after its successor maps successfully and places the root skb pointer on
the final descriptor alone. Any failure unwinds the complete successful
prefix without publishing the producer index. Completion and pending
packet cleanup use the same unmap/free helper. Packet statistics are
updated before publishing the producer, because completion on another
CPU can immediately free the skb afterwards.

Allocation rollback no longer reads hardware indices before the rings
are configured. The port-disable routine also keeps its computed
per-port ring index; it previously overwrote it and repeatedly disabled
port 1's rings when stopping other ports.

The hardware quiescence contract still needs device validation. Software
cleanup retains the existing port-stop, delay and ring-disable ordering;
the inspected register definitions expose no TX-idle acknowledgement
proving that all late DMA/completions have stopped. Close/unload under
load and DMA-debug traffic tests are needed to establish that hardware
property. This review does not claim to have proved it from source.

### QCA8084: release shared resources after the last user

The package now counts successful users under its existing package mutex.
Its clocks, reset and PCS/XPCS handles are acquired once and released on
the last successful PHY user's exit. Every partial acquisition also has
a matching release. PCS/XPCS allocations and references belong to this
package lifetime instead of devres attached to sibling MDIO devices.

The per-PHY devres order releases that PHY's resources first, its shared
package reference second, and the shared package storage last. Failure to
register the release action also immediately balances the acquired user.
Exact phylib teardown cancels the PHY state worker before devres cleanup.

PCS and channel clock-enable ownership is recorded explicitly. Repeated
speed notifications no longer increase enable counts indefinitely, and
a partial channel enable unwinds only the enables acquired by that call.
The deferred BaseR/XPCS startup introduced in 0365 remains in place.

These fixes address failed probe, retry and removal. An ordinary first
probe that defers because a PCS device is not yet present is not evidence
of an inevitable cold-boot failure.

### Board and image checks

The PCI bridge correction removes the two existing `pci_device_reg`
warnings. Linux derives devfn from the first address cell, so the former
third-cell values alone did not establish failed enumeration.

The factory pipeline now checks the finished UBI file against the known
190 MiB rootfs partition. This is a partition upper bound; it does not
invent a total NAND capacity or reserve an estimated bad-block margin.
The archived 17,432,576-byte image was already much smaller, so this
omission does not explain that archived image's SSH symptom.

## Validation and remaining device evidence

The changes were applied to the exact Linux 6.18.64 and backports 7.2
sources with this fork's existing patches. Validation completed as follows:

- All five new driver patches applied without fuzz or offsets; the
  resulting files match the independently reviewed candidates.
- Linux `checkpatch.pl --strict --no-tree` reported **zero errors,
  warnings or checks** for each of 0366, 0367, 0368, 0369 and 702.
- The complete PPE directory compiled for ARM64 after the final 0369
  revision and linked `qcom-ppe.o`.
- The Qualcomm PHY directory compiled, including `qca808x.o` and
  `qca8084_serdes.o`. The host `pcs-qcom-ipq9574.o` target also passed.
- The entire configured ath12k directory compiled, including changed
  `core.o` and `qmi.o`, and linked `ath12k.o` and `ath12k_wifi7.o` against
  the exact patched Linux 6.18.64 headers.
- These builds used actual **AArch64 GCC 14.2.0** with debug metadata
  disabled, completed without compiler warnings/errors, and produced
  AArch64 ELF objects. No mock tests were used.
- The repaired board DTB compiled successfully to **45,555 bytes**; the
  two previous PCI bridge `reg` warnings are gone.
- QMI event lifetime, QCA8084 devres ownership, and EDMA mapping/unmapping
  and teardown received independent source reviews. Documentation links
  and final source whitespace checks passed.

This review does not establish a successful hardware boot or a working
SSH connection. It also does not substitute for a complete OpenWrt image
build, final module validation or traffic testing. The changes take
effect on the device only after rebuilding and installing an image from
the updated source.

For device validation, the intended management path remains one of the
four QCA8084 LAN ports, `192.168.1.1`, root, TCP port 22. The 10G copper
port is WAN. A LAN DHCP lease would demonstrate that boot and networking
progressed; an SSH handshake would establish transport reachability. A
timeout alone does not locate the failure. The
[first-flash audit's stage discriminators](be18000-no-ssh-audit.md#6-smallest-evidence-that-locates-the-failing-stage)
give the boot markers and minimal captures needed to identify the
remaining stage if the rebuilt image still fails.
