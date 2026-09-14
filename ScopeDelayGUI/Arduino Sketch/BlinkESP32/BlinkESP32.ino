#include <Adafruit_NeoPixel.h>

#define LED_PIN 38
#define LED_COUNT 1

Adafruit_NeoPixel pixel(LED_COUNT, LED_PIN, NEO_GRB + NEO_KHZ800);

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("ESP32-S3 is alive!");
  pixel.begin();
  pixel.setBrightness(50);
}

void loop() {
  Serial.println("Red");
  pixel.setPixelColor(0, pixel.Color(255, 0, 0));
  pixel.show();
  delay(500);

  Serial.println("Green");
  pixel.setPixelColor(0, pixel.Color(0, 255, 0));
  pixel.show();
  delay(500);

  Serial.println("Blue");
  pixel.setPixelColor(0, pixel.Color(0, 0, 255));
  pixel.show();
  delay(500);
}