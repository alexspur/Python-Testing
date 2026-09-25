/*
 * Opta WiFi (AFX00002) pressure monitor, Modbus TCP server
 *
 * Replaces the pressure readback portion of the old Mega sketch.
 * No Glassman control, no GP8413 DAC, no Marx rail channels.
 *
 * Board: Arduino Mbed OS Opta Boards -> Opta
 * Libraries: ArduinoModbus, ArduinoRS485
 *
 * TRANSDUCER
 *   0-10 V output, 0-160 psi. 1 V = 16 psi.
 *
 * WIRING CHANGE FROM THE MEGA
 *   The Mega needed a 10k/10k divider because its ADC tops out at 5 V.
 *   The Opta accepts 0-10 V on I1..I8 directly. Remove the divider and
 *   land the transducer output straight on I1. Tie transducer supply
 *   ground to Opta ground.
 *
 * REGISTER MAP (0-based, as pymodbus expects)
 *
 *   Input registers (read only, FC04)
 *     0   Averaged raw ADC counts, 0..4095
 *     1   Input voltage at I1 in mV, 0..10000
 *     2   Pressure in centi-psi, so 4237 means 42.37 psi
 *     3   Uptime in seconds
 *     4   Status bits. bit0 under range, bit1 over range
 *
 *   Holding registers (read/write, FC03/FC06/FC16)
 *     0   Full scale pressure in psi x10. Default 1600 = 160.0 psi
 *     1   Zero offset in mV, subtracted before scaling
 *     2   Averaging depth, 1..64 samples
 *     3   Reserved
 *
 *   Coils (read/write, FC01/FC05)
 *     0..3  Front panel LEDs, free to use as state indicators
 */

#include <PortentaEthernet.h>
#include <Ethernet.h>
#include <ArduinoRS485.h>
#include <ArduinoModbus.h>

// ---------------------------------------------------------------- network
IPAddress ip(192, 168, 10, 20);
IPAddress dnsSrv(192, 168, 10, 10);
IPAddress gw(192, 168, 10, 10);
IPAddress sn(255, 255, 255, 0);

EthernetServer ethServer(502);
ModbusTCPServer modbusServer;

// ---------------------------------------------------------------- hardware
const int PRESSURE_PIN = A0;   // Opta input I1
const int LED_PIN[4] = { LED_D0, LED_D1, LED_D2, LED_D3 };

// Opta divides its 0-10 V input down to the MCU ADC range on board.
// Verify OPTA_DIVIDER with a known voltage on I1 before trusting the mV
// register. This replaces the old PRESSURE_DIVIDER_RATIO of 2.0.
const float ADC_VREF_MV  = 3300.0f;
const float ADC_FULL     = 4095.0f;
const float OPTA_DIVIDER = 0.3085f;

// 0-10 V transducer, 0-160 psi
const float SENSOR_FULL_SCALE_MV = 10000.0f;

const uint16_t DEFAULT_FULL_SCALE_PSI_X10 = 1000;   // 160.0 psi
const uint16_t DEFAULT_ZERO_OFFSET_MV     = 0;
const uint16_t DEFAULT_AVG_SAMPLES        = 32;

const uint16_t UNDER_RANGE_MV = 100;      // sensor unpowered or wire off
const uint16_t OVER_RANGE_MV  = 10200;

// ---------------------------------------------------------------- filter
// Non-blocking ring buffer. The old sketch averaged with delay(2) inside
// the read, which would stall the Modbus poll loop for 40 ms per pass.
const int RING_SIZE = 64;
uint16_t ring[RING_SIZE];
int      ringIndex = 0;
bool     ringPrimed = false;

const unsigned long SAMPLE_INTERVAL_MS = 2;
const unsigned long UPDATE_INTERVAL_MS = 50;
const unsigned long PRINT_INTERVAL_MS  = 500;

unsigned long lastSample = 0;
unsigned long lastUpdate = 0;
unsigned long lastPrint  = 0;

void setup() {
  Serial.begin(115200);

  analogReadResolution(12);
  pinMode(PRESSURE_PIN, INPUT);

  for (int i = 0; i < 4; i++) {
    pinMode(LED_PIN[i], OUTPUT);
    digitalWrite(LED_PIN[i], LOW);
  }

  for (int i = 0; i < RING_SIZE; i++) {
    ring[i] = analogRead(PRESSURE_PIN);
    delay(2);
  }
  ringPrimed = true;

  Ethernet.begin(ip, dnsSrv, gw, sn);
  delay(500);
  Serial.print("Opta IP: ");
  Serial.println(Ethernet.localIP());

  ethServer.begin();

  if (!modbusServer.begin()) {
    Serial.println("Modbus TCP server failed to start");
    while (1) { delay(1000); }
  }

  modbusServer.configureInputRegisters(0, 5);
  modbusServer.configureHoldingRegisters(0, 4);
  modbusServer.configureCoils(0, 4);

  modbusServer.holdingRegisterWrite(0, DEFAULT_FULL_SCALE_PSI_X10);
  modbusServer.holdingRegisterWrite(1, DEFAULT_ZERO_OFFSET_MV);
  modbusServer.holdingRegisterWrite(2, DEFAULT_AVG_SAMPLES);
  modbusServer.holdingRegisterWrite(3, 0);

  updateRegisters();

  Serial.println("Pressure monitor ready on port 502, I1 = 0-10V / 0-160 psi transducer");
}

