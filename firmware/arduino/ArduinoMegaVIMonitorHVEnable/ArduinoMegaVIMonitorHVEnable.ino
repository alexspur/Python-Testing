// // Glassman WR125 monitor reader + HV enable for Arduino Mega
// //
// // Reads:
// //   A0 = V-MONITOR through 1:1 divider
// //   A1 = I-MONITOR through 1:1 divider
// //
// // Controls:
// //   D7 = HV ENABLE
// //
// // Assumptions:
// // - Mega analog reference = 5.0 V
// // - Divider is 10k / 10k, so actual Glassman monitor voltage = 2x Arduino pin voltage
// // - WR125 model scaling:
// //      0-10 V monitor = 0-125 kV
// //      0-10 V monitor = 0-2 mA
// //
// // Wiring:
// //   Mega A0  -> Glassman pin 4 (V-MONITOR) through divider
// //   Mega A1  -> Glassman pin 7 (I-MONITOR) through divider
// //   Mega D7  -> Glassman pin 11 (HV ENABLE)
// //   Mega GND -> Glassman pin 2 (COMMON)
// //   Glassman pin 3 (INTERLOCK) -> Glassman pin 2 (COMMON)

// const int V_MON_PIN = A0;
// const int I_MON_PIN = A1;
// const int HV_ENABLE_PIN = 7;

// const float ADC_REF_V = 5.0;
// const int ADC_COUNTS = 1023;
// // const float DIVIDER_RATIO = 3.057f;
// // const float DIVIDER_RATIO = 3.0f;
// // const float VMON_FULL_SCALE_V = 6.64f;
// // const float IMON_FULL_SCALE_V = 6.64f;  // verify this matches I-MON at full scale
// const float VMON_DIVIDER_SLOPE     = 2.035875f;
// const float VMON_DIVIDER_INTERCEPT = 0.009092f;
// const float VMON_FULL_SCALE_V      = 6.65f;
// const float HV_FULL_SCALE_KV       = 125.0f;

// const float I_FULL_SCALE_MA = 2.0;

// const int NUM_SAMPLES = 20;
// const unsigned long PRINT_INTERVAL_MS = 500;

// unsigned long lastPrint = 0;
// bool hvEnabled = false;

// float readAveragedVoltage(int pin, int samples, float adcRef) {
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

// // void printReadings() {
// //   float vMonPinVolts = readAveragedVoltage(V_MON_PIN, NUM_SAMPLES, ADC_REF_V);
// //   float iMonPinVolts = readAveragedVoltage(I_MON_PIN, NUM_SAMPLES, ADC_REF_V);

// //   float vMonActualVolts = vMonPinVolts * DIVIDER_RATIO;
// //   float iMonActualVolts = iMonPinVolts * DIVIDER_RATIO;

// //   // float outputKV = (vMonActualVolts / 10.0) * HV_FULL_SCALE_KV;
// //   // float outputMA = (iMonActualVolts / 10.0) * I_FULL_SCALE_MA;
// //   float outputKV = (vMonActualVolts / VMON_FULL_SCALE_V) * HV_FULL_SCALE_KV;
// //   float outputMA = (iMonActualVolts / IMON_FULL_SCALE_V) * I_FULL_SCALE_MA;

// //   if (outputKV < 0.0) outputKV = 0.0;
// //   if (outputMA < 0.0) outputMA = 0.0;

// //   Serial.print("HV=");
// //   Serial.print(hvEnabled ? "ON" : "OFF");

// //   Serial.print(" | V_MON pin: ");
// //   Serial.print(vMonPinVolts, 3);
// //   Serial.print(" V");

// //   Serial.print(" | Glassman V_MON: ");
// //   Serial.print(vMonActualVolts, 3);
// //   Serial.print(" V");

// //   Serial.print(" | Output: ");
// //   Serial.print(outputKV, 2);
// //   Serial.print(" kV");

// //   Serial.print(" || I_MON pin: ");
// //   Serial.print(iMonPinVolts, 3);
// //   Serial.print(" V");

// //   Serial.print(" | Glassman I_MON: ");
// //   Serial.print(iMonActualVolts, 3);
// //   Serial.print(" V");

// //   Serial.print(" | Output: ");
// //   Serial.print(outputMA, 4);
// //   Serial.println(" mA");
// // }
// // void printReadings() {
// //   float vMonPinVolts = readAveragedVoltage(V_MON_PIN, NUM_SAMPLES, ADC_REF_V);
// //   float iMonPinVolts = readAveragedVoltage(I_MON_PIN, NUM_SAMPLES, ADC_REF_V);

  
// //   Serial.print("HV=");
// //   Serial.print(hvEnabled ? "ON" : "OFF");

// //   Serial.print(" | V_MON pin: ");
// //   Serial.print(vMonPinVolts, 4);
// //   Serial.print(" V");

