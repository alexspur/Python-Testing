"""
Modbus TCP client for the Opta pressure monitor.

Pairs with opta_pressure_modbus.ino. Register map is documented there.

Requires pymodbus 3.x:  pip install "pymodbus>=3.6,<4"

Note on the slave keyword. pymodbus 2.x used unit=, 3.x uses slave=, and
recent 3.9+ releases renamed it to device_id=. _unit_kw picks whichever
your installed version accepts. The Opta server ignores the unit id.
"""

import inspect
import threading
import time

from pymodbus.client import ModbusTcpClient


# ---------------------------------------------------------------- calibration
#
# The transducer is a 0-10 V / 0-100 psi unit, so full scale at 10.0 V is
# 100.0 psi. These live in the Opta's holding registers, which reset to the
# firmware defaults on every Opta reboot, so the GUI writes them at each
# connect and verifies the readback rather than trusting whatever is loaded.
OPTA_FULL_SCALE_PSI = 100.0   # holding register 0, psi x10
OPTA_ZERO_OFFSET_MV = 0       # holding register 1
OPTA_AVG_SAMPLES = 32         # holding register 2


def _unit_kw(client):
    params = inspect.signature(client.read_input_registers).parameters
    for name in ("slave", "device_id", "unit"):
        if name in params:
            return name
    return None


class OptaPressure:
    """Blocking Modbus TCP interface to the Opta pressure monitor.

    Each call is one network round trip, roughly 2 to 10 ms on a
    point-to-point link. Call from a worker thread, never from the Qt GUI
    thread.
    """

    def __init__(self, host="192.168.10.20", port=502, timeout=1.0, unit=1,
                 retries=3):
        self.host = host
        self.port = port
        self.unit = unit
        # A dead link raises only after timeout * (retries + 1).
        self._client = ModbusTcpClient(
            host, port=port, timeout=timeout, retries=retries
        )
        self._kw = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------ lifecycle

    def connect(self):
        ok = self._client.connect()
        if ok and self._kw is None:
            self._kw = _unit_kw(self._client)
        return ok

    def close(self):
        self._client.close()

    @property
    def connected(self):
        return self._client.connected

    def _args(self):
        return {self._kw: self.unit} if self._kw else {}

    def _check(self, rr, what):
        if rr is None or rr.isError():
            raise IOError(f"Modbus {what} failed: {rr}")
        return rr

    # ------------------------------------------------------------ reads

    def read_psi(self):
        """Pressure in psi. One register read."""
        with self._lock:
            rr = self._client.read_input_registers(
                address=2, count=1, **self._args()
            )
        return self._check(rr, "read pressure").registers[0] / 100.0

    def read_all(self):
        """Full snapshot for a GUI poll tick. One register read."""
        with self._lock:
            rr = self._client.read_input_registers(
                address=0, count=5, **self._args()
            )
        regs = self._check(rr, "read snapshot").registers
        status = regs[4]
        return {
            "counts": regs[0],
            "volts": regs[1] / 1000.0,
            "psi": regs[2] / 100.0,
            "uptime_s": regs[3],
            "under_range": bool(status & 0x0001),
            "over_range": bool(status & 0x0002),
        }

    def read_calibration(self):
        with self._lock:
            rr = self._client.read_holding_registers(
                address=0, count=3, **self._args()
            )
        regs = self._check(rr, "read calibration").registers
        return {
            "full_scale_psi": regs[0] / 10.0,
            "zero_offset_mv": regs[1],
            "avg_samples": regs[2],
        }

    # ------------------------------------------------------------ calibration

    def set_full_scale_psi(self, psi):
        """Pressure at 10.0 V in. 100.0 for the 0-100 psi transducer."""
        value = int(round(psi * 10))
        if not 0 < value <= 65535:
            raise ValueError(f"full scale out of range: {psi}")
        with self._lock:
            rr = self._client.write_register(
                address=0, value=value, **self._args()
            )
        self._check(rr, "set full scale")

    def set_zero_offset_mv(self, mv):
        """Subtracted from the measured input before scaling to psi."""
        with self._lock:
            rr = self._client.write_register(
                address=1, value=int(mv), **self._args()
            )
        self._check(rr, "set zero offset")

    def set_averaging(self, samples):
        """Averaging depth, 1 to 64. Each sample is 2 ms of history."""
        if not 1 <= samples <= 64:
            raise ValueError("averaging must be 1 to 64")
        with self._lock:
            rr = self._client.write_register(
                address=2, value=int(samples), **self._args()
            )
        self._check(rr, "set averaging")

    def zero_here(self):
        """Take the current input as 0 psi. Vent the line first."""
        snap = self.read_all()
        self.set_zero_offset_mv(int(round(snap["volts"] * 1000)))
        return snap["volts"]

    def set_led(self, index, state):
        if not 0 <= index < 4:
            raise ValueError(f"LED index out of range: {index}")
        with self._lock:
            rr = self._client.write_coil(
                address=index, value=bool(state), **self._args()
            )
        self._check(rr, f"set LED {index}")

    # ------------------------------------------------------------ context

    def __enter__(self):
        if not self.connect():
            raise IOError(f"could not connect to Opta at {self.host}:{self.port}")
        return self

    def __exit__(self, *exc):
        self.close()
        return False


# ---------------------------------------------------------------- PyQt6 worker
#
# The GUI polls through utils/pressure_worker.py, which runs PressureWorker
# on its own QThread.


# ---------------------------------------------------------------- smoke test

def main():
    with OptaPressure("192.168.10.20") as opta:
        print("connected")
        print("calibration:", opta.read_calibration())
        print("streaming, ctrl-c to stop")

        try:
            while True:
                s = opta.read_all()
                flags = ""
                if s["under_range"]:
                    flags += " UNDER"
                if s["over_range"]:
                    flags += " OVER"
                print(
                    f"{s['volts']:.4f} V  {s['psi']:7.2f} psi  "
                    f"counts={s['counts']:4d}  up={s['uptime_s']}s{flags}"
                )
                time.sleep(0.2)
        except KeyboardInterrupt:
            print("\nstopped")


if __name__ == "__main__":
    main()
