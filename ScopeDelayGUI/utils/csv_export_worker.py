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
    
    def _export_two_channel(self):
        (t1, v1), (t2, v2) = self.data
        self.progress.emit(10)
        
        max_len = max(len(t1), len(t2))
        
        t1 = np.pad(t1, (0, max_len - len(t1)), constant_values=np.nan)
        v1 = np.pad(v1, (0, max_len - len(v1)), constant_values=np.nan)
        t2 = np.pad(t2, (0, max_len - len(t2)), constant_values=np.nan)
        v2 = np.pad(v2, (0, max_len - len(v2)), constant_values=np.nan)
        
        self.progress.emit(30)
        
        df = pd.DataFrame({
            'Time_CH1 (s)': t1,
            'Voltage_CH1 (V)': v1,
            'Time_CH2 (s)': t2,
            'Voltage_CH2 (V)': v2
        })
        
        self.progress.emit(50)
        df.to_csv(self.filename, index=False, float_format='%.9e')
        self.progress.emit(95)
        
    def _export_four_channel(self):
        (t1, v1), (t2, v2), (t3, v3), (t4, v4) = self.data
        self.progress.emit(10)
        
        max_len = max(len(t1), len(t2), len(t3), len(t4))
        
        t1 = np.pad(t1, (0, max_len - len(t1)), constant_values=np.nan)
        v1 = np.pad(v1, (0, max_len - len(v1)), constant_values=np.nan)
        t2 = np.pad(t2, (0, max_len - len(t2)), constant_values=np.nan)
        v2 = np.pad(v2, (0, max_len - len(v2)), constant_values=np.nan)
        t3 = np.pad(t3, (0, max_len - len(t3)), constant_values=np.nan)
        v3 = np.pad(v3, (0, max_len - len(v3)), constant_values=np.nan)
        t4 = np.pad(t4, (0, max_len - len(t4)), constant_values=np.nan)
        v4 = np.pad(v4, (0, max_len - len(v4)), constant_values=np.nan)
        
        self.progress.emit(35)
        
        df = pd.DataFrame({
            'Time_CH1 (s)': t1,
            'Voltage_CH1 (V)': v1,
            'Time_CH2 (s)': t2,
            'Voltage_CH2 (V)': v2,
            'Time_CH3 (s)': t3,
            'Voltage_CH3 (V)': v3,
            'Time_CH4 (s)': t4,
            'Voltage_CH4 (V)': v4
        })
        
        self.progress.emit(60)
        df.to_csv(self.filename, index=False, float_format='%.9e')
        self.progress.emit(95)