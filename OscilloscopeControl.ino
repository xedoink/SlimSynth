int freq = 100;
int joyXPin = A0;        // Joystick X-axis (sweep speed control)
int joyYPin = A1;        // Joystick Y-axis (filter cutoff control)
int joyButtonPin = 2;    // Joystick button (waveform selector)
int waveformType = 0;    // 0-7 for 8 waveforms

bool lastJoyButtonState = HIGH;
unsigned long lastSendTime = 0;
const int sendInterval = 20;  // 20ms = 50Hz update rate

void setup() {
  Serial.begin(115200);
  pinMode(joyXPin, INPUT);
  pinMode(joyYPin, INPUT);
  pinMode(joyButtonPin, INPUT_PULLUP);
  delay(1000);
}

void loop() {
  // Read joystick button (waveform cycling)
  bool joyButtonState = digitalRead(joyButtonPin);
  if (joyButtonState == LOW && lastJoyButtonState == HIGH) {
    waveformType = (waveformType + 1) % 8;  // Cycle through 0-7
    
    // Immediate feedback transmission on button press
    int xValue = analogRead(joyXPin);
    int yValue = analogRead(joyYPin);
    Serial.print(freq);
    Serial.print(",");
    Serial.print(xValue);
    Serial.print(",");
    Serial.print(yValue);
    Serial.print(",");
    Serial.println(waveformType);
    
    delay(200);  // Debounce
  }
  lastJoyButtonState = joyButtonState;
  
  // Read joystick axes
  int xValue = analogRead(joyXPin);  // Sweep speed
  int yValue = analogRead(joyYPin);  // Filter cutoff
  
  // Map X-axis to sweep speed (2-100 Hz per step)
  int sweepSpeed = map(xValue, 0, 1023, 2, 100);
  
  // Periodic data transmission
  unsigned long currentTime = millis();
  if (currentTime - lastSendTime >= sendInterval) {
    Serial.print(freq);
    Serial.print(",");
    Serial.print(xValue);
    Serial.print(",");
    Serial.print(yValue);
    Serial.print(",");
    Serial.println(waveformType);
    lastSendTime = currentTime;
  }
  
  // Update frequency with variable sweep speed
  freq += sweepSpeed;
  if (freq > 2000) {
    freq = 100;
  }
  
  delay(5);  // Main loop timing
}