#pragma once

// =============================================================================
// universal-io-board-Hat -- Pin Definitions
// ESP32-S3-DevKitC-1
// SOURCE OF TRUTH: project context GPIO table (collision-free, strapping-safe).
// This supersedes the earlier pins.h, which had multiple GPIO collisions
// (GPIO19, 3, 4, 5, 6, 7, 8 each assigned to two signals).
// =============================================================================

// --- I2C Bus ---
// Shared by U4 (ADS1115 0x48, 0-10V inputs) and U8 (ADS1115 0x49, 4-20mA inputs).
// NOTE: SCL (GPIO20) and A2DINT_I (GPIO19) overlap the native USB-OTG peripheral.
// This is harmless ONLY if native USB-CDC is never enabled. Flash and talk over
// the UART bridge (GPIO43/44). Do NOT build with ARDUINO_USB_CDC_ON_BOOT=1.
#define PIN_SDA             21
#define PIN_SCL             20

// --- ADC Alert/Ready Lines ---
// U4 (voltage): J4-pin20 lands on the DevKit GND rail -> NO usable interrupt.
// A2DINT_V is set to -1 and U4 is read by polling. The Adafruit single-shot
// readADC_SingleEnded() blocks until conversion completes, so no alert pin is
// needed for correct reads.
#define PIN_A2DINT_V        -1   // U4: UNAVAILABLE (tied to GND on DevKit) -- poll
#define PIN_A2DINT_I        19   // U8: 4-20mA input ADC alert (shares USB D-)

// --- I2C Addresses ---
#define ADS1115_ADDR_VINPUT     0x48   // U4, ADDR -> GND
#define ADS1115_ADDR_IINPUT     0x49   // U8, ADDR -> VDD

// --- PWM Outputs: 0-10V (4 channels) ---
// PWM -> RC filter -> LM258DT buffer (IC4/IC5). >= 20 kHz to hold ripple down.
#define PIN_PWM_VOUT1       4
#define PIN_PWM_VOUT2       5
#define PIN_PWM_VOUT3       6
#define PIN_PWM_VOUT4       7

#define LEDC_CH_VOUT1       0
#define LEDC_CH_VOUT2       1
#define LEDC_CH_VOUT3       2
#define LEDC_CH_VOUT4       3
#define LEDC_FREQ_VOUT      19531   // ~20 kHz; exact divider for 12-bit on ESP32-S3
#define LEDC_RES_VOUT       12      // 12-bit = 0-4095

// --- PWM Outputs: 4-20mA (4 channels) ---
// PWM -> RN filter -> IC6/IC7 summing input -> DMG4800 N-FET.
#define PIN_PWM_IOUT5       15
#define PIN_PWM_IOUT6       16
#define PIN_PWM_IOUT7       17
#define PIN_PWM_IOUT8       18

#define LEDC_CH_IOUT5       4
#define LEDC_CH_IOUT6       5
#define LEDC_CH_IOUT7       6
#define LEDC_CH_IOUT8       7
#define LEDC_FREQ_IOUT      19531   // ~20 kHz; exact divider for 12-bit on ESP32-S3
#define LEDC_RES_IOUT       12

// --- 4-20mA Output Feedback Check Lines (active-LOW from XTR111 fault detect) ---
// HIGH = OK, LOW = fault. Pulled up via RN8/RN9/RN10.
#define PIN_O_CHECK1        1   // ch5
#define PIN_O_CHECK2        2   // ch6
#define PIN_O_CHECK3        8   // ch7
#define PIN_O_CHECK4        3   // ch8 -- STRAPPING PIN: INPUT_PULLUP only, never drive

// --- Digital Inputs (Optocoupler, TLP293-4, HY1/HY2) ---
// Isolated 24V field inputs. Active HIGH when field-side LED energised.
#define PIN_OPTO_IN1        39
#define PIN_OPTO_IN2        40
#define PIN_OPTO_IN3        41
#define PIN_OPTO_IN4        42

// --- Digital Outputs (Open-Drain, DMG4800LFG-7, Q12-Q15) ---
// Pull-up to +12VA. Drive LOW = active; INPUT (high-Z) = released.
// GPIO47 (OD1) may be driven HIGH at boot on some module variants (RGB LED).
// Verify with a meter that GPIO47 is not sourcing current before wiring the gate.
#define PIN_OD1             47
#define PIN_OD2             48
#define PIN_OD3             13
#define PIN_OD4             14

// --- UART bridge (flashing + USB serial console) -- DO NOT REPURPOSE ---
// GPIO43 = TX, GPIO44 = RX. Left free so Serial works over the USB-UART bridge.

// --- Strapping / reserved pins ---
// GPIO0  (spare, J5-pin14): INPUT only
// GPIO45 (spare, J5-pin15): leave floating or HIGH
// GPIO46 (spare, J4-pin14): leave floating or LOW
// GPIO35/36/37: internally used by octal-PSRAM (WROOM-1-N8R8 / WROOM-2). Do not use.
