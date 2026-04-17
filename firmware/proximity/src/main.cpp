#include <Arduino.h>

// ── Threshold ────────────────────────────────────────────────────────
const float THRESHOLD_CM = 20.0;

// ── HC-SR04 pins ─────────────────────────────────────────────────────
const int TRIG1 = 2;  const int ECHO1 = 3;
const int TRIG2 = 4;  const int ECHO2 = 5;
const int TRIG3 = 6;  const int ECHO3 = 7;

// ── Output pins ──────────────────────────────────────────────────────
const int LED1   = 8;
const int LED2   = 9;
const int BUZZER = 10;

// ── Buzzer pulse timing (ms) ─────────────────────────────────────────
const unsigned long BUZZ_ON_MS  = 100;
const unsigned long BUZZ_OFF_MS = 100;

// ── Sensor read interval (ms) ────────────────────────────────────────
const unsigned long READ_INTERVAL_MS = 100;

// ── State ────────────────────────────────────────────────────────────
bool buzzerOn = false;
unsigned long lastBuzzToggle = 0;
unsigned long lastRead = 0;

// Read distance from one HC-SR04 in centimeters.
// Returns -1.0 if no echo (out of range / sensor error).
float readDistanceCM(int trigPin, int echoPin) {
  digitalWrite(trigPin, LOW);
  delayMicroseconds(2);
  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin, LOW);

  unsigned long duration = pulseIn(echoPin, HIGH, 30000);  // 30 ms timeout
  if (duration == 0) return -1.0;
  return duration / 58.0;
}

void setup() {
  Serial.begin(115200);

  pinMode(TRIG1, OUTPUT);  pinMode(ECHO1, INPUT);
  pinMode(TRIG2, OUTPUT);  pinMode(ECHO2, INPUT);
  pinMode(TRIG3, OUTPUT);  pinMode(ECHO3, INPUT);

  pinMode(LED1,   OUTPUT);
  pinMode(LED2,   OUTPUT);
  pinMode(BUZZER, OUTPUT);

  digitalWrite(LED1,   LOW);
  digitalWrite(LED2,   LOW);
  digitalWrite(BUZZER, LOW);
}

void loop() {
  unsigned long now = millis();

  if (now - lastRead < READ_INTERVAL_MS) return;
  lastRead = now;

  float d1 = readDistanceCM(TRIG1, ECHO1);
  float d2 = readDistanceCM(TRIG2, ECHO2);
  float d3 = readDistanceCM(TRIG3, ECHO3);

  bool t1 = d1 >= 0 && d1 < THRESHOLD_CM;
  bool t2 = d2 >= 0 && d2 < THRESHOLD_CM;
  bool t3 = d3 >= 0 && d3 < THRESHOLD_CM;
  bool alert = t1 || t2 || t3;

  // ── LEDs ───────────────────────────────────────────────────────────
  digitalWrite(LED1, alert ? HIGH : LOW);
  digitalWrite(LED2, alert ? HIGH : LOW);

  // ── Buzzer (pulsing when alert, off otherwise) ─────────────────────
  if (alert) {
    unsigned long interval = buzzerOn ? BUZZ_ON_MS : BUZZ_OFF_MS;
    if (now - lastBuzzToggle >= interval) {
      buzzerOn = !buzzerOn;
      digitalWrite(BUZZER, buzzerOn ? HIGH : LOW);
      lastBuzzToggle = now;
    }
  } else {
    digitalWrite(BUZZER, LOW);
    buzzerOn = false;
  }

  // ── Serial output ─────────────────────────────────────────────────
  if (alert) {
    if (t1) { Serial.print("S1:"); Serial.print(d1, 1); Serial.print("cm "); }
    if (t2) { Serial.print("S2:"); Serial.print(d2, 1); Serial.print("cm "); }
    if (t3) { Serial.print("S3:"); Serial.print(d3, 1); Serial.print("cm "); }
    Serial.println();
  }
}
