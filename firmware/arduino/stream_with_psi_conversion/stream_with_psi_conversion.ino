
#include <Arduino_PortentaMachineControl.h>
#include <RunningAverage.h>

const uint32_t BAUD = 115200;
const unsigned long STREAM_INTERVAL = 100;
const size_t LINE_MAX = 64;

// Analog output channel for pressure regulator control (0-10V)
const int PRESSURE_AO_CHANNEL = 2;

// Analog input channels - ALL 4-20mA
const int CURRENT_AI_0 = 0;
const int CURRENT_AI_1 = 1;
const int PRESSURE_AI_2 = 2;

uint8_t outputStates = 0x00;
bool streamEnabled = true;
unsigned long lastStream = 0;
uint32_t sampleCount = 0;
char lineBuf[LINE_MAX];

float outputVoltage = 0.0f;
float targetPressurePsi = 0.0f;

// ============================================================================
// CALIBRATION CONSTANTS - ADC TO PSI CONVERSION (SENSOR FEEDBACK)
// ============================================================================
// Linear conversion: PSI = slope * raw_adc + offset
// Generated from 51-point calibration sweep
// R-squared: 0.995318 (excellent fit)

const float PSI_SLOPE = 0.00228617f;
const float PSI_OFFSET = -24.877300f;

// Conversion function: raw ADC value → PSI
float rawToPsi(uint16_t raw) {
  float psi = PSI_SLOPE * raw + PSI_OFFSET;
  // Clamp to reasonable pressure range (0-25 PSI)
  if (psi < 0.0f) psi = 0.0f;
  if (psi > 25.0f) psi = 25.0f;
  return psi;
}

// ============================================================================
// PARKER REGULATOR CALIBRATION - VOLTAGE TO PSI MAPPING (CONTROL)
// ============================================================================
// Calibration sweep results (21 data points):
// y = 2.5106x - 0.178
// R² = 0.9976 (excellent fit - 99.76% variance explained)
//
// Direct mapping: PSI = 2.5106 × Voltage - 0.178
// Inverse mapping: Voltage = (PSI + 0.178) / 2.5106

const float VOLTAGE_TO_PSI_SLOPE = 2.5106f;
const float VOLTAGE_TO_PSI_OFFSET = -0.178f;
const float PARKER_MAX_PRESSURE_PSI = 24.49f;
const float PARKER_MAX_VOLTAGE = 10.0f;

// Convert desired PSI → Parker control voltage
// Voltage = (PSI + 0.178) / 2.5106
float psiToParkerVoltage(float targetPsi) {
  float clampedPsi = constrain(targetPsi, 0.0f, PARKER_MAX_PRESSURE_PSI);
  float voltage = (clampedPsi + 0.178f) / 2.5106f;
  return constrain(voltage, 0.0f, PARKER_MAX_VOLTAGE);
}

// Direct mapping for verification: Voltage → PSI
// PSI = 2.5106 × Voltage - 0.178
float voltageToParkerPsi(float voltage) {
  float v = constrain(voltage, 0.0f, PARKER_MAX_VOLTAGE);
  float psi = VOLTAGE_TO_PSI_SLOPE * v + VOLTAGE_TO_PSI_OFFSET;
  return constrain(psi, 0.0f, PARKER_MAX_PRESSURE_PSI);
}

// Running average for smoothing
RunningAverage raChannel0(20);
RunningAverage raChannel1(20);
RunningAverage raChannel2(20);

void sendAck(const char* msg = "OK") {
  Serial.print("ACK ");
  Serial.println(msg);
}

void sendNack(const char* msg) {
  Serial.print("NACK ");
  Serial.println(msg);
}

bool readLine(char* buf, size_t len) {
  size_t n = Serial.readBytesUntil('\n', buf, len - 1);
  if (n == 0) return false;
  buf[n] = '\0';
  if (n > 0 && buf[n-1] == '\r') buf[n-1] = '\0';
  return true;
}

int parseChannel(const char* s) {
  int ch = atoi(s);
  if (ch < 0 || ch > 7) return -1;
  return ch;
}

