#pragma once
#include <Arduino.h>
#include <stdint.h>
#include <stdbool.h>

// =============================================================================
// universal-io-board-Hat -- Hardware Abstraction Layer
// =============================================================================
// All physical units at the API boundary:
//   Voltage inputs:   float, volts (0.0 - 10.0 V)
//   Current inputs:   float, milliamps (4.0 - 20.0 mA)
//   Voltage outputs:  float, volts (0.0 - 10.0 V)
//   Current outputs:  float, milliamps (4.0 - 20.0 mA)
//   Digital inputs:   bool, true = field signal active
//   Digital outputs:  bool, true = output pulled low (active)
// =============================================================================

// --- Init ---
// Call hal_init() once in setup(). Returns false if any subsystem fails.
bool hal_init();

// --- 0-10V Analog Inputs (4 channels, ADS1115 U4, polled) ---
// Returns the measured voltage in volts, or -1.0 on error.
// Channels 0-3 correspond to IN10V1-4 on J2.
float hal_vinput_read(uint8_t channel);

// --- 4-20mA Analog Inputs (4 channels, ADS1115 U8) ---
// Returns loop current in milliamps, or -1.0 on error.
// Channels 0-3 correspond to J3 pins 1-4 (IN1P-IN4P).
float hal_iinput_read(uint8_t channel);

// --- 0-10V Analog Outputs (4 channels, PWM + op-amp buffer IC4/IC5) ---
// Sets output voltage. Clamps to 0.0-10.0 V.
// Channels 1-4 correspond to J6 pins 1-4.
void hal_voutput_set(uint8_t channel, float volts);
float hal_voutput_get(uint8_t channel);

// --- 4-20mA Analog Outputs (4 channels, PWM + IC6/IC7 + DMG4800) ---
// Sets loop current in milliamps. Clamps to 4.0-20.0 mA.
// Channels 5-8 correspond to J7 pins 1-4 (OUT1-OUT4).
void hal_ioutput_set(uint8_t channel, float milliamps);
float hal_ioutput_get(uint8_t channel);

// Check the hardware fault line for a given output channel (5-8).
// Returns true if the output is confirmed in-range (no fault).
bool hal_ioutput_check(uint8_t channel);

// --- Digital Inputs (4 channels, TLP293-4 optocouplers HY1/HY2) ---
// Returns true when the field-side is energised.
// Channels 1-4 correspond to OPTO_IN1-4 (J8/J9).
bool hal_din_read(uint8_t channel);

// --- Digital Outputs (4 channels, open-drain DMG4800 FETs Q12-Q15) ---
// Set true to pull output low; false to release (high-impedance).
// Channels 1-4 correspond to OD1-4 (J8/J9).
void hal_dout_set(uint8_t channel, bool active);
bool hal_dout_get(uint8_t channel);

// --- Calibration ---
#define CAL_VINPUT_SCALE    6.061f   // ADS1115 volts -> field volts (bench-trim)
#define CAL_IINPUT_RSHUNT   49.9f    // shunt resistor, ohms
#define CAL_VOUT_SCALE      10.0f    // volts at full PWM duty (4095/4095)
#define CAL_IOUT_MA_MIN     4.0f
#define CAL_IOUT_MA_MAX     20.0f
