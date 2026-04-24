#include <Arduino.h>
#include <NewPing.h>

const float THRESHOLD_CM = 20.0;
const int SONAR_NUM = 3;
const int MAX_DISTANCE = 200;

const int LED1 = 8;
const int LED2 = 9;
const int BUZZER = 10;

const unsigned long BUZZ_PULSE = 100;
unsigned long lastBuzzToggle = 0;
bool buzzerOn = false;

NewPing sonar[SONAR_NUM] = {
  NewPing(2, 3, MAX_DISTANCE),
  NewPing(4, 5, MAX_DISTANCE),
  NewPing(6, 7, MAX_DISTANCE)
};

float distances[SONAR_NUM];
unsigned long pingTimer[SONAR_NUM];
int currentSensor = 0;

void echoCheck() {
  if (sonar[currentSensor].check_timer()) {
    distances[currentSensor] = sonar[currentSensor].ping_result / US_ROUNDTRIP_CM;
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(LED1, OUTPUT);
  pinMode(LED2, OUTPUT);
  pinMode(BUZZER, OUTPUT);

  pingTimer[0] = millis() + 75;
  for (int i = 1; i < SONAR_NUM; i++) {
    pingTimer[i] = pingTimer[i - 1] + 33;
  }
}

void loop() {
  for (int i = 0; i < SONAR_NUM; i++) {
    if (millis() >= pingTimer[i]) {
      pingTimer[i] += 33 * SONAR_NUM;
      sonar[currentSensor].timer_stop();
      currentSensor = i;
      distances[currentSensor] = 0;
      sonar[currentSensor].ping_timer(echoCheck);
    }
  }

  bool alert = false;
  for (int i = 0; i < SONAR_NUM; i++) {
    if (distances[i] > 0 && distances[i] < THRESHOLD_CM) {
      alert = true;
    }
  }

  digitalWrite(LED1, alert ? HIGH : LOW);
  digitalWrite(LED2, alert ? HIGH : LOW);

  if (alert) {
    if (millis() - lastBuzzToggle >= BUZZ_PULSE) {
      buzzerOn = !buzzerOn;
      digitalWrite(BUZZER, buzzerOn ? HIGH : LOW);
      lastBuzzToggle = millis();
    }
  } else {
    digitalWrite(BUZZER, LOW);
    buzzerOn = false;
  }

  static unsigned long lastPrint = 0;
  if (millis() - lastPrint > 200) {
    Serial.print("S1: "); Serial.print(distances[0]);
    Serial.print(" S2: "); Serial.print(distances[1]);
    Serial.print(" S3: "); Serial.println(distances[2]);
    lastPrint = millis();
  }
}