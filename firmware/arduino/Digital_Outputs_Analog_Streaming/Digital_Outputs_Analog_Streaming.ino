#include <Arduino_PortentaMachineControl.h>

// ------------------------------------------------------------
// DIGITAL OUTPUT STATE
// ------------------------------------------------------------
uint8_t outputStates = 0;  // DO0..DO7 state bits

// ------------------------------------------------------------
// ANALOG INPUT CONFIGURATION (4–20 mA)
// ------------------------------------------------------------
#define SENSE_RES 120
const float REFERENCE = 3.0;

// Stream every 100 ms (10 Hz)
unsigned long lastStream = 0;
const unsigned long STREAM_INTERVAL = 100;

// ------------------------------------------------------------
// SETUP
// ------------------------------------------------------------
void setup() {
  Serial.begin(9600);
  while (!Serial);

  Serial.println("=== Portenta Machine Control: DO + 4-20mA Streaming ===");

  // --- DIGITAL OUTPUTS ---
  MachineControl_DigitalOutputs.begin(true);
  MachineControl_DigitalOutputs.writeAll(0);

  // --- ANALOG INPUTS ---
  MachineControl_AnalogIn.begin(SensorType::MA_4_20);
}

// ------------------------------------------------------------
// MAIN LOOP
// ------------------------------------------------------------
void loop() {
  handleSerialCommands();
  streamAnalogInputs();
}

// ------------------------------------------------------------
// DIGITAL COMMAND PARSER
// ------------------------------------------------------------
void handleSerialCommands() {
  if (!Serial.available()) return;

  String input = Serial.readStringUntil('\n');
  input.trim();
  if (input.length() == 0) return;

  int spaceIndex = input.indexOf(' ');
  String cmd = (spaceIndex == -1) ? input : input.substring(0, spaceIndex);
  String arg = (spaceIndex == -1) ? "" : input.substring(spaceIndex + 1);

  cmd.trim();
  arg.trim();

  int ch = arg.toInt();
  bool validChannel = (ch >= 0 && ch <= 7);

  if (cmd.equalsIgnoreCase("on") && validChannel) {
    MachineControl_DigitalOutputs.write(ch, HIGH);
    bitSet(outputStates, ch);
    Serial.print("DO"); Serial.print(ch); Serial.println(" ON");
  }
  else if (cmd.equalsIgnoreCase("off") && validChannel) {
    MachineControl_DigitalOutputs.write(ch, LOW);
    bitClear(outputStates, ch);
    Serial.print("DO"); Serial.print(ch); Serial.println(" OFF");
  }
  else if (cmd.equalsIgnoreCase("status") && validChannel) {
    Serial.print("DO"); Serial.print(ch); Serial.print(" = ");
    Serial.println(bitRead(outputStates, ch));
  }
  else if (cmd.equalsIgnoreCase("all")) {
    if (arg.equalsIgnoreCase("on")) {
      MachineControl_DigitalOutputs.writeAll(0xFF);
      outputStates = 0xFF;
      Serial.println("ALL ON");
    }
    else if (arg.equalsIgnoreCase("off")) {
      MachineControl_DigitalOutputs.writeAll(0x00);
      outputStates = 0x00;
      Serial.println("ALL OFF");
    }
  }
  else {
    Serial.println("Invalid command.");
  }
}

// ------------------------------------------------------------
// ANALOG INPUT STREAMING (4–20 mA → mA)
// ------------------------------------------------------------
void streamAnalogInputs() {
  unsigned long now = millis();
  if (now - lastStream < STREAM_INTERVAL) return;
  lastStream = now;

  float current[3];

  for (int i = 0; i < 3; i++) {
    float raw = MachineControl_AnalogIn.read(i);
    float voltage = (raw * REFERENCE) / 65535.0;
    current[i] = (voltage / SENSE_RES) * 1000.0;  // mA
  }

  // Python-friendly output: AI,<mA0>,<mA1>,<mA2>
  Serial.print("AI,");
  Serial.print(current[0], 3); Serial.print(",");
  Serial.print(current[1], 3); Serial.print(",");
  Serial.println(current[2], 3);
}
