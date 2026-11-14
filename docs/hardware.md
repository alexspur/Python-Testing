# Hardware interfaces

The repository includes modules for the following systems. This is a code inventory, not a verified connection or operating procedure.

| Interface | Source module |
| --- | --- |
| Rigol oscilloscopes | `ScopeDelayGUI/instruments/rigol.py` |
| DG535 delay generator | `ScopeDelayGUI/instruments/dg535.py` |
| BNC 575 trigger generator | `ScopeDelayGUI/instruments/bnc575.py` |
| CFR laser interface | `ScopeDelayGUI/instruments/cfr_laser.py` |
| WJ power supply | `ScopeDelayGUI/instruments/wj.py` |
| Numato relay | `ScopeDelayGUI/instruments/numato_relay.py` |
| Opta pressure monitor | `ScopeDelayGUI/instruments/opta_pressure.py` |
| Arduino | `ScopeDelayGUI/instruments/arduino.py` |

The GUI includes auto-connect controls in `ScopeDelayGUI/main.py`. Their current defaults enable attempts to connect to multiple instruments.

## Operating precautions

- Confirm wiring, addressing, instrument readiness, interlocks, and the approved laboratory procedure before connecting.
- Do not treat GUI defaults as validated safe operating parameters.
- Keep automated tests isolated from physical hardware.
- Record instrument identifiers, firmware versions, calibration provenance, and cabling assignments for reproducibility.

See `ScopeDelayGUI/analysis/scope_channels.py` for code-defined shot-dependent probe and scope channel mappings. These mappings should be reviewed against experiment records before reuse.
