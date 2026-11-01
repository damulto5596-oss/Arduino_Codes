/*
  LM386 앰프 모듈 및 스피커 하드웨어 테스트 스케치 (Arduino UNO Q - STM32 MCU용)
  
  [목적]
  - LM386 앰프 모듈과 스피커가 올바르게 연결되었는지 확인
  - LM386 기판의 가변저항(파란색/은색 볼륨 노브)을 돌려 적정 볼륨을 맞추기 위한 테스트
  
  [연결 배선]
  - LM386 [VCC] ──► 아두이노 Q [ 5V ]
  - LM386 [GND] ──► 아두이노 Q [ GND ]
  - LM386 [ IN] ──► 아두이노 Q [ D8 ]
  - LM386 [스피커 단자] ──► 스피커 전선 2가닥
*/

const int SPEAKER_PIN = 8;
const int LED_PIN = LED_BUILTIN;

// 음계 주파수 정의 (Hz)
#define NOTE_C4 262
#define NOTE_D4 294
#define NOTE_E4 330
#define NOTE_F4 349
#define NOTE_G4 392
#define NOTE_A4 440
#define NOTE_B4 494
#define NOTE_C5 523
#define NOTE_E5 659
#define NOTE_G5 784
#define NOTE_C6 1047

void playScale() {
  Serial.println(">> [테스트 1] 음계 재생 (도-레-미-파-솔-라-시-도)");
  Serial.println("   -> 소리가 너무 크거나 찌그러지면 LM386의 파란 볼륨 다이얼을 시계 반대방향으로 돌리세요!");
  
  int scale[] = {NOTE_C4, NOTE_D4, NOTE_E4, NOTE_F4, NOTE_G4, NOTE_A4, NOTE_B4, NOTE_C5};
  for (int i = 0; i < 8; i++) {
    digitalWrite(LED_PIN, HIGH);
    tone(SPEAKER_PIN, scale[i], 180);
    delay(200);
    digitalWrite(LED_PIN, LOW);
  }
  noTone(SPEAKER_PIN);
}

void playRainAlarm() {
  Serial.println(">> [테스트 2] 현재 비 내림 경보 사이렌 재생 (삐-뽀-삐-뽀)");
  for (int i = 0; i < 3; i++) {
    digitalWrite(LED_PIN, HIGH);
    tone(SPEAKER_PIN, 988, 180); // B5
    delay(200);
    digitalWrite(LED_PIN, LOW);
    tone(SPEAKER_PIN, 1319, 250); // E6
    delay(270);
  }
  noTone(SPEAKER_PIN);
}

void playRainForecastAlert() {
  Serial.println(">> [테스트 3] 오늘 비 예보 알림 (딩-동-댕-동)");
  int notes[] = {NOTE_G4, NOTE_C5, NOTE_E5, NOTE_G5};
  for (int i = 0; i < 4; i++) {
    digitalWrite(LED_PIN, HIGH);
    tone(SPEAKER_PIN, notes[i], 220);
    delay(260);
    digitalWrite(LED_PIN, LOW);
  }
  noTone(SPEAKER_PIN);
}

void playClearMelody() {
  Serial.println(">> [테스트 4] 맑음 팡파레 재생");
  int notes[] = {NOTE_C5, NOTE_E5, NOTE_G5, NOTE_C6};
  for (int i = 0; i < 4; i++) {
    digitalWrite(LED_PIN, HIGH);
    tone(SPEAKER_PIN, notes[i], 140);
    delay(160);
    digitalWrite(LED_PIN, LOW);
  }
  noTone(SPEAKER_PIN);
}

void setup() {
  pinMode(SPEAKER_PIN, OUTPUT);
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

  Serial.begin(115200);
  delay(1000);

  Serial.println("\n=======================================================");
  Serial.println("   🔊 LM386 앰프 스피커 모듈 하드웨어 테스트 시작     ");
  Serial.println("=======================================================");
  Serial.println("시리얼 모니터에 아래 숫자를 입력하면 특정 소리를 재생합니다:");
  Serial.println("  1 : 현재 비 내림 경보 사이렌");
  Serial.println("  2 : 오늘 비 예보 알림 멜로디");
  Serial.println("  3 : 맑음 팡파레");
  Serial.println("  4 : 기본 음계 테스트 (도레미파솔라시도)");
  Serial.println("-------------------------------------------------------\n");

  // 시작 시 기본 음계 1회 연주
  playScale();
}

void loop() {
  if (Serial.available()) {
    char ch = Serial.read();
    if (ch == '1') {
      playRainAlarm();
    } else if (ch == '2') {
      playRainForecastAlert();
    } else if (ch == '3') {
      playClearMelody();
    } else if (ch == '4') {
      playScale();
    }
  }
}
