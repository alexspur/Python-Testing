#include <Arduino.h>
#include <Wire.h>
#include "hal.h"

// =============================================================================
// universal-io-board-Hat -- USB serial command interface
// =============================================================================
// Talk over the USB-to-UART bridge at 115200 (NOT native USB-CDC; that conflicts
// with GPIO19/20 which carry A2DINT_I and SCL).
//
// Commands (case-insensitive, one per line):
//   VIN <0-3>                read 0-10V input channel, volts
//   IIN <0-3>                read 4-20mA input channel, mA
//   VOUT <1-4> <volts>       set 0-10V output (0.0-10.0)
//   VOUT <1-4>               read back commanded 0-10V output
//   IOUT <5-8> <mA>          set 4-20mA output (4.0-20.0)
//   IOUT <5-8>               read back commanded 4-20mA output
//   CHECK <5-8>              read 4-20mA output fault line (OK/FAULT)
//   DIN <1-4>                read digital input (ACTIVE/idle)
//   DOUT <1-4> ON|OFF        set open-drain output
//   DOUT <1-4>               read back open-drain state
//   STATUS                   dump all I/O
//   TEST                     run the bring-up sweep once
//   HELP                     list commands
// =============================================================================

static const size_t LINE_BUF = 64;
static char _line[LINE_BUF];
static size_t _len = 0;

// ---- small parse helpers ---------------------------------------------------

static bool tok_eq(const char* a, const char* b) {
    return strcasecmp(a, b) == 0;
}

static void print_help() {
    Serial.println(F("Commands:"));
    Serial.println(F("  VIN <0-3>              read 0-10V input (V)"));
    Serial.println(F("  IIN <0-3>              read 4-20mA input (mA)"));
    Serial.println(F("  VOUT <1-4> [volts]     set/read 0-10V output"));
    Serial.println(F("  IOUT <5-8> [mA]        set/read 4-20mA output"));
    Serial.println(F("  CHECK <5-8>            read output fault line"));
    Serial.println(F("  DIN <1-4>              read digital input"));
    Serial.println(F("  DOUT <1-4> [ON|OFF]    set/read open-drain output"));
    Serial.println(F("  STATUS                 dump all I/O"));
    Serial.println(F("  SCAN                   probe I2C bus (expect 0x48, 0x49)"));
    Serial.println(F("  TEST                   run bring-up sweep"));
    Serial.println(F("  HELP                   this list"));
}

static void cmd_status() {
    Serial.println(F("--- 0-10V Inputs ---"));
    for (uint8_t ch = 0; ch < 4; ch++)
        Serial.printf("  IN10V%d: %.3f V\n", ch + 1, hal_vinput_read(ch));

    Serial.println(F("--- 4-20mA Inputs ---"));
    for (uint8_t ch = 0; ch < 4; ch++)
        Serial.printf("  I_IN%d: %.2f mA\n", ch + 1, hal_iinput_read(ch));

    Serial.println(F("--- 0-10V Outputs (commanded) ---"));
    for (uint8_t ch = 1; ch <= 4; ch++)
        Serial.printf("  VOUT%d: %.3f V\n", ch, hal_voutput_get(ch));

    Serial.println(F("--- 4-20mA Outputs (commanded / fault) ---"));
    for (uint8_t ch = 5; ch <= 8; ch++)
        Serial.printf("  IOUT%d: %.2f mA  [%s]\n", ch,
                      hal_ioutput_get(ch),
                      hal_ioutput_check(ch) ? "OK" : "FAULT");

    Serial.println(F("--- Digital Inputs ---"));
    for (uint8_t ch = 1; ch <= 4; ch++)
        Serial.printf("  OPTO_IN%d: %s\n", ch, hal_din_read(ch) ? "ACTIVE" : "idle");

    Serial.println(F("--- Open-Drain Outputs ---"));
    for (uint8_t ch = 1; ch <= 4; ch++)
        Serial.printf("  OD%d: %s\n", ch, hal_dout_get(ch) ? "ACTIVE" : "released");
}

static void cmd_test() {
    Serial.println(F("=== bring-up sweep ==="));
    cmd_status();

    Serial.println(F("0-10V output ramp..."));
    for (float v = 0.0f; v <= 10.0f; v += 2.5f) {
        for (uint8_t ch = 1; ch <= 4; ch++) hal_voutput_set(ch, v);
        Serial.printf("  VOUT1-4 = %.1f V\n", v);
        delay(200);
    }
    for (uint8_t ch = 1; ch <= 4; ch++) hal_voutput_set(ch, 0.0f);

    Serial.println(F("4-20mA output ramp..."));
    for (float ma = 4.0f; ma <= 20.0f; ma += 4.0f) {
        for (uint8_t ch = 5; ch <= 8; ch++) hal_ioutput_set(ch, ma);
        Serial.printf("  IOUT5-8 = %.1f mA\n", ma);
        delay(200);
    }
    for (uint8_t ch = 5; ch <= 8; ch++) hal_ioutput_set(ch, 4.0f);

    Serial.println(F("open-drain toggle..."));
    for (uint8_t ch = 1; ch <= 4; ch++) {
        hal_dout_set(ch, true);
        Serial.printf("  OD%d ACTIVE\n", ch);
        delay(100);
        hal_dout_set(ch, false);
        Serial.printf("  OD%d released\n", ch);
    }
    Serial.println(F("=== sweep done ==="));
}

// ---- dispatch --------------------------------------------------------------

static void dispatch(char* line) {
    char* cmd = strtok(line, " \t");
    if (!cmd) return;

    char* a1 = strtok(nullptr, " \t");
    char* a2 = strtok(nullptr, " \t");

    if (tok_eq(cmd, "HELP")) { print_help(); return; }
    if (tok_eq(cmd, "STATUS")) { cmd_status(); return; }
    if (tok_eq(cmd, "TEST")) { cmd_test(); return; }
    if (tok_eq(cmd, "SCAN")) {
        Serial.println(F("Scanning I2C bus..."));
        int found = 0;
        for (uint8_t addr = 1; addr < 127; addr++) {
            Wire.beginTransmission(addr);
            if (Wire.endTransmission() == 0) {
                Serial.printf("  device at 0x%02X\n", addr);
                found++;
            }
        }
        Serial.printf("Found %d device(s). Expected 0x48 (U4) and 0x49 (U8).\n", found);
        return;
    }

    if (tok_eq(cmd, "VIN")) {
        if (!a1) { Serial.println(F("ERR: VIN <0-3>")); return; }
        int ch = atoi(a1);
        if (ch < 0 || ch > 3) { Serial.println(F("ERR: channel 0-3")); return; }
        Serial.printf("VIN %d = %.3f V\n", ch, hal_vinput_read(ch));
        return;
    }

    if (tok_eq(cmd, "IIN")) {
        if (!a1) { Serial.println(F("ERR: IIN <0-3>")); return; }
        int ch = atoi(a1);
        if (ch < 0 || ch > 3) { Serial.println(F("ERR: channel 0-3")); return; }
        Serial.printf("IIN %d = %.2f mA\n", ch, hal_iinput_read(ch));
        return;
    }

    if (tok_eq(cmd, "VOUT")) {
        if (!a1) { Serial.println(F("ERR: VOUT <1-4> [volts]")); return; }
        int ch = atoi(a1);
        if (ch < 1 || ch > 4) { Serial.println(F("ERR: channel 1-4")); return; }
        if (a2) {
            float v = atof(a2);
            hal_voutput_set(ch, v);
            Serial.printf("VOUT %d set %.3f V (clamped %.3f)\n", ch, v, hal_voutput_get(ch));
        } else {
            Serial.printf("VOUT %d = %.3f V\n", ch, hal_voutput_get(ch));
        }
        return;
    }

    if (tok_eq(cmd, "IOUT")) {
        if (!a1) { Serial.println(F("ERR: IOUT <5-8> [mA]")); return; }
        int ch = atoi(a1);
        if (ch < 5 || ch > 8) { Serial.println(F("ERR: channel 5-8")); return; }
        if (a2) {
            float ma = atof(a2);
            hal_ioutput_set(ch, ma);
            Serial.printf("IOUT %d set %.2f mA (clamped %.2f)\n", ch, ma, hal_ioutput_get(ch));
        } else {
            Serial.printf("IOUT %d = %.2f mA\n", ch, hal_ioutput_get(ch));
        }
        return;
    }

    if (tok_eq(cmd, "CHECK")) {
        if (!a1) { Serial.println(F("ERR: CHECK <5-8>")); return; }
        int ch = atoi(a1);
        if (ch < 5 || ch > 8) { Serial.println(F("ERR: channel 5-8")); return; }
        Serial.printf("CHECK %d = %s\n", ch, hal_ioutput_check(ch) ? "OK" : "FAULT");
        return;
    }

    if (tok_eq(cmd, "DIN")) {
        if (!a1) { Serial.println(F("ERR: DIN <1-4>")); return; }
        int ch = atoi(a1);
        if (ch < 1 || ch > 4) { Serial.println(F("ERR: channel 1-4")); return; }
        Serial.printf("DIN %d = %s\n", ch, hal_din_read(ch) ? "ACTIVE" : "idle");
        return;
    }

    if (tok_eq(cmd, "DOUT")) {
        if (!a1) { Serial.println(F("ERR: DOUT <1-4> [ON|OFF]")); return; }
        int ch = atoi(a1);
        if (ch < 1 || ch > 4) { Serial.println(F("ERR: channel 1-4")); return; }
        if (a2) {
            bool on;
            if (tok_eq(a2, "ON") || tok_eq(a2, "1"))       on = true;
            else if (tok_eq(a2, "OFF") || tok_eq(a2, "0")) on = false;
            else { Serial.println(F("ERR: use ON or OFF")); return; }
            hal_dout_set(ch, on);
            Serial.printf("DOUT %d = %s\n", ch, on ? "ACTIVE" : "released");
        } else {
            Serial.printf("DOUT %d = %s\n", ch, hal_dout_get(ch) ? "ACTIVE" : "released");
        }
        return;
    }

    Serial.printf("ERR: unknown command '%s' (try HELP)\n", cmd);
}

// ---- arduino entry points --------------------------------------------------

void setup() {
    Serial.begin(115200);
    delay(500);
    Serial.println(F("\n=== universal-io-board-Hat ==="));

    if (!hal_init()) {
        Serial.println(F("HAL init had errors (see above). Continuing in degraded mode."));
    } else {
        Serial.println(F("HAL init OK"));
    }
    print_help();
    Serial.print(F("> "));
}

void loop() {
    while (Serial.available()) {
        char c = (char)Serial.read();
        if (c == '\r') continue;
        if (c == '\n') {
            _line[_len] = '\0';
            if (_len > 0) dispatch(_line);
            _len = 0;
            Serial.print(F("> "));
        } else if (_len < LINE_BUF - 1) {
            _line[_len++] = c;
        } else {
            // overflow: reset line
            _len = 0;
            Serial.println(F("ERR: line too long"));
            Serial.print(F("> "));
        }
    }
}
