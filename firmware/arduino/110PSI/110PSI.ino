

// #include <DFRobot_GP8XXX.h>

// const int PRESSURE_PIN = A5;

// const float ADC_REF_V = 5.0f;
// const int   ADC_COUNTS = 1023;

// const float PRESSURE_DIVIDER_RATIO  = 2.0f;
// const float PRESSURE_FULL_SCALE_V   = 10.0f;
// const float PRESSURE_FULL_SCALE_PSI = 159.4f;   // trimmed to match physical dial

// DFRobot_GP8413 dac(0x58);
// const int   DAC_CH_PSI = 1;
// const float DAC_FULL_V = 10.0f;

// // ---- Parker regulator setpoint calibration (CH1) ----
// // Measured by sweep: delivered_psi = CAL_SLOPE * dac_V + CAL_OFFSET
// // Command inversion: dac_V = (target - CAL_OFFSET) / CAL_SLOPE
// const float CAL_SLOPE  = 15.0226f;   // psi per DAC volt
// const float CAL_OFFSET = -2.3129f;   // psi at 0 V
// const float PSI_MAX_CMD = 145.0f;    // hard clamp on requested pressure

// bool  dacReady = false;
// float currentSetPSI = 110.0f;

// const int NUM_SAMPLES = 20;
// const unsigned long PRINT_INTERVAL_MS = 500;
// unsigned long lastPrint = 0;

// const float BOOT_PRESSURE_PSI = 110.0f;


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

// void setDacVoltage(float volts, int channel) {
//   if (volts < 0.0f) volts = 0.0f;
//   if (volts > DAC_FULL_V) volts = DAC_FULL_V;

//   uint16_t code = (uint16_t)((volts / DAC_FULL_V) * 32767.0f + 0.5f);

//   if (dacReady) {
//     dac.setDACOutVoltage(code, channel);
//   }
// }

// void setPSI(float psi) {
//   if (psi < 0.0f) psi = 0.0f;
//   if (psi > PSI_MAX_CMD) psi = PSI_MAX_CMD;

//   currentSetPSI = psi;

//   // Invert the measured calibration to get the commanding voltage.
//   float volts = (psi - CAL_OFFSET) / CAL_SLOPE;
//   if (volts < 0.0f) volts = 0.0f;
//   if (volts > DAC_FULL_V) volts = DAC_FULL_V;

//   setDacVoltage(volts, DAC_CH_PSI);

//   Serial.print("Setpoint: ");
//   Serial.print(psi, 1);
//   Serial.print(" psi -> ");
//   Serial.print(volts, 4);
//   Serial.println(" V at DAC CH1");
// }

// void printReadings() {
//   float pressPinVolts = readAveragedVoltage(PRESSURE_PIN, NUM_SAMPLES, ADC_REF_V);

//   float pressActualVolts = pressPinVolts * PRESSURE_DIVIDER_RATIO;
//   float outputPSI = (pressActualVolts / PRESSURE_FULL_SCALE_V) * PRESSURE_FULL_SCALE_PSI;
//   if (outputPSI < 0.0f) outputPSI = 0.0f;

//   Serial.print("SET: ");
//   Serial.print(currentSetPSI, 1);
//   Serial.print(" psi | P pin: ");
//   Serial.print(pressPinVolts, 4);
//   Serial.print(" V | Sensor: ");
//   Serial.print(pressActualVolts, 4);
//   Serial.print(" V | Gauge: ");
//   Serial.print(outputPSI, 1);
//   Serial.println(" psi");
// }

// void handleSerialCommands() {
//   if (!Serial.available()) return;

//   String cmd = Serial.readStringUntil('\n');
//   cmd.trim();
//   cmd.toUpperCase();

