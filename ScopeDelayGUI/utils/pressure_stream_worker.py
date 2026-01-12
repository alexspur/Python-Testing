# utils/pressure_stream_worker.py
"""
Stream worker for Arduino pressure sensor data with PSI calibration.

Parses the DATA format: DATA,count,mA0,mA1,raw2,voltage
- mA0, mA1: Current readings in milliamps (4-20mA sensors)
- raw2: Raw ADC value from pressure sensor (requires calibration)
- voltage: Output voltage to regulator (0-10V)

Converts raw ADC to PSI using linear interpolation with calibration table.
Converts mA0, mA1 to PSI using standard 4-20mA to 0-200 PSI mapping.
"""

from PyQt6.QtCore import QThread, pyqtSignal
import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class PressureData:
    """Container for parsed pressure sensor data."""
    count: int
    mA0: float       # Channel 0 current (mA)
    mA1: float       # Channel 1 current (mA)
    psi0: float      # Channel 0 PSI (from 4-20mA)
    psi1: float      # Channel 1 PSI (from 4-20mA)
    raw_adc: int     # Raw ADC from pressure sensor (AI2)
    psi2: float      # Channel 2 PSI (from raw ADC calibration)
    voltage: float   # Output voltage to regulator


class PressureCalibration:
    """
    Pressure sensor calibration using linear interpolation.

    Converts raw ADC values to PSI using a calibration table.
    Values outside the table range are clamped.
    """

    # Calibration table: raw ADC -> PSI
    CAL_N = 13
    RAW_TABLE = [10969, 12536, 16311, 19824, 22713, 25821, 29063, 32171, 35217, 38179, 41147, 43818, 45516]
    PSI_TABLE = [0.000, 5.800, 15.500, 22.520, 29.250, 36.890, 43.960, 51.100, 58.660, 66.060, 73.500, 79.100, 79.320]

    # Saturation clamp
    RAW_SAT = 45516
    PSI_SAT = 79.500

    # Minimum raw value (below this, clamp to 0 PSI)
    RAW_MIN = 10969
    PSI_MIN = 0.0

    @classmethod
    def raw_to_psi(cls, raw: int) -> float:
        """
        Convert raw ADC value to PSI using linear interpolation.

        Args:
            raw: Raw ADC value from pressure sensor

        Returns:
            Pressure in PSI
        """
        # Saturation clamp (high end)
        if raw >= cls.RAW_SAT:
            return cls.PSI_SAT

        # Below minimum (low end)
        if raw <= cls.RAW_MIN:
            return cls.PSI_MIN

        # Find the interpolation segment
        for i in range(cls.CAL_N - 1):
            raw_lo = cls.RAW_TABLE[i]
            raw_hi = cls.RAW_TABLE[i + 1]

            if raw_lo <= raw <= raw_hi:
                # Linear interpolation
                psi_lo = cls.PSI_TABLE[i]
                psi_hi = cls.PSI_TABLE[i + 1]

                # Avoid division by zero
                if raw_hi == raw_lo:
                    return psi_lo

                fraction = (raw - raw_lo) / (raw_hi - raw_lo)
                return psi_lo + fraction * (psi_hi - psi_lo)

        # Fallback (shouldn't reach here with valid data)
        return cls.PSI_SAT

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

    Continuously reads serial data, parses the DATA format, performs
    PSI calibration, and emits signals with converted values.

    Signals:
        data_signal(psi0, psi1, psi2, voltage): Emitted with all PSI values
        raw_data_signal(mA0, mA1, raw_adc, psi2, voltage): Raw data with calibrated PSI
        error_signal(str): Emitted on errors
    """

    # Signal with all PSI values: psi0, psi1, psi2 (calibrated), voltage
    data_signal = pyqtSignal(float, float, float, float)

    # Signal with raw values: mA0, mA1, raw_adc, psi2 (calibrated), voltage
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
        Get current sensor values with PSI conversion.

        Returns:
            Tuple of (psi0, psi1, psi2, voltage) or None if no data available
        """
        if self._latest_data is None:
            return None
        return (
            self._latest_data.psi0,
            self._latest_data.psi1,
            self._latest_data.psi2,
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

                # Read a line from serial
                try:
                    line = self.arduino.serial.readline().decode(errors="ignore").strip()
                except Exception as e:
                    self.error_signal.emit(f"Serial read error: {e}")
                    time.sleep(0.1)
                    continue

                # Parse DATA format: DATA,count,mA0,mA1,raw2,voltage
                if line.startswith("DATA,"):
                    try:
                        parts = line.split(",")
                        if len(parts) >= 6:
                            _, count_str, mA0_str, mA1_str, raw2_str, voltage_str = parts[:6]

                            count = int(count_str)
                            mA0 = float(mA0_str)
                            mA1 = float(mA1_str)
                            raw_adc = int(raw2_str)
                            voltage = float(voltage_str)

                            # Convert mA0, mA1 to PSI (4-20mA -> 0-200 PSI)
                            psi0 = PressureCalibration.mA_to_psi(mA0)
                            psi1 = PressureCalibration.mA_to_psi(mA1)

                            # Convert raw ADC to PSI using calibration table
                            psi2 = PressureCalibration.raw_to_psi(raw_adc)

                            # Store latest data
                            self._latest_data = PressureData(
                                count=count,
                                mA0=mA0,
                                mA1=mA1,
                                psi0=psi0,
                                psi1=psi1,
                                raw_adc=raw_adc,
                                psi2=psi2,
                                voltage=voltage
                            )

                            # Emit signals
                            self.data_signal.emit(psi0, psi1, psi2, voltage)
                            self.raw_data_signal.emit(mA0, mA1, raw_adc, psi2, voltage)

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


# Standalone utility functions for use outside the worker
def raw_adc_to_psi(raw: int) -> float:
    """
    Convert raw ADC value to PSI using calibration table.

    Args:
        raw: Raw ADC value from pressure sensor

    Returns:
        Pressure in PSI
    """
    return PressureCalibration.raw_to_psi(raw)


def mA_to_psi(mA: float) -> float:
    """
    Convert 4-20mA current to PSI (0-200 PSI range).

    Args:
        mA: Current in milliamps

    Returns:
        Pressure in PSI
    """
    return PressureCalibration.mA_to_psi(mA)
