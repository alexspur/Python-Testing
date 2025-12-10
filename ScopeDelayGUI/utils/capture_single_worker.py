# # utils/capture_single_worker.py
# from PyQt6.QtCore import QThread, pyqtSignal
# class CaptureSingleWorker(QThread):
#     finished = pyqtSignal(object, object, str)  # (t1v1, t2v2, name)
#     error = pyqtSignal(str)

#     def __init__(self, rigol, name):
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

#     # def run(self):
#     #     try:
#     #         self.rigol.inst.write(":STOP")
#     #         self.rigol.inst.write(":SINGLE")

#     #         # (t1, v1), (t2, v2) = self.rigol.wait_and_capture()

#     #         # self.finished.emit((t1, v1), (t2, v2), self.name)

#     #         (t1v1, t2v2) = self.rigol.wait_and_capture()
#     #         self.finished.emit(t1v1, t2v2, self.name)

#     #     except Exception as e:
#     #         self.error.emit(str(e))
# utils/capture_single_worker.py
from PyQt6.QtCore import QThread, pyqtSignal
from typing import Dict, Tuple, Optional
import numpy as np


class CaptureSingleWorker(QThread):
    """
    Worker thread for capturing waveforms from a single Rigol scope.
    Supports both legacy 2-channel and new N-channel capture modes.
    """
    
    # Signal for legacy 2-channel mode
    finished = pyqtSignal(object, object, str)  # (ch1_data, ch2_data, name)
    
    # Signal for N-channel mode (dict of channel data)
    finished_multi = pyqtSignal(dict, str)  # (channel_data_dict, name)
    
    error = pyqtSignal(str)

    def __init__(self, rigol, name, use_multi_channel: bool = True):
        """
        Initialize capture worker.
        
        Args:
            rigol: RigolScope instance
            name: Name for logging
            use_multi_channel: If True, capture all configured channels
        """
        super().__init__()
        self.rigol = rigol
        self.name = name
        self.use_multi_channel = use_multi_channel
        
    def run(self):
        try:
            self.rigol.inst.write(":STOP")
            self.rigol.inst.write(":SINGLE")

            if self.use_multi_channel:
                # New N-channel capture
                data = self.rigol.wait_and_capture()
                
                if data is None:
                    self.error.emit("No trigger detected for this scope.")
                    return
                
                # Emit multi-channel signal
                self.finished_multi.emit(data, self.name)
                
                # Also emit legacy signal for backward compatibility
                # Extract first two channels
                ch1_data = data.get("CHAN1", (np.array([]), np.array([])))
                ch2_data = data.get("CHAN2", (np.array([]), np.array([])))
                self.finished.emit(ch1_data, ch2_data, self.name)
                
            else:
                # Legacy 2-channel capture
                data = self.rigol.wait_and_capture_two()

                if data is None:
                    self.error.emit("No trigger detected for this scope.")
                    return

                (t1v1, t2v2) = data
                self.finished.emit(t1v1, t2v2, self.name)

        except Exception as e:
            self.error.emit(str(e))
