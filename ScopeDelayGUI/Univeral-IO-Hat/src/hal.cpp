#include "hal.h"
#include "pins.h"
#include <Wire.h>
#include <Adafruit_ADS1X15.h>
#include <esp32-hal-ledc.h>

// =============================================================================
// Internal state
// =============================================================================

static Adafruit_ADS1115 _ads_v;   // U4: 0-10V voltage inputs (polled)
static Adafruit_ADS1115 _ads_i;   // U8: 4-20mA current inputs

static bool _ads_v_ok = false;
static bool _ads_i_ok = false;

static float _vout_commanded[5] = {0};   // index 1-4
static float _iout_commanded[9] = {0};   // index 5-8
static bool  _dout_state[5]     = {0};   // index 1-4

// =============================================================================
// Helpers
// =============================================================================

static uint32_t _volts_to_duty(float volts) {
    float clamped = constrain(volts, 0.0f, CAL_VOUT_SCALE);
    return (uint32_t)((clamped / CAL_VOUT_SCALE) * 4095.0f);
}

static uint32_t _ma_to_duty(float ma) {
    float clamped = constrain(ma, CAL_IOUT_MA_MIN, CAL_IOUT_MA_MAX);
    float frac = (clamped - CAL_IOUT_MA_MIN) / (CAL_IOUT_MA_MAX - CAL_IOUT_MA_MIN);
    return (uint32_t)(frac * 4095.0f);
}

static uint8_t _vout_ledc_ch(uint8_t channel) {
    const uint8_t ch[] = {0, LEDC_CH_VOUT1, LEDC_CH_VOUT2, LEDC_CH_VOUT3, LEDC_CH_VOUT4};
    return ch[channel];
}

static uint8_t _iout_ledc_ch(uint8_t channel) {
    const uint8_t ch[] = {0,0,0,0,0, LEDC_CH_IOUT5, LEDC_CH_IOUT6, LEDC_CH_IOUT7, LEDC_CH_IOUT8};
    return ch[channel];
}

// =============================================================================
// Init
// =============================================================================

bool hal_init() {
    bool ok = true;

    // --- I2C ---
    Wire.begin(PIN_SDA, PIN_SCL, 400000);

    // --- ADS1115: 0-10V inputs (U4) -- polled, no alert line ---
    if (!_ads_v.begin(ADS1115_ADDR_VINPUT)) {
        Serial.println("[HAL] ERROR: ADS1115 (voltage inputs, U4) not found");
        ok = false;
    } else {
        _ads_v.setGain(GAIN_ONE);                    // FSR +/-4.096V
        _ads_v.setDataRate(RATE_ADS1115_250SPS);
        _ads_v_ok = true;
        Serial.println("[HAL] ADS1115 voltage inputs OK (polled)");
    }

    // --- ADS1115: 4-20mA inputs (U8) ---
    if (!_ads_i.begin(ADS1115_ADDR_IINPUT)) {
        Serial.println("[HAL] ERROR: ADS1115 (current inputs, U8) not found");
        ok = false;
    } else {
        _ads_i.setGain(GAIN_TWO);                    // FSR +/-2.048V; 20mA*49.9R=0.998V
        _ads_i.setDataRate(RATE_ADS1115_250SPS);
        _ads_i_ok = true;
        Serial.println("[HAL] ADS1115 current inputs OK");
    }

    // --- LEDC: 0-10V outputs ---
    ledcSetup(LEDC_CH_VOUT1, LEDC_FREQ_VOUT, LEDC_RES_VOUT);
    ledcAttachPin(PIN_PWM_VOUT1, LEDC_CH_VOUT1);
    ledcSetup(LEDC_CH_VOUT2, LEDC_FREQ_VOUT, LEDC_RES_VOUT);
    ledcAttachPin(PIN_PWM_VOUT2, LEDC_CH_VOUT2);
    ledcSetup(LEDC_CH_VOUT3, LEDC_FREQ_VOUT, LEDC_RES_VOUT);
    ledcAttachPin(PIN_PWM_VOUT3, LEDC_CH_VOUT3);
    ledcSetup(LEDC_CH_VOUT4, LEDC_FREQ_VOUT, LEDC_RES_VOUT);
    ledcAttachPin(PIN_PWM_VOUT4, LEDC_CH_VOUT4);

    // --- LEDC: 4-20mA outputs ---
    ledcSetup(LEDC_CH_IOUT5, LEDC_FREQ_IOUT, LEDC_RES_IOUT);
    ledcAttachPin(PIN_PWM_IOUT5, LEDC_CH_IOUT5);
    ledcSetup(LEDC_CH_IOUT6, LEDC_FREQ_IOUT, LEDC_RES_IOUT);
    ledcAttachPin(PIN_PWM_IOUT6, LEDC_CH_IOUT6);
    ledcSetup(LEDC_CH_IOUT7, LEDC_FREQ_IOUT, LEDC_RES_IOUT);
    ledcAttachPin(PIN_PWM_IOUT7, LEDC_CH_IOUT7);
    ledcSetup(LEDC_CH_IOUT8, LEDC_FREQ_IOUT, LEDC_RES_IOUT);
    ledcAttachPin(PIN_PWM_IOUT8, LEDC_CH_IOUT8);

    // Safe state: 0V and 4mA (live-zero)
    for (uint8_t ch = 1; ch <= 4; ch++) hal_voutput_set(ch, 0.0f);
    for (uint8_t ch = 5; ch <= 8; ch++) hal_ioutput_set(ch, CAL_IOUT_MA_MIN);

    // --- Fault check inputs (O_CHECK1-4, active-LOW, externally pulled up) ---
    pinMode(PIN_O_CHECK1, INPUT);
    pinMode(PIN_O_CHECK2, INPUT);
    pinMode(PIN_O_CHECK3, INPUT);
    pinMode(PIN_O_CHECK4, INPUT_PULLUP);   // GPIO3 strapping pin: pull-up, never drive LOW

    // --- Digital inputs (optocoupler outputs, active HIGH) ---
    pinMode(PIN_OPTO_IN1, INPUT);
    pinMode(PIN_OPTO_IN2, INPUT);
    pinMode(PIN_OPTO_IN3, INPUT);
    pinMode(PIN_OPTO_IN4, INPUT);

    // --- Open-drain outputs: start released (high-Z) ---
    for (uint8_t pin : {PIN_OD1, PIN_OD2, PIN_OD3, PIN_OD4}) {
        pinMode(pin, INPUT);
    }

    // --- Alert pins (guard against the unavailable U4 line) ---
    if (PIN_A2DINT_V >= 0) pinMode(PIN_A2DINT_V, INPUT_PULLUP);
    if (PIN_A2DINT_I >= 0) pinMode(PIN_A2DINT_I, INPUT_PULLUP);

    return ok;
}

