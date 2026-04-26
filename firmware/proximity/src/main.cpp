#include <Arduino.h>
#include <NewPing.h>

#define SONAR_NUM 3
#define MAX_DISTANCE 200

#define LED1 2
#define LED2 3

#define TRIG1 4
#define ECHO1 5
#define TRIG2 6
#define ECHO2 7
#define TRIG3 8
#define ECHO3 9

#define BUZZER 10

#define THRESHOLD_CM 25

NewPing sonar[SONAR_NUM] = {
  NewPing(TRIG1, ECHO1, MAX_DISTANCE),
  NewPing(TRIG2, ECHO2, MAX_DISTANCE),
  NewPing(TRIG3, ECHO3, MAX_DISTANCE)
};

unsigned int leftDist, centerDist, rightDist;

unsigned long previousMillis = 0;
const long beepInterval = 500;
bool buzzerState = false;

// Host-controlled enable. Boots disabled so the buzzer doesn't beep until
// the driver explicitly turns the backup ADAS on from the HMI.
//   '1' over serial -> enable LEDs + buzzer
//   '0' over serial -> disable (silent, LEDs off) — distance stream keeps
//                      flowing either way
bool alertsEnabled = false;

void setup() {
  Serial.begin(115200);

  pinMode(LED1, OUTPUT);
  pinMode(LED2, OUTPUT);
  pinMode(BUZZER, OUTPUT);

  digitalWrite(LED1, LOW);
  digitalWrite(LED2, LOW);
  digitalWrite(BUZZER, LOW);

  Serial.println("Parking Sensor Ready");
}

void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '1') alertsEnabled = true;
    else if (c == '0') alertsEnabled = false;
  }

  leftDist = sonar[0].ping_cm();
  delay(40);

  centerDist = sonar[1].ping_cm();
  delay(40);

  rightDist = sonar[2].ping_cm();
  delay(40);

  Serial.print("L: ");
  Serial.print(leftDist);
  Serial.print(" cm\tC: ");
  Serial.print(centerDist);
  Serial.print(" cm\tR: ");
  Serial.print(rightDist);
  Serial.println(" cm");

  digitalWrite(LED1, LOW);
  digitalWrite(LED2, LOW);

  bool alert = false;

  if (alertsEnabled) {
    if (leftDist > 0 && leftDist <= THRESHOLD_CM) {
      digitalWrite(LED2, HIGH);
      alert = true;
    }

    if (rightDist > 0 && rightDist <= THRESHOLD_CM) {
      digitalWrite(LED1, HIGH);
      alert = true;
    }

    if (centerDist > 0 && centerDist <= THRESHOLD_CM) {
      digitalWrite(LED1, HIGH);
      digitalWrite(LED2, HIGH);
      alert = true;
    }
  }

  if (alert) {
    unsigned long currentMillis = millis();
    if (currentMillis - previousMillis >= beepInterval) {
      previousMillis = currentMillis;
      buzzerState = !buzzerState;
      
      if (buzzerState) {
        tone(BUZZER, 1000);
      } else {
        noTone(BUZZER);
      }
    }
  } else {
    noTone(BUZZER);
    buzzerState = false;
    previousMillis = 0;
  }

  delay(50);
}