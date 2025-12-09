#include <Arduino_PortentaMachineControl.h>

// ---------------------------
// CONFIG
// ---------------------------
const uint32_t BAUD = 115200;
const float REFERENCE = 3.0f;     // ADC reference volts
const float SENSE_RES = 120.0f;   // ohms
const unsigned long STREAM_INTERVAL = 100; // ms (10 Hz)
const size_t LINE_MAX = 64;

// ---------------------------
// STATE
// ---------------------------
uint8_t outputStates = 0x00;  // DO0..DO7 bitfield
bool streamEnabled = true;
unsigned long lastStream = 0;
uint32_t sampleCount = 0;
char lineBuf[LINE_MAX];

// ---------------------------
// HELPERS
// ---------------------------
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
  // trim CR
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
void reportStatusAll() {
  Serial.print("STATUS ");
  for (int ch = 0; ch < 8; ch++) {
    Serial.print(bitRead(outputStates, ch));
    if (ch < 7) Serial.print(',');
  }
  Serial.println();
}

// ---------------------------
// COMMAND HANDLER
// ---------------------------
void handleSerialCommands() {
  if (!Serial.available()) return;
  if (!readLine(lineBuf, LINE_MAX)) return;

  // tokenize
  char* cmd = strtok(lineBuf, " ");
  char* arg = strtok(nullptr, " ");
  if (!cmd || cmd[0] == '\0') return;

  // uppercase compare
  auto eq = [](const char* a, const char* b) {
    while (*a && *b) {
      char ca = toupper(*a++), cb = toupper(*b++);
      if (ca != cb) return false;
    }
    return (*a == '\0' && *b == '\0');
  };

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
    reportStatusAll();
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

// ---------------------------
// ANALOG STREAM
// ---------------------------
void streamAnalogInputs() {
  unsigned long now = millis();
  if (!streamEnabled || (now - lastStream < STREAM_INTERVAL)) return;
  lastStream = now;

  float current[3];
  for (int i = 0; i < 3; i++) {
    float raw = MachineControl_AnalogIn.read(i);
    float voltage = (raw * REFERENCE) / 65535.0f;
    float mA = (voltage / SENSE_RES) * 1000.0f;
    // clamp to avoid negatives
    if (mA < 0) mA = 0;
    current[i] = mA;
  }

  Serial.print("AI,");
  Serial.print(sampleCount++);
  Serial.print(',');
  Serial.print(current[0], 3); Serial.print(',');
  Serial.print(current[1], 3); Serial.print(',');
  Serial.println(current[2], 3);
}

// ---------------------------
// SETUP / LOOP
// ---------------------------
void setup() {
  Serial.begin(BAUD);
  while (!Serial) {}

  Serial.println("READY");
  MachineControl_DigitalOutputs.begin(true);
  applyOutputs();

  MachineControl_AnalogIn.begin(SensorType::MA_4_20);
}

void loop() {
  handleSerialCommands();
  streamAnalogInputs();
}
