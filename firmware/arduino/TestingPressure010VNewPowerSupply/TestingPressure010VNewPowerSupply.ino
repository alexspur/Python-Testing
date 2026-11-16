#include <Arduino_PortentaMachineControl.h>
#include <RunningAverage.h>

const uint32_t BAUD = 115200;
const unsigned long STREAM_INTERVAL = 100;
const size_t LINE_MAX = 64;

// =========================
// ANALOG OUTPUT CHANNEL MAP
// =========================
// AO0 -> Glassman V-PROGRAM
// AO1 -> Glassman I-PROGRAM
// AO2 -> Parker pressure regulator control
// AO3 -> spare
const int GLASSMAN_VOLTAGE_AO_CHANNEL = 0;
const int GLASSMAN_CURRENT_AO_CHANNEL = 1;
const int PRESSURE_AO_CHANNEL         = 2;

// =========================
// ANALOG INPUT CHANNEL MAP
// =========================
// AI0 -> 4-20 mA current loop
// AI1 -> 4-20 mA current loop
// AI2 -> 0-10 V pressure sensor feedback (0-100 PSI)
const int CURRENT_AI_0    = 0;
const int CURRENT_AI_1    = 1;
const int PRESSURE_AI_2   = 2;

// =========================
// ANALOG OUTPUT TIMING
// =========================
#define PERIOD_MS 4   // 4 ms = 250 Hz

uint8_t outputStates = 0x00;
bool streamEnabled = true;
unsigned long lastStream = 0;
uint32_t sampleCount = 0;
char lineBuf[LINE_MAX];

// =========================
// OUTPUT STATE VARIABLES
// =========================
float outputVoltage = 0.0f;        // AO2 Parker regulator voltage
float targetPressurePsi = 0.0f;    // pressure setpoint

float hvVoltageCommand = 0.0f;     // AO0 Glassman V-PROGRAM, 0-10 V
float hvCurrentCommand = 0.0f;     // AO1 Glassman I-PROGRAM, 0-10 V

// =========================
// GLASSMAN SCALING (WR125)
// =========================
// 0-10 V => 0-125 kV
// 0-10 V => 0-2 mA
const float GLASSMAN_MAX_VOLTAGE_KV = 125.0f;
const float GLASSMAN_MAX_CURRENT_MA = 2.0f;

// =========================
// AO GAIN CALIBRATION
// =========================
// Measured from 11-point linearity sweep
const float AO0_GAIN_CAL = 10.0f / 9.850f;  // 1.01523
const float AO1_GAIN_CAL = 10.0f / 9.850f;  // 1.01523

float aoVoltsToGlassmanKV(float volts) {
  volts = constrain(volts, 0.0f, 10.0f);
  return volts * (GLASSMAN_MAX_VOLTAGE_KV / 10.0f);   // 12.5 kV/V
}

float aoVoltsToGlassmanMA(float volts) {
  volts = constrain(volts, 0.0f, 10.0f);
  return volts * (GLASSMAN_MAX_CURRENT_MA / 10.0f);   // 0.2 mA/V
}

// ============================================================================
// PRESSURE SENSOR CALIBRATION - 0-10 V => 0-100 PSI
// ============================================================================
const float PRESSURE_SENSOR_FS_PSI  = 100.0f;
const float PRESSURE_SENSOR_FS_VOLT = 10.0f;

float voltsToPsi(float volts) {
  if (volts < 0.0f) volts = 0.0f;
  if (volts > PRESSURE_SENSOR_FS_VOLT) volts = PRESSURE_SENSOR_FS_VOLT;
  return (volts / PRESSURE_SENSOR_FS_VOLT) * PRESSURE_SENSOR_FS_PSI;
}

// ============================================================================
// PARKER REGULATOR CALIBRATION - VOLTAGE TO PSI MAPPING (CONTROL)
// ============================================================================
// y = 2.5106x - 0.178
// Inverse: Voltage = (PSI + 0.178) / 2.5106

const float VOLTAGE_TO_PSI_SLOPE = 2.5106f;
const float VOLTAGE_TO_PSI_OFFSET = -0.178f;
const float PARKER_MAX_PRESSURE_PSI = 24.49f;
const float PARKER_MAX_VOLTAGE = 10.0f;

float psiToParkerVoltage(float targetPsi) {
  float clampedPsi = constrain(targetPsi, 0.0f, PARKER_MAX_PRESSURE_PSI);
  float voltage = (clampedPsi + 0.178f) / 2.5106f;
  return constrain(voltage, 0.0f, PARKER_MAX_VOLTAGE);
}