// //   Serial.print(" | I_MON pin: ");
// //   Serial.print(iMonPinVolts, 4);
// //   Serial.println(" V");
// // }
// void printReadings() {
//   float vMonPinVolts = readAveragedVoltage(V_MON_PIN, NUM_SAMPLES, ADC_REF_V);
//   float iMonPinVolts = readAveragedVoltage(I_MON_PIN, NUM_SAMPLES, ADC_REF_V);

//   float vMonActualVolts = (vMonPinVolts * VMON_DIVIDER_SLOPE) + VMON_DIVIDER_INTERCEPT;
//   float outputKV = (vMonActualVolts / VMON_FULL_SCALE_V) * HV_FULL_SCALE_KV;

//   if (outputKV < 0.0) outputKV = 0.0;

//   Serial.print("HV=");
//   Serial.print(hvEnabled ? "ON" : "OFF");

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
//   Serial.print("N/A");

//   Serial.print(" | Output: ");
//   Serial.println("0.0000 mA");
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
//   } else if (cmd == "STATUS") {
//     Serial.print("HV STATUS: ");
//     Serial.println(hvEnabled ? "ON" : "OFF");
//   } else if (cmd == "READ") {
//     printReadings();
//   } else if (cmd == "HELP") {
//     Serial.println("Commands:");
//     Serial.println("  ON      -> HV enable HIGH");
//     Serial.println("  OFF     -> HV enable LOW");
//     Serial.println("  TOGGLE  -> toggle HV enable");
//     Serial.println("  STATUS  -> print HV enable state");
//     Serial.println("  READ    -> print one measurement line");
//     Serial.println("  HELP    -> show commands");
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

//   for (int i = 0; i < 10; i++) {
//     analogRead(V_MON_PIN);
//     analogRead(I_MON_PIN);
//     delay(5);
//   }

//   Serial.println("Glassman WR125 Monitor Reader + HV Enable");
//   Serial.println("A0 = V-MONITOR, A1 = I-MONITOR, D7 = HV ENABLE");
//   Serial.println("Commands: ON, OFF, TOGGLE, STATUS, READ, HELP");
//   Serial.println();
// }

// void loop() {
//   handleSerialCommands();

//   if (millis() - lastPrint >= PRINT_INTERVAL_MS) {
//     lastPrint = millis();
//     printReadings();
//   }
// }
// // // Glassman WR125 monitor reader + HV enable for Arduino Mega
// // //
// // // Reads:
// // //   A0 = V-MONITOR (Glassman pin 4) through 2:1 divider (10k + 10k)
// // //   A1 = I-MONITOR (Glassman pin 7) through 2:1 divider (10k + 10k)
// // //
// // // Controls:
// // //   D7 = HV ENABLE (Glassman pin 11)
// // //
// // // Common:
// // //   Mega GND -> Glassman pin 2
// // //   Glassman pin 3 (INTERLOCK) -> Glassman pin 2
// // //
// // // WR125 spec: 0-10 V monitor -> 0-125 kV / 0-2 mA.

// // const int V_MON_PIN     = A0;
// // const int I_MON_PIN     = A1;
// // const int HV_ENABLE_PIN = 7;

// // const float ADC_REF_V  = 5.0f;
// // const int   ADC_COUNTS = 1023;

// // // ---- V-MON calibration (already characterized) ----
// // const float VMON_DIVIDER_SLOPE     = 2.035875f;
// // const float VMON_DIVIDER_INTERCEPT = 0.009092f;
// // const float VMON_FULL_SCALE_V      = 6.65f;     // terminal V at cmd=10V
// // const float HV_FULL_SCALE_KV       = 125.0f;

// // // ---- I-MON calibration (start from V-MON values; re-cal with a meter) ----
// // // If the I-MON tap is the same 10k+10k divider as V-MON, the slope/intercept
// // // are close to the V-MON ones. IMON_FULL_SCALE_V = the *terminal* voltage
// // // you see on Glassman pin 7 at full-scale 2 mA. Default to 10.0 V (spec)
// // // and refine after measuring with a multimeter.
// // const float IMON_DIVIDER_SLOPE     = 2.035875f;
// // const float IMON_DIVIDER_INTERCEPT = 0.009092f;
// // const float IMON_FULL_SCALE_V      = 10.0f;
// // const float I_FULL_SCALE_MA        = 2.0f;       // WR125 max output current

// // const int           NUM_SAMPLES       = 8;
// // const unsigned long PRINT_INTERVAL_MS = 100;     // 10 Hz

// // unsigned long lastPrint = 0;
// // bool          hvEnabled = false;

