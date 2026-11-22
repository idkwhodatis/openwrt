#!/usr/bin/env python3
"""Offline event-ordering checks for the ath12k coldboot patch 701.

The model mirrors the state machine in the patch and the source checks
enforce the ordering properties the model exercises.  It is not a hardware
test and does not execute the kernel module.

Run from the repository root:

    python3 QWRT/tests/test_coldboot_ordering.py
"""
from pathlib import Path

PATCH = (Path(__file__).resolve().parents[2] /
         "package/kernel/mac80211/patches/ath12k" /
         "701-ath12k-add-opt-in-coldboot-calibration.patch")

IDLE, WAIT_CAL, RESET, COMPLETE, FAILED, CANCELLED = range(6)
TIMEOUT_S = 60


class IncompatibleCaldb(Exception):
    pass


class ColdBoot:
    def __init__(self, caldb=True, caldb_size=8 << 20):
        self.state = IDLE
        self.cal_done = False
        self.cal_timeout = False
        self.caldb_valid = False
        self.caldb = []
        if caldb:
            self.caldb.append({"type": "CALDB", "size": caldb_size,
                               "paddr": 0x10000000, "mapped": True})
        self.caldb_idx = -1
        self.caldb_size = 0
        self.caldb_paddr = 0
        self.fw_ready = False
        self.timer_start = None
        self.timed_out = False
        self.reset_count = 0
        self.clock = 0

    def invalidate_caldb(self):
        self.cal_done = False
        self.caldb_valid = False
        self.caldb_idx = -1
        self.caldb_size = 0
        self.caldb_paddr = 0

    def fw_ready_event(self):
        self.fw_ready = True

    def worker_begin(self):
        if not self.fw_ready or self.state != IDLE:
            return
        # The mode-7 state is entered before the request so an immediate
        # CAL_DONE indication is not lost.
        self.state = WAIT_CAL

    def mode_send_ok(self):
        self.timer_start = self.clock

    def mode_send_fail(self):
        self.cal_timeout = True
        self.invalidate_caldb()
        self.state = RESET

    def cal_done_event(self):
        if (self.state != WAIT_CAL or self.cal_done or self.cal_timeout):
            return False
        found = [c for c in self.caldb if c["type"] == "CALDB"]
        if len(found) != 1 or not found[0]["mapped"]:
            self.cal_timeout = True
            return False
        self.caldb_idx = self.caldb.index(found[0])
        self.caldb_size = found[0]["size"]
        self.caldb_paddr = found[0]["paddr"]
        self.caldb_valid = True
        self.cal_done = True
        return True

    def advance(self, seconds):
        self.clock += seconds
        if (self.state == WAIT_CAL and self.timer_start is not None and
                not self.cal_done and
                self.clock >= self.timer_start + TIMEOUT_S):
            self.timed_out = True
            self.cal_timeout = True
            self.invalidate_caldb()
            self.state = RESET

    def worker_finish(self):
        success = not self.timed_out and self.cal_done and self.caldb_valid
        if not success:
            self.cal_timeout = True
            self.invalidate_caldb()
            if self.state == WAIT_CAL:
                self.state = RESET
        self.reset_count += 1
        self.state = COMPLETE if success else FAILED
        return success

    def host_cap_cal_done(self):
        return self.cal_done and self.caldb_valid

    def mission_mem_request(self, segments):
        if not self.caldb_valid:
            return True
        found = [i for i, (kind, _size, _paddr) in enumerate(segments)
                 if kind == "CALDB"]
        if len(found) != 1 or found[0] != self.caldb_idx:
            self.invalidate_caldb()
            raise IncompatibleCaldb("mission request has duplicate or moved CALDB")
        _kind, size, paddr = segments[found[0]]
        if (size != self.caldb_size or paddr != self.caldb_paddr or
                not self.caldb[self.caldb_idx]["mapped"]):
            self.invalidate_caldb()
            raise IncompatibleCaldb("CALDB replacement would lose calibrated data")
        return True


def source_checks():
    text = PATCH.read_text()
    work = text.split("static void ath12k_qmi_cold_boot_work", 1)[1]
    work = work.split("void ath12k_qmi_schedule_cold_boot", 1)[0]
    assert "ath12k_qmi_wlanfw_mode_send" in work
    assert "wait_for_completion_timeout(&qmi->cal_done_completion" in work
    assert (work.index("ath12k_qmi_wlanfw_mode_send") <
            work.index("wait_for_completion_timeout(&qmi->cal_done_completion"))
    assert "if (timeout && qmi->cal_done && qmi->caldb_valid)" in work
    assert "if (!qmi->cold_boot_cal || qmi->cal_done || qmi->cal_timeout)" not in work

    cb = text.split("static void ath12k_qmi_msg_cal_done_cb", 1)[1]
    cb = cb.split("static const struct qmi_msg_handler", 1)[0]
    assert "ATH12K_QMI_COLD_BOOT_WAIT_CAL" in cb
    assert "ath12k_qmi_cold_boot_find_caldb" in cb

    assert "rejecting incompatible mission CALDB request" in text
    assert "ath12k_qmi_cold_boot_mission_caldb_valid(&ab->qmi)" in text
    assert "return found == 1;" in text
    assert "chunk->prev_type != CALDB_MEM_REGION_TYPE" in text

    assert "req.cal_done = ath12k_qmi_cold_boot_caldb_valid(ab);" in text
    assert "ath12k_qmi_cold_boot_invalidate_caldb(ab);" in text


def test_fast_cal_done_still_restarts():
    cb = ColdBoot()
    cb.fw_ready_event()
    cb.worker_begin()
    cb.mode_send_ok()
    assert cb.cal_done_event()
    assert cb.worker_finish()
    assert cb.reset_count == 1
    assert cb.state == COMPLETE
    assert cb.host_cap_cal_done()


def test_timer_starts_after_mode_accept():
    cb = ColdBoot()
    cb.fw_ready_event()
    cb.worker_begin()
    cb.advance(1000)
    assert not cb.cal_timeout
    cb.mode_send_ok()
    cb.advance(TIMEOUT_S - 1)
    assert not cb.cal_timeout
    cb.advance(1)
    assert cb.cal_timeout
    assert not cb.worker_finish()
    assert cb.reset_count == 1


def test_late_cal_done_is_rejected():
    cb = ColdBoot()
    cb.fw_ready_event()
    cb.worker_begin()
    cb.mode_send_ok()
    cb.advance(TIMEOUT_S)
    assert cb.cal_timeout
    assert not cb.cal_done_event()
    assert not cb.worker_finish()
    assert not cb.host_cap_cal_done()


def test_cal_done_without_caldb_is_rejected():
    cb = ColdBoot(caldb=False)
    cb.fw_ready_event()
    cb.worker_begin()
    cb.mode_send_ok()
    assert not cb.cal_done_event()
    assert cb.cal_timeout
    assert not cb.worker_finish()
    assert not cb.host_cap_cal_done()


def test_deadline_race_is_rejected():
    cb = ColdBoot()
    cb.fw_ready_event()
    cb.worker_begin()
    cb.mode_send_ok()
    cb.clock = TIMEOUT_S
    cb.timed_out = True
    # A result delivered after the deadline but before the worker takes the
    # state lock must not become a successful calibration.
    cb.caldb_idx = 0
    cb.caldb_size = cb.caldb[0]["size"]
    cb.caldb_paddr = cb.caldb[0]["paddr"]
    cb.caldb_valid = True
    cb.cal_done = True
    assert not cb.worker_finish()
    assert not cb.host_cap_cal_done()


def test_mode_request_failure_still_restarts():
    cb = ColdBoot()
    cb.fw_ready_event()
    cb.worker_begin()
    cb.mode_send_fail()
    assert not cb.worker_finish()
    assert cb.reset_count == 1
    assert cb.state == FAILED


def test_mission_memory_keeps_caldb():
    cb = ColdBoot()
    cb.fw_ready_event()
    cb.worker_begin()
    cb.mode_send_ok()
    assert cb.cal_done_event()
    assert cb.worker_finish()
    assert cb.host_cap_cal_done()
    assert cb.mission_mem_request(
        [("CALDB", cb.caldb_size, cb.caldb_paddr)])


def test_mission_memory_replacement_is_rejected():
    cb = ColdBoot()
    cb.fw_ready_event()
    cb.worker_begin()
    cb.mode_send_ok()
    assert cb.cal_done_event()
    assert cb.worker_finish()
    try:
        cb.mission_mem_request(
            [("CALDB", cb.caldb_size // 2, cb.caldb_paddr)])
    except IncompatibleCaldb:
        pass
    else:
        raise AssertionError("incompatible CALDB request was accepted")
    assert not cb.host_cap_cal_done()
    assert not cb.caldb_valid


def test_mission_duplicate_caldb_request_is_rejected():
    cb = ColdBoot()
    cb.fw_ready_event()
    cb.worker_begin()
    cb.mode_send_ok()
    assert cb.cal_done_event()
    assert cb.worker_finish()
    segment = ("CALDB", cb.caldb_size, cb.caldb_paddr)
    try:
        cb.mission_mem_request([segment, segment])
    except IncompatibleCaldb:
        pass
    else:
        raise AssertionError("duplicate CALDB request was accepted")
    assert not cb.host_cap_cal_done()


def test_mission_omitted_caldb_request_is_rejected():
    cb = ColdBoot()
    cb.fw_ready_event()
    cb.worker_begin()
    cb.mode_send_ok()
    assert cb.cal_done_event()
    assert cb.worker_finish()
    try:
        cb.mission_mem_request([])
    except IncompatibleCaldb:
        pass
    else:
        raise AssertionError("CALDB-less mission request was accepted")
    assert not cb.host_cap_cal_done()


def main():
    source_checks()
    tests = [
        test_fast_cal_done_still_restarts,
        test_timer_starts_after_mode_accept,
        test_late_cal_done_is_rejected,
        test_cal_done_without_caldb_is_rejected,
        test_deadline_race_is_rejected,
        test_mode_request_failure_still_restarts,
        test_mission_memory_keeps_caldb,
        test_mission_memory_replacement_is_rejected,
        test_mission_duplicate_caldb_request_is_rejected,
        test_mission_omitted_caldb_request_is_rejected,
    ]
    for test in tests:
        test()
        print(f"ok {test.__name__}")
    print(f"{len(tests)} event-ordering tests passed")


if __name__ == "__main__":
    main()
