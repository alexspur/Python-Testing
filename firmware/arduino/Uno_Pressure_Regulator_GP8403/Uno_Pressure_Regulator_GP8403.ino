// Arduino Uno R3 + DFRobot GP8403 pressure regulator control
//
// GP8403 OUT0 -> Parker pressure regulator 0-10V input
// GP8403 VCC  -> Arduino 5V
// GP8403 GND  -> Arduino GND
// GP8403 SDA  -> Arduino A4
// GP8403 SCL  -> Arduino A5
//
// Commands:
//   PSI <value>   set pressure in psi
//   VOLT <value>  set raw 0-10V output
//   ZERO          set output to 0V
//   STATUS        show current output
//   HELP          show commands

#include <Wire.h>
#include "DFRobot_GP8403.h"

const uint32_t BAUD = 115200;

// GP8403 default I2C address is usually 0x58
// DFRobot_GP8403 dac(&Wire, 0x58);
DFRobot_GP8403 dac(&Wire, 0x5F);

const uint8_t DAC_CHANNEL = 0;   // OUT0
const float DAC_MAX_VOLTAGE = 10.0f;

// Parker regulator calibration from your old code:
// PSI = 2.5106 * Voltage - 0.178
// Voltage = (PSI + 0.178) / 2.5106
const float VOLTAGE_TO_PSI_SLOPE  = 2.5106f;
const float VOLTAGE_TO_PSI_OFFSET = -0.178f;

const float PARKER_MAX_PRESSURE_PSI = 24.49f;
const float PARKER_MAX_VOLTAGE      = 10.0f;

float outputVoltage = 0.0f;
float targetPressurePsi = 0.0f;

const unsigned long PRINT_INTERVAL_MS = 500;
unsigned long lastPrint = 0;

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

void setDacVoltage(float volts) {
  volts = constrain(volts, 0.0f, DAC_MAX_VOLTAGE);

  // GP8403 uses 12-bit code, 0-4095
  uint16_t code = (uint16_t)((volts / DAC_MAX_VOLTAGE) * 4095.0f + 0.5f);

  dac.setDACOutVoltage(code, DAC_CHANNEL);

  outputVoltage = volts;
}

void setPressureVoltage(float volts) {
  volts = constrain(volts, 0.0f, PARKER_MAX_VOLTAGE);
  setDacVoltage(volts);

  targetPressurePsi = voltageToParkerPsi(volts);

  Serial.print("ACK VOLT:");
  Serial.print(outputVoltage, 3);
  Serial.print(" V, expected pressure ");
  Serial.print(targetPressurePsi, 2);
  Serial.println(" psi");
}

void setPressureSetpoint(float psi) {
  float requestedPsi = psi;
  psi = constrain(psi, 0.0f, PARKER_MAX_PRESSURE_PSI);

  if (requestedPsi > PARKER_MAX_PRESSURE_PSI) {
    Serial.print("WARN PSI clamped from ");
    Serial.print(requestedPsi, 2);
    Serial.print(" to ");
    Serial.print(PARKER_MAX_PRESSURE_PSI, 2);
    Serial.println(" psi");
  }

  targetPressurePsi = psi;

  float requiredVoltage = psiToParkerVoltage(psi);
  setDacVoltage(requiredVoltage);

  Serial.print("ACK PSI:");
  Serial.print(targetPressurePsi, 2);
  Serial.print(" psi -> ");
  Serial.print(outputVoltage, 3);
  Serial.println(" V");
}

void printStatus() {
  Serial.print("STATUS | Target: ");
  Serial.print(targetPressurePsi, 2);
  Serial.print(" psi");

  Serial.print(" | Output: ");
  Serial.print(outputVoltage, 3);
  Serial.print(" V");

  Serial.print(" | Expected Pressure: ");
  Serial.print(voltageToParkerPsi(outputVoltage), 2);
  Serial.println(" psi");
}

void printHelp() {
  Serial.println();
  Serial.println("Commands:");
  Serial.println("  PSI <value>   set pressure setpoint in psi, 0-24.49");
  Serial.println("  VOLT <value>  set raw regulator voltage, 0-10");
  Serial.println("  ZERO          set output to 0 V");
  Serial.println("  STATUS        show current output");
  Serial.println("  HELP          show commands");
  Serial.println();
}

void handleSerialCommands() {
  if (!Serial.available()) return;

  String cmd = Serial.readStringUntil('\n');
  cmd.trim();
  cmd.toUpperCase();

  if (cmd.startsWith("PSI ")) {
    float psi = cmd.substring(4).toFloat();
    setPressureSetpoint(psi);
  }
  else if (cmd.startsWith("VOLT ")) {
    float volts = cmd.substring(5).toFloat();
    setPressureVoltage(volts);
  }
  else if (cmd == "ZERO") {
    setPressureVoltage(0.0f);
  }
  else if (cmd == "STATUS") {
    printStatus();
  }
  else if (cmd == "HELP") {
    printHelp();
  }
  else if (cmd.length() > 0) {
    Serial.print("Unknown command: ");
    Serial.println(cmd);
    Serial.println("Type HELP for commands.");
  }
}

void setup() {
  Serial.begin(BAUD);
  delay(1000);

  Wire.begin();

  Serial.println("Arduino Uno R3 Pressure Regulator Controller");
  Serial.println("Initializing GP8403...");

  while (dac.begin() != 0) {
    Serial.println("GP8403 init error. Check wiring and I2C address.");
    delay(1000);
  }

  Serial.println("GP8403 init success.");

  dac.setDACOutRange(dac.eOutputRange10V);

  // Safe startup
  setPressureVoltage(0.0f);

  printHelp();
}

void loop() {
  handleSerialCommands();

  if (millis() - lastPrint >= PRINT_INTERVAL_MS) {
    lastPrint = millis();
    printStatus();
  }
}