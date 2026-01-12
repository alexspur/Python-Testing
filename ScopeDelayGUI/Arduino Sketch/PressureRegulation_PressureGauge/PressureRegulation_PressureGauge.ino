#include <Arduino_PortentaMachineControl.h>

const uint32_t BAUD = 115200;
const float REFERENCE = 3.0f;
const float SENSE_RES = 120.0f;
const unsigned long STREAM_INTERVAL = 100;
const size_t LINE_MAX = 64;

// Analog output channel for pressure regulator control (0-10V)
const int PRESSURE_AO_CHANNEL = 2;

// Analog input channels - ALL 4-20mA
const int CURRENT_AI_0 = 0;   // 4-20mA current sensor
const int CURRENT_AI_1 = 1;   // 4-20mA current sensor
const int PRESSURE_AI_2 = 2;  // 4-20mA pressure sensor (P.Touch Output 2 in 4-20mA mode)

uint8_t outputStates = 0x00;
bool streamEnabled = true;
unsigned long lastStream = 0;
uint32_t sampleCount = 0;
char lineBuf[LINE_MAX];

float outputVoltage = 0.0f;

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

// Set analog output voltage (0-10V)
void setVoltage(float volts) {
  outputVoltage = constrain(volts, 0.0f, 10.0f);
  MachineControl_AnalogOut.write(PRESSURE_AO_CHANNEL, outputVoltage);
  Serial.print("SET V:");
  Serial.println(outputVoltage, 3);
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

  // VOLT <value> - Set output voltage directly (0-10V)
  if (eq(cmd, "VOLT") || eq(cmd, "V")) {
    if (!arg) {
      Serial.print("V:");
      Serial.println(outputVoltage, 3);
      return;
    }
    float val = atof(arg);
    setVoltage(val);
    return;
  }

  if (eq(cmd, "PING")) {
    Serial.println("PONG");
    return;
  }

  if (eq(cmd, "STREAM")) {
    if (!arg) { sendNack("ARG"); return; }
    if (eq(arg, "ON")) {
      streamEnabled = true;
      sendAck("STREAM ON");
    } else if (eq(arg, "OFF")) {
      streamEnabled = false;
      sendAck("STREAM OFF");
    } else {
      sendNack("ARG");
    }
    return;
  }

  if (eq(cmd, "STATUS")) {
    Serial.print("STATUS DO:");
    for (int ch = 0; ch < 8; ch++) {
      Serial.print(bitRead(outputStates, ch));
      if (ch < 7) Serial.print(',');
    }
    Serial.print(" V:");
    Serial.println(outputVoltage, 3);
    return;
  }

  if (eq(cmd, "ALL")) {
    if (!arg) { sendNack("ARG"); return; }
    if (eq(arg, "ON")) {
      outputStates = 0xFF;
      applyOutputs();
      sendAck("ALL ON");
    } else if (eq(arg, "OFF")) {
      outputStates = 0x00;
      applyOutputs();
      sendAck("ALL OFF");
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

  // Read ALL THREE channels as 4-20mA (with 120Ω burden resistor)
  // This now works WITHOUT overcurrent because P.Touch Output 2 is 4-20mA
  float current[3];
  for (int i = 0; i < 3; i++) {
    float raw = MachineControl_AnalogIn.read(i);
    float voltage = (raw * REFERENCE) / 65535.0f;
    float mA = (voltage / SENSE_RES) * 1000.0f;
    if (mA < 0) mA = 0;
    current[i] = mA;
  }

  // Convert AI2 (pressure sensor) from 4-20mA to PSI
  // P.Touch: 4-20mA = 0-100 psi
  // PSI = ((mA - 4) / 16) * 100
  float pressurePsi = ((current[2] - 4.0f) / 16.0f) * 100.0f;

  Serial.print("AI,");
  Serial.print(sampleCount++);
  Serial.print(',');
  Serial.print(current[0], 3); Serial.print(',');
  Serial.print(current[1], 3); Serial.print(',');
  Serial.print(current[2], 3); Serial.print(',');
  Serial.println(pressurePsi, 3);
}

void setup() {
  Serial.begin(BAUD);
  while (!Serial) {}

  MachineControl_DigitalOutputs.begin(true);
  applyOutputs();
  
  // Initialize analog inputs for 4-20mA on ALL channels
  MachineControl_AnalogIn.begin(SensorType::MA_4_20);
  
  // Initialize analog output for 0-10V control on AO2
  MachineControl_AnalogOut.begin();
  
  setVoltage(0.0f);

  Serial.println("READY");
}

void loop() {
  handleSerialCommands();
  streamAnalogInputs();
}