// // float readAveragedVoltage(int pin, int samples, float adcRef) {
// //   unsigned long sum = 0;
// //   for (int i = 0; i < samples; i++) {
// //     sum += analogRead(pin);
// //   }
// //   float avgCounts = (float)sum / samples;
// //   return (avgCounts / ADC_COUNTS) * adcRef;
// // }

// // void setHVEnable(bool enable) {
// //   hvEnabled = enable;
// //   digitalWrite(HV_ENABLE_PIN, enable ? HIGH : LOW);
// //   Serial.print("HV ENABLE: ");
// //   Serial.println(enable ? "ON" : "OFF");
// // }

// // void printReadings() {
// //   float vMonPinVolts = readAveragedVoltage(V_MON_PIN, NUM_SAMPLES, ADC_REF_V);
// //   float iMonPinVolts = readAveragedVoltage(I_MON_PIN, NUM_SAMPLES, ADC_REF_V);

// //   float vMonActualVolts = (vMonPinVolts * VMON_DIVIDER_SLOPE) + VMON_DIVIDER_INTERCEPT;
// //   float iMonActualVolts = (iMonPinVolts * IMON_DIVIDER_SLOPE) + IMON_DIVIDER_INTERCEPT;

// //   float outputKV = (vMonActualVolts / VMON_FULL_SCALE_V) * HV_FULL_SCALE_KV;
// //   float outputMA = (iMonActualVolts / IMON_FULL_SCALE_V) * I_FULL_SCALE_MA;
// //   if (outputKV < 0.0f) outputKV = 0.0f;
// //   if (outputMA < 0.0f) outputMA = 0.0f;

// //   Serial.print("HV=");
// //   Serial.print(hvEnabled ? "ON" : "OFF");

// //   Serial.print(" | V_MON pin: ");
// //   Serial.print(vMonPinVolts, 4);
// //   Serial.print(" V");

// //   Serial.print(" | Glassman V_MON: ");
// //   Serial.print(vMonActualVolts, 4);
// //   Serial.print(" V");

// //   Serial.print(" | Output: ");
// //   Serial.print(outputKV, 2);
// //   Serial.print(" kV");

// //   Serial.print(" || I_MON pin: ");
// //   Serial.print(iMonPinVolts, 4);
// //   Serial.print(" V");

// //   Serial.print(" | Glassman I_MON: ");
// //   Serial.print(iMonActualVolts, 4);
// //   Serial.print(" V");

// //   Serial.print(" | Output: ");
// //   Serial.print(outputMA, 4);
// //   Serial.println(" mA");
// // }

// // void handleSerialCommands() {
// //   if (!Serial.available()) return;
// //   String cmd = Serial.readStringUntil('\n');
// //   cmd.trim();
// //   cmd.toUpperCase();

// //   if      (cmd == "ON")     setHVEnable(true);
// //   else if (cmd == "OFF")    setHVEnable(false);
// //   else if (cmd == "TOGGLE") setHVEnable(!hvEnabled);
// //   else if (cmd == "STATUS") {
// //     Serial.print("HV STATUS: ");
// //     Serial.println(hvEnabled ? "ON" : "OFF");
// //   }
// //   else if (cmd == "READ") printReadings();
// //   else if (cmd == "HELP") {
// //     Serial.println("Commands: ON, OFF, TOGGLE, STATUS, READ, HELP");
// //   }
// //   else if (cmd.length() > 0) {
// //     Serial.print("Unknown command: ");
// //     Serial.println(cmd);
// //   }
// // }

// // void setup() {
// //   Serial.begin(115200);
// //   pinMode(HV_ENABLE_PIN, OUTPUT);
// //   digitalWrite(HV_ENABLE_PIN, LOW);
// //   hvEnabled = false;

// //   // ADC warm-up
// //   for (int i = 0; i < 10; i++) {
// //     analogRead(V_MON_PIN);
// //     analogRead(I_MON_PIN);
// //     delay(5);
// //   }

// //   Serial.println("Glassman WR125 Monitor Reader + HV Enable");
// //   Serial.println("A0 = V-MONITOR, A1 = I-MONITOR, D7 = HV ENABLE");
// //   Serial.println("Commands: ON, OFF, TOGGLE, STATUS, READ, HELP");
// //   Serial.println();
// // }

// // void loop() {
// //   handleSerialCommands();
// //   if (millis() - lastPrint >= PRINT_INTERVAL_MS) {
// //     lastPrint = millis();
// //     printReadings();
// //   }
// // }

