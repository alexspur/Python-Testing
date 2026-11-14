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

  if (eq(cmd, "PING")) {
    Serial.println("ACK PONG");
    return;
  }

  if (eq(cmd, "STREAM")) {
    if (!arg) { sendNack("ARG"); return; }
    if (eq(cmd, "ON")) {
      streamEnabled = true;
      sendAck("STREAM_ON");
    } else if (eq(cmd, "OFF")) {
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
    for (int ch = 0; ch < 8; ch++) {
      Serial.print(bitRead(outputStates, ch));
    }
    Serial.println();
    return;
  }

  if (eq(cmd, "HELP")) {
    Serial.println("ACK VOLT <voltage>");
    Serial.println("ACK STREAM ON/OFF");
    Serial.println("ACK PING");
    Serial.println("ACK STATUS");
    return;
  }

  if (eq(cmd, "ALL")) {
    if (!arg) { sendNack("ARG"); return; }
    if (eq(cmd, "ON")) {
      outputStates = 0xFF;
      applyOutputs();
      sendAck("ALL_ON");
    } else if (eq(cmd, "OFF")) {
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

  // Stream format: DATA,count,mA0,mA1,raw2,voltage
  Serial.print("DATA,");
  Serial.print(sampleCount++);
  Serial.print(",");
  Serial.print(mA0, 3);
  Serial.print(",");
  Serial.print(mA1, 3);
  Serial.print(",");
  Serial.print(smoothedRaw2);
  Serial.print(",");
  Serial.println(outputVoltage, 2);
}

void setup() {
  Serial.begin(BAUD);
  while (!Serial) {}

  MachineControl_DigitalOutputs.begin(true);
  applyOutputs();
  
  MachineControl_AnalogIn.begin(SensorType::MA_4_20);
  MachineControl_AnalogOut.begin();
  
  setVoltage(0.0f);

  Serial.println("ACK READY");
  Serial.println("FORMAT: DATA,count,mA0,mA1,raw2,voltage");
}

void loop() {
  handleSerialCommands();
  streamAnalogInputs();
}
