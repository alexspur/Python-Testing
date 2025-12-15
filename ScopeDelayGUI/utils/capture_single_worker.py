
# """
# Worker thread for single oscilloscope capture.

# Runs capture in background thread to avoid blocking the GUI.
# """

# from PyQt6.QtCore import QThread, pyqtSignal


# class CaptureSingleWorker(QThread):
#     """
#     Worker thread for capturing waveform data from a single oscilloscope.

#     Signals:
#         finished: Emitted when capture completes with (ch1_data, ch2_data, scope_name)
#                   where ch1_data = (t1, v1) and ch2_data = (t2, v2)
#         error: Emitted on capture error with (error_message, scope_name)
#     """

#     # Signal: ((t1, v1), (t2, v2), scope_name)
#     finished = pyqtSignal(object, object, str)

#     # Signal: (error_message, scope_name)
#     error = pyqtSignal(str, str)

#     def __init__(self, scope, scope_name: str, timeout: float = 300.0, parent=None):
#         """
#         Initialize the capture worker.

#         Args:
#             scope: RigolScope instance (must already be connected)
#             scope_name: Name identifier for this scope (e.g., 'R1', 'R2', 'R3')
#             timeout: Capture timeout in seconds
#             parent: Parent QObject
#         """
#         super().__init__(parent)
#         self.scope = scope
#         self.scope_name = scope_name
#         self.timeout = timeout

#     def run(self):
#         """Execute the capture operation."""
#         try:
#             # Wait for trigger and capture both channels
#             (t1, v1), (t2, v2) = self.scope.wait_and_capture(
#                 ch1=1, ch2=2, timeout=self.timeout
#             )

#             # Emit success signal with data
#             self.finished.emit((t1, v1), (t2, v2), self.scope_name)

#         except Exception as e:
#             # Emit error signal
#             self.error.emit(str(e), self.scope_name)
"""
Worker thread for single oscilloscope capture.

Runs capture in background thread to avoid blocking the GUI.
Supports both 2-channel (legacy) and 4-channel capture modes.
"""

from PyQt6.QtCore import QThread, pyqtSignal


class CaptureSingleWorker(QThread):
    """
    Worker thread for capturing waveform data from a single oscilloscope.

    Signals:
        finished: Emitted when 2-channel capture completes with (ch1_data, ch2_data, scope_name)
                  where ch1_data = (t1, v1) and ch2_data = (t2, v2)
        finished_four: Emitted when 4-channel capture completes with (data_tuple, scope_name)
                       where data_tuple = ((t1,v1), (t2,v2), (t3,v3), (t4,v4))
        error: Emitted on capture error with (error_message, scope_name)
    """

    # Signal: ((t1, v1), (t2, v2), scope_name) - 2 channel legacy
    finished = pyqtSignal(object, object, str)
    
    # Signal: (4-channel data tuple, scope_name)
    finished_four = pyqtSignal(object, str)

    # Signal: (error_message, scope_name)
    error = pyqtSignal(str, str)

    def __init__(self, scope, scope_name: str, timeout: float = 300.0, 
                 four_channel: bool = False, parent=None):
        """
        Initialize the capture worker.

        Args:
            scope: RigolScope instance (must already be connected)
            scope_name: Name identifier for this scope (e.g., 'R1', 'R2', 'R3')
            timeout: Capture timeout in seconds
            four_channel: If True, capture 4 channels; otherwise capture 2
            parent: Parent QObject
        """
        super().__init__(parent)
        self.scope = scope
        self.scope_name = scope_name
        self.timeout = timeout
        self.four_channel = four_channel

    def run(self):
        """Execute the capture operation."""
        try:
            if self.four_channel:
                # Wait for trigger and capture all four channels
                data = self.scope.wait_and_capture_four(
                    ch1=1, ch2=2, ch3=3, ch4=4, timeout=self.timeout
                )
                # Emit 4-channel signal
                self.finished_four.emit(data, self.scope_name)
            else:
                # Wait for trigger and capture two channels (legacy)
                (t1, v1), (t2, v2) = self.scope.wait_and_capture(
                    ch1=1, ch2=2, timeout=self.timeout
                )
                # Emit 2-channel signal
                self.finished.emit((t1, v1), (t2, v2), self.scope_name)

        except Exception as e:
            # Emit error signal
            self.error.emit(str(e), self.scope_name)


class CaptureFourChannelWorker(QThread):
    """
    Worker thread specifically for 4-channel capture.
    
    Signals:
        finished: Emitted when capture completes with 
                  (((t1,v1), (t2,v2), (t3,v3), (t4,v4)), scope_name)
        error: Emitted on capture error with (error_message, scope_name)
    """
    
    # Signal: (4-channel data tuple, scope_name)
    finished = pyqtSignal(object, str)
    
    # Signal: (error_message, scope_name)
    error = pyqtSignal(str, str)
    
    def __init__(self, scope, scope_name: str, timeout: float = 300.0, parent=None):
        """
        Initialize the 4-channel capture worker.

        Args:
            scope: RigolScope instance (must already be connected)
            scope_name: Name identifier for this scope
            timeout: Capture timeout in seconds
            parent: Parent QObject
        """
        super().__init__(parent)
        self.scope = scope
        self.scope_name = scope_name
        self.timeout = timeout
        
    def run(self):
        """Execute the 4-channel capture operation."""
        try:
            # Wait for trigger and capture all four channels
            data = self.scope.wait_and_capture_four(
                ch1=1, ch2=2, ch3=3, ch4=4, timeout=self.timeout
            )
            self.finished.emit(data, self.scope_name)
            
        except Exception as e:
            self.error.emit(str(e), self.scope_name)


class ImmediateFourChannelWorker(QThread):
    """
    Worker for immediate 4-channel capture (no trigger wait).
    
    Use this when the scope is already stopped with data on screen.
    """
    
    # Signal: (4-channel data tuple, scope_name)
    finished = pyqtSignal(object, str)
    
    # Signal: (error_message, scope_name)
    error = pyqtSignal(str, str)
    
    def __init__(self, scope, scope_name: str, parent=None):
        """
        Initialize immediate capture worker.

        Args:
            scope: RigolScope instance
            scope_name: Name identifier
            parent: Parent QObject
        """
        super().__init__(parent)
        self.scope = scope
        self.scope_name = scope_name
        
    def run(self):
        """Execute immediate 4-channel capture."""
        try:
            # Capture all four channels without waiting for trigger
            data = self.scope.capture_four_channels()
            self.finished.emit(data, self.scope_name)
            
        except Exception as e:
            self.error.emit(str(e), self.scope_name)