// Glassman WR125 monitor reader + HV enable for Arduino Mega
//
// Reads:
//   A0 = V-MONITOR through 1:1 divider
//   A1 = I-MONITOR through 1:1 divider
//   A3 = PRESSURE (0-10V, 0-100 psi) through 10k/10k divider
//
// Controls:
//   D7 = HV ENABLE
//
// Assumptions:
// - Mega analog reference = 5.0 V
// - V-MON divider is 10k / 10k, so actual Glassman monitor voltage = 2x Arduino pin voltage
// - Pressure divider is 10k / 10k, so actual sensor voltage = 2x Arduino pin voltage
// - WR125 model scaling:
//      0-10 V monitor = 0-125 kV
//      0-10 V monitor = 0-2 mA
// - Pressure sensor: 0-10 V = 0-100 psi
//
// Wiring:
//   Mega A0  -> Glassman pin 4 (V-MONITOR) through divider
//   Mega A1  -> Glassman pin 7 (I-MONITOR) through divider
//   Mega A3  -> Pressure sensor output through 10k/10k divider
//   Mega D7  -> Glassman pin 11 (HV ENABLE)
//   Mega GND -> Glassman pin 2 (COMMON)
//   Glassman pin 3 (INTERLOCK) -> Glassman pin 2 (COMMON)

const int V_MON_PIN = A0;
const int I_MON_PIN = A1;
const int PRESSURE_PIN = A3;
const int HV_ENABLE_PIN = 7;

const float ADC_REF_V = 5.0;
const int ADC_COUNTS = 1023;

const float VMON_DIVIDER_SLOPE     = 2.035875f;
const float VMON_DIVIDER_INTERCEPT = 0.009092f;
const float VMON_FULL_SCALE_V      = 6.65f;
const float HV_FULL_SCALE_KV       = 125.0f;

const float I_FULL_SCALE_MA = 2.0;

// ---- Pressure channel (A3) ----
// 0-10 V sensor through 10k/10k divider -> 0-5 V at pin.
// Pin voltage * 2 = sensor voltage. 0-10 V = 0-100 psi.
const float PRESSURE_DIVIDER_RATIO  = 2.0f;
const float PRESSURE_FULL_SCALE_V   = 10.0f;
const float PRESSURE_FULL_SCALE_PSI = 100.0f;

const int NUM_SAMPLES = 20;
const unsigned long PRINT_INTERVAL_MS = 500;

unsigned long lastPrint = 0;
bool hvEnabled = false;

float readAveragedVoltage(int pin, int samples, float adcRef) {
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

void printReadings() {
  float vMonPinVolts = readAveragedVoltage(V_MON_PIN, NUM_SAMPLES, ADC_REF_V);
  float iMonPinVolts = readAveragedVoltage(I_MON_PIN, NUM_SAMPLES, ADC_REF_V);
  float pressPinVolts = readAveragedVoltage(PRESSURE_PIN, NUM_SAMPLES, ADC_REF_V);

  float vMonActualVolts = (vMonPinVolts * VMON_DIVIDER_SLOPE) + VMON_DIVIDER_INTERCEPT;
  float outputKV = (vMonActualVolts / VMON_FULL_SCALE_V) * HV_FULL_SCALE_KV;
  if (outputKV < 0.0) outputKV = 0.0;

  float pressActualVolts = pressPinVolts * PRESSURE_DIVIDER_RATIO;
  float outputPSI = (pressActualVolts / PRESSURE_FULL_SCALE_V) * PRESSURE_FULL_SCALE_PSI;
  if (outputPSI < 0.0) outputPSI = 0.0;

  Serial.print("HV=");
  Serial.print(hvEnabled ? "ON" : "OFF");

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
  Serial.print("N/A");

  Serial.print(" | Output: ");
  Serial.print("0.0000 mA");

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
  } else if (cmd == "STATUS") {
    Serial.print("HV STATUS: ");
    Serial.println(hvEnabled ? "ON" : "OFF");
  } else if (cmd == "READ") {
    printReadings();
  } else if (cmd == "HELP") {
    Serial.println("Commands:");
    Serial.println("  ON      -> HV enable HIGH");
    Serial.println("  OFF     -> HV enable LOW");
    Serial.println("  TOGGLE  -> toggle HV enable");
    Serial.println("  STATUS  -> print HV enable state");
    Serial.println("  READ    -> print one measurement line");
    Serial.println("  HELP    -> show commands");
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

  for (int i = 0; i < 10; i++) {
    analogRead(V_MON_PIN);
    analogRead(I_MON_PIN);
    analogRead(PRESSURE_PIN);
    delay(5);
  }

  Serial.println("Glassman WR125 Monitor Reader + HV Enable + Pressure");
  Serial.println("A0 = V-MONITOR, A1 = I-MONITOR, A3 = PRESSURE, D7 = HV ENABLE");
  Serial.println("Commands: ON, OFF, TOGGLE, STATUS, READ, HELP");
  Serial.println();
}

void loop() {
  handleSerialCommands();

  if (millis() - lastPrint >= PRINT_INTERVAL_MS) {
    lastPrint = millis();
    printReadings();
  }
}