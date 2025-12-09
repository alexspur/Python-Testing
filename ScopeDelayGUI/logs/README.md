# Experiment Data Logger

## Overview

This folder contains CSV log files from your Python GUI experiments. Every time you start the GUI, a new log file is created with a timestamp.

## Log File Format

**Filename**: `experiment_log_YYYYMMDD_HHMMSS.csv`

**Columns**:
- `timestamp_sec`: Time in seconds since logger started
- `datetime`: Human-readable timestamp
- `event_type`: Type of event (see below)
- `source`: Instrument that generated the event
- `param1`, `param2`, `param3`, `param4`: Event-specific parameters
- `notes`: Human-readable description

## Event Types

### Arduino / SF6 System
- **ARDUINO_PSI**: Pressure sensor readings
  - param1: Channel 0 pressure (PSI)
  - param2: Channel 1 pressure (PSI)
  - param3: Channel 2 pressure (PSI)

- **ARDUINO_SWITCH**: Digital output switch changes
  - param1: Switch index (0-7)
  - param2: State (0=OFF, 1=ON)

### WJ Power Supplies
- **WJ_VOLTAGE**: Voltage/current readback
  - param1: Voltage (kV)
  - param2: Current (mA)
  - param3: HV status (0=OFF, 1=ON)
  - param4: Fault status (0=NO, 1=YES)

- **WJ_COMMAND**: Commands sent to WJ
  - param1: Command type (HV_ON, HV_OFF, RESET, SET_PROGRAM)
  - param2: Command value (if applicable)

### DG535 Delay Generator
- **DG535_CONFIG**: Configuration change
  - param1: Delay A (seconds, scientific notation)
  - param2: Width A (seconds, scientific notation)

- **DG535_PULSE**: Pulse fired
  - param1: Delay A (seconds, scientific notation)
  - param2: Width A (seconds, scientific notation)

### BNC575 Delay Generator
- **BNC575_CONFIG**: Configuration change
  - param1: Width A (seconds)
  - param2: Delay A (seconds)
  - param3: Width B (seconds)
  - param4: Delay B (seconds)
  - notes: Full configuration string

- **BNC575_ARM**: Armed for external trigger
  - param1: Trigger level (V)

- **BNC575_PULSE**: Pulse fired
  - param1: Mode (INTERNAL or EXTERNAL)

### Oscilloscopes
- **SCOPE_ARM**: Scope armed for trigger
  - param1: Scope ID (1, 2, or 3)

- **SCOPE_CAPTURE**: Individual scope captured
  - param1: Scope ID (1, 2, or 3)
  - param2: Channel 1 data points
  - param3: Channel 2 data points

- **SCOPE_ALL**: Master capture event (all scopes triggered)

### Other Events
- **ERROR**: Error occurred
  - notes: Error message

- **INFO**: Informational message
  - notes: Information text

## Loading Data in MATLAB

### Method 1: Use the provided MATLAB script

```matlab
cd 'C:\Users\ESpurbeck.P3E-HIGHBAY-01\Desktop\LANL Project\GUI\Python Testing\ScopeDelayGUI\logs'
data = load_experiment_data();  % Automatically loads most recent file
```

This will:
- Load the most recent experiment log
- Print a summary of events
- Create comprehensive plots of all instrument data

### Method 2: Load specific file

```matlab
data = load_experiment_data('experiment_log_20250109_143022.csv');
```

### Method 3: Manual import

```matlab
% Read CSV file
opts = detectImportOptions('experiment_log_20250109_143022.csv');
opts = setvartype(opts, 'notes', 'string');
data = readtable('experiment_log_20250109_143022.csv', opts);

% Filter by event type
arduino_data = data(strcmp(data.event_type, 'ARDUINO_PSI'), :);
wj_data = data(strcmp(data.event_type, 'WJ_VOLTAGE'), :);
pulses = data(strcmp(data.event_type, 'DG535_PULSE'), :);

% Plot Arduino pressure
plot(arduino_data.timestamp_sec, str2double(arduino_data.param1), 'r-');
hold on;
plot(arduino_data.timestamp_sec, str2double(arduino_data.param2), 'g-');
plot(arduino_data.timestamp_sec, str2double(arduino_data.param3), 'b-');
xlabel('Time (s)');
ylabel('Pressure (PSI)');
legend('CH0', 'CH1', 'CH2');
```

## Example: Finding Pulse Events

```matlab
% Load data
data = load_experiment_data();

% Find all DG535 pulses
pulses = data(strcmp(data.event_type, 'DG535_PULSE'), :);

% Get pulse times
pulse_times = pulses.timestamp_sec;

% Find data within ±1 second of first pulse
first_pulse = pulse_times(1);
window_data = data(abs(data.timestamp_sec - first_pulse) < 1.0, :);

% Extract WJ voltage during that window
wj_window = window_data(strcmp(window_data.event_type, 'WJ_VOLTAGE'), :);
```

## Example: Correlating Events

```matlab
% Find when WJ HV was turned on
wj_hv_on = data(strcmp(data.event_type, 'WJ_COMMAND') & strcmp(data.param1, 'HV_ON'), :);

if ~isempty(wj_hv_on)
    hv_on_time = wj_hv_on.timestamp_sec(1);
    fprintf('WJ HV turned on at t = %.3f seconds\n', hv_on_time);

    % Find first pulse after HV was enabled
    pulses = data(strcmp(data.event_type, 'DG535_PULSE'), :);
    first_pulse_after = pulses(pulses.timestamp_sec > hv_on_time, :);

    if ~isempty(first_pulse_after)
        delay = first_pulse_after.timestamp_sec(1) - hv_on_time;
        fprintf('First pulse fired %.3f seconds after HV ON\n', delay);
    end
end
```

## Tips

1. **One log file per session**: Each time you start the GUI, a new log file is created
2. **Continuous logging**: All events are logged automatically - you don't need to do anything
3. **Timestamp synchronization**: All events use the same time reference (seconds since logger start)
4. **CSV format**: Easy to import into MATLAB, Python, Excel, or any other analysis tool
5. **Thread-safe**: Multiple instruments can log simultaneously without issues

## File Location

Log files are saved in:
```
C:\Users\ESpurbeck.P3E-HIGHBAY-01\Desktop\LANL Project\GUI\Python Testing\ScopeDelayGUI\logs\
```

The GUI will print the exact log file path when it starts.
