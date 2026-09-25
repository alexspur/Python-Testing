# utils/data_logger.py
import csv
import os
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
    - WJ_VOLTAGE: WJ power supply (param1=kV, param2=mA, param3=hv_on, param4=fault)
    - OPTA_PSI: Opta dome pressure (param1=psi, param2=input V, param3=raw counts,
      param4=OK/UNDER_RANGE/OVER_RANGE)
    - DG535_PULSE: DG535 pulse fired (param1=delay, param2=width)
    - BNC575_PULSE: BNC575 pulse fired (param1=mode, notes=settings)
    - BNC575_ARM: BNC575 armed (param1=trigger_level)
    - SCOPE_CAPTURE: Scope capture (param1=scope_id, param4=shot number)
    - SCOPE_EXPORT: one waveform CSV written or not (param2=file, notes OK/FAILED)
    - SCOPE_CHANNEL: per-channel capture stats and preamble (param2=channel)
    - CLIP_WARNING: samples on the ADC rails (param2=channel, param3=count)
    - CONFIG / CONNECT / DISCONNECT / TIMING: device settings, links, capture timing
    - ANALYSIS: one shot's analysis result (param1=status, param4=shot number)
    - SCOPE_ALL: All scopes captured
    - RELAY_COMMAND / RELAY_STATE: relay switching (param1=name, param2=requested,
      param3=confirmed or UNKNOWN, param4=ok/failed)
    - RELAY_MODE: one GROUND/FLOAT/CHARGE transition (param1=from, param2=to,
      param3=result, param4=HV-off wait s, notes=writes in order)
    - LASER_ARM / LASER_DISARM / LASER_FIRE / LASER_INTERLOCK / LASER_ERROR
    - INTERLOCK_CHECK / INTERLOCK_PASS / INTERLOCK_FAIL / FIRE_BLOCKED
    - SHOT: one row per real shot (param1=shot number), mirroring shot_log CSV
    - SESSION_START / SESSION_END

    Also owns the plain-text mirror of the on-screen GUI log,
    gui_log_<session ts>.txt, in the same session folder.
    """

    def __init__(self, log_dir="logs"):
        self.base_dir = Path(log_dir)
        self.base_dir.mkdir(exist_ok=True)

        # Single "now" shared by the day folder, the session folder, and the
        # session timestamp so the log file and every scope export line up.
        now = datetime.now()

        # Day folder for this launch: logs/YYYY.MM.DD
        self.day_dir = self.base_dir / now.strftime("%Y.%m.%d")
        self.day_dir.mkdir(exist_ok=True)

        # Session timestamp + name shared by the log file and all CSV exports.
        self.session_timestamp = now.strftime("%Y%m%d_%H%M%S")
        self.session_name = f"experiment_log_{self.session_timestamp}"

        # Per-launch folder named after the experiment log, inside the day
        # folder. Scope exports (rigol<N>_<timestamp>.csv), the shot log and
        # the GUI text log also land here.
        self.session_dir = self.day_dir / self.session_name
        self.session_dir.mkdir(exist_ok=True)

        # Kept for backwards-compatibility with code that references log_dir.
        self.log_dir = self.session_dir
        self.log_file = self.session_dir / f"{self.session_name}.csv"
        self.gui_log_file = self.session_dir / f"gui_log_{self.session_timestamp}.txt"

        # Thread lock for safe concurrent logging
        self.lock = threading.Lock()
        self._gui_lock = threading.Lock()

        # Start time for relative timestamps
        self.start_time = now

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
    # On-screen GUI log mirror (gui_log_<session ts>.txt)
    # ================================================================
    def append_gui_line(self, text):
        """Mirror one on-screen log line to the session's text log.

        Flushed and fsynced per line: the GUI is usually closed within seconds
        of a shot, so buffered lines would be lost.
        """
        stamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        try:
            with self._gui_lock:
                with open(self.gui_log_file, 'a', encoding='utf-8') as f:
                    f.write(f"[{stamp}] {text}\n")
                    f.flush()
                    os.fsync(f.fileno())
        except Exception:
            # Never let logging break the GUI.
            pass

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
    def log_wj_voltage(self, unit_id, kv, ma, hv_on=False, fault=False, state_source='readback'):
        """Log WJ power supply readback.

        hv_on / fault come from the supply's own Q reply (byte 11). Pass
        state_source='unknown' when the caller has no confirmed state so the
        row cannot be mistaken for a verified reading.
        """
        self._log_event(
            event_type='WJ_VOLTAGE',
            source=f'WJ{unit_id}',
            param1=f"{kv:.3f}",
            param2=f"{ma:.3f}",
            param3='1' if hv_on else '0',
            param4='1' if fault else '0',
            notes=(f"HV={'ON' if hv_on else 'OFF'}, Fault={'YES' if fault else 'NO'}, "
                   f"source={state_source}")
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
    # Opta Pressure Monitor Logging (Modbus TCP)
    # ================================================================
    def log_opta_pressure(self, psi, volts, counts, under_range=False, over_range=False):
        """Log an Opta dome pressure snapshot. param4 carries the sensor state so
        a dead transducer's 0.00 psi row can't be mistaken for a real reading."""
        if under_range:
            state = 'UNDER_RANGE'
        elif over_range:
            state = 'OVER_RANGE'
        else:
            state = 'OK'
        self._log_event(
            event_type='OPTA_PSI',
            source='Opta',
            param1=f"{psi:.2f}",
            param2=f"{volts:.3f}",
            param3=counts,
            param4=state
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

    def log_dg535_readback(self, channels, trigger_mode, source='DG535_laser'):
        """Log a full DG535 configuration readback (connect time / after apply).

        channels: {"A": (ref_name, delay_seconds), ...}
        """
        parts = [f"{ch}={ref}+{delay * 1e6:.6f}us" for ch, (ref, delay) in sorted(channels.items())]
        self._log_event(
            event_type='DG535_READBACK',
            source=source,
            param1=trigger_mode,
            notes=" ".join(parts)
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
    # Relay Logging (Numato)
    # ================================================================
    def log_relay_command(self, name, channel, requested, ok=True, confirmed=None):
        """Log a relay switch command.

        confirmed is None whenever the hardware gives no usable feedback: the
        Numato driver's get_state() returns the software's own cache, not a
        hardware read, so a commanded state is never reported as confirmed.
        """
        self._log_event(
            event_type='RELAY_COMMAND',
            source=f'Relay_CH{channel}',
            param1=name,
            param2='ON' if requested else 'OFF',
            param3='UNKNOWN' if confirmed is None else ('ON' if confirmed else 'OFF'),
            param4='ok' if ok else 'failed',
            notes=f"{name} (CH{channel}) commanded {'ON' if requested else 'OFF'}"
                  + ("" if ok else " - COMMAND FAILED")
        )

    def log_relay_mode(self, from_mode, to_mode, result, writes, hv_wait_s='', notes=''):
        """One three-state relay transition (GROUND / FLOAT / CHARGE).

        param1 = from, param2 = to, param3 = result (ok, refused, failed,
        timeout), param4 = seconds waited for the HV-off readback (blank when
        no wait was needed). notes lists every relay write in order as
        name=ON|OFF ok|FAILED, then the reason or context. Commanded, never
        read back: the Numato reports only its own cache.
        """
        rendered = ", ".join(
            f"{r}={'ON' if on else 'OFF'} {'ok' if ok else 'FAILED'}" for r, on, ok in writes
        ) or "no writes"
        self._log_event(
            event_type='RELAY_MODE',
            source='Relay',
            param1=from_mode,
            param2=to_mode,
            param3=result,
            param4=hv_wait_s,
            notes=f"writes: {rendered}" + (f"; {notes}" if notes else "")
        )

    def log_relay_state(self, states, source='commanded'):
        """Log the full relay picture. states: {name: True/False/None}"""
        rendered = ", ".join(
            f"{n}={'ON' if v else 'OFF' if v is not None else 'UNKNOWN'}"
            for n, v in states.items()
        )
        self._log_event(
            event_type='RELAY_STATE',
            source='Relay',
            param1=source,
            notes=rendered
        )

    # ================================================================
    # Laser Logging (CFR / ICE450)
    # ================================================================
    def log_laser_event(self, laser_tag, event, state='', detail=''):
        """Log a laser event: ARM, DISARM, FIRE, INTERLOCK, ERROR, PREP, STOP."""
        event_map = {
            'ARM': 'LASER_ARM',
            'DISARM': 'LASER_DISARM',
            'FIRE': 'LASER_FIRE',
            'INTERLOCK': 'LASER_INTERLOCK',
            'ERROR': 'LASER_ERROR',
        }
        self._log_event(
            event_type=event_map.get(event, f'LASER_{event}'),
            source=laser_tag,
            param1=event,
            param2=state,
            notes=detail
        )

    # ================================================================
    # Interlock Logging
    # ================================================================
    def log_interlock(self, event, step='', detail='', passed=None):
        """Log INTERLOCK_CHECK / INTERLOCK_PASS / INTERLOCK_FAIL."""
        self._log_event(
            event_type=f'INTERLOCK_{event}',
            source='Interlock',
            param1=step,
            param2='' if passed is None else ('pass' if passed else 'fail'),
            notes=detail
        )

    def log_fire_blocked(self, reason, detail=''):
        """A fire attempt that never reached the hardware. Consumes no shot number."""
        self._log_event(
            event_type='FIRE_BLOCKED',
            source='Shot',
            param1=reason,
            notes=detail
        )

    # ================================================================
    # Shot + session Logging
    # ================================================================
    def log_shot(self, shot_number, session_shot_index, notes=''):
        """Mirror a shot into the event log, so the timeline shows the trigger."""
        self._log_event(
            event_type='SHOT',
            source='Shot',
            param1=shot_number,
            param2=session_shot_index,
            notes=notes
        )

    def log_session_start(self, next_shot_number, gui_version, notes=''):
        self._log_event(
            event_type='SESSION_START',
            source='SYSTEM',
            param1=next_shot_number,
            param2=gui_version,
            notes=notes
        )

    def log_session_end(self, shots_this_session=0, notes=''):
        self._log_event(
            event_type='SESSION_END',
            source='SYSTEM',
            param1=shots_this_session,
            notes=notes
        )

    # ================================================================
    # Oscilloscope Logging
    # ================================================================
    def log_scope_capture(self, scope_id, num_points_ch1=0, num_points_ch2=0, shot_number=''):
        """Log individual scope capture"""
        self._log_event(
            event_type='SCOPE_CAPTURE',
            source=f'Rigol{scope_id}',
            param1=scope_id,
            param2=num_points_ch1,
            param3=num_points_ch2,
            param4=shot_number,
            notes=f"Rigol #{scope_id} captured (CH1:{num_points_ch1} pts, CH2:{num_points_ch2} pts)"
                  + (f" for shot {shot_number}" if shot_number != '' else "")
        )

    def log_scope_export(self, scope_id, filename, points, ok, shot_number='',
                         reason=''):
        """Log the outcome of writing one scope's waveform CSV.

        param1 = scope id, param2 = filename, param3 = total points written,
        param4 = shot number. notes begins "OK" or "FAILED" so the session
        report can tell whether the file named in the shot row actually
        exists with data in it.
        """
        self._log_event(
            event_type='SCOPE_EXPORT',
            source=f'Rigol{scope_id}',
            param1=scope_id,
            param2=filename,
            param3=points,
            param4=shot_number,
            notes=(f"OK: {points} pts written to {filename}" if ok
                   else f"FAILED: {filename} not written"
                        + (f" ({reason})" if reason else ""))
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

    def log_scope_channel(self, scope_id, channel, points, stats, shot_number=''):
        """One row per channel per capture, after the read: the outcome, the
        clip counts and the waveform preamble the volts were scaled with.

        param1 = scope id, param2 = channel, param3 = points read, param4 =
        shot number. notes is 'key=value; ...' in this order: state, clipped,
        clipped_low, clipped_high, code_min, code_max, v_min, v_max (the
        capturable range, ADC rail to rail, from the preamble), then the
        preamble fields format, xincrement, xorigin, yincrement, yorigin,
        yreference. A value the driver did not supply is omitted, not invented.
        """
        stats = stats or {}
        pairs = []
        for key in ("state", "clipped", "clipped_low", "clipped_high",
                    "code_min", "code_max", "v_min", "v_max"):
            if stats.get(key) is not None:
                pairs.append(f"{key}={stats[key]}")
        preamble = stats.get("preamble") or {}
        for key in ("format", "xincrement", "xorigin", "yincrement",
                    "yorigin", "yreference"):
            if preamble.get(key) is not None:
                pairs.append(f"{key}={preamble[key]}")
        self._log_event(
            event_type='SCOPE_CHANNEL',
            source=f'Rigol{scope_id}',
            param1=scope_id,
            param2=channel,
            param3=points,
            param4=shot_number,
            notes="; ".join(pairs)
        )

    def log_clip_warning(self, scope_id, channel, clipped, points, shot_number='',
                         low=0, high=0, code_min=None, code_max=None):
        """Samples on the ADC rails in one channel of one capture.

        param1 = scope id, param2 = channel, param3 = clipped sample count,
        param4 = shot number. notes says how many of how many, split by
        rail, with the raw code range that was seen.
        """
        self._log_event(
            event_type='CLIP_WARNING',
            source=f'Rigol{scope_id}',
            param1=scope_id,
            param2=channel,
            param3=clipped,
            param4=shot_number,
            notes=(f"CH{channel}: {clipped} of {points} samples on the ADC rails "
                   f"(low rail {low}, high rail {high}, codes {code_min}..{code_max})")
        )

    def log_analysis(self, shot_number, status, spacing_cmd_ns='', spacing_qsw_ns='',
                     spacing_rvm_ns='', error=''):
        """One shot's analysis result, from a '[ANALYSIS] result' line.

        param1 = status (ok, no_fire, missing_waveforms, failed), param2 =
        commanded pulse spacing in ns, param3 = spacing measured from the
        Q-switch monitors in ns, param4 = shot number (the per-shot key the
        other scope events use). notes = 'spacing_rvm_ns=<RVM-measured
        spacing>; error=<pipeline error or blank>'.
        """
        self._log_event(
            event_type='ANALYSIS',
            source='Analysis',
            param1=status,
            param2='' if spacing_cmd_ns is None else spacing_cmd_ns,
            param3='' if spacing_qsw_ns is None else spacing_qsw_ns,
            param4='' if shot_number is None else shot_number,
            notes=f"spacing_rvm_ns={'' if spacing_rvm_ns is None else spacing_rvm_ns}; "
                  f"error={error or ''}"
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
    # Device configuration, links and timing
    # ================================================================
    def log_config(self, source, group, settings, origin='readback'):
        """One CONFIG row per settings group, e.g. ('Rigol1', 'channel2', {...}).

        notes is 'key=value; key=value' in key order, so a device's whole
        configuration reads straight off the timeline. param2 records
        whether it was read back from the instrument or commanded by us.
        """
        rendered = "; ".join(f"{k}={settings[k]}" for k in sorted(settings, key=str))
        self._log_event(
            event_type='CONFIG',
            source=source,
            param1=group,
            param2=origin,
            notes=rendered
        )

    def log_connect(self, source, target, idn=''):
        """A device link came up. param1 = port or VISA resource, notes = *IDN?."""
        self._log_event(
            event_type='CONNECT',
            source=source,
            param1=target,
            notes=idn
        )

    def log_disconnect(self, source, reason=''):
        """A device link went down, by request or by failure."""
        self._log_event(
            event_type='DISCONNECT',
            source=source,
            notes=reason
        )

    def log_timing(self, source, summary, shot_number=''):
        """Per-scope capture timing, stamped inside the worker. param4 = shot."""
        self._log_event(
            event_type='TIMING',
            source=source,
            param4=shot_number,
            notes=summary
        )

    # ================================================================
    # File Management
    # ================================================================
    def get_log_file_path(self):
        """Return the current log file path"""
        return str(self.log_file)

    def get_session_dir(self):
        """Return the per-launch session folder (where exports should go)."""
        return str(self.session_dir)

    def get_logs_root(self):
        """Return the logs/ root that holds the day folders, the shot counter
        and the cumulative master shot log."""
        return str(self.base_dir)

    def scope_export_path(self, scope_id, shot_index=None):
        r"""Build the export path for a scope inside this launch's folder.

        The first shot of a session keeps the historic name
        rigol<N>_<session ts>.csv, because Post Test Analysis/parse_test_log.py
        finds waveform files with re.findall(r"(rigol\d_\d{8}_\d{6}\.csv)").

        A second or later shot in the same session would overwrite those
        files, so it gets rigol<N>_<session ts>_shot<NN>.csv. That name is not
        matched by the analysis regex (".csv" no longer follows the 6-digit
        time), so the old tooling ignores it instead of mis-parsing it.
        """
        stem = f"rigol{scope_id}_{self.session_timestamp}"
        if shot_index and shot_index > 1:
            stem += f"_shot{int(shot_index):02d}"
        return str(self.session_dir / f"{stem}.csv")

    def scope_read_path(self, scope_id, read_index):
        r"""Build the export path for a manual Read, never a shot.

        A Read pulls back the acquisition already in the scope's memory. It
        must never land on the shot's filename: pressing Read R1 after a shot
        used to rewrite all three rigol<N>_<session ts>.csv files through the
        auto-save path, replacing the shot's own data.

        The _read<NN> suffix also keeps these files away from
        Post Test Analysis/parse_test_log.py, whose
        re.findall(r"(rigol\d_\d{8}_\d{6}\.csv)") only matches a name ending
        right after the 6-digit time.
        """
        stem = f"rigol{scope_id}_{self.session_timestamp}_read{int(read_index):02d}"
        return str(self.session_dir / f"{stem}.csv")

    def close(self):
        """Close logger (placeholder for future cleanup if needed)"""
        print(f"[DataLogger] Log saved to: {self.log_file}")