float voltageToParkerPsi(float voltage) {
  float v = constrain(voltage, 0.0f, PARKER_MAX_VOLTAGE);
  float psi = VOLTAGE_TO_PSI_SLOPE * v + VOLTAGE_TO_PSI_OFFSET;
  return constrain(psi, 0.0f, PARKER_MAX_PRESSURE_PSI);
}
// ============================================================================
// PER-CHANNEL AI MODE CONFIG
// ============================================================================
// The stock library begin() sets the same mode on all three AI channels.
// This helper reconfigures one channel independently by writing the same
// resistor-network pin patterns the library uses internally.
void configureAIChannel(int channel, SensorType type) {
  int in1, in2, in3, in4;
  switch (channel) {
    case 0:
      in1 = MC_AI_CH0_IN1_PIN; in2 = MC_AI_CH0_IN2_PIN;
      in3 = MC_AI_CH0_IN3_PIN; in4 = MC_AI_CH0_IN4_PIN;
      break;
    case 1:
      in1 = MC_AI_CH1_IN1_PIN; in2 = MC_AI_CH1_IN2_PIN;
      in3 = MC_AI_CH1_IN3_PIN; in4 = MC_AI_CH1_IN4_PIN;
      break;
    case 2:
      in1 = MC_AI_CH2_IN1_PIN; in2 = MC_AI_CH2_IN2_PIN;
      in3 = MC_AI_CH2_IN3_PIN; in4 = MC_AI_CH2_IN4_PIN;
      break;
    default:
      return;
  }

  pinMode(in1, OUTPUT);
  pinMode(in2, OUTPUT);
  pinMode(in3, OUTPUT);
  pinMode(in4, OUTPUT);

  switch (type) {
    case SensorType::NTC:
      digitalWrite(in1, LOW);
      digitalWrite(in2, LOW);
      digitalWrite(in3, HIGH);
      digitalWrite(in4, HIGH);
      break;
    case SensorType::V_0_10:
      digitalWrite(in1, HIGH);
      digitalWrite(in2, HIGH);
      digitalWrite(in3, LOW);
      digitalWrite(in4, HIGH);
      break;
    case SensorType::MA_4_20:
      digitalWrite(in1, HIGH);
      digitalWrite(in2, LOW);
      digitalWrite(in3, HIGH);
      digitalWrite(in4, LOW);
      break;
    default:
      break;
  }
}
// =========================
// RUNNING AVERAGES
// =========================
RunningAverage raChannel0(20);
RunningAverage raChannel1(20);
RunningAverage raChannel2(20);

// =========================
// HELPERS
// =========================
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
  if (n > 0 && buf[n - 1] == '\r') buf[n - 1] = '\0';
  return true;
}

int parseChannel(const char* s) {
  int ch = atoi(s);
  if (ch < 0 || ch > 7) return -1;
  return ch;
}

bool eqNoCase(const char* a, const char* b) {
  while (*a && *b) {
    char ca = toupper(*a++);
    char cb = toupper(*b++);
    if (ca != cb) return false;
  }
  return (*a == '\0' && *b == '\0');
}

void applyOutputs() {
  MachineControl_DigitalOutputs.writeAll(outputStates);
}

// =========================
// PRESSURE AO2 CONTROL
// =========================
void setPressureVoltage(float volts) {
  outputVoltage = constrain(volts, 0.0f, 10.0f);
  MachineControl_AnalogOut.write(PRESSURE_AO_CHANNEL, outputVoltage);

  Serial.print("ACK SET_VOLT:");
  Serial.print(outputVoltage, 3);
  Serial.print("V (expected pressure ");
  Serial.print(voltageToParkerPsi(outputVoltage), 2);
  Serial.println(" PSI)");
}

void setPressureSetpoint(float psi) {
  targetPressurePsi = psi;
  float requiredVoltage = psiToParkerVoltage(psi);

  if (psi > PARKER_MAX_PRESSURE_PSI) {
    Serial.print("WARN PSI_CLAMPED:");
    Serial.print(psi, 2);
    Serial.print(" -> ");
    Serial.println(PARKER_MAX_PRESSURE_PSI, 2);
  }

  setPressureVoltage(requiredVoltage);

  Serial.print("ACK SET_PSI:");
  Serial.print(psi, 2);
  Serial.print(" (clamped to ");
  Serial.print(PARKER_MAX_PRESSURE_PSI, 2);
  Serial.print(") V:");
  Serial.println(requiredVoltage, 3);
}