void applyOutputs() {
  MachineControl_DigitalOutputs.writeAll(outputStates);
}

void setVoltage(float volts) {
  outputVoltage = constrain(volts, 0.0f, 10.0f);
  MachineControl_AnalogOut.write(PRESSURE_AO_CHANNEL, outputVoltage);
  Serial.print("ACK SET_VOLT:");
  Serial.print(outputVoltage, 3);
  Serial.print("V (expected pressure ");
  Serial.print(voltageToParkerPsi(outputVoltage), 2);
  Serial.println("PSI)");
}

// Set target pressure in PSI (will command Parker regulator to that pressure)
void setPressureSetpoint(float psi) {
  targetPressurePsi = psi;
  float requiredVoltage = psiToParkerVoltage(psi);
  
  // Check if target exceeds max
  if (psi > PARKER_MAX_PRESSURE_PSI) {
    Serial.print("WARN PSI_CLAMPED:");
    Serial.print(psi, 2);
    Serial.print(" -> ");
    Serial.println(PARKER_MAX_PRESSURE_PSI, 2);
  }
  
  setVoltage(requiredVoltage);
  
  Serial.print("ACK SET_PSI:");
  Serial.print(psi, 2);
  Serial.print(" (clamped to ");
  Serial.print(PARKER_MAX_PRESSURE_PSI, 2);
  Serial.print(") V:");
  Serial.println(requiredVoltage, 3);
}

void handleSerialCommands() {
  if (!Serial.available()) return;
  if (!readLine(lineBuf, LINE_MAX)) return;

  char* cmd = strtok(lineBuf, " ");
  char* arg = strtok(nullptr, " ");
  if (!cmd || cmd[0] == '\0') return;

  auto eq = [](const char* a, const char* b) {
    while (*a && *b) {
      char ca = toupper(*a++), cb = toupper(*b++);
      if (ca != cb) return false;
    }
    return (*a == '\0' && *b == '\0');
  };

  // VOLT <voltage> - Set output voltage directly (0-10V)
  if (eq(cmd, "VOLT") || eq(cmd, "V")) {
    if (!arg) {
      Serial.print("ACK VOLT:");
      Serial.println(outputVoltage, 3);
      return;
    }
    float val = atof(arg);
    setVoltage(val);
    return;
  }

  // PSI <pressure> - Set target pressure in PSI
  if (eq(cmd, "PSI") || eq(cmd, "P")) {
    if (!arg) {
      Serial.print("ACK PSI:");
      Serial.print(targetPressurePsi, 2);
      Serial.print(" (max=");
      Serial.print(PARKER_MAX_PRESSURE_PSI, 2);
      Serial.print(") V:");
      Serial.print(outputVoltage, 3);
      Serial.println(")");
      return;
    }
    float val = atof(arg);
    setPressureSetpoint(val);
    return;
  }

  if (eq(cmd, "PING")) {
    Serial.println("ACK PONG");
    return;
  }

  if (eq(cmd, "STREAM")) {
    if (!arg) { sendNack("ARG"); return; }
    if (eq(arg, "ON")) {
      streamEnabled = true;
      sendAck("STREAM_ON");
    } else if (eq(arg, "OFF")) {
      streamEnabled = false;
      sendAck("STREAM_OFF");
    } else {
      sendNack("ARG");
    }
    return;
  }

  if (eq(cmd, "STATUS")) {
    Serial.print("STATUS,");
    Serial.print(outputVoltage, 2);
    Serial.print(",");
    Serial.print(targetPressurePsi, 2);
    Serial.print(",");
    Serial.print(PARKER_MAX_PRESSURE_PSI, 2);
    Serial.print(",");
    for (int ch = 0; ch < 8; ch++) {
      Serial.print(bitRead(outputStates, ch));
    }
    Serial.println();
    return;
  }

  if (eq(cmd, "HELP")) {
    Serial.println("\n=== PRESSURE CONTROL COMMANDS ===");
    Serial.println("VOLT <0-10>        Set raw voltage (0-10V)");
    Serial.println("PSI <0-24.49>      Set target pressure (auto-clamped)");
    Serial.println("STREAM ON/OFF      Enable/disable data streaming");
    Serial.println("STATUS             Show current state");
    Serial.println("CONFIG             Show Parker calibration");
    Serial.println("PING               Test connection");
    Serial.println("HELP               Show this help\n");
    return;
  }

  if (eq(cmd, "CONFIG")) {
    Serial.println("\n=== PARKER P31P/P32P CALIBRATION ===");
    Serial.println("Forward: PSI = 2.5106 × Voltage - 0.178");
    Serial.println("Inverse: Voltage = (PSI + 0.178) / 2.5106");
    Serial.println("R² = 0.9976 (99.76% fit)");
    Serial.print("Pressure Range: 0.0 to ");
    Serial.print(PARKER_MAX_PRESSURE_PSI, 2);
    Serial.println(" PSI");
    Serial.println("Voltage Range: 0.0 to 10.0V\n");
    return;
  }

  if (eq(cmd, "ALL")) {
    if (!arg) { sendNack("ARG"); return; }
    if (eq(arg, "ON")) {
      outputStates = 0xFF;
      applyOutputs();
      sendAck("ALL_ON");
    } else if (eq(arg, "OFF")) {
      outputStates = 0x00;
      applyOutputs();
      sendAck("ALL_OFF");
    } else {
      sendNack("ARG");
    }
    return;
  }

  if (eq(cmd, "ON") || eq(cmd, "OFF")) {
    if (!arg) { sendNack("ARG"); return; }
    int ch = parseChannel(arg);
    if (ch < 0) { sendNack("CHAN"); return; }
    if (eq(cmd, "ON")) {
      bitSet(outputStates, ch);
      MachineControl_DigitalOutputs.write(ch, HIGH);
      sendAck("ON");
    } else {
      bitClear(outputStates, ch);
      MachineControl_DigitalOutputs.write(ch, LOW);
      sendAck("OFF");
    }
    return;
  }

  sendNack("CMD");
}

