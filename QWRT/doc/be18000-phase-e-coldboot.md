# BE18000 Phase E: coldboot calibration status

Date: 2026-11-22

Status: **implemented behind an explicit opt-in, not enabled in the
default image.**  The offline build carries the coldboot QMI lifecycle
in `ath12k`, but the module parameter defaults to off and no hardware
has run the sequence yet.  Normal mission-mode boot remains the default.

## Implementation

The feature is in the mac80211 package patch
`package/kernel/mac80211/patches/ath12k/701-ath12k-add-opt-in-coldboot-calibration.patch`.
It is compiled into `kmod-ath12k` and only activates when the module is
loaded with:

```text
ath12k.cold_boot_cal=1
```

It implements:

- `QMI_WLFW_CAL_DONE_IND_V01` (`0x003e`) with the vendor TLV layout.
- Calibration mode 7 after the first `FW_READY` indication.
- A per-radio completion and a separate work item for the CAL_DONE wait,
  so the hardware-group mutex is never held while QMI target-memory
  allocation runs.
- CALDB target-memory DMA lifetime across the firmware reset; the
  mission-mode boot reuses the same chunks.
- `WLAN_MODE_OFF`, HIF power-down, HIF power-up and a second `HOST_CAP`
  carrying `cal_done=1`.
- MLO capability suppressed in the coldboot `HOST_CAP` and advertised
  only after every radio has completed calibration.
- Group host-cap negotiation is deferred while any radio is still
  coldboot-pending, and mission-mode partner triggers skip those radios,
  so calibration is not interrupted by a second `HOST_CAP`.
- A 60-second CAL_DONE timeout with a mission-mode fallback.
- Cancellation before HIF teardown and QMI handle release.
- Gating on QCN9274 hw2.0 and the default (DMA) target-memory mode.

The fixed-memory target path remains excluded because
`CALDB_MEM_REGION_TYPE` has no reserved-memory region there; only the
ordinary PCI DMA path is accepted.

## Why it is off by default

- The official QCN9274 `firmware-2.bin` has not been observed accepting
  mode 7 or requesting `CALDB_MEM_REGION_TYPE` on the QCN9224.
- The QSDK flow also loads QCN9224 INI files and uses fixed `caldb-addr`
  windows that mainline does not consume.  The patch is the mainline QMI
  equivalent, not a drop-in replacement for the vendor firmware plumbing.
- A boot that reaches firmware without CAL_DONE is a failure, not a
  pass.  Blank ART high-band slices and zero-filled
  `/data/vendor/wifi` caches are still forbidden as calibration input.
- Wired management is independent: a coldboot failure only affects
  Wi-Fi probe and cannot block LAN/WAN boot.

## Enabling for a hardware experiment

Add a module option to `/etc/modules.conf` (OpenWrt's `kmodloader`
reads its `options` lines from there):

```text
options ath12k cold_boot_cal=1
```

Alternatively append `ath12k.cold_boot_cal=1` to the kernel command
line.  A serial
console and the full QMI trace must be captured before enabling this on
a production unit.  The known-good image should remain available for
recovery.

## Hardware evidence to collect

- Per-radio cold power-on QMI trace: mode 7 response, CALDB memory
  request (type, length, address/ack), CAL_DONE, OFF, power cycle,
  second `HOST_CAP` TLV `0x1a`, mission readiness.
- `Coldboot Calibration completed` or equivalent firmware indication
  for each of the three radios.
- A rejected/timeout path and a second-boot/unload/recovery path.
- Sane txpower/rates and a 5G/6G association, plus wired traffic
  throughout.
- MLO only after all three radios pass coldboot and mission mode.

## Acceptance

Do not enable the feature by default from this document alone.  If the
candidate firmware cannot support the sequence, keep the normal
mission-mode path and report the radio limitation rather than installing
invalid caldata.