//   if (cmd.startsWith("PSI ")) {
//     setPSI(cmd.substring(4).toFloat());
//   } else if (cmd.startsWith("VDAC ")) {
//     float v = cmd.substring(5).toFloat();
//     setDacVoltage(v, DAC_CH_PSI);
//     Serial.print("DAC CH1 set to ");
//     Serial.print(v, 4);
//     Serial.println(" V raw");
//   } else if (cmd == "ZERO") {
//     setPSI(0.0f);
//   } else if (cmd == "STATUS") {
//     Serial.print("PSI setpoint: ");
//     Serial.println(currentSetPSI, 1);
//   } else if (cmd == "READ") {
//     printReadings();
//   } else if (cmd == "HELP") {
//     Serial.println("Commands:");
//     Serial.println("  PSI <val>   -> set setpoint 0-145 psig (calibrated)");
//     Serial.println("  VDAC <val>  -> set raw DAC CH1 volts 0-10");
//     Serial.println("  ZERO        -> setpoint to 0");
//     Serial.println("  STATUS      -> print setpoint");
//     Serial.println("  READ        -> print one gauge reading");
//     Serial.println("  HELP        -> show commands");
//   } else if (cmd.length() > 0) {
//     Serial.print("Unknown command: ");
//     Serial.println(cmd);
//   }
// }

// void setup() {
//   Serial.begin(115200);

//   if (dac.begin() == 0) {
//     dac.setDACOutRange(dac.eOutputRange10V);
//     dacReady = true;
//     setPSI(BOOT_PRESSURE_PSI);   // come up to 110 psi on boot
//   } else {
//     Serial.println("WARNING: GP8413 not found, setpoint control disabled");
//   }

//   for (int i = 0; i < 10; i++) {
//     analogRead(PRESSURE_PIN);
//     delay(5);
//   }

//   Serial.println("Parker Regulator Test (calibrated) | A5=PRESS gauge | GP8413 CH1=setpoint");
//   Serial.println("Cmd: dac_V = (psi - CAL_OFFSET)/CAL_SLOPE | Gauge FS=159.4 psi");
//   Serial.println("Commands: PSI, VDAC, ZERO, STATUS, READ, HELP");
//   Serial.println();
// }

// void loop() {
//   handleSerialCommands();

//   if (millis() - lastPrint >= PRINT_INTERVAL_MS) {
//     lastPrint = millis();
//     printReadings();
//   }
// }

















// Test
// Parker P31P/P32P regulator SELF-CALIBRATING SWEEP
//
// Sweeps reachable setpoints up then down, settles + averages each point,
// computes best-fit scale/offset on board, prints a CALIBRATION SUMMARY
// at the end. No PC-side processing needed; just watch the Serial Monitor.
//
// Commands:  GO start | STOP abort | PSI <v> | VDAC <v> | ZERO

#include <DFRobot_GP8XXX.h>
#include <math.h>

const int PRESSURE_PIN = A5;
const float ADC_REF_V = 5.0f;
const int   ADC_COUNTS = 1023;

const float PRESSURE_DIVIDER_RATIO  = 2.0f;
const float PRESSURE_FULL_SCALE_V   = 10.0f;
const float PRESSURE_FULL_SCALE_PSI = 159.4f;

DFRobot_GP8413 dac(0x58);
const int   DAC_CH_PSI = 1;
const float DAC_FULL_V = 10.0f;

float PSI_FULL_SCALE = 145.0f;   // current value used to COMMAND during sweep

// ---- Sweep config: keep all points below your inlet minus ~8 psi ----
// const float sweepPoints[] = {20, 40, 60, 80, 90, 100, 105, 110, 112};
const float sweepPoints[] = {95, 100, 105, 108, 110, 112, 113};
const int   N_POINTS = sizeof(sweepPoints) / sizeof(sweepPoints[0]);

// const unsigned long SETTLE_MS = 25000;
const unsigned long SETTLE_MS = 15000;
const unsigned long SAMPLE_MS = 5000;
const unsigned long SAMPLE_DT = 100;
const int NUM_SAMPLES = 20;

bool dacReady = false;
bool sweeping = false;
bool abortFlag = false;

// storage for fit: every measured point (both directions)
const int MAXROWS = 2 * 16;
float cmdArr[MAXROWS], dacArr[MAXROWS], gaugeArr[MAXROWS];
int   rowCount = 0;

