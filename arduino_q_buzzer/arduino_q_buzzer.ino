/*
  Arduino UNO Q STM32 MCU 스케치 (스피커 TTS 방송 연동용)
  
  [역할]
  1. Linux MPU에서 TTS 음성 안내가 시작되기 전:
     - 스피커 방송 시작을 알리는 안내 차임벨 ("딩-동~") 연주
     - 온보드 LED를 켜서 방송 중임을 시각적으로 표시
  2. TTS 음성 방송이 끝나면 LED 끄기
  3. 시리얼 모니터 수동 테스트 지원
*/

#if __has_include("Arduino_RouterBridge.h")
  #include "Arduino_RouterBridge.h"
  #define HAS_ROUTER_BRIDGE 1
#else
  #define HAS_ROUTER_BRIDGE 0
#endif

const int BUZZER_PIN = 8;
const int LED_PIN = LED_BUILTIN;

#define NOTE_E5 659
#define NOTE_C5 523
#define NOTE_G5 784

// 방송 시작 전 차임벨 ("딩-동~")
void playChime(bool isRainAlert) {
  digitalWrite(LED_PIN, HIGH);
  if (isRainAlert) {
    // 비 경보일 때는 주의를 끄는 단조 차임
    tone(BUZZER_PIN, 880, 150);  // 라
    delay(180);
    tone(BUZZER_PIN, 698, 300);  // 파
    delay(350);
  } else {
    // 평상시 경쾌한 딩-동
    tone(BUZZER_PIN, NOTE_E5, 180); // 미
    delay(200);
    tone(BUZZER_PIN, NOTE_C5, 300); // 도
    delay(320);
  }
  noTone(BUZZER_PIN);
}

// --- 방식 1: Arduino App Lab Bridge RPC ---
#if HAS_ROUTER_BRIDGE
void onTtsStart(int rainAlertCode) {
  Serial.print("[Bridge RPC] TTS 시작 알림: code=");
  Serial.println(rainAlertCode);
  playChime(rainAlertCode == 1);
}

void onTtsEnd() {
  Serial.println("[Bridge RPC] TTS 종료 알림.");
  digitalWrite(LED_PIN, LOW);
}
#endif

// --- 방식 2: UART Serial 명령 파싱 ---
void processSerialLine(String line) {
  line.trim();
  if (line.startsWith("TTS_START:")) {
    int code = line.substring(10).toInt();
    Serial.print("[UART] TTS_START 수신 (code=");
    Serial.print(code);
    Serial.println(")");
    playChime(code == 1);
  } else if (line == "TTS_END") {
    Serial.println("[UART] TTS_END 수신");
    digitalWrite(LED_PIN, LOW);
  } else if (line == "TEST_CHIME") {
    playChime(false);
  }
}

void setup() {
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

  Serial.begin(115200);
  Serial1.begin(115200);

#if HAS_ROUTER_BRIDGE
  Bridge.begin();
  Bridge.provide("on_tts_start", onTtsStart);
  Bridge.provide("on_tts_end", onTtsEnd);
  Serial.println(">> [STM32] RouterBridge TTS 연동 준비 완료.");
#else
  Serial.println(">> [STM32] UART 시리얼 연동 대기 중.");
#endif

  // 시작 비프 1회
  tone(BUZZER_PIN, 1000, 80);
  delay(100);
  noTone(BUZZER_PIN);
}

void loop() {
  if (Serial1.available()) {
    String line = Serial1.readStringUntil('\n');
    processSerialLine(line);
  }
  if (Serial.available()) {
    String line = Serial.readStringUntil('\n');
    processSerialLine(line);
  }
}
