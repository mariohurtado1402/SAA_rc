#include <Arduino.h>
#include <Servo.h>

// ESC signal wire goes to D3 on this Nano.
// (D5 is used by the servo Nano; keeping them different avoids mixing
// the sketches up between boards.)
const int ESC_PIN = 3;

// Standard RC pulse range, microseconds.
const int PULSE_MIN = 1000;      // full reverse
const int PULSE_NEUTRAL = 1500;  // stop / idle
const int PULSE_MAX = 2000;      // full forward

Servo esc;

void setup() {
  Serial.begin(115200);
  Serial.setTimeout(5);

  esc.attach(ESC_PIN);
  // Auto-arm: hold neutral for 3 s so the XR10 completes its startup
  // beeps and arms before we accept any serial commands.
  esc.writeMicroseconds(PULSE_NEUTRAL);
  delay(3000);
}

void loop() {
  if (Serial.available() > 0) {
    char c = Serial.peek();
    if (isDigit(c) || c == '-') {
      int value = Serial.parseInt();

      // Only accept valid RC pulse widths. Anything out of range is
      // ignored rather than coerced, so a corrupted byte cannot command
      // full throttle accidentally.
      if (value >= PULSE_MIN && value <= PULSE_MAX) {
        esc.writeMicroseconds(value);
      }
    } else {
      Serial.read();
    }
  }
}
