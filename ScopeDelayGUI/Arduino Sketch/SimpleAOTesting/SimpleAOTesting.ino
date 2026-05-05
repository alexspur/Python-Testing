#include <Arduino_PortentaMachineControl.h>

const uint32_t BAUD = 115200;

// Change these to test
float voltageAO0 = 2.0;   // volts (0–10V)
float voltageAO1 = 5.0;   // volts (0–10V)

void setup() {
  Serial.begin(BAUD);
  while (!Serial) {}

  // Initialize analog outputs
  MachineControl_AnalogOut.begin();

  Serial.println("=== AO TEST START ===");

  // Set outputs once at startup
  MachineControl_AnalogOut.write(0, voltageAO0);  // AO0
  MachineControl_AnalogOut.write(1, voltageAO1);  // AO1

  Serial.print("AO0 set to: ");
  Serial.print(voltageAO0);
  Serial.println(" V");

  Serial.print("AO1 set to: ");
  Serial.print(voltageAO1);
  Serial.println(" V");

  Serial.println("Measure with a multimeter between AOx and GND.");
}

void loop() {
  // Optional: allow changing voltage from Serial
  if (Serial.available()) {
    String input = Serial.readStringUntil('\n');
    input.trim();

    if (input.startsWith("AO0")) {
      float v = input.substring(3).toFloat();
      v = constrain(v, 0.0, 10.5);
      MachineControl_AnalogOut.write(0, v);
      Serial.print("AO0 -> ");
      Serial.print(v);
      Serial.println(" V");
    }

    if (input.startsWith("AO1")) {
      float v = input.substring(3).toFloat();
      v = constrain(v, 0.0, 10.5);
      MachineControl_AnalogOut.write(1, v);
      Serial.print("AO1 -> ");
      Serial.print(v);
      Serial.println(" V");
    }
  }
}