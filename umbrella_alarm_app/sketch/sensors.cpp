#include "sensors.h"
#include "config.h"

static int          fsrBuf[FSR_SAMPLE_COUNT];
static int          fsrIdx          = 0;
static int          fsrAvg          = 0;
static bool         umbrellaPresent = false;

static bool         doorRaw         = false;
static bool         doorStable      = false;
static unsigned long doorLastChange  = 0;

static unsigned long lastFsrTime    = 0;
static unsigned long lastDoorTime   = 0;

// 시뮬레이션 전용 상태
static bool simUmbrella = false;
static bool simDoor     = false;

// FSR 이동 평균 계산
static int calcFsrAvg() {
  long sum = 0;
  for (int i = 0; i < FSR_SAMPLE_COUNT; i++) sum += fsrBuf[i];
  return (int)(sum / FSR_SAMPLE_COUNT);
}

// 핀 설정 및 초기 센서 상태 확정
void sensorsBegin() {
  pinMode(PIN_DOOR, INPUT_PULLUP);
  for (int i = 0; i < FSR_SAMPLE_COUNT; i++) fsrBuf[i] = 0;
  bool init = (digitalRead(PIN_DOOR) != DOOR_CLOSED_LEVEL);
  doorRaw = doorStable = init;
}

// 매 loop()에서 호출 — 시간 기반으로 FSR·MC-38 상태 갱신
void sensorsUpdate(unsigned long now) {
  if (SIMULATE_SENSORS) {
    // 주의: 시뮬레이션 모드에서 Serial을 직접 읽으므로 2·3단계에서 link.cpp와 충돌 가능
    if (Serial.available()) {
      char c = Serial.read();
      if (c == 'f') simUmbrella = !simUmbrella;
      if (c == 'd') simDoor     = !simDoor;
    }
    umbrellaPresent = simUmbrella;
    doorStable      = simDoor;
    return;
  }

  // FSR 이동 평균 + 히스테리시스
  if (now - lastFsrTime >= INTERVAL_FSR_MS) {
    fsrBuf[fsrIdx] = analogRead(PIN_FSR);
    fsrIdx = (fsrIdx + 1) % FSR_SAMPLE_COUNT;
    fsrAvg = calcFsrAvg();
    if      (fsrAvg >= FSR_ON_THRESHOLD)  umbrellaPresent = true;
    else if (fsrAvg <= FSR_OFF_THRESHOLD) umbrellaPresent = false;
    // 사이 구간은 이전 상태 유지 (히스테리시스)
    lastFsrTime = now;
  }

  // MC-38 디바운스
  if (now - lastDoorTime >= INTERVAL_DOOR_MS) {
    bool raw = (digitalRead(PIN_DOOR) != DOOR_CLOSED_LEVEL);
    if (raw != doorRaw) { doorRaw = raw; doorLastChange = now; }
    if (now - doorLastChange >= DOOR_DEBOUNCE_MS) doorStable = doorRaw;
    lastDoorTime = now;
  }
}

// 현재 확정된 센서 상태 반환
SystemState sensorsGetState() {
  return { fsrAvg, doorStable, umbrellaPresent };
}