// =============================================================================
// 0-10V Analog Inputs (polled)
// =============================================================================

float hal_vinput_read(uint8_t channel) {
    if (channel > 3) return -1.0f;
    if (!_ads_v_ok) return -1.0f;
    int16_t raw = _ads_v.readADC_SingleEnded(channel);  // blocks until conversion done
    if (raw < 0) raw = 0;                                // below GND, clamp
    float adc_volts = _ads_v.computeVolts(raw);
    return adc_volts * CAL_VINPUT_SCALE;
}

// =============================================================================
// 4-20mA Analog Inputs
// =============================================================================

float hal_iinput_read(uint8_t channel) {
    if (channel > 3) return -1.0f;
    if (!_ads_i_ok) return -1.0f;
    int16_t raw = _ads_i.readADC_SingleEnded(channel);
    if (raw < 0) raw = 0;
    float shunt_volts = _ads_i.computeVolts(raw);
    float ma = (shunt_volts / CAL_IINPUT_RSHUNT) * 1000.0f;
    return constrain(ma, 0.0f, 25.0f);
}

// =============================================================================
// 0-10V Analog Outputs
// =============================================================================

void hal_voutput_set(uint8_t channel, float volts) {
    if (channel < 1 || channel > 4) return;
    _vout_commanded[channel] = constrain(volts, 0.0f, CAL_VOUT_SCALE);
    ledcWrite(_vout_ledc_ch(channel), _volts_to_duty(_vout_commanded[channel]));
}

float hal_voutput_get(uint8_t channel) {
    if (channel < 1 || channel > 4) return -1.0f;
    return _vout_commanded[channel];
}

// =============================================================================
// 4-20mA Analog Outputs
// =============================================================================

void hal_ioutput_set(uint8_t channel, float milliamps) {
    if (channel < 5 || channel > 8) return;
    _iout_commanded[channel] = constrain(milliamps, CAL_IOUT_MA_MIN, CAL_IOUT_MA_MAX);
    ledcWrite(_iout_ledc_ch(channel), _ma_to_duty(_iout_commanded[channel]));
}

float hal_ioutput_get(uint8_t channel) {
    if (channel < 5 || channel > 8) return -1.0f;
    return _iout_commanded[channel];
}

bool hal_ioutput_check(uint8_t channel) {
    // active-LOW fault: HIGH = OK, LOW = fault
    switch (channel) {
        case 5: return digitalRead(PIN_O_CHECK1) == HIGH;
        case 6: return digitalRead(PIN_O_CHECK2) == HIGH;
        case 7: return digitalRead(PIN_O_CHECK3) == HIGH;
        case 8: return digitalRead(PIN_O_CHECK4) == HIGH;
        default: return false;
    }
}

// =============================================================================
// Digital Inputs
// =============================================================================

bool hal_din_read(uint8_t channel) {
    switch (channel) {
        case 1: return digitalRead(PIN_OPTO_IN1) == HIGH;
        case 2: return digitalRead(PIN_OPTO_IN2) == HIGH;
        case 3: return digitalRead(PIN_OPTO_IN3) == HIGH;
        case 4: return digitalRead(PIN_OPTO_IN4) == HIGH;
        default: return false;
    }
}

// =============================================================================
// Digital Outputs (open-drain)
// =============================================================================

void hal_dout_set(uint8_t channel, bool active) {
    if (channel < 1 || channel > 4) return;
    _dout_state[channel] = active;
    uint8_t pin;
    switch (channel) {
        case 1: pin = PIN_OD1; break;
        case 2: pin = PIN_OD2; break;
        case 3: pin = PIN_OD3; break;
        case 4: pin = PIN_OD4; break;
        default: return;
    }
    if (active) {
        pinMode(pin, OUTPUT);
        digitalWrite(pin, LOW);
    } else {
        pinMode(pin, INPUT);   // high-Z; board pull-up releases the output
    }
}

bool hal_dout_get(uint8_t channel) {
    if (channel < 1 || channel > 4) return false;
    return _dout_state[channel];
}