void loop() {
  EthernetClient client = ethServer.available();

  if (client) {
    Serial.println("Client connected");
    modbusServer.accept(client);

    // ArduinoModbus serves one client and this inner loop owns the CPU
    // for the life of the connection. Sampling has to happen in here too.
    while (client.connected()) {
      modbusServer.poll();
      serviceSampling();
      applyLeds();
    }

    Serial.println("Client disconnected");
  }

  serviceSampling();
  applyLeds();
}

// Take one sample per tick, refresh the registers on a slower cadence,
// and print a line over USB for bench debugging.
void serviceSampling() {
  unsigned long now = millis();

  if (now - lastSample >= SAMPLE_INTERVAL_MS) {
    lastSample = now;
    ring[ringIndex] = analogRead(PRESSURE_PIN);
    ringIndex = (ringIndex + 1) % RING_SIZE;
  }

  if (now - lastUpdate >= UPDATE_INTERVAL_MS) {
    lastUpdate = now;
    updateRegisters();
  }

  if (now - lastPrint >= PRINT_INTERVAL_MS) {
    lastPrint = now;
    printReading();
  }
}

// Average the most recent N samples, where N comes from holding register 2.
uint16_t averagedCounts() {
  int n = (int)modbusServer.holdingRegisterRead(2);
  if (n < 1) n = 1;
  if (n > RING_SIZE) n = RING_SIZE;

  uint32_t sum = 0;
  for (int i = 0; i < n; i++) {
    int idx = (ringIndex - 1 - i + 2 * RING_SIZE) % RING_SIZE;
    sum += ring[idx];
  }
  return (uint16_t)(sum / n);
}

void updateRegisters() {
  uint16_t counts = averagedCounts();

  float mvf = counts * (ADC_VREF_MV / ADC_FULL) / OPTA_DIVIDER;
  if (mvf < 0.0f) mvf = 0.0f;
  uint16_t mv = (uint16_t)(mvf + 0.5f);

  uint16_t status = 0;
  if (mv < UNDER_RANGE_MV) status |= 0x0001;
  if (mv > OVER_RANGE_MV)  status |= 0x0002;

  uint16_t offsetMv = modbusServer.holdingRegisterRead(1);
  float corrected = (float)mv - (float)offsetMv;
  if (corrected < 0.0f) corrected = 0.0f;

  float fullScalePsi = modbusServer.holdingRegisterRead(0) / 10.0f;
  float psi = (corrected / SENSOR_FULL_SCALE_MV) * fullScalePsi;
  if (psi < 0.0f) psi = 0.0f;

  uint32_t centiPsi = (uint32_t)(psi * 100.0f + 0.5f);
  if (centiPsi > 65535UL) centiPsi = 65535UL;

  modbusServer.inputRegisterWrite(0, counts);
  modbusServer.inputRegisterWrite(1, mv);
  modbusServer.inputRegisterWrite(2, (uint16_t)centiPsi);
  modbusServer.inputRegisterWrite(3, (uint16_t)(millis() / 1000UL));
  modbusServer.inputRegisterWrite(4, status);
}

void applyLeds() {
  for (int i = 0; i < 4; i++) {
    int state = modbusServer.coilRead(i);
    digitalWrite(LED_PIN[i], state > 0 ? HIGH : LOW);
  }
}

void printReading() {
  uint16_t counts = modbusServer.inputRegisterRead(0);
  uint16_t mv     = modbusServer.inputRegisterRead(1);
  uint16_t cpsi   = modbusServer.inputRegisterRead(2);
  uint16_t status = modbusServer.inputRegisterRead(4);

  Serial.print("counts=");
  Serial.print(counts);
  Serial.print(" | I1=");
  Serial.print(mv / 1000.0f, 4);
  Serial.print(" V | Pressure=");
  Serial.print(cpsi / 100.0f, 2);
  Serial.print(" psi");

  if (status & 0x0001) Serial.print(" | UNDER RANGE");
  if (status & 0x0002) Serial.print(" | OVER RANGE");
  Serial.println();
}