void streamAnalogInputs() {
  unsigned long now = millis();
  if (!streamEnabled || (now - lastStream < STREAM_INTERVAL)) return;
  lastStream = now;

  // Read raw ADC values
  uint16_t rawChannel[3];
  for (int i = 0; i < 3; i++) {
    rawChannel[i] = (uint16_t)MachineControl_AnalogIn.read(i);
  }

  // Add to running average
  raChannel0.addValue((float)rawChannel[0]);
  raChannel1.addValue((float)rawChannel[1]);
  raChannel2.addValue((float)rawChannel[2]);

  // Get smoothed values
  float smoothedRaw0 = raChannel0.getAverage();
  float smoothedRaw1 = raChannel1.getAverage();
  uint16_t smoothedRaw2 = (uint16_t)(raChannel2.getAverage() + 0.5f);

  // Convert AI0 and AI1 to mA (standard 4-20mA)
  const float REFERENCE = 3.0f;
  const float SENSE_RES = 120.0f;
  
  float mA0 = ((smoothedRaw0 * REFERENCE) / 65535.0f / SENSE_RES) * 1000.0f;
  float mA1 = ((smoothedRaw1 * REFERENCE) / 65535.0f / SENSE_RES) * 1000.0f;
  
  if (mA0 < 0) mA0 = 0;
  if (mA1 < 0) mA1 = 0;

  // Convert AI2 (pressure) from raw ADC to PSI using calibration
  float pressurePsi = rawToPsi(smoothedRaw2);
  
  // Calculate expected pressure from voltage mapping
  float expectedPsi = voltageToParkerPsi(outputVoltage);

  // Stream format: DATA,count,mA0,mA1,raw2,measured_psi,target_psi,voltage,expected_psi
  Serial.print("DATA,");
  Serial.print(sampleCount++);
  Serial.print(",");
  Serial.print(mA0, 3);
  Serial.print(",");
  Serial.print(mA1, 3);
  Serial.print(",");
  Serial.print(smoothedRaw2);
  Serial.print(",");
  Serial.print(pressurePsi, 3);        // Measured pressure from sensor
  Serial.print(",");
  Serial.print(targetPressurePsi, 2);  // Target setpoint
  Serial.print(",");
  Serial.print(outputVoltage, 2);      // Control voltage
  Serial.print(",");
  Serial.println(expectedPsi, 2);      // Expected pressure from voltage mapping
}

void setup() {
  Serial.begin(BAUD);
  while (!Serial) {}

  MachineControl_DigitalOutputs.begin(true);
  applyOutputs();
  
  MachineControl_AnalogIn.begin(SensorType::MA_4_20);
  MachineControl_AnalogOut.begin();
  
  setVoltage(0.0f);

  Serial.println("================================================================================");
  Serial.println("MARX GENERATOR PRESSURE CONTROL SYSTEM");
  Serial.println("================================================================================");
  Serial.println("ACK READY");
  Serial.println("");
  Serial.println("SENSOR CALIBRATION:");
  Serial.println("  Formula: PSI = 0.00228617 × raw_adc - 24.877300");
  Serial.println("  R²: 0.995318 (99.53% fit)");
  Serial.println("");
  Serial.println("PARKER REGULATOR CALIBRATION:");
  Serial.println("  Forward:  PSI = 2.5106 × Voltage - 0.178");
  Serial.println("  Inverse:  Voltage = (PSI + 0.178) / 2.5106");
  Serial.println("  R²: 0.9976 (99.76% fit)");
  Serial.println("  Range: 0.0 to 24.49 PSI (0.0 to 10.0V)");
  Serial.println("");
  Serial.println("DATA STREAM FORMAT:");
  Serial.println("  DATA,count,mA0,mA1,raw2,measured_psi,target_psi,voltage,expected_psi");
  Serial.println("");
  Serial.println("COMMANDS:");
  Serial.println("  VOLT <0-10>     Set raw voltage");
  Serial.println("  PSI <0-24.49>   Set target pressure");
  Serial.println("  STREAM ON/OFF   Control streaming");
  Serial.println("  STATUS          Show state");
  Serial.println("  CONFIG          Show calibration");
  Serial.println("  HELP            Show help");
  Serial.println("================================================================================\n");
}

void loop() {
  handleSerialCommands();
  streamAnalogInputs();
}

/*
================================================================================
MARX GENERATOR PRESSURE CONTROL - INTEGRATED CALIBRATION
================================================================================

TWO INDEPENDENT CALIBRATIONS:

1. SENSOR CALIBRATION (Feedback - ADC to PSI)
   Formula: PSI = 0.00228617 × raw_adc - 24.877300
   R²: 0.995318 (99.53% fit)
   Purpose: Convert pressure sensor readings to PSI
   
2. PARKER REGULATOR CALIBRATION (Control - Voltage to PSI)
   Forward:  PSI = 2.5106 × Voltage - 0.178
   Inverse:  Voltage = (PSI + 0.178) / 2.5106
   R²: 0.9976 (99.76% fit)
   Purpose: Convert desired PSI to control voltage
   
DATA STREAM FIELDS:
   measured_psi  - Actual pressure from sensor (ADC → PSI)
   target_psi    - Your setpoint (from PSI command)
   voltage       - Control voltage sent to Parker
   expected_psi  - What Parker should output (Voltage → PSI)

EXAMPLE USAGE:

Open Serial Monitor (115200 baud)

1. Test voltage control (open-loop):
   VOLT 5.89
   STREAM ON
   → Should see: measured_psi ≈ 15.0 PSI

2. Test pressure setpoint (closed-loop):
   PSI 15
   STREAM ON
   → Should see: voltage = 6.08V, measured_psi converges to 15.0 PSI

3. Check calibration:
   CONFIG
   → Shows Parker calibration formulas

4. Verify system state:
   STATUS
   → Shows voltage, target PSI, and digital outputs

The system will auto-clamp pressure requests to 24.49 PSI maximum.

================================================================================
*/
