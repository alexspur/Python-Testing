#include <Arduino_PortentaMachineControl.h>

// We'll store the current state of all 8 outputs in a variable.
uint8_t outputStates = 0; // Each bit = 1 channel, 1 = ON, 0 = OFF

void setup() {
  Serial.begin(9600);
  while (!Serial) {
    ; // wait for Serial Monitor
  }

  Serial.println("=== Portenta Machine Control: 8-Channel Digital Output Control ===");
  Serial.println("Commands:");
  Serial.println("  on <channel>     → turn ON channel 0–7");
  Serial.println("  off <channel>    → turn OFF channel 0–7");
  Serial.println("  status <channel> → show current state of channel 0–7");
  Serial.println("  all on/off       → toggle all outputs");
  Serial.println("Example: on 3");

  // Initialize digital outputs (true = latch mode)
  MachineControl_DigitalOutputs.begin(true);

  // Ensure all outputs start OFF
  MachineControl_DigitalOutputs.writeAll(0);
}

void loop() {
  if (Serial.available() > 0) {
    String input = Serial.readStringUntil('\n');
    input.trim();

    if (input.length() == 0) return;

    // Split input into command and argument
    int spaceIndex = input.indexOf(' ');
    String cmd = (spaceIndex == -1) ? input : input.substring(0, spaceIndex);
    String arg = (spaceIndex == -1) ? "" : input.substring(spaceIndex + 1);
    cmd.trim(); arg.trim();

    int ch = arg.toInt();
    bool validChannel = (ch >= 0 && ch <= 7);

    if (cmd.equalsIgnoreCase("on") && validChannel) {
      MachineControl_DigitalOutputs.write(ch, HIGH);
      bitSet(outputStates, ch);
      Serial.print("✅ DO0");
      Serial.print(ch);
      Serial.println(" turned ON.");
    }
    else if (cmd.equalsIgnoreCase("off") && validChannel) {
      MachineControl_DigitalOutputs.write(ch, LOW);
      bitClear(outputStates, ch);
      Serial.print("❌ DO0");
      Serial.print(ch);
      Serial.println(" turned OFF.");
    }
    else if (cmd.equalsIgnoreCase("status") && validChannel) {
      bool state = bitRead(outputStates, ch);
      Serial.print("ℹ️  DO0");
      Serial.print(ch);
      Serial.print(" is currently ");
      Serial.println(state ? "ON." : "OFF.");
    }
    else if (cmd.equalsIgnoreCase("all")) {
      if (arg.equalsIgnoreCase("on")) {
        MachineControl_DigitalOutputs.writeAll(255);
        outputStates = 0xFF;
        Serial.println("✅ All outputs turned ON.");
      } 
      else if (arg.equalsIgnoreCase("off")) {
        MachineControl_DigitalOutputs.writeAll(0);
        outputStates = 0x00;
        Serial.println("❌ All outputs turned OFF.");
      } 
      else {
        Serial.println("⚠️  Usage: all on   or   all off");
      }
    }
    else {
      Serial.println("⚠️  Invalid command. Use:");
      Serial.println("  on <0-7>   |  off <0-7>   |  status <0-7>   |  all on/off");
    }
  }
}