// store up/down separately for hysteresis report
float upCmd[16], upMeas[16];   int upN = 0;
float dnCmd[16], dnMeas[16];   int dnN = 0;

float readAveragedVoltage(int pin, int samples) {
  analogRead(pin); delay(1);
  unsigned long sum = 0;
  for (int i = 0; i < samples; i++) { sum += analogRead(pin); delay(2); }
  return ((float)sum / samples / ADC_COUNTS) * ADC_REF_V;
}

float gaugePSI() {
  float sensorV = readAveragedVoltage(PRESSURE_PIN, NUM_SAMPLES) * PRESSURE_DIVIDER_RATIO;
  float psi = (sensorV / PRESSURE_FULL_SCALE_V) * PRESSURE_FULL_SCALE_PSI;
  return psi < 0 ? 0 : psi;
}

void setDacVoltage(float volts, int channel) {
  if (volts < 0) volts = 0;
  if (volts > DAC_FULL_V) volts = DAC_FULL_V;
  uint16_t code = (uint16_t)((volts / DAC_FULL_V) * 32767.0f + 0.5f);
  if (dacReady) dac.setDACOutVoltage(code, channel);
}

float commandPSI(float psi) {
  if (psi < 0) psi = 0;
  if (psi > PSI_FULL_SCALE) psi = PSI_FULL_SCALE;
  float volts = (psi / PSI_FULL_SCALE) * DAC_FULL_V;
  setDacVoltage(volts, DAC_CH_PSI);
  return volts;
}

bool checkAbort() {
  if (Serial.available()) {
    String c = Serial.readStringUntil('\n');
    c.trim(); c.toUpperCase();
    if (c == "STOP") { abortFlag = true; return true; }
  }
  return false;
}

float sampleMean() {
  unsigned long t0 = millis();
  double sum = 0; int n = 0;
  while (millis() - t0 < SAMPLE_MS) {
    sum += gaugePSI(); n++;
    delay(SAMPLE_DT);
  }
  return (float)(sum / n);
}

void runOnePoint(bool up, float cmdPSI) {
  float dacV = commandPSI(cmdPSI);
  Serial.print(F("# settling ")); Serial.print(cmdPSI, 0);
  Serial.print(F(" psi (")); Serial.print(dacV, 4); Serial.println(F(" V)..."));

  unsigned long t0 = millis();
  while (millis() - t0 < SETTLE_MS) {
    if (checkAbort()) return;
    Serial.print(F("  t=")); Serial.print((millis() - t0) / 1000);
    Serial.print(F("s gauge=")); Serial.print(gaugePSI(), 1); Serial.println(F(" psi"));
    delay(1000);
  }

  float meas = sampleMean();

  Serial.print(F("DATA,")); Serial.print(up ? F("UP") : F("DOWN"));
  Serial.print(F(",")); Serial.print(cmdPSI, 1);
  Serial.print(F(",")); Serial.print(dacV, 4);
  Serial.print(F(",")); Serial.println(meas, 2);

  // store for fit
  if (rowCount < MAXROWS) {
    cmdArr[rowCount] = cmdPSI; dacArr[rowCount] = dacV; gaugeArr[rowCount] = meas;
    rowCount++;
  }
  if (up && upN < 16)  { upCmd[upN] = cmdPSI;  upMeas[upN] = meas;  upN++; }
  if (!up && dnN < 16) { dnCmd[dnN] = cmdPSI;  dnMeas[dnN] = meas;  dnN++; }
}