// =========================
// GLASSMAN AO0/AO1 CONTROL
// =========================
void setHVVoltageCommand(float volts) {
  hvVoltageCommand = constrain(volts, 0.0f, 10.0f);
  float calibrated = constrain(hvVoltageCommand * AO0_GAIN_CAL, 0.0f, 10.5f);
  MachineControl_AnalogOut.write(GLASSMAN_VOLTAGE_AO_CHANNEL, calibrated);

  Serial.print("ACK HVVOLT:");
  Serial.print(hvVoltageCommand, 3);
  Serial.print("V (");
  Serial.print(aoVoltsToGlassmanKV(hvVoltageCommand), 2);
  Serial.println(" kV setpoint)");
}

void setHVCurrentCommand(float volts) {
  hvCurrentCommand = constrain(volts, 0.0f, 10.0f);
  float calibrated = constrain(hvCurrentCommand * AO1_GAIN_CAL, 0.0f, 10.5f);
  MachineControl_AnalogOut.write(GLASSMAN_CURRENT_AO_CHANNEL, calibrated);

  Serial.print("ACK HVCURR:");
  Serial.print(hvCurrentCommand, 3);
  Serial.print("V (");
  Serial.print(aoVoltsToGlassmanMA(hvCurrentCommand), 4);
  Serial.println(" mA setpoint)");
}

