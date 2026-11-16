// // Glassman WR125 monitor reader + HV enable + pressure + GP8413 kV & PSI setpoints + Marx rail monitors
// //
// // Reads:
// //   A3  = V-MONITOR through 10k/10k divider
// //   A4  = I-MONITOR through 10k/10k divider
// //   A5  = PRESSURE (0-10V, 0-100 psi) through 10k/10k divider
// //   A10 = MARX POSITIVE RAIL monitor, 0-5V = 0-100kV
// //   A11 = MARX NEGATIVE RAIL monitor, -5V to 0V (-100kV to 0kV)
// //         read through a summing divider so the ADC sees 5V at 0kV and
// //         2.5V at -100kV (1k series + Schottky clamp).
// //         Transfer: V_mon = 2*V_adc - 10
// //
// // Controls:
// //   D7  = HV ENABLE
// //   I2C = GP8413 DAC
// //         CH0 -> Glassman V-PROGRAM (0-10V = 0-125 kV)
// //         CH1 -> Parker pressure regulator setpoint (0-10V = 0-24.49 psi)

// // Glassman WR125 monitor reader + HV enable + pressure + GP8413 kV & PSI setpoints + Marx rail monitors
// //
// // Reads:
// //   A3  = V-MONITOR through 10k/10k divider
// //   A4  = I-MONITOR through 10k/10k divider
// //   A5  = PRESSURE (0-10V, 0-100 psi) through 10k/10k divider
// //   A10 = MARX POSITIVE RAIL monitor, 0-5V = 0-100kV
// //   A11 = MARX NEGATIVE RAIL monitor through 10k/10k level shift
// //
// // Marx negative monitor:
// //   Actual monitor:  0V to -5V
// //   Arduino A11:     2.5V to 0V
// //   Transfer:        V_mon = 2*V_adc - 5
// //
// // Controls:
// //   D7  = HV ENABLE
// //   I2C = GP8413 DAC
// //         CH0 -> Glassman V-PROGRAM
// //         CH1 -> Parker pressure regulator setpoint

// #include <DFRobot_GP8XXX.h>

// const int V_MON_PIN     = A3;
// const int I_MON_PIN     = A4;
// const int PRESSURE_PIN  = A5;
// const int MARX_POS_PIN  = A10;
// const int MARX_NEG_PIN  = A11;
// const int HV_ENABLE_PIN = 8;

// const float ADC_REF_V = 5.0f;
// const int ADC_COUNTS = 1023;

// const float VMON_DIVIDER_SLOPE     = 2.035875f;
// const float VMON_DIVIDER_INTERCEPT = 0.009092f;
// const float VMON_FULL_SCALE_V      = 6.65f;
// const float HV_FULL_SCALE_KV       = 125.0f;

// const float IMON_DIVIDER_SLOPE     = 2.035875f;
// const float IMON_DIVIDER_INTERCEPT = 0.009092f;
// const float IMON_FULL_SCALE_V      = 10.0f;
// const float I_FULL_SCALE_MA        = 2.0f;

// const float PRESSURE_DIVIDER_RATIO  = 2.0f;
// const float PRESSURE_FULL_SCALE_V   = 10.0f;
// const float PRESSURE_FULL_SCALE_PSI = 160.0f;

// const float MARX_FULL_SCALE_PIN_V = 5.0f;
// const float MARX_FULL_SCALE_KV    = 100.0f;

// // For 10k from -5V..0V monitor and 10k to +5V reference:
// // V_adc = (V_mon + 5) / 2
// // V_mon = 2*V_adc - 5
// const float MARX_NEG_DIVIDER_SLOPE     = 2.0f;
// const float MARX_NEG_DIVIDER_INTERCEPT = -5.0f;

// DFRobot_GP8413 dac(0x58);
// const int   DAC_CH_KV  = 0;
// const int   DAC_CH_PSI = 1;
// const float DAC_FULL_V = 10.0f;

// const float PSI_FULL_SCALE = 24.49f;

