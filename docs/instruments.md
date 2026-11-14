# Supported instruments

Drivers live in `ScopeDelayGUI/instruments/`. COM ports are remembered in
`connection_memory.json` at the repository root. Port numbers below are the
lab PC's values at the time of writing. Windows reassigns COM numbers, so
check Device Manager or `tools/instrument_checks/COMPort_Information.py`.

| Instrument | Role | Driver | Transport | Defaults |
| --- | --- | --- | --- | --- |
| BNC 575 pulse/delay generator | Master trigger | `bnc575.py` (`BNC575Controller`) | USB serial | 115200 baud, COM5 |
| SRS DG535 digital delay generator | Laser lamp and Q-switch timing | `dg535.py` (`DG535Controller`) | Prologix GPIB-USB, serial | 9600 baud, GPIB address 15, COM4 |
| Rigol DS7000 / MSO7000 scopes (×3) | RVMs, D-dots, B-dots, Q-switch monitors | `rigol.py` | VISA over LAN, raw socket | `TCPIP0::192.168.10.51-53::5555::SOCKET` |
| XP Glassman WJ 70-125 kV supplies (×2) | Marx charging, WJ1 negative and WJ2 positive | `wj.py` (`WJPowerSupply`), `glassman_id.py` | USB / RS-232 | 9600 baud. Ports resolved by firmware revision |
| Quantel CFR lasers (×2) | LTGS triggering | `cfr_laser.py` (`CFRLaserController`) | RS-232 over USB | 9600 baud |
| Numato 4-channel USB relay | Charging and grounding relays | `numato_relay.py` | USB CDC serial | 19200 baud, COM7 |
| Arduino Opta | Marx pressure monitor and regulator | `opta_pressure.py` | Modbus TCP over fiber Ethernet | `192.168.10.20:502`, polled every 200 ms |
| Arduino (legacy) | Analog streaming | `arduino.py` | USB serial | 115200 baud. Not used by the current GUI |

Manuals: `docs/manuals/` (BNC 575, DG535, Rigol DS7000 programming guide,
WJ supply).

Firmware for the Opta, the Glassman controller Arduinos and the Universal IO
Hat: `firmware/`. The Opta register map is in
`firmware/arduino/opta_pressure_modbus/opta_pressure_modbus.ino`.

## Start-up settings

`ScopeDelayGUI/main.py` holds the settings an operator changes most:

| Setting | Meaning |
| --- | --- |
| `AUTO_CONNECT` | Which instruments connect at start-up. Missing keys default to on |
| `OPTA_HOST`, `OPTA_PORT`, `OPTA_POLL_MS` | Opta pressure monitor link |
| `AUTO_SAVE_DELAY_SEC` | Delay before captured waveforms auto-save |
| `PRESSURE_GAUGE_MIN_PSI`, `PRESSURE_GAUGE_MAX_PSI` | Gauge scale, 0 to 100 psi transducer |
| `STARTUP_CHARGE_KV`, `STARTUP_CHARGE_MA` | Values preloaded into the WJ panels. Current limit is 6.0 mA |

To work on the GUI away from the lab, set every `AUTO_CONNECT` entry to
`False`. The window then opens without touching any port.

## Scope transport

`utils/connect_memory.py` builds every scope VISA string from
`SCOPE_TRANSPORT` (`"socket"` or `"instr"`) and `SCOPE_IPS`. It is the only
place those strings are built.

## What cannot be tested without hardware

The CI suite replaces every instrument with fakes. These behaviors need the
lab bench:

* Serial, GPIB and VISA command timing and replies for every driver.
* BNC 575 firing, DG535 delay readback, laser arming, WJ HV on and off.
* Full-depth scope capture and transfer speed.
* Opta Modbus polling over the fiber link.
* Relay switching and the GROUND / FLOAT / CHARGE sequence on real coils.
* Every script in `tools/calibration/`, `tools/instrument_checks/` and
  `tools/laser/` beyond import.
