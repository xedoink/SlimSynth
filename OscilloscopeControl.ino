int freq = 100;
int potPin = A0;
int buttonPin = 2;
int waveformType = 0;    // 0-7 for 8 waveforms

bool lastButtonState = HIGH;
unsigned long lastSendTime = 0;
const int sendInterval = 20;

void setup() {
  Serial.begin(115200);
  pinMode(potPin, INPUT);
  pinMode(buttonPin, INPUT_PULLUP);
  delay(1000);
}

void loop() {
  // Read button
  bool buttonState = digitalRead(buttonPin);
  if (buttonState == LOW && lastButtonState == HIGH) {
    waveformType = (waveformType + 1) % 8;  // Cycle through 0-7
    
    // Immediately send on button press
    Serial.print(freq);
    Serial.print(",");
    Serial.print(analogRead(potPin));
    Serial.print(",");
    Serial.println(waveformType);
    delay(200);  // Debounce
  }
  lastButtonState = buttonState;
  
  // Read potentiometer
  int potValue = analogRead(potPin);
  
  // Map potentiometer to sweep speed
  int sweepSpeed = map(potValue, 0, 1023, 2, 100);
  
  // Send data at regular intervals
  unsigned long currentTime = millis();
  if (currentTime - lastSendTime >= sendInterval) {
    Serial.print(freq);
    Serial.print(",");
    Serial.print(potValue);
    Serial.print(",");
    Serial.println(waveformType);
    lastSendTime = currentTime;
  }
  
  // Update frequency
  freq += sweepSpeed;
  if (freq > 2000) {
    freq = 100;
  }
  
  delay(5);
}