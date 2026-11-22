# BE18000 Phase E: coldboot calibration porting brief

Date: 2026-11-22

Status: **not enabled**.  The offline image keeps the normal ath12k
mission-mode path.  This brief records the exact work and evidence
needed before a coldboot patch can be merged or enabled on hardware.

## Why it is not enabled yet

- Backports 7.2 in this tree has no `QMI_WLFW_CAL_DONE_IND_V01`
  handler, no coldboot mode-7 request, no `cal_done` waitqueue, and no
  OFF/power-down/power-up/restart transition for calibration.
- The QSDK ath12k patches `670-ath12k-Add-support-for-cold-boot-calibartion`
  and `703-ath12k-fix-cold-boot-sequence-for-SoC-grouping` are deltas on
  a vendor ath12k base that already contains that lifecycle.  They do
  not apply to the mainline backports 7.2 source.
- The live QSDK driver uses cnss2's separate coldboot state machine
  (`qca-cnss/main.c`, `qmi.c`), including `cal_done`, `cal_timeout`,
  mode 7, CALDB upload, and a firmware power cycle before mission mode.
- Blank ART high-band slices and zero-filled `/data/vendor/wifi` caches
  are not calibration and must not be used as a shortcut.

## Required mainline work

1. Add the `CAL_DONE` QMI indication message/EI and a per-`ath12k_base`
   completion/waitqueue.
2. Send the device/firmware-scoped calibration mode (vendor mode 7)
   before mission mode, only when explicitly opted in.
3. Let the existing CALDB DMA chunk allocation run when firmware
   requests `CALDB_MEM_REGION_TYPE`; keep the backing alive through the
   OFF/restart and second `HOST_CAP`.
4. Handle CAL_DONE, timeout and duplicate/stale indications; set
   `ab->qmi.cal_done` only for the active boot attempt.
5. Perform a controlled firmware power cycle after CAL_DONE or timeout,
   then send mission-mode `HOST_CAP` with TLV `0x1a` reflecting
   `cal_done`.
6. Skip MLO capability in the coldboot `HOST_CAP`; send it only in
   mission mode.
7. Gate the feature on a board/firmware opt-in (DT property or module
   parameter, default off) and keep wired management independent.

## Hardware evidence to collect

- Per-radio cold power-on QMI trace: mode 7 response, CALDB memory
  request (type, length, address/ack), CAL_DONE, OFF, power cycle,
  second `HOST_CAP` TLV `0x1a`, mission readiness.
- `Coldboot Calibration completed` or equivalent firmware indication
  for each of the three radios.
- A rejected/timeout path and a second-boot/unload/recovery path.
- Sane txpower/rates and a 5G/6G association, plus wired traffic
  throughout.

## Acceptance

Do not enable the feature from this brief alone.  A boot that reaches
firmware without calibration completion is a failure, not a pass.  If
the candidate firmware cannot support the sequence, keep the normal
mission-mode path and report the radio limitation rather than installing
invalid caldata.
