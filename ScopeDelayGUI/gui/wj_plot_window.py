# gui/wj_plot_window.py
"""
Background reader for a WJ power supply.

main_window starts one WJReaderThread per supply (see start_wj_readers); the
readings drive the SF6 window's kV/mA gauges and plot. Polling a supply is a
blocking serial round trip, so it never runs on the GUI thread.
"""

from PyQt6.QtCore import QThread, pyqtSignal
import time


class WJReaderThread(QThread):
    new_data = pyqtSignal(float, float, float)   # time, kV, mA
    # The whole Q reply: kV, mA plus the supply's own HV and fault bits. The
    # plot only needs kV/mA, but the shot log needs the real HV state, which
    # new_data drops.
    new_packet = pyqtSignal(dict)

    def __init__(self, wj, poll_interval=0.05):
        super().__init__()
        self.wj = wj
        self.poll_interval = poll_interval
        self.running = True
        self.t0 = time.time()

    def run(self):
        while self.running:
            try:
                data = self.wj.query()
                if data.get("type") == "R":
                    kv = data["kv"]
                    ma = data["ma"]
                    t = time.time() - self.t0
                    self.new_data.emit(t, kv, ma)
                    self.new_packet.emit(data)
            except Exception:
                pass

            self.msleep(int(self.poll_interval * 1000))

    def stop(self):
        self.running = False
        self.wait()
