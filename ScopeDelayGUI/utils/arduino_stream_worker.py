# utils/arduino_stream_worker.py
from PyQt6.QtCore import QThread, pyqtSignal
import time

class ArduinoStreamWorker(QThread):
    data_signal = pyqtSignal(float, float, float)  # ch0, ch1, ch2
    error_signal = pyqtSignal(str)

    def __init__(self, arduino):
        super().__init__()
        self.arduino = arduino
        self.running = True
        self.poll_interval = 0.002  # seconds

    def run(self):
        try:
            while self.running:
                if not self.arduino.serial:
                    time.sleep(0.05)
                    continue

                line = self.arduino.serial.readline().decode(errors="ignore").strip()

                # Expect format: AI,<count>,<ch0>,<ch1>,<ch2> (count optional)
                if line.startswith("AI,"):
                    try:
                        parts = line.split(",")
                        if len(parts) == 4:
                            _, c0, c1, c2 = parts
                        elif len(parts) >= 5:
                            _, _, c0, c1, c2 = parts[:5]
                        else:
                            continue

                        self.data_signal.emit(float(c0), float(c1), float(c2))
                    except Exception:
                        pass

                time.sleep(self.poll_interval)

        except Exception as e:
            self.error_signal.emit(str(e))

    def stop(self):
        self.running = False
        self.quit()
        self.wait()