// =========================
// SERIAL COMMAND HANDLER
// =========================
void handleSerialCommands() {
  if (!Serial.available()) return;
  if (!readLine(lineBuf, LINE_MAX)) return;

  char* cmd = strtok(lineBuf, " ");
  char* arg = strtok(nullptr, " ");
  if (!cmd || cmd[0] == '\0') return;

  if (eqNoCase(cmd, "VOLT") || eqNoCase(cmd, "V")) {
    if (!arg) {
      Serial.print("ACK VOLT:");
      Serial.println(outputVoltage, 3);
      return;
    }
    setPressureVoltage(atof(arg));
    return;
  }

  if (eqNoCase(cmd, "PSI") || eqNoCase(cmd, "P")) {
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
    setPressureSetpoint(atof(arg));
    return;
  }

  if (eqNoCase(cmd, "HVVOLT") || eqNoCase(cmd, "HVV")) {
    if (!arg) {
      Serial.print("ACK HVVOLT:");
      Serial.print(hvVoltageCommand, 3);
      Serial.print("V,");
      Serial.print(aoVoltsToGlassmanKV(hvVoltageCommand), 2);
      Serial.println("kV");
      return;
    }
    setHVVoltageCommand(atof(arg));
    return;
  }

  if (eqNoCase(cmd, "HVCURR") || eqNoCase(cmd, "HVI")) {
    if (!arg) {
      Serial.print("ACK HVCURR:");
      Serial.print(hvCurrentCommand, 3);
      Serial.print("V,");
      Serial.print(aoVoltsToGlassmanMA(hvCurrentCommand), 4);
      Serial.println("mA");
      return;
    }
    setHVCurrentCommand(atof(arg));
    return;
  }

  if (eqNoCase(cmd, "HVSTATUS")) {
    Serial.print("HVSTATUS,AO0_V=");
    Serial.print(hvVoltageCommand, 3);
    Serial.print(",HV_kV_SET=");
    Serial.print(aoVoltsToGlassmanKV(hvVoltageCommand), 2);
    Serial.print(",AO1_V=");
    Serial.print(hvCurrentCommand, 3);
    Serial.print(",HV_mA_SET=");
    Serial.println(aoVoltsToGlassmanMA(hvCurrentCommand), 4);
    return;
  }

  if (eqNoCase(cmd, "PING")) {
    Serial.println("ACK PONG");
    return;
  }

  if (eqNoCase(cmd, "STREAM")) {
    if (!arg) {
      sendNack("ARG");
      return;
    }
    if (eqNoCase(arg, "ON")) {
      streamEnabled = true;
      sendAck("STREAM_ON");
    } else if (eqNoCase(arg, "OFF")) {
      streamEnabled = false;
      sendAck("STREAM_OFF");
    } else {
      sendNack("ARG");
    }
    return;
  }

  if (eqNoCase(cmd, "STATUS")) {
    Serial.print("STATUS,");
    Serial.print(outputVoltage, 2);
    Serial.print(",");
    Serial.print(targetPressurePsi, 2);
    Serial.print(",");
    Serial.print(PARKER_MAX_PRESSURE_PSI, 2);
    Serial.print(",");
    Serial.print(hvVoltageCommand, 2);
    Serial.print(",");
    Serial.print(hvCurrentCommand, 2);
    Serial.print(",");
    for (int ch = 0; ch < 8; ch++) {
      Serial.print(bitRead(outputStates, ch));
    }
    Serial.println();
    return;
  }

  if (eqNoCase(cmd, "HELP")) {
    Serial.println("\n=== COMMANDS ===");
    Serial.println("VOLT <0-10>        Set Parker raw voltage on AO2");
    Serial.println("PSI <0-24.49>      Set Parker pressure setpoint on AO2");
    Serial.println("HVVOLT <0-10>      Set Glassman voltage command on AO0");
    Serial.println("HVCURR <0-10>      Set Glassman current command on AO1");
    Serial.println("HVSTATUS           Show AO0/AO1 and implied HV setpoints");
    Serial.println("STREAM ON/OFF      Enable/disable data streaming");
    Serial.println("STATUS             Show current state");
    Serial.println("CONFIG             Show calibration/config");
    Serial.println("PING               Test connection");
    Serial.println("HELP               Show this help\n");
    return;
  }

  if (eqNoCase(cmd, "CONFIG")) {
    Serial.println("\n=== PARKER CALIBRATION ===");
    Serial.println("Forward: PSI = 2.5106 * Voltage - 0.178");
    Serial.println("Inverse: Voltage = (PSI + 0.178) / 2.5106");
    Serial.println("Range: 0.0 to 24.49 PSI (AO2)");
    Serial.println("");
    Serial.println("=== PRESSURE SENSOR (AI2, 0-10V) ===");
    Serial.println("Range: 0-10 V => 0-100 PSI");
    Serial.println("");
    Serial.println("=== GLASSMAN WR125 SCALING ===");
    Serial.println("AO0: 0-10V => 0-125 kV");
    Serial.println("AO1: 0-10V => 0-2 mA");
    Serial.println("");
    return;
  }

  if (eqNoCase(cmd, "ALL")) {
    if (!arg) {
      sendNack("ARG");
      return;
    }
    if (eqNoCase(arg, "ON")) {
      outputStates = 0xFF;
      applyOutputs();
      sendAck("ALL_ON");
    } else if (eqNoCase(arg, "OFF")) {
      outputStates = 0x00;
      applyOutputs();
      sendAck("ALL_OFF");
    } else {
      sendNack("ARG");
    }
    return;
  }

  if (eqNoCase(cmd, "ON") || eqNoCase(cmd, "OFF")) {
    if (!arg) {
      sendNack("ARG");
      return;
    }
    int ch = parseChannel(arg);
    if (ch < 0) {
      sendNack("CHAN");
      return;
    }
    if (eqNoCase(cmd, "ON")) {
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

// =========================
// STREAMING
// =========================
void streamAnalogInputs() {
  unsigned long now = millis();
  if (!streamEnabled || (now - lastStream < STREAM_INTERVAL)) return;
  lastStream = now;

  // Read raw ADC values
  uint16_t rawChannel[3];
  for (int i = 0; i < 3; i++) {
    rawChannel[i] = (uint16_t)MachineControl_AnalogIn.read(i);
  }

  raChannel0.addValue((float)rawChannel[0]);
  raChannel1.addValue((float)rawChannel[1]);
  raChannel2.addValue((float)rawChannel[2]);

  float smoothedRaw0 = raChannel0.getAverage();
  float smoothedRaw1 = raChannel1.getAverage();
  float smoothedRaw2 = raChannel2.getAverage();

  // Conversion constants
  const float REFERENCE = 3.0f;       // PMC ADC reference
  const float SENSE_RES = 120.0f;     // 4-20 mA sense resistor
  const float RES_DIVIDER = 0.28057f; // 0-10 V mode input divider

  // AI0 and AI1 are 4-20 mA
  float mA0 = ((smoothedRaw0 * REFERENCE) / 65535.0f / SENSE_RES) * 1000.0f;
  float mA1 = ((smoothedRaw1 * REFERENCE) / 65535.0f / SENSE_RES) * 1000.0f;
  if (mA0 < 0) mA0 = 0;
  if (mA1 < 0) mA1 = 0;

  // AI2 is 0-10 V
  float volts2 = (smoothedRaw2 * REFERENCE) / 65535.0f / RES_DIVIDER;
  if (volts2 < 0) volts2 = 0;
  float pressurePsi = voltsToPsi(volts2);

  float expectedPsi = voltageToParkerPsi(outputVoltage);

  // Stream format:
  // DATA,count,mA0,mA1,ai2_v,measured_psi,target_psi,pressure_ao_v,expected_psi,hv_ao0_v,hv_kv_set,hv_ao1_v,hv_ma_set
  Serial.print("DATA,");
  Serial.print(sampleCount++);
  Serial.print(",");
  Serial.print(mA0, 3);
  Serial.print(",");
  Serial.print(mA1, 3);
  Serial.print(",");
  Serial.print(volts2, 3);
  Serial.print(",");
  Serial.print(pressurePsi, 3);
  Serial.print(",");
  Serial.print(targetPressurePsi, 2);
  Serial.print(",");
  Serial.print(outputVoltage, 2);
  Serial.print(",");
  Serial.print(expectedPsi, 2);
  Serial.print(",");
  Serial.print(hvVoltageCommand, 3);
  Serial.print(",");
  Serial.print(aoVoltsToGlassmanKV(hvVoltageCommand), 2);
  Serial.print(",");
  Serial.print(hvCurrentCommand, 3);
  Serial.print(",");
  Serial.println(aoVoltsToGlassmanMA(hvCurrentCommand), 4);
}

void setup() {
  Serial.begin(BAUD);
  while (!Serial) {}

  MachineControl_DigitalOutputs.begin(true);
  applyOutputs();

// Initialize analog inputs: all to 4-20 mA, then override AI2 to 0-10 V
  MachineControl_AnalogIn.begin(SensorType::MA_4_20);
  configureAIChannel(PRESSURE_AI_2, SensorType::V_0_10);

  
  MachineControl_AnalogOut.begin();
  MachineControl_AnalogOut.setPeriod(0, PERIOD_MS);
  MachineControl_AnalogOut.setPeriod(1, PERIOD_MS);
  MachineControl_AnalogOut.setPeriod(2, PERIOD_MS);
  MachineControl_AnalogOut.setPeriod(3, PERIOD_MS);

  // Safe startup defaults
  setHVVoltageCommand(0.0f);
  setHVCurrentCommand(0.0f);
  setPressureVoltage(0.0f);
  MachineControl_AnalogOut.write(3, 0.0f);

  Serial.println("================================================================================");
  Serial.println("PORTENTA MACHINE CONTROL - PRESSURE + GLASSMAN AO CONTROL");
  Serial.println("================================================================================");
  Serial.println("ACK READY");
  Serial.println("");
  Serial.println("AO CHANNEL MAP:");
  Serial.println("  AO0 -> Glassman V-PROGRAM");
  Serial.println("  AO1 -> Glassman I-PROGRAM");
  Serial.println("  AO2 -> Parker pressure regulator");
  Serial.println("  AO3 -> spare");
  Serial.println("");
  Serial.println("AI CHANNEL MAP:");
  Serial.println("  AI0 -> 4-20 mA");
  Serial.println("  AI1 -> 4-20 mA");
  Serial.println("  AI2 -> 0-10 V (0-100 PSI sensor)");
  Serial.println("");
  Serial.println("PARKER REGULATOR CALIBRATION:");
  Serial.println("  Forward: PSI = 2.5106 * Voltage - 0.178");
  Serial.println("  Inverse: Voltage = (PSI + 0.178) / 2.5106");
  Serial.println("  Range: 0.0 to 24.49 PSI");
  Serial.println("");
  Serial.println("GLASSMAN WR125 SCALING:");
  Serial.println("  AO0 0-10V -> 0-125 kV");
  Serial.println("  AO1 0-10V -> 0-2 mA");
  Serial.println("");
  Serial.println("DATA STREAM FORMAT:");
  Serial.println("  DATA,count,mA0,mA1,ai2_v,measured_psi,target_psi,pressure_ao_v,expected_psi,hv_ao0_v,hv_kv_set,hv_ao1_v,hv_ma_set");
  Serial.println("");
  Serial.println("COMMANDS:");
  Serial.println("  VOLT <0-10>      Set Parker raw voltage on AO2");
  Serial.println("  PSI <0-24.49>    Set Parker target pressure on AO2");
  Serial.println("  HVVOLT <0-10>    Set Glassman voltage command on AO0");
  Serial.println("  HVCURR <0-10>    Set Glassman current command on AO1");
  Serial.println("  HVSTATUS         Show Glassman AO state");
  Serial.println("  STREAM ON/OFF    Control streaming");
  Serial.println("  STATUS           Show current state");
  Serial.println("  CONFIG           Show calibration/config");
  Serial.println("  HELP             Show help");
  Serial.println("================================================================================\n");
}

void loop() {
  handleSerialCommands();
  streamAnalogInputs();
}
