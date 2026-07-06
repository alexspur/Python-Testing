"""
CSV Export Worker - Non-blocking export to CSV files.
"""

from PyQt6.QtCore import QThread, pyqtSignal
import pandas as pd
import numpy as np


class CSVExportWorker(QThread):
    """Worker thread for exporting waveform data to CSV files."""
    
    progress = pyqtSignal(int)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    
    def __init__(self, data, filename: str, parent=None):
        super().__init__(parent)
        self.data = data
        self.filename = filename
        
    def run(self):
        try:
            self.progress.emit(5)
            
            num_channels = len(self.data)
            
            if num_channels == 2:
                self._export_two_channel()
            elif num_channels == 4:
                self._export_four_channel()
            else:
                raise ValueError(f"Unexpected channels: {num_channels}")
            
            self.progress.emit(100)
            self.finished.emit(self.filename)
            
        except Exception as e:
            self.error.emit(str(e))
    
    @staticmethod
    def _common_time_axis(time_arrays):
        """All channels on one scope share a single timebase, so emit ONE time
        column instead of one per channel. Use the longest non-empty time array
        as the axis (a disabled/empty channel has none of its own)."""
        non_empty = [np.asarray(t) for t in time_arrays if len(t) > 0]
        if not non_empty:
            return np.array([])
        return max(non_empty, key=len)

    @staticmethod
    def _pad_to(arr, length):
        arr = np.asarray(arr, dtype=float)
        if len(arr) < length:
            return np.pad(arr, (0, length - len(arr)), constant_values=np.nan)
        return arr

    def _export_two_channel(self):
        (t1, v1), (t2, v2) = self.data
        self.progress.emit(10)

        time_axis = self._common_time_axis([t1, t2])
        n = len(time_axis)

        self.progress.emit(30)

        df = pd.DataFrame({
            'Time (s)': time_axis,
            'Voltage_CH1 (V)': self._pad_to(v1, n),
            'Voltage_CH2 (V)': self._pad_to(v2, n),
        })

        self.progress.emit(50)
        df.to_csv(self.filename, index=False, float_format='%.9e')
        self.progress.emit(95)

    def _export_four_channel(self):
        (t1, v1), (t2, v2), (t3, v3), (t4, v4) = self.data
        self.progress.emit(10)

        time_axis = self._common_time_axis([t1, t2, t3, t4])
        n = len(time_axis)

        self.progress.emit(35)

        df = pd.DataFrame({
            'Time (s)': time_axis,
            'Voltage_CH1 (V)': self._pad_to(v1, n),
            'Voltage_CH2 (V)': self._pad_to(v2, n),
            'Voltage_CH3 (V)': self._pad_to(v3, n),
            'Voltage_CH4 (V)': self._pad_to(v4, n),
        })

        self.progress.emit(60)
        df.to_csv(self.filename, index=False, float_format='%.9e')
        self.progress.emit(95)