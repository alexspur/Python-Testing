# utils/capture_single_worker.py
from PyQt6.QtCore import QThread, pyqtSignal
class CaptureSingleWorker(QThread):
    finished = pyqtSignal(object, object, str)  # (t1v1, t2v2, name)
    error = pyqtSignal(str)

    def __init__(self, rigol, name):
        super().__init__()
        self.rigol = rigol
        self.name = name
        
    def run(self):
        try:
            self.rigol.inst.write(":STOP")
            self.rigol.inst.write(":SINGLE")

            data = self.rigol.wait_and_capture()

            if data is None:
                self.error.emit("No trigger detected for this scope.")
                return

            (t1v1, t2v2) = data
            self.finished.emit(t1v1, t2v2, self.name)

        except Exception as e:
            self.error.emit(str(e))

    # def run(self):
    #     try:
    #         self.rigol.inst.write(":STOP")
    #         self.rigol.inst.write(":SINGLE")

    #         # (t1, v1), (t2, v2) = self.rigol.wait_and_capture()

    #         # self.finished.emit((t1, v1), (t2, v2), self.name)

    #         (t1v1, t2v2) = self.rigol.wait_and_capture()
    #         self.finished.emit(t1v1, t2v2, self.name)

    #     except Exception as e:
    #         self.error.emit(str(e))