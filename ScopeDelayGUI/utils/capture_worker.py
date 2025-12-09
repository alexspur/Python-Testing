# utils/capture_worker.py
from PyQt6.QtCore import QObject, QThread, pyqtSignal
import time

class CaptureWorker(QObject):
    finished = pyqtSignal()
    error = pyqtSignal(str)
    update = pyqtSignal(str)
    plot_result = pyqtSignal(int, object)

    def __init__(self, dg, bnc, scopes):
        super().__init__()
        self.dg = dg
        self.bnc = bnc
        self.scopes = scopes   # list of (connected?, scopeObj)

    def run(self):
        try:
            self.update.emit("Arming Rigol scopes...")

            # Arm scopes
            for connected, scope in self.scopes:
                if connected:
                    scope.arm()

            # Arm BNC575
            self.update.emit("Arming BNC575...")
            self.bnc.arm_external_trigger(level=3.0)

            # Fire DG535
            self.update.emit("Firing DG535...")
            self.dg.set_single_shot()
            self.dg.fire()

            time.sleep(0.35)

            # Capture from each scope
            # for idx, (connected, scope) in enumerate(self.scopes):
            #     if connected:
            #         try:
            #             # data = scope.wait_and_capture()
            #             # self.plot_result.emit(idx, data)
            #             (t1v1, t2v2) = scope.wait_and_capture()
            #             self.plot_result.emit(idx, (t1v1, t2v2))
            #         except Exception as e:
            #             self.update.emit(f"Rigol {idx+1} capture error: {e}")
            for idx, (connected, scope) in enumerate(self.scopes):
                if connected:
                    try:
                        data = scope.wait_and_capture()
                        if data is None:
                            self.update.emit(f"Rigol {idx+1}: No trigger detected.")
                            continue

                        (t1v1, t2v2) = data
                        self.plot_result.emit(idx, (t1v1, t2v2))

                    except Exception as e:
                        self.update.emit(f"Rigol {idx+1} capture error: {e}")


            self.finished.emit()

        except Exception as e:
            self.error.emit(str(e))
