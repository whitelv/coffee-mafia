/*
 * HX711 Calibration Sketch — Coffee Bar ESP32
 *
 * Instructions:
 *   1. Upload this sketch to your ESP32.
 *   2. Open Serial Monitor at 115200 baud.
 *   3. Remove all weight from the scale and wait for tare to complete.
 *   4. Place a known weight on the scale.
 *   5. Type the weight in grams and press Enter.
 *   6. Copy the printed CALIBRATION_F value into firmware/coffee_esp32/config.h.
 *
 * Required library: HX711 Arduino Library by Bogdan Necula (search "HX711 by bogde")
 */

#include <HX711.h>

#define HX711_DOUT 4
#define HX711_SCK  2

HX711 scale;

void setup() {
  Serial.begin(115200);
  scale.begin(HX711_DOUT, HX711_SCK);
  scale.tare(20);
  Serial.println("Tare complete. Place known weight on scale.");
  Serial.println("Then type the weight in grams and press Enter.");
}

void loop() {
  if (Serial.available()) {
    String line = Serial.readStringUntil('\n');
    line.trim();
    float knownGrams = line.toFloat();
    if (knownGrams > 0) {
      long raw = 0;
      for (int i = 0; i < 10; i++) raw += scale.get_value(1);
      raw /= 10;
      float factor = (float)raw / knownGrams;
      Serial.print("CALIBRATION_F = ");
      Serial.println(factor, 4);
      Serial.println("Copy this value into config.h");
      scale.set_scale(factor);
      Serial.print("Verification — current weight: ");
      Serial.print(scale.get_units(10), 2);
      Serial.println("g");
      Serial.println("Place another weight to verify, or reflash coffee_esp32.ino");
    }
  }
}
