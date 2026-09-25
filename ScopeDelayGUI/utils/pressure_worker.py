# utils/pressure_worker.py
"""
Polls the Opta pressure monitor over Modbus TCP on its own QThread.

Every OptaPressure call blocks on a network round trip, so none of them may
run on the GUI thread. The GUI never touches worker.io. It emits the
request_* signals, which Qt delivers queued into the worker's thread, and
listens to the result signals.

    thread = QThread()
    worker = PressureWorker("192.168.10.20")
    worker.moveToThread(thread)
    worker.data_ready.connect(...)
    thread.start()
    worker.request_connect.emit()
    ...
    worker.request_shutdown.emit()   # closes the socket, then quits the thread
    thread.wait()

A failed connect, poll or write stops the poll timer, closes the socket and
emits link_lost. Nothing reconnects on its own; the GUI offers Reconnect,
which emits request_connect again.
"""

from PyQt6.QtCore import QObject, QThread, QTimer, pyqtSignal, pyqtSlot

from instruments.opta_pressure import (
    OptaPressure, OPTA_FULL_SCALE_PSI, OPTA_ZERO_OFFSET_MV, OPTA_AVG_SAMPLES,
)


class PressureWorker(QObject):
    # Worker -> GUI
    data_ready = pyqtSignal(dict)          # read_all() snapshot, once per poll
    link_up = pyqtSignal(str)              # "host:port" after a good connect
    link_lost = pyqtSignal(str)            # reason; polling has stopped
    calibration_ready = pyqtSignal(dict)   # read_calibration(), after connect and each write
    calibration_mismatch = pyqtSignal(str) # readback differs from what we wrote
    command_done = pyqtSignal(str)         # calibration write accepted
    command_failed = pyqtSignal(str)       # calibration write refused, link still up

    # GUI -> worker. The slots are pyqtSlot-decorated so a request emitted on
    # the GUI thread runs in this object's thread after moveToThread.
    request_connect = pyqtSignal()
    request_disconnect = pyqtSignal()
    request_shutdown = pyqtSignal()
    request_full_scale = pyqtSignal(float)
    request_zero_here = pyqtSignal()

    def __init__(self, host="192.168.10.20", port=502, poll_ms=200,
                 timeout=0.5, retries=1):
        super().__init__()
        # A pulled fiber surfaces after roughly timeout * (retries + 1).
        self.io = OptaPressure(host, port=port, timeout=timeout, retries=retries)
        self.poll_ms = poll_ms
        self.timer = None

        self.request_connect.connect(self.open_link)
        self.request_disconnect.connect(self.close_link)
        self.request_shutdown.connect(self.shutdown)
        self.request_full_scale.connect(self.set_full_scale)
        self.request_zero_here.connect(self.zero_here)

    def _where(self):
        return f"{self.io.host}:{self.io.port}"

    # ------------------------------------------------------------ link

    @pyqtSlot()
    def open_link(self):
        self._stop_timer()
        self.io.close()
        try:
            if not self.io.connect():
                raise IOError("no TCP connection")
            cal = self._apply_calibration()
        except Exception as e:
            self._drop(f"could not reach Opta at {self._where()}: {e}")
            return

        self.link_up.emit(self._where())
        self.calibration_ready.emit(cal)
        # Created here, not in __init__, so the timer lives in this thread.
        if self.timer is None:
            self.timer = QTimer(self)
            self.timer.timeout.connect(self.poll)
        self.timer.start(self.poll_ms)

    @pyqtSlot()
    def poll(self):
        try:
            snap = self.io.read_all()
        except Exception as e:
            self._drop(str(e))
            return
        self.data_ready.emit(snap)

    @pyqtSlot()
    def close_link(self):
        self._stop_timer()
        self.io.close()

    @pyqtSlot()
    def shutdown(self):
        self.close_link()
        QThread.currentThread().quit()

    # ------------------------------------------------------------ calibration

    def _apply_calibration(self):
        """Write the known calibration, read it back and verify it.

        The Opta keeps these in RAM and reverts to the firmware defaults on
        every reboot, so writing at each connect is what keeps the reading
        trustworthy rather than whatever happens to be loaded. A mismatch
        does not drop the link: the pressure is still live, it just is not
        the calibration we asked for, and the GUI has to say so.
        """
        self.io.set_full_scale_psi(OPTA_FULL_SCALE_PSI)
        self.io.set_zero_offset_mv(OPTA_ZERO_OFFSET_MV)

        cal = self.io.read_calibration()
        problems = []
        # Full scale round-trips through an integer register (psi x10), so
        # compare with a tolerance rather than for equality.
        if abs(cal["full_scale_psi"] - OPTA_FULL_SCALE_PSI) > 0.05:
            problems.append(
                f"full scale {cal['full_scale_psi']:.1f} psi, expected {OPTA_FULL_SCALE_PSI:.1f}")
        if cal["zero_offset_mv"] != OPTA_ZERO_OFFSET_MV:
            problems.append(
                f"zero offset {cal['zero_offset_mv']} mV, expected {OPTA_ZERO_OFFSET_MV}")
        # Averaging is not written, only reported: it changes the response
        # time, never the calibration of the reading.
        if cal["avg_samples"] != OPTA_AVG_SAMPLES:
            problems.append(
                f"averaging {cal['avg_samples']} samples, expected {OPTA_AVG_SAMPLES}")

        cal["verified"] = not problems
        cal["mismatch"] = "; ".join(problems)
        if problems:
            self.calibration_mismatch.emit(cal["mismatch"])
        return cal

    @pyqtSlot(float)
    def set_full_scale(self, psi):
        self._command(lambda: self.io.set_full_scale_psi(psi),
                      lambda _: f"full scale set to {psi:.1f} psi")

    @pyqtSlot()
    def zero_here(self):
        self._command(self.io.zero_here,
                      lambda volts: f"zero offset set to {volts * 1000:.0f} mV")

    def _command(self, fn, describe):
        if self.timer is None or not self.timer.isActive():
            self.command_failed.emit("Opta link is not up")
            return
        try:
            result = fn()
        except ValueError as e:
            self.command_failed.emit(str(e))
            return
        except Exception as e:
            # A write can be refused with the link still fine. Probe before
            # tearing the link down over what may only be a bad value.
            try:
                self.io.read_all()
            except Exception:
                self._drop(str(e))
                return
            self.command_failed.emit(str(e))
            return

        self.command_done.emit(describe(result))
        try:
            self.calibration_ready.emit(self.io.read_calibration())
        except Exception as e:
            self._drop(str(e))

    # ------------------------------------------------------------ helpers

    def _stop_timer(self):
        if self.timer is not None:
            self.timer.stop()

    def _drop(self, reason):
        self._stop_timer()
        self.io.close()
        self.link_lost.emit(reason)
