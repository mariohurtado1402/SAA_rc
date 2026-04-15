#include <Arduino.h>
#include <Servo.h>

Servo myservo;

void setup() {
  Serial.begin(115200);
  // Lower timeout makes the loop more responsive
  Serial.setTimeout(5);
  myservo.attach(5);
  // Start at center
  myservo.write(90);
}

void loop() {
  if (Serial.available() > 0) {
    // peek() checks the first byte without removing it.
    // Helps skip non-digit characters like leftover \r or spaces.
    char c = Serial.peek();
    if (isDigit(c) || c == '-') {
      int value = Serial.parseInt();

      // Basic safety check for servo range
      if (value >= 0 && value <= 180) {
        myservo.write(value);
      }
    } else {
      // Discard non-digit characters (like \n or \r)
      Serial.read();
    }
  }
}
