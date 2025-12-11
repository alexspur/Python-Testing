# # from PyQt6.QtCore import QThread, pyqtSignal


# # class CaptureSingleWorker(QThread):
# #     """
# #     Worker thread for capturing waveforms from a single Rigol scope.
# #     Assumes the scope has ALREADY been armed by the caller.
# #     """

# #     finished = pyqtSignal(object, object, str)  # (ch1_data, ch2_data, name)
# #     error = pyqtSignal(str)

# #     def __init__(self, rigol, name):
# #         """
# #         Initialize capture worker.

# #         Args:
# #             rigol: RigolScope instance
# #             name: Name for logging
# #         """
# #         super().__init__()
# #         self.rigol = rigol
# #         self.name = name

# #     def run(self):
# #         try:
# #             # Wait for trigger and capture
# #             data = self.rigol.wait_and_capture()

# #             if data is None:
# #                 self.error.emit("No trigger detected for this scope.")
# #                 return

# #             (t1v1, t2v2) = data
# #             self.finished.emit(t1v1, t2v2, self.name)

# #         except Exception as e:
# #             self.error.emit(str(e))
# # utils/capture_single_worker.py
# from PyQt6.QtCore import QThread, pyqtSignal


# class CaptureSingleWorker(QThread):
#     finished = pyqtSignal(object, object, str)  # (t1v1, t2v2, name)
#     error = pyqtSignal(str)

#     def __init__(self, rigol, name, **kwargs):
#         super().__init__()
#         self.rigol = rigol
#         self.name = name
        
#     def run(self):
#         try:
#             self.rigol.inst.write(":STOP")
#             self.rigol.inst.write(":SINGLE")

#             data = self.rigol.wait_and_capture()

#             if data is None:
#                 self.error.emit("No trigger detected for this scope.")
#                 return

#             (t1v1, t2v2) = data
#             self.finished.emit(t1v1, t2v2, self.name)

#         except Exception as e:
#             self.error.emit(str(e))

"""
Worker thread for single oscilloscope capture.

Runs capture in background thread to avoid blocking the GUI.
"""

from PyQt6.QtCore import QThread, pyqtSignal


class CaptureSingleWorker(QThread):
    """
    Worker thread for capturing waveform data from a single oscilloscope.

    Signals:
        finished: Emitted when capture completes with (ch1_data, ch2_data, scope_name)
                  where ch1_data = (t1, v1) and ch2_data = (t2, v2)
        error: Emitted on capture error with (error_message, scope_name)
    """

    # Signal: ((t1, v1), (t2, v2), scope_name)
    finished = pyqtSignal(object, object, str)

    # Signal: (error_message, scope_name)
    error = pyqtSignal(str, str)

    def __init__(self, scope, scope_name: str, timeout: float = 300.0, parent=None):
        """
        Initialize the capture worker.

        Args:
            scope: RigolScope instance (must already be connected)
            scope_name: Name identifier for this scope (e.g., 'R1', 'R2', 'R3')
            timeout: Capture timeout in seconds
            parent: Parent QObject
        """
        super().__init__(parent)
        self.scope = scope
        self.scope_name = scope_name
        self.timeout = timeout

    def run(self):
        """Execute the capture operation."""
        try:
            # Wait for trigger and capture both channels
            (t1, v1), (t2, v2) = self.scope.wait_and_capture(
                ch1=1, ch2=2, timeout=self.timeout
            )

            # Emit success signal with data
            self.finished.emit((t1, v1), (t2, v2), self.scope_name)

        except Exception as e:
            # Emit error signal
            self.error.emit(str(e), self.scope_name)
