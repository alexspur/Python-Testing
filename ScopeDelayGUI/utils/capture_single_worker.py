from PyQt6.QtCore import QThread, pyqtSignal


class CaptureSingleWorker(QThread):
    """
    Worker thread for capturing waveforms from a single Rigol scope.
    Assumes the scope has ALREADY been armed by the caller.
    """

    finished = pyqtSignal(object, object, str)  # (ch1_data, ch2_data, name)
    error = pyqtSignal(str)

    def __init__(self, rigol, name):
        """
        Initialize capture worker.

        Args:
            rigol: RigolScope instance
            name: Name for logging
        """
        super().__init__()
        self.rigol = rigol
        self.name = name

    def run(self):
        try:
            # Wait for trigger and capture
            data = self.rigol.wait_and_capture()

            if data is None:
                self.error.emit("No trigger detected for this scope.")
                return

            (t1v1, t2v2) = data
            self.finished.emit(t1v1, t2v2, self.name)

        except Exception as e:
            self.error.emit(str(e))