// // Pressure setpoint applied automatically on boot/reset. The dome should hold a
// // safe operating pressure even if the Mega reboots (loose USB, power glitch),
// // instead of venting to 0. kV is still forced to 0 on boot for HV safety.
// const float BOOT_PRESSURE_PSI = 10.0f;

// bool dacReady = false;
// float currentSetKV  = 0.0f;
// float currentSetPSI = 0.0f;

// const int NUM_SAMPLES = 20;
// const unsigned long PRINT_INTERVAL_MS = 500;

// unsigned long lastPrint = 0;
// bool hvEnabled = false;

// float readAveragedVoltage(int pin, int samples, float adcRef) {
//   analogRead(pin);
//   delay(1);

//   unsigned long sum = 0;
//   for (int i = 0; i < samples; i++) {
//     sum += analogRead(pin);
//     delay(2);
//   }

//   float avgCounts = (float)sum / samples;
//   return (avgCounts / ADC_COUNTS) * adcRef;
// }

// void setHVEnable(bool enable) {
//   hvEnabled = enable;
//   digitalWrite(HV_ENABLE_PIN, enable ? HIGH : LOW);

//   Serial.print("HV ENABLE: ");
//   Serial.println(enable ? "ON" : "OFF");
// }

// void setDacVoltage(float volts, int channel) {
//   if (volts < 0.0f) volts = 0.0f;
//   if (volts > DAC_FULL_V) volts = DAC_FULL_V;

//   uint16_t code = (uint16_t)((volts / DAC_FULL_V) * 32767.0f + 0.5f);

//   if (dacReady) {
//     dac.setDACOutVoltage(code, channel);
//   }
// }

// void setKV(float kv) {
//   if (kv < 0.0f) kv = 0.0f;
//   if (kv > HV_FULL_SCALE_KV) kv = HV_FULL_SCALE_KV;

//   currentSetKV = kv;

//   float volts = (kv / HV_FULL_SCALE_KV) * DAC_FULL_V;
//   setDacVoltage(volts, DAC_CH_KV);

//   Serial.print("Setpoint: ");
//   Serial.print(kv, 1);
//   Serial.print(" kV -> ");
//   Serial.print(volts, 4);
//   Serial.println(" V at DAC CH0");
// }

// void setPSI(float psi) {
//   if (psi < 0.0f) psi = 0.0f;
//   if (psi > PSI_FULL_SCALE) psi = PSI_FULL_SCALE;

//   currentSetPSI = psi;

//   float volts = (psi / PSI_FULL_SCALE) * DAC_FULL_V;
//   setDacVoltage(volts, DAC_CH_PSI);

//   Serial.print("Pressure setpoint: ");
//   Serial.print(psi, 2);
//   Serial.print(" psi -> ");
//   Serial.print(volts, 4);
//   Serial.println(" V at DAC CH1");
// }

// void printReadings() {
//   float vMonPinVolts    = readAveragedVoltage(V_MON_PIN, NUM_SAMPLES, ADC_REF_V);
//   float iMonPinVolts    = readAveragedVoltage(I_MON_PIN, NUM_SAMPLES, ADC_REF_V);
//   float pressPinVolts   = readAveragedVoltage(PRESSURE_PIN, NUM_SAMPLES, ADC_REF_V);
//   float marxPosPinVolts = readAveragedVoltage(MARX_POS_PIN, NUM_SAMPLES, ADC_REF_V);
//   float marxNegPinVolts = readAveragedVoltage(MARX_NEG_PIN, NUM_SAMPLES, ADC_REF_V);

//   float vMonActualVolts = (vMonPinVolts * VMON_DIVIDER_SLOPE) + VMON_DIVIDER_INTERCEPT;
//   float outputKV = (vMonActualVolts / VMON_FULL_SCALE_V) * HV_FULL_SCALE_KV;
//   if (outputKV < 0.0f) outputKV = 0.0f;

//   float iMonActualVolts = (iMonPinVolts * IMON_DIVIDER_SLOPE) + IMON_DIVIDER_INTERCEPT;
//   float outputMA = (iMonActualVolts / IMON_FULL_SCALE_V) * I_FULL_SCALE_MA;
//   if (outputMA < 0.0f) outputMA = 0.0f;

//   float pressActualVolts = pressPinVolts * PRESSURE_DIVIDER_RATIO;
//   float outputPSI = (pressActualVolts / PRESSURE_FULL_SCALE_V) * PRESSURE_FULL_SCALE_PSI;
//   if (outputPSI < 0.0f) outputPSI = 0.0f;

//   float marxPosKV = (marxPosPinVolts / MARX_FULL_SCALE_PIN_V) * MARX_FULL_SCALE_KV;
//   if (marxPosKV < 0.0f) marxPosKV = 0.0f;

//   float marxNegMonV = (marxNegPinVolts * MARX_NEG_DIVIDER_SLOPE) + MARX_NEG_DIVIDER_INTERCEPT;

//   // -5V monitor means 100 kV magnitude.
//   // 0V monitor means 0 kV.
//   float marxNegKV = -marxNegMonV * (MARX_FULL_SCALE_KV / 5.0f);

//   if (marxNegKV < 0.0f) marxNegKV = 0.0f;
//   if (marxNegKV > MARX_FULL_SCALE_KV) marxNegKV = MARX_FULL_SCALE_KV;

//   Serial.print("HV=");
//   Serial.print(hvEnabled ? "ON" : "OFF");

//   Serial.print(" | SET: ");
//   Serial.print(currentSetKV, 1);
//   Serial.print(" kV / ");
//   Serial.print(currentSetPSI, 2);
//   Serial.print(" psi");

//   Serial.print(" | V_MON pin: ");
//   Serial.print(vMonPinVolts, 4);
//   Serial.print(" V");

//   Serial.print(" | Glassman V_MON: ");
//   Serial.print(vMonActualVolts, 4);
//   Serial.print(" V");

//   Serial.print(" | Output: ");
//   Serial.print(outputKV, 2);
//   Serial.print(" kV");

//   Serial.print(" || I_MON pin: ");
//   Serial.print(iMonPinVolts, 4);
//   Serial.print(" V");

//   Serial.print(" | Glassman I_MON: ");
//   Serial.print(iMonActualVolts, 4);
//   Serial.print(" V");

//   Serial.print(" | Output: ");
//   Serial.print(outputMA, 4);
//   Serial.print(" mA");

//   Serial.print(" || P pin: ");
//   Serial.print(pressPinVolts, 4);
//   Serial.print(" V");

//   Serial.print(" | Sensor: ");
//   Serial.print(pressActualVolts, 4);
//   Serial.print(" V");

//   Serial.print(" | Pressure: ");
//   Serial.print(outputPSI, 2);
//   Serial.print(" psi");

//   Serial.print(" || Marx+: ");
//   Serial.print(marxPosPinVolts, 4);
//   Serial.print(" V -> ");
//   Serial.print(marxPosKV, 2);
//   Serial.print(" kV");

//   Serial.print(" || Marx- pin: ");
//   Serial.print(marxNegPinVolts, 4);
//   Serial.print(" V");

//   Serial.print(" | Marx- mon: ");
//   Serial.print(marxNegMonV, 4);
//   Serial.print(" V");

//   Serial.print(" | Marx-: ");
//   Serial.print(marxNegKV, 2);
//   Serial.println(" kV");
// }

// void handleSerialCommands() {
//   if (!Serial.available()) return;

//   String cmd = Serial.readStringUntil('\n');
//   cmd.trim();
//   cmd.toUpperCase();

//   if (cmd == "ON") {
//     setHVEnable(true);
//   } else if (cmd == "OFF") {
//     setHVEnable(false);
//   } else if (cmd == "TOGGLE") {
//     setHVEnable(!hvEnabled);
//   } else if (cmd.startsWith("KV ")) {
//     setKV(cmd.substring(3).toFloat());
//   } else if (cmd.startsWith("PSI ")) {
//     setPSI(cmd.substring(4).toFloat());
//   } else if (cmd.startsWith("VDAC ")) {
//     float v = cmd.substring(5).toFloat();
//     setDacVoltage(v, DAC_CH_KV);

//     Serial.print("DAC CH0 set to ");
//     Serial.print(v, 4);
//     Serial.println(" V raw");
//   } else if (cmd.startsWith("VDAC2 ")) {
//     float v = cmd.substring(6).toFloat();
//     setDacVoltage(v, DAC_CH_PSI);

//     Serial.print("DAC CH1 set to ");
//     Serial.print(v, 4);
//     Serial.println(" V raw");
//   } else if (cmd == "ZERO") {
//     setKV(0.0f);
//     setPSI(0.0f);
//   } else if (cmd == "STATUS") {
//     Serial.print("HV STATUS: ");
//     Serial.print(hvEnabled ? "ON" : "OFF");
//     Serial.print(" | kV setpoint: ");
//     Serial.print(currentSetKV, 1);
//     Serial.print(" | PSI setpoint: ");
//     Serial.println(currentSetPSI, 2);
//   } else if (cmd == "READ") {
//     printReadings();
//   } else if (cmd == "HELP") {
//     Serial.println("Commands:");
//     Serial.println("  ON          -> HV enable HIGH");
//     Serial.println("  OFF         -> HV enable LOW");
//     Serial.println("  TOGGLE      -> toggle HV enable");
//     Serial.println("  KV <val>    -> set HV setpoint 0-125 kV");
//     Serial.println("  PSI <val>   -> set pressure setpoint 0-24.49 psi");
//     Serial.println("  VDAC <val>  -> set raw DAC CH0 volts 0-10");
//     Serial.println("  VDAC2 <val> -> set raw DAC CH1 volts 0-10");
//     Serial.println("  ZERO        -> zero both setpoints");
//     Serial.println("  STATUS      -> print HV state and setpoints");
//     Serial.println("  READ        -> print one measurement line");
//     Serial.println("  HELP        -> show commands");
//   } else if (cmd.length() > 0) {
//     Serial.print("Unknown command: ");
//     Serial.println(cmd);
//   }
// }

// void setup() {
//   Serial.begin(115200);

//   pinMode(HV_ENABLE_PIN, OUTPUT);
//   digitalWrite(HV_ENABLE_PIN, LOW);
//   hvEnabled = false;

//   if (dac.begin() == 0) {
//     dac.setDACOutRange(dac.eOutputRange10V);
//     dacReady = true;

//     setKV(0.0f);                  // HV setpoint always 0 on boot (safety)
//     setPSI(BOOT_PRESSURE_PSI);    // keep the dome at a safe pressure on boot
//   } else {
//     Serial.println("WARNING: GP8413 not found, setpoint control disabled");
//   }

//   for (int i = 0; i < 10; i++) {
//     analogRead(V_MON_PIN);
//     analogRead(I_MON_PIN);
//     analogRead(PRESSURE_PIN);
//     analogRead(MARX_POS_PIN);
//     analogRead(MARX_NEG_PIN);
//     delay(5);
//   }

//   Serial.println("Glassman WR125 + Pressure Reg + Marx Rail Monitor + Dual Setpoint");
//   Serial.println("A3=V-MON, A4=I-MON, A5=PRESS, A10=MARX+, A11=MARX-");
//   Serial.println("Marx- mapping: A11 2.5V = 0kV, A11 0V = -100kV magnitude");
//   Serial.println("Commands: ON, OFF, TOGGLE, KV, PSI, VDAC, VDAC2, ZERO, STATUS, READ, HELP");
//   Serial.println();
// }

// void loop() {
//   handleSerialCommands();

//   if (millis() - lastPrint >= PRINT_INTERVAL_MS) {
//     lastPrint = millis();
//     printReadings();
//   }
// }
// Glassman WR125 monitor reader + HV enable + pressure + GP8413 kV & PSI setpoints + Marx rail monitors
//
// Reads:
//   A3  = V-MONITOR through 10k/10k divider
//   A4  = I-MONITOR through 10k/10k divider
//   A5  = PRESSURE (0-10V, 0-160 psi gauge) through 10k/10k divider
//   A10 = MARX POSITIVE RAIL monitor, 0-5V = 0-100kV
//   A11 = MARX NEGATIVE RAIL monitor through 10k/10k level shift
//
// Marx negative monitor:
//   Actual monitor:  0V to -5V
//   Arduino A11:     2.5V to 0V
//   Transfer:        V_mon = 2*V_adc - 5
//
// Controls:
//   D8  = HV ENABLE
//   I2C = GP8413 DAC
//         CH0 -> Glassman V-PROGRAM (0-10V = 0-125 kV)
//         CH1 -> Parker pressure regulator setpoint (calibrated, see CAL_ constants)

#include <DFRobot_GP8XXX.h>

const int V_MON_PIN     = A3;
const int I_MON_PIN     = A4;
const int PRESSURE_PIN  = A5;
const int MARX_POS_PIN  = A10;
const int MARX_NEG_PIN  = A11;
const int HV_ENABLE_PIN = 8;

const float ADC_REF_V = 5.0f;
const int ADC_COUNTS = 1023;

const float VMON_DIVIDER_SLOPE     = 2.035875f;
const float VMON_DIVIDER_INTERCEPT = 0.009092f;
const float VMON_FULL_SCALE_V      = 6.65f;
const float HV_FULL_SCALE_KV       = 125.0f;

const float IMON_DIVIDER_SLOPE     = 2.035875f;
const float IMON_DIVIDER_INTERCEPT = 0.009092f;
const float IMON_FULL_SCALE_V      = 10.0f;
const float I_FULL_SCALE_MA        = 2.0f;

// Pressure gauge readback (A5). Trimmed to match physical dial.
const float PRESSURE_DIVIDER_RATIO  = 2.0f;
const float PRESSURE_FULL_SCALE_V   = 10.0f;
const float PRESSURE_FULL_SCALE_PSI = 159.4f;

const float MARX_FULL_SCALE_PIN_V = 5.0f;
const float MARX_FULL_SCALE_KV    = 100.0f;

const float MARX_NEG_DIVIDER_SLOPE     = 2.0f;
const float MARX_NEG_DIVIDER_INTERCEPT = -5.0f;

DFRobot_GP8413 dac(0x58);
const int   DAC_CH_KV  = 0;
const int   DAC_CH_PSI = 1;
const float DAC_FULL_V = 10.0f;

// ---- Parker regulator setpoint calibration (CH1) ----
// Measured by sweep: delivered_psi = CAL_SLOPE * dac_V + CAL_OFFSET
// To command a target, invert: dac_V = (target - CAL_OFFSET) / CAL_SLOPE
// Re-run the cal sweep (ceiling <= 105 psi, inlet >= target + ~8 psi) and
// drop new numbers in here if anything in the pneumatic path changes.
const float CAL_SLOPE   = 15.0226f;   // psi per DAC volt
// const float CAL_OFFSET  = -2.3129f;   // psi at 0 V
const float CAL_OFFSET = -0.21f;   // was -2.3129, +2.1 to center 110
const float PSI_MAX_CMD  = 145.0f;    // hard clamp on requested pressure

// Pressure setpoint applied automatically on boot/reset. The dome should hold a
// safe operating pressure even if the Mega reboots (loose USB, power glitch),
// instead of venting to 0. kV is still forced to 0 on boot for HV safety.
const float BOOT_PRESSURE_PSI = 50.0f;

bool dacReady = false;
float currentSetKV  = 0.0f;
float currentSetPSI = 0.0f;

const int NUM_SAMPLES = 20;
const unsigned long PRINT_INTERVAL_MS = 500;

unsigned long lastPrint = 0;
bool hvEnabled = false;

float readAveragedVoltage(int pin, int samples, float adcRef) {
  analogRead(pin);
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

void setDacVoltage(float volts, int channel) {
  if (volts < 0.0f) volts = 0.0f;
  if (volts > DAC_FULL_V) volts = DAC_FULL_V;

  uint16_t code = (uint16_t)((volts / DAC_FULL_V) * 32767.0f + 0.5f);

  if (dacReady) {
    dac.setDACOutVoltage(code, channel);
  }
}

void setKV(float kv) {
  if (kv < 0.0f) kv = 0.0f;
  if (kv > HV_FULL_SCALE_KV) kv = HV_FULL_SCALE_KV;

  currentSetKV = kv;

  float volts = (kv / HV_FULL_SCALE_KV) * DAC_FULL_V;
  setDacVoltage(volts, DAC_CH_KV);

  Serial.print("Setpoint: ");
  Serial.print(kv, 1);
  Serial.print(" kV -> ");
  Serial.print(volts, 4);
  Serial.println(" V at DAC CH0");
}

void setPSI(float psi) {
  if (psi < 0.0f) psi = 0.0f;
  if (psi > PSI_MAX_CMD) psi = PSI_MAX_CMD;

  currentSetPSI = psi;

  // Invert the measured calibration to get the commanding voltage.
  float volts = (psi - CAL_OFFSET) / CAL_SLOPE;
  if (volts < 0.0f) volts = 0.0f;
  if (volts > DAC_FULL_V) volts = DAC_FULL_V;

  setDacVoltage(volts, DAC_CH_PSI);

  Serial.print("Pressure setpoint: ");
  Serial.print(psi, 2);
  Serial.print(" psi -> ");
  Serial.print(volts, 4);
  Serial.println(" V at DAC CH1");
}

void printReadings() {
  float vMonPinVolts    = readAveragedVoltage(V_MON_PIN, NUM_SAMPLES, ADC_REF_V);
  float iMonPinVolts    = readAveragedVoltage(I_MON_PIN, NUM_SAMPLES, ADC_REF_V);
  float pressPinVolts   = readAveragedVoltage(PRESSURE_PIN, NUM_SAMPLES, ADC_REF_V);
  float marxPosPinVolts = readAveragedVoltage(MARX_POS_PIN, NUM_SAMPLES, ADC_REF_V);
  float marxNegPinVolts = readAveragedVoltage(MARX_NEG_PIN, NUM_SAMPLES, ADC_REF_V);

  float vMonActualVolts = (vMonPinVolts * VMON_DIVIDER_SLOPE) + VMON_DIVIDER_INTERCEPT;
  float outputKV = (vMonActualVolts / VMON_FULL_SCALE_V) * HV_FULL_SCALE_KV;
  if (outputKV < 0.0f) outputKV = 0.0f;

  float iMonActualVolts = (iMonPinVolts * IMON_DIVIDER_SLOPE) + IMON_DIVIDER_INTERCEPT;
  float outputMA = (iMonActualVolts / IMON_FULL_SCALE_V) * I_FULL_SCALE_MA;
  if (outputMA < 0.0f) outputMA = 0.0f;

  float pressActualVolts = pressPinVolts * PRESSURE_DIVIDER_RATIO;
  float outputPSI = (pressActualVolts / PRESSURE_FULL_SCALE_V) * PRESSURE_FULL_SCALE_PSI;
  if (outputPSI < 0.0f) outputPSI = 0.0f;

  float marxPosKV = (marxPosPinVolts / MARX_FULL_SCALE_PIN_V) * MARX_FULL_SCALE_KV;
  if (marxPosKV < 0.0f) marxPosKV = 0.0f;

  float marxNegMonV = (marxNegPinVolts * MARX_NEG_DIVIDER_SLOPE) + MARX_NEG_DIVIDER_INTERCEPT;

  float marxNegKV = -marxNegMonV * (MARX_FULL_SCALE_KV / 5.0f);
  if (marxNegKV < 0.0f) marxNegKV = 0.0f;
  if (marxNegKV > MARX_FULL_SCALE_KV) marxNegKV = MARX_FULL_SCALE_KV;

  Serial.print("HV=");
  Serial.print(hvEnabled ? "ON" : "OFF");

  Serial.print(" | SET: ");
  Serial.print(currentSetKV, 1);
  Serial.print(" kV / ");
  Serial.print(currentSetPSI, 2);
  Serial.print(" psi");

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
  Serial.print(" psi");

  Serial.print(" || Marx+: ");
  Serial.print(marxPosPinVolts, 4);
  Serial.print(" V -> ");
  Serial.print(marxPosKV, 2);
  Serial.print(" kV");

  Serial.print(" || Marx- pin: ");
  Serial.print(marxNegPinVolts, 4);
  Serial.print(" V");

  Serial.print(" | Marx- mon: ");
  Serial.print(marxNegMonV, 4);
  Serial.print(" V");

  Serial.print(" | Marx-: ");
  Serial.print(marxNegKV, 2);
  Serial.println(" kV");
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
  } else if (cmd.startsWith("PSI ")) {
    setPSI(cmd.substring(4).toFloat());
  } else if (cmd.startsWith("VDAC ")) {
    float v = cmd.substring(5).toFloat();
    setDacVoltage(v, DAC_CH_KV);

    Serial.print("DAC CH0 set to ");
    Serial.print(v, 4);
    Serial.println(" V raw");
  } else if (cmd.startsWith("VDAC2 ")) {
    float v = cmd.substring(6).toFloat();
    setDacVoltage(v, DAC_CH_PSI);

    Serial.print("DAC CH1 set to ");
    Serial.print(v, 4);
    Serial.println(" V raw");
  } else if (cmd == "ZERO") {
    setKV(0.0f);
    setPSI(0.0f);
  } else if (cmd == "STATUS") {
    Serial.print("HV STATUS: ");
    Serial.print(hvEnabled ? "ON" : "OFF");
    Serial.print(" | kV setpoint: ");
    Serial.print(currentSetKV, 1);
    Serial.print(" | PSI setpoint: ");
    Serial.println(currentSetPSI, 2);
  } else if (cmd == "READ") {
    printReadings();
  } else if (cmd == "HELP") {
    Serial.println("Commands:");
    Serial.println("  ON          -> HV enable HIGH");
    Serial.println("  OFF         -> HV enable LOW");
    Serial.println("  TOGGLE      -> toggle HV enable");
    Serial.println("  KV <val>    -> set HV setpoint 0-125 kV");
    Serial.println("  PSI <val>   -> set pressure setpoint 0-145 psi (calibrated)");
    Serial.println("  VDAC <val>  -> set raw DAC CH0 volts 0-10");
    Serial.println("  VDAC2 <val> -> set raw DAC CH1 volts 0-10");
    Serial.println("  ZERO        -> zero both setpoints");
    Serial.println("  STATUS      -> print HV state and setpoints");
    Serial.println("  READ        -> print one measurement line");
    Serial.println("  HELP        -> show commands");
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

  if (dac.begin() == 0) {
    dac.setDACOutRange(dac.eOutputRange10V);
    dacReady = true;

    setKV(0.0f);                  // HV setpoint always 0 on boot (safety)
    setPSI(BOOT_PRESSURE_PSI);    // keep the dome at a safe pressure on boot
  } else {
    Serial.println("WARNING: GP8413 not found, setpoint control disabled");
  }

  for (int i = 0; i < 10; i++) {
    analogRead(V_MON_PIN);
    analogRead(I_MON_PIN);
    analogRead(PRESSURE_PIN);
    analogRead(MARX_POS_PIN);
    analogRead(MARX_NEG_PIN);
    delay(5);
  }

  Serial.println("Glassman WR125 + Pressure Reg + Marx Rail Monitor + Dual Setpoint");
  Serial.println("A3=V-MON, A4=I-MON, A5=PRESS, A10=MARX+, A11=MARX-");
  Serial.println("Marx- mapping: A11 2.5V = 0kV, A11 0V = -100kV magnitude");
  Serial.println("Pressure CH1 calibrated: dac_V = (psi - CAL_OFFSET)/CAL_SLOPE");
  Serial.println("Commands: ON, OFF, TOGGLE, KV, PSI, VDAC, VDAC2, ZERO, STATUS, READ, HELP");
  Serial.println();
}

void loop() {
  handleSerialCommands();

  if (millis() - lastPrint >= PRINT_INTERVAL_MS) {
    lastPrint = millis();
    printReadings();
  }
}