const int pinLDR = A0;
const int pinMOSFET = 12;

int valorLDR = 0;
unsigned long tiempoAnterior = 0;
const long intervalo = 100;

void setup() {
  Serial.begin(9600);
  pinMode(pinMOSFET, OUTPUT);
  digitalWrite(pinMOSFET, LOW);
}

void loop() {
  unsigned long tiempoActual = millis();

  if (tiempoActual - tiempoAnterior >= intervalo) {
    tiempoAnterior = tiempoActual;
    valorLDR = analogRead(pinLDR);
    Serial.println(valorLDR);
  }

  if (Serial.available() > 0) {
    char comando = Serial.read();
    
    if (comando == '1') {
      digitalWrite(pinMOSFET, HIGH);
    } 
    else if (comando == '0') {
      digitalWrite(pinMOSFET, LOW);
    }
  }
}