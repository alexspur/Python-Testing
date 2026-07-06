# utils/pressure_stream_worker.py
"""
Stream worker for Arduino pressure sensor data.

Parses the DATA format from stream_with_psi_conversion.ino:
    DATA,count,mA0,mA1,raw2,measured_psi,target_psi,voltage,expected_psi

Fields:
- count: Sample number
- mA0, mA1: Current readings in milliamps (4-20mA sensors)
- raw2: Raw ADC value from pressure sensor
- measured_psi: Actual pressure from sensor (calibrated on Arduino)
- target_psi: Setpoint pressure
- voltage: Control voltage sent to regulator (0-10V)
- expected_psi: Expected pressure based on voltage mapping

Arduino performs sensor calibration: PSI = 0.00228617 * raw_adc - 24.877300
"""

from PyQt6.QtCore import QThread, pyqtSignal
import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class PressureData:
    """Container for parsed pressure sensor data."""
    count: int
    mA0: float           # Channel 0 current (mA)
    mA1: float           # Channel 1 current (mA)
    psi0: float          # Channel 0 PSI (from 4-20mA)
    psi1: float          # Channel 1 PSI (from 4-20mA)
    raw_adc: int         # Raw ADC from pressure sensor (AI2)
    measured_psi: float  # Measured pressure from sensor (calibrated on Arduino)
    target_psi: float    # Target setpoint pressure
    voltage: float       # Control voltage to regulator
    expected_psi: float  # Expected pressure from voltage mapping


class PressureCalibration:
    """
    Pressure calibration utilities.

    Sensor calibration (done on Arduino):
        PSI = 0.00228617 * raw_adc - 24.877300

    4-20mA to PSI conversion for AI0/AI1 (0-200 PSI range).
    """

    @staticmethod
    def mA_to_psi(mA: float) -> float:
        """
        Convert 4-20mA current reading to PSI (0-200 PSI range).

        Args:
            mA: Current in milliamps

        Returns:
            Pressure in PSI
        """
        if mA < 4.0:
            return 0.0
        if mA > 20.0:
            return 200.0
        return (mA - 4.0) * 12.5  # (mA - 4) / 16 * 200


class PressureStreamWorker(QThread):
    """
    Background worker for streaming pressure sensor data from Arduino.

    Parses the new 9-field DATA format and emits signals with pressure values.

    Signals:
        data_signal(psi0, psi1, measured_psi, voltage): PSI values for gauges
        raw_data_signal(mA0, mA1, raw_adc, measured_psi, voltage): Raw data
        error_signal(str): Emitted on errors
    """

    # Signal with PSI values for gauges: psi0, psi1, measured_psi, voltage
    data_signal = pyqtSignal(float, float, float, float)

    # Signal with raw values: mA0, mA1, raw_adc, measured_psi, voltage
    raw_data_signal = pyqtSignal(float, float, int, float, float)

    # Error signal
    error_signal = pyqtSignal(str)

    def __init__(self, arduino):
        """
        Initialize the stream worker.

        Args:
            arduino: ArduinoController instance with active serial connection
        """
        super().__init__()
        self.arduino = arduino
        self.running = True
        self.poll_interval = 0.002  # 2ms polling interval

        # Latest parsed data (thread-safe access via property)
        self._latest_data: Optional[PressureData] = None

    @property
    def latest_data(self) -> Optional[PressureData]:
        """Get the most recent parsed data."""
        return self._latest_data

    def get_current_values(self) -> Optional[tuple]:
        """
        Get current sensor values.

        Returns:
            Tuple of (psi0, psi1, measured_psi, voltage) or None if no data
        """
        if self._latest_data is None:
            return None
        return (
            self._latest_data.psi0,
            self._latest_data.psi1,
            self._latest_data.measured_psi,
            self._latest_data.voltage
        )

    def run(self):
        """Main worker loop - reads and parses serial data."""
        try:
            while self.running:
                # Check if Arduino is connected
                if not self.arduino.serial:
                    time.sleep(0.05)
                    continue

                # Read a line from serial via the controller's thread-safe
                # readline so we share the lock with set_pressure_voltage /
                # set_digital_output / glassman_send_portenta. Otherwise the
                # GUI thread's write+read can race with this thread's read
                # and one of them ends up with a sliced response.
                try:
                    line = self.arduino.readline()
                except Exception as e:
                    self.error_signal.emit(f"Serial read error: {e}")
                    time.sleep(0.1)
                    continue

                # Parse DATA format (firmware after 2026-05-27 AI2 → 0-10 V switch):
                # DATA,count,mA0,mA1,ai2_v,measured_psi,target_psi,voltage,expected_psi,...
                # Field 4 is now a FLOAT (AI2 voltage) instead of an INT (raw ADC).
                if line.startswith("DATA,"):
                    try:
                        parts = line.split(",")
                        if len(parts) >= 9:
                            (_, count_str, mA0_str, mA1_str, ai2_v_str,
                             measured_psi_str, target_psi_str, voltage_str,
                             expected_psi_str) = parts[:9]

                            count = int(count_str)
                            mA0 = float(mA0_str)
                            mA1 = float(mA1_str)
                            ai2_v = float(ai2_v_str)               # was int(raw2)
                            measured_psi = float(measured_psi_str)
                            target_psi = float(target_psi_str)
                            voltage = float(voltage_str)
                            expected_psi = float(expected_psi_str)

                            # Convert mA0, mA1 to PSI (4-20mA -> 0-200 PSI)
                            psi0 = PressureCalibration.mA_to_psi(mA0)
                            psi1 = PressureCalibration.mA_to_psi(mA1)

                            # Store latest data. raw_adc field is now the AI2
                            # voltage rounded to an int for backwards compat
                            # with consumers that read raw_adc (none currently).
                            self._latest_data = PressureData(
                                count=count,
                                mA0=mA0,
                                mA1=mA1,
                                psi0=psi0,
                                psi1=psi1,
                                raw_adc=int(ai2_v * 1000),
                                measured_psi=measured_psi,
                                target_psi=target_psi,
                                voltage=voltage,
                                expected_psi=expected_psi
                            )

                            # Emit signals (measured_psi is the calibrated sensor reading)
                            self.data_signal.emit(psi0, psi1, measured_psi, voltage)
                            self.raw_data_signal.emit(mA0, mA1, int(ai2_v * 1000), measured_psi, voltage)

                    except (ValueError, IndexError):
                        # Malformed line, skip it
                        pass

                time.sleep(self.poll_interval)

        except Exception as e:
            self.error_signal.emit(f"Stream worker error: {e}")

    def stop(self):
        """Stop the worker thread."""
        self.running = False
        self.quit()
        self.wait()


# Standalone utility function
def mA_to_psi(mA: float) -> float:
    """
    Convert 4-20mA current to PSI (0-200 PSI range).

    Args:
        mA: Current in milliamps

    Returns:
        Pressure in PSI
    """
    return PressureCalibration.mA_to_psi(mA)