void printSummary() {
  Serial.println();
  Serial.println(F("================ CALIBRATION SUMMARY ================"));

  // Fit measured_psi = m * dac_volts + b   (what the regulator actually delivers per volt)
  int n = rowCount;
  double sx=0, sy=0, sxx=0, sxy=0;
  for (int i = 0; i < n; i++) {
    sx  += dacArr[i];      sy  += gaugeArr[i];
    sxx += dacArr[i]*dacArr[i];
    sxy += dacArr[i]*gaugeArr[i];
  }
  double denom = n*sxx - sx*sx;
  double m = (n*sxy - sx*sy) / denom;     // psi per volt delivered
  double b = (sy - m*sx) / n;             // psi offset at 0 V

  // R^2
  double meanY = sy/n, ssTot=0, ssRes=0;
  for (int i = 0; i < n; i++) {
    double pred = m*dacArr[i] + b;
    ssRes += (gaugeArr[i]-pred)*(gaugeArr[i]-pred);
    ssTot += (gaugeArr[i]-meanY)*(gaugeArr[i]-meanY);
  }
  double r2 = 1.0 - ssRes/ssTot;

  Serial.print(F("Fit: delivered_psi = "));
  Serial.print(m, 4); Serial.print(F(" * dac_V + "));
  Serial.print(b, 4); Serial.print(F("   R^2="));
  Serial.println(r2, 5);

  // Recommended PSI_FULL_SCALE: the delivered psi at full 10 V.
  // If offset b is near 0, this is just m*10. With offset, invert at your
  // operating point for best local accuracy.
  double fsRecommend = m * 10.0 + b;
  Serial.print(F("Recommended PSI_FULL_SCALE (psi at 10V) = "));
  Serial.println(fsRecommend, 2);

  Serial.println(F("If you operate mainly near one pressure, this lands it close."));
  Serial.println(F("For dead-on across range, use the slope+offset two-point form."));

  // Hysteresis: match up vs down at same commanded points
  Serial.println();
  Serial.println(F("Hysteresis (same command, UP vs DOWN delivered):"));
  Serial.println(F("  cmd_psi   up_psi   down_psi   gap_psi"));
  for (int i = 0; i < upN; i++) {
    for (int j = 0; j < dnN; j++) {
      if (fabs(upCmd[i] - dnCmd[j]) < 0.1f) {
        float gap = dnMeas[j] - upMeas[i];
        Serial.print(F("  "));
        Serial.print(upCmd[i], 0);    Serial.print(F("       "));
        Serial.print(upMeas[i], 1);   Serial.print(F("     "));
        Serial.print(dnMeas[j], 1);   Serial.print(F("      "));
        Serial.println(gap, 1);
      }
    }
  }
  Serial.println(F("===================================================="));
}

void runSweep() {
  sweeping = true; abortFlag = false; rowCount = 0; upN = 0; dnN = 0;
  Serial.println(F("# direction,commanded_psi,dac_volts,mean_gauge_psi"));

  for (int i = 0; i < N_POINTS && !abortFlag; i++) runOnePoint(true,  sweepPoints[i]);
  for (int i = N_POINTS - 1; i >= 0 && !abortFlag; i--) runOnePoint(false, sweepPoints[i]);

  commandPSI(0);
  sweeping = false;

  if (abortFlag) Serial.println(F("# ABORTED (partial data below)"));
  printSummary();
}

void handleSerial() {
  if (!Serial.available()) return;
  String cmd = Serial.readStringUntil('\n');
  cmd.trim(); cmd.toUpperCase();
  if (cmd == "GO") runSweep();
  else if (cmd.startsWith("PSI ")) commandPSI(cmd.substring(4).toFloat());
  else if (cmd.startsWith("VDAC ")) setDacVoltage(cmd.substring(5).toFloat(), DAC_CH_PSI);
  else if (cmd == "ZERO") commandPSI(0);
  else if (cmd.length() > 0) { Serial.print(F("Unknown: ")); Serial.println(cmd); }
}

void setup() {
  Serial.begin(115200);
  if (dac.begin() == 0) {
    dac.setDACOutRange(dac.eOutputRange10V);
    dacReady = true; commandPSI(0);
  } else Serial.println(F("WARNING: GP8413 not found"));
  for (int i = 0; i < 10; i++) { analogRead(PRESSURE_PIN); delay(5); }

  Serial.println(F("Parker Regulator SELF-CAL SWEEP"));
  Serial.println(F("Type GO to start, STOP to abort."));
  Serial.print(F("Points: "));
  for (int i = 0; i < N_POINTS; i++) { Serial.print(sweepPoints[i], 0); Serial.print(F(" ")); }
  Serial.println(F("psi"));
}

void loop() {
  if (!sweeping) handleSerial();
}