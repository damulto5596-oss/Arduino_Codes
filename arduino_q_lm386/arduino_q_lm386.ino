/*
  Arduino UNO Q - STM32 MCU 날씨 알림 스케치 (LM386 앰프 스피커용)
  
  [동작 설명]
  1. Linux MPU(Qualcomm QRB2210)로부터 날씨 분석 결과를 수신합니다.
  2. LM386 앰프 스피커 모듈을 통해 상태에 맞는 전용 멜로디와 사운드를 연주합니다.
     - 코드 1 (현재 비 내림): 긴급 비 경보 사이렌 ("삐-뽀-삐-뽀")
     - 코드 2 (오늘 비 예보): 비 주의 알림 멜로디 ("딩-동-댕-동")
     - 코드 0 (오늘 종일 맑음): 경쾌한 맑음 팡파레 ("도-미-솔-도")
     - 코드 4 (TTS 방송 모드): 안내 방송 시작 차임벨 ("딩-동~")
  
  [하드웨어 배선]
  - LM386 [VCC] ──► 아두이노 Q [ 5V ]
  - LM386 [GND] ──► 아두이노 Q [ GND ]
  - LM386 [ IN] ──► 아두이노 Q [ D8 ] (방법 B 사용 시)
  - LM386 [스피커 단자] ──► 8옴 스피커 2선
*/

#if __has_include("Arduino_RouterBridge.h")
  #include "Arduino_RouterBridge.h"
  #define HAS_ROUTER_BRIDGE 1
#else
  #define HAS_ROUTER_BRIDGE 0
#endif

const int SPEAKER_PIN = 8;
const int LED_PIN = LED_BUILTIN;

// 음계 주파수 정의
#define NOTE_G4 392
#define NOTE_C5 523
#define NOTE_D5 587
#define NOTE_E5 659
#define NOTE_F5 698
#define NOTE_G5 784
#define NOTE_A5 880
#define NOTE_B5 988
#define NOTE_C6 1047
#define NOTE_E6 1319

// 1. 현재 비 내림 경보 (긴급 사이렌)
void soundRainNow() {
  Serial.println("[LM386] 🚨 현재 비 내림 경보 사이렌 재생!");
  for (int i = 0; i < 4; i++) {
    digitalWrite(LED_PIN, HIGH);
    tone(SPEAKER_PIN, NOTE_B5, 160);
    delay(180);
    digitalWrite(LED_PIN, LOW);
    tone(SPEAKER_PIN, NOTE_E6, 220);
    delay(240);
  }
  noTone(SPEAKER_PIN);
}

// 2. 오늘 비 예보 알림 (외출 전 주의 멜로디: 딩-동-댕-동)
void soundRainToday() {
  Serial.println("[LM386] ☔ 오늘 비 예보 주의 멜로디 재생!");
  int melody[] = {NOTE_G4, NOTE_C5, NOTE_E5, NOTE_G5};
  for (int i = 0; i < 4; i++) {
    digitalWrite(LED_PIN, HIGH);
    tone(SPEAKER_PIN, melody[i], 220);
    delay(260);
    digitalWrite(LED_PIN, LOW);
  }
  noTone(SPEAKER_PIN);
}

// 3. 오늘 종일 맑음 (경쾌한 팡파레)
void soundClear() {
  Serial.println("[LM386] ☀️ 맑음 팡파레 재생!");
  int melody[] = {NOTE_C5, NOTE_E5, NOTE_G5, NOTE_C6};
  for (int i = 0; i < 4; i++) {
    digitalWrite(LED_PIN, HIGH);
    tone(SPEAKER_PIN, melody[i], 130);
    delay(150);
    digitalWrite(LED_PIN, LOW);
  }
  noTone(SPEAKER_PIN);
}

// 4. TTS 안내 방송 전 시작 차임벨 (딩-동~)
void soundTtsChime() {
  Serial.println("[LM386] 🔔 TTS 안내 방송 차임벨 재생!");
  digitalWrite(LED_PIN, HIGH);
  tone(SPEAKER_PIN, NOTE_E5, 180); // 미
  delay(200);
  tone(SPEAKER_PIN, NOTE_C5, 300); // 도
  delay(320);
  noTone(SPEAKER_PIN);
}

// 사운드 디스패처
void dispatchAudio(int soundCode) {
  switch (soundCode) {
    case 1: // 현재 비 내림
      soundRainNow();
      break;
    case 2: // 오늘 비 예보 있음
      soundRainToday();
      break;
    case 0: // 맑음
      soundClear();
      break;
    case 4: // TTS 차임
      soundTtsChime();
      break;
    default:
      soundRainToday();
      break;
  }
}

// --- 방식 1: App Lab Bridge RPC ---
#if HAS_ROUTER_BRIDGE
void onPlayWeatherAudio(int soundCode) {
  Serial.print("[Bridge RPC 수신] soundCode=");
  Serial.println(soundCode);
  dispatchAudio(soundCode);
}
#endif

// --- 방식 2: 내부 UART Serial1 수신 ---
// 규격: "PLAY:<soundCode>\n"
void processSerialInput(String line) {
  line.trim();
  if (line.startsWith("PLAY:")) {
    int code = line.substring(5).toInt();
    Serial.print("[UART 수신] 코드: ");
    Serial.println(code);
    dispatchAudio(code);
  } else if (line == "TEST_RAIN") {
    soundRainNow();
  } else if (line == "TEST_FORECAST") {
    soundRainToday();
  } else if (line == "TEST_CLEAR") {
    soundClear();
  }
}

void setup() {
  pinMode(SPEAKER_PIN, OUTPUT);
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

  Serial.begin(115200);
  Serial1.begin(115200);

#if HAS_ROUTER_BRIDGE
  Bridge.begin();
  Bridge.provide("play_weather_audio", onPlayWeatherAudio);
  Serial.println(">> [STM32] RouterBridge 연동 준비 완료.");
#else
  Serial.println(">> [STM32] UART 시리얼 연동 모드 대기 중.");
#endif

  // 기기 부팅 시 짧은 비프 1회
  tone(SPEAKER_PIN, 1000, 80);
  delay(100);
  noTone(SPEAKER_PIN);
  Serial.println(">> LM386 스피커 준비 완료.");
}

void loop() {
  if (Serial1.available()) {
    String line = Serial1.readStringUntil('\n');
    processSerialInput(line);
  }
  if (Serial.available()) {
    String line = Serial.readStringUntil('\n');
    processSerialInput(line);
  }
}
