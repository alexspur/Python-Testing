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

    def run(self):
        try:
            while self.running:
                if not self.arduino.serial:
                    time.sleep(0.05)
                    continue

                line = self.arduino.serial.readline().decode(errors="ignore").strip()

                # Expect format: AI,<ch0>,<ch1>,<ch2>
                if line.startswith("AI,"):
                    try:
                        _, c0, c1, c2 = line.split(",")
                        self.data_signal.emit(float(c0), float(c1), float(c2))
                    except:
                        pass

                time.sleep(0.002)

        except Exception as e:
            self.error_signal.emit(str(e))

    def stop(self):
        self.running = False
        self.quit()
        self.wait()
