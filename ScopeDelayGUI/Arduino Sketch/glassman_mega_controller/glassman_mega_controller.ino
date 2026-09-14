// Glassman WR125 monitor reader + HV enable + pressure + GP8413 kV setpoint
//
// Reads:
//   A3 = V-MONITOR through 10k/10k divider
//   A4 = I-MONITOR through 10k/10k divider
//   A5 = PRESSURE (0-10V, 0-100 psi) through 10k/10k divider
//
// Controls:
//   D7  = HV ENABLE
//   I2C = GP8413 DAC -> Glassman V-PROGRAM (0-10V = 0-125 kV)
//
// Wiring:
//   Mega A3  -> Glassman pin 4 (V-MONITOR) through divider
//   Mega A4  -> Glassman pin 7 (I-MONITOR) through divider
//   Mega A5  -> Pressure sensor output through 10k/10k divider
//   Mega D7  -> Glassman pin 11 (HV ENABLE)
//   Mega 20 (SDA) -> GP8413 SDA
//   Mega 21 (SCL) -> GP8413 SCL
//   Mega 5V  -> GP8413 VCC
//   Mega GND -> GP8413 GND, Glassman pin 2 (COMMON), pressure sensor GND
//   GP8413 OUT0 -> Glassman V-PROGRAM
//   Glassman pin 3 (INTERLOCK) -> Glassman pin 2 (COMMON)

#include <DFRobot_GP8XXX.h>

const int V_MON_PIN = A3;
const int I_MON_PIN = A4;
const int PRESSURE_PIN = A5;
const int HV_ENABLE_PIN = 7;

const float ADC_REF_V = 5.0;
const int ADC_COUNTS = 1023;

const float VMON_DIVIDER_SLOPE     = 2.035875f;
const float VMON_DIVIDER_INTERCEPT = 0.009092f;
const float VMON_FULL_SCALE_V      = 6.65f;
const float HV_FULL_SCALE_KV       = 125.0f;

// ---- I-MON channel (A4) ----
// Same 10k/10k divider as V-MON, so start from V-MON slope/intercept.
// IMON_FULL_SCALE_V = terminal volts on Glassman pin 7 at full-scale 2 mA.
// Default to spec (10 V); refine with a meter once running.
const float IMON_DIVIDER_SLOPE     = 2.035875f;
const float IMON_DIVIDER_INTERCEPT = 0.009092f;
const float IMON_FULL_SCALE_V      = 10.0f;
const float I_FULL_SCALE_MA        = 2.0f;

// ---- Pressure channel (A5) ----
const float PRESSURE_DIVIDER_RATIO  = 2.0f;
const float PRESSURE_FULL_SCALE_V   = 10.0f;
const float PRESSURE_FULL_SCALE_PSI = 100.0f;

// ---- GP8413 DAC (V-PROGRAM setpoint) ----
DFRobot_GP8413 dac(0x58);
const int   DAC_CHANNEL  = 0;       // 0=ch0, 1=ch1, 2=both
const float DAC_FULL_V   = 10.0f;   // 10 V = 125 kV
bool  dacReady = false;
float currentSetKV = 0.0f;

const int NUM_SAMPLES = 20;
const unsigned long PRINT_INTERVAL_MS = 500;

unsigned long lastPrint = 0;
bool hvEnabled = false;

float readAveragedVoltage(int pin, int samples, float adcRef) {
  analogRead(pin);   // dummy read to settle the ADC mux
  delay(1);
  unsigned long sum = 0;
  for (int i = 0; i < samples; i++) {
    sum += analogRead(pin);
    delay(2);
  }
  float avgCounts = (float)sum / samples;
  return (avgCounts / ADC_COUNTS) * adcRef;
}

void setHVEnable(bool enable) {
  hvEnabled = enable;
  digitalWrite(HV_ENABLE_PIN, enable ? HIGH : LOW);
  Serial.print("HV ENABLE: ");
  Serial.println(enable ? "ON" : "OFF");
}

void setDacVoltage(float volts) {
  if (volts < 0) volts = 0;
  if (volts > DAC_FULL_V) volts = DAC_FULL_V;
  uint16_t code = (uint16_t)((volts / DAC_FULL_V) * 32767.0f + 0.5f);
  if (dacReady) dac.setDACOutVoltage(code, DAC_CHANNEL);
}

void setKV(float kv) {
  if (kv < 0) kv = 0;
  if (kv > HV_FULL_SCALE_KV) kv = HV_FULL_SCALE_KV;
  currentSetKV = kv;
  float volts = (kv / HV_FULL_SCALE_KV) * DAC_FULL_V;
  setDacVoltage(volts);
  Serial.print("Setpoint: ");
  Serial.print(kv, 1);
  Serial.print(" kV  ->  ");
  Serial.print(volts, 4);
  Serial.println(" V at DAC");
}

void printReadings() {
  float vMonPinVolts = readAveragedVoltage(V_MON_PIN, NUM_SAMPLES, ADC_REF_V);
  float iMonPinVolts = readAveragedVoltage(I_MON_PIN, NUM_SAMPLES, ADC_REF_V);
  float pressPinVolts = readAveragedVoltage(PRESSURE_PIN, NUM_SAMPLES, ADC_REF_V);

  float vMonActualVolts = (vMonPinVolts * VMON_DIVIDER_SLOPE) + VMON_DIVIDER_INTERCEPT;
  float outputKV = (vMonActualVolts / VMON_FULL_SCALE_V) * HV_FULL_SCALE_KV;
  if (outputKV < 0.0) outputKV = 0.0;

  float iMonActualVolts = (iMonPinVolts * IMON_DIVIDER_SLOPE) + IMON_DIVIDER_INTERCEPT;
  float outputMA = (iMonActualVolts / IMON_FULL_SCALE_V) * I_FULL_SCALE_MA;
  if (outputMA < 0.0) outputMA = 0.0;

  float pressActualVolts = pressPinVolts * PRESSURE_DIVIDER_RATIO;
  float outputPSI = (pressActualVolts / PRESSURE_FULL_SCALE_V) * PRESSURE_FULL_SCALE_PSI;
  if (outputPSI < 0.0) outputPSI = 0.0;

  Serial.print("HV=");
  Serial.print(hvEnabled ? "ON" : "OFF");

  Serial.print(" | SET: ");
  Serial.print(currentSetKV, 1);
  Serial.print(" kV");

  Serial.print(" | V_MON pin: ");
  Serial.print(vMonPinVolts, 4);
  Serial.print(" V");

  Serial.print(" | Glassman V_MON: ");
  Serial.print(vMonActualVolts, 4);
  Serial.print(" V");

  Serial.print(" | Output: ");
  Serial.print(outputKV, 2);
  Serial.print(" kV");

  Serial.print(" || I_MON pin: ");
  Serial.print(iMonPinVolts, 4);
  Serial.print(" V");

  Serial.print(" | Glassman I_MON: ");
  Serial.print(iMonActualVolts, 4);
  Serial.print(" V");

  Serial.print(" | Output: ");
  Serial.print(outputMA, 4);
  Serial.print(" mA");

  Serial.print(" || P pin: ");
  Serial.print(pressPinVolts, 4);
  Serial.print(" V");

  Serial.print(" | Sensor: ");
  Serial.print(pressActualVolts, 4);
  Serial.print(" V");

  Serial.print(" | Pressure: ");
  Serial.print(outputPSI, 2);
  Serial.println(" psi");
}

void handleSerialCommands() {
  if (!Serial.available()) return;

  String cmd = Serial.readStringUntil('\n');
  cmd.trim();
  cmd.toUpperCase();

  if (cmd == "ON") {
    setHVEnable(true);
  } else if (cmd == "OFF") {
    setHVEnable(false);
  } else if (cmd == "TOGGLE") {
    setHVEnable(!hvEnabled);
  } else if (cmd.startsWith("KV ")) {
    setKV(cmd.substring(3).toFloat());
  } else if (cmd.startsWith("VDAC ")) {
    float v = cmd.substring(5).toFloat();
    setDacVoltage(v);
    Serial.print("DAC set to ");
    Serial.print(v, 4);
    Serial.println(" V (raw)");
  } else if (cmd == "ZERO") {
    setKV(0);
  } else if (cmd == "STATUS") {
    Serial.print("HV STATUS: ");
    Serial.print(hvEnabled ? "ON" : "OFF");
    Serial.print(" | Setpoint: ");
    Serial.print(currentSetKV, 1);
    Serial.println(" kV");
  } else if (cmd == "READ") {
    printReadings();
  } else if (cmd == "HELP") {
    Serial.println("Commands:");
    Serial.println("  ON         -> HV enable HIGH");
    Serial.println("  OFF        -> HV enable LOW");
    Serial.println("  TOGGLE     -> toggle HV enable");
    Serial.println("  KV <val>   -> set output setpoint in kV (0-125)");
    Serial.println("  VDAC <val> -> set raw DAC volts (0-10)");
    Serial.println("  ZERO       -> set setpoint to 0 kV");
    Serial.println("  STATUS     -> print HV state and setpoint");
    Serial.println("  READ       -> print one measurement line");
    Serial.println("  HELP       -> show commands");
  } else if (cmd.length() > 0) {
    Serial.print("Unknown command: ");
    Serial.println(cmd);
  }
}

void setup() {
  Serial.begin(115200);

  pinMode(HV_ENABLE_PIN, OUTPUT);
  digitalWrite(HV_ENABLE_PIN, LOW);
  hvEnabled = false;

  // GP8413 init
  if (dac.begin() == 0) {
    dac.setDACOutRange(dac.eOutputRange10V);
    dacReady = true;
    setKV(0);  // start safe at 0
  } else {
    Serial.println("WARNING: GP8413 not found, setpoint control disabled");
  }

  for (int i = 0; i < 10; i++) {
    analogRead(V_MON_PIN);
    analogRead(I_MON_PIN);
    analogRead(PRESSURE_PIN);
    delay(5);
  }

  Serial.println("Glassman WR125 Reader + HV Enable + Pressure + Setpoint");
  Serial.println("A3=V-MON, A4=I-MON, A5=PRESS, D7=HV EN, I2C=GP8413 V-PROGRAM");
  Serial.println("Commands: ON, OFF, TOGGLE, KV, VDAC, ZERO, STATUS, READ, HELP");
  Serial.println();
}

void loop() {
  handleSerialCommands();

  if (millis() - lastPrint >= PRINT_INTERVAL_MS) {
    lastPrint = millis();
    printReadings();
  }
}