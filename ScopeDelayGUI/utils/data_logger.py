# utils/data_logger.py
import csv
import threading
from datetime import datetime
from pathlib import Path


class DataLogger:
    """
    Centralized data logger for all instruments.
    Logs to CSV format for easy MATLAB import.

    CSV Format:
    timestamp, event_type, source, param1, param2, param3, param4, notes

    Event Types:
    - ARDUINO_PSI: Arduino pressure readings (param1=ch0, param2=ch1, param3=ch2)
    - WJ_VOLTAGE: WJ power supply (param1=unit_id, param2=kV, param3=mA, param4=hv_on)
    - DG535_PULSE: DG535 pulse fired (param1=delay, param2=width)
    - BNC575_PULSE: BNC575 pulse fired (param1=mode, notes=settings)
    - BNC575_ARM: BNC575 armed (param1=trigger_level)
    - SCOPE_CAPTURE: Scope capture (param1=scope_id)
    - SCOPE_ALL: All scopes captured
    """

    def __init__(self, log_dir="logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)

        # Create new log file with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = self.log_dir / f"experiment_log_{timestamp}.csv"

        # Thread lock for safe concurrent logging
        self.lock = threading.Lock()

        # Start time for relative timestamps
        self.start_time = datetime.now()

        # Initialize CSV file with header
        self._init_log_file()

        print(f"[DataLogger] Logging to: {self.log_file}")

    def _init_log_file(self):
        """Initialize CSV file with header"""
        with open(self.log_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                'timestamp_sec',
                'datetime',
                'event_type',
                'source',
                'param1',
                'param2',
                'param3',
                'param4',
                'notes'
            ])

    def _get_timestamp(self):
        """Get elapsed time in seconds since logger start"""
        elapsed = datetime.now() - self.start_time
        return elapsed.total_seconds()

    def _log_event(self, event_type, source, param1='', param2='', param3='', param4='', notes=''):
        """Internal method to log an event"""
        with self.lock:
            timestamp = self._get_timestamp()
            datetime_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

            with open(self.log_file, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    f"{timestamp:.6f}",
                    datetime_str,
                    event_type,
                    source,
                    param1,
                    param2,
                    param3,
                    param4,
                    notes
                ])

    # ================================================================
    # Arduino / SF6 Logging
    # ================================================================
    def log_arduino_psi(self, ch0_psi, ch1_psi, ch2_psi):
        """Log Arduino pressure sensor readings"""
        self._log_event(
            event_type='ARDUINO_PSI',
            source='Arduino',
            param1=f"{ch0_psi:.3f}",
            param2=f"{ch1_psi:.3f}",
            param3=f"{ch2_psi:.3f}"
        )

    def log_arduino_switch(self, switch_index, state):
        """Log Arduino digital output switch change"""
        self._log_event(
            event_type='ARDUINO_SWITCH',
            source='Arduino',
            param1=switch_index,
            param2=state,
            notes=f"DO{switch_index:02d} {'ON' if state else 'OFF'}"
        )

    # ================================================================
    # WJ Power Supply Logging
    # ================================================================
    def log_wj_voltage(self, unit_id, kv, ma, hv_on=False, fault=False):
        """Log WJ power supply readback"""
        self._log_event(
            event_type='WJ_VOLTAGE',
            source=f'WJ{unit_id}',
            param1=f"{kv:.3f}",
            param2=f"{ma:.3f}",
            param3='1' if hv_on else '0',
            param4='1' if fault else '0',
            notes=f"HV={'ON' if hv_on else 'OFF'}, Fault={'YES' if fault else 'NO'}"
        )

    def log_wj_command(self, unit_id, command, value=''):
        """Log WJ command sent (HV ON/OFF, SET, RESET)"""
        self._log_event(
            event_type='WJ_COMMAND',
            source=f'WJ{unit_id}',
            param1=command,
            param2=value,
            notes=f"{command} {value}"
        )

    # ================================================================
    # DG535 Delay Generator Logging
    # ================================================================
    def log_dg535_pulse(self, delay_a, width_a):
        """Log DG535 pulse fired"""
        self._log_event(
            event_type='DG535_PULSE',
            source='DG535',
            param1=f"{delay_a:.9e}",
            param2=f"{width_a:.9e}",
            notes=f"Delay={delay_a:.3e}s, Width={width_a:.3e}s"
        )

    def log_dg535_config(self, delay_a, width_a):
        """Log DG535 configuration change"""
        self._log_event(
            event_type='DG535_CONFIG',
            source='DG535',
            param1=f"{delay_a:.9e}",
            param2=f"{width_a:.9e}",
            notes=f"Configured: Delay={delay_a:.3e}s, Width={width_a:.3e}s"
        )

    # ================================================================
    # BNC575 Delay Generator Logging
    # ================================================================
    def log_bnc575_pulse(self, mode='INTERNAL', settings=''):
        """Log BNC575 pulse fired"""
        self._log_event(
            event_type='BNC575_PULSE',
            source='BNC575',
            param1=mode,
            notes=settings if settings else mode
        )

    def log_bnc575_arm(self, trigger_level):
        """Log BNC575 armed for external trigger"""
        self._log_event(
            event_type='BNC575_ARM',
            source='BNC575',
            param1=f"{trigger_level:.3f}",
            notes=f"Armed for EXT trigger at {trigger_level}V"
        )

    def log_bnc575_config(self, wa, da, wb, db, wc, dc, wd, dd):
        """Log BNC575 configuration"""
        settings = f"A:d={da:.3e},w={wa:.3e} B:d={db:.3e},w={wb:.3e} C:d={dc:.3e},w={wc:.3e} D:d={dd:.3e},w={wd:.3e}"
        self._log_event(
            event_type='BNC575_CONFIG',
            source='BNC575',
            param1=f"{wa:.9e}",
            param2=f"{da:.9e}",
            param3=f"{wb:.9e}",
            param4=f"{db:.9e}",
            notes=settings
        )

    # ================================================================
    # Oscilloscope Logging
    # ================================================================
    def log_scope_capture(self, scope_id, num_points_ch1=0, num_points_ch2=0):
        """Log individual scope capture"""
        self._log_event(
            event_type='SCOPE_CAPTURE',
            source=f'Rigol{scope_id}',
            param1=scope_id,
            param2=num_points_ch1,
            param3=num_points_ch2,
            notes=f"Rigol #{scope_id} captured (CH1:{num_points_ch1} pts, CH2:{num_points_ch2} pts)"
        )

    def log_scope_all_capture(self):
        """Log master capture event (all scopes triggered)"""
        self._log_event(
            event_type='SCOPE_ALL',
            source='ALL_SCOPES',
            notes='Master trigger - all scopes captured'
        )

    def log_scope_arm(self, scope_id):
        """Log scope armed for trigger"""
        self._log_event(
            event_type='SCOPE_ARM',
            source=f'Rigol{scope_id}',
            param1=scope_id,
            notes=f"Rigol #{scope_id} armed (SINGLE mode)"
        )

    # ================================================================
    # Generic Event Logging
    # ================================================================
    def log_custom(self, event_type, source, notes='', **params):
        """Log custom event with arbitrary parameters"""
        self._log_event(
            event_type=event_type,
            source=source,
            param1=params.get('param1', ''),
            param2=params.get('param2', ''),
            param3=params.get('param3', ''),
            param4=params.get('param4', ''),
            notes=notes
        )

    def log_error(self, source, error_msg):
        """Log error event"""
        self._log_event(
            event_type='ERROR',
            source=source,
            notes=error_msg
        )

    def log_info(self, source, message):
        """Log informational message"""
        self._log_event(
            event_type='INFO',
            source=source,
            notes=message
        )

    # ================================================================
    # File Management
    # ================================================================
    def get_log_file_path(self):
        """Return the current log file path"""
        return str(self.log_file)

    def close(self):
        """Close logger (placeholder for future cleanup if needed)"""
        print(f"[DataLogger] Log saved to: {self.log_file}")
