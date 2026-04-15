#include <Arduino.h>
#include <Servo.h>

Servo myservo;

void setup() {
  Serial.begin(115200);
  Serial.setTimeout(10);
  myservo.attach(5);
}

void loop() {
  if (Serial.available() > 0) {
    int value = Serial.parseInt();
    myservo.write(value);
  }
}
