#include "config.h"
#include "sensors.h"
#include "link.h"
#include "audio_rx.h"
#include "audio_player.h"

enum AppState { SENSING, RECEIVING, PLAYING };

static AppState      appState    = SENSING;
static SystemState   prevState   = {0, false, false};
static unsigned long lastSendMs  = 0;
static unsigned long playStartMs = 0;
static bool          firstLoop   = true;

// 현재 센서 상태를 STATE로 즉시 전송 (Bridge로 Python에 전달)
static void sendState() {
  SystemState s = sensorsGetState();
  linkSendState(millis(), s.fsr, s.doorOpen, s.umbrellaPresent);
  lastSendMs = millis();
  prevState  = s;
  firstLoop  = false;
}

// 전체 상태 전환 로직 — loop()는 이 함수와 센서/수신 갱신만 호출
static void runStateMachine(unsigned long now) {
  AudioRxState rxSt = audioRxGetState();

  if (appState == SENSING) {
    SystemState s = sensorsGetState();
    bool changed = (s.doorOpen != prevState.doorOpen ||
                    s.umbrellaPresent != prevState.umbrellaPresent);
    if (firstLoop || changed || (now - lastSendMs >= INTERVAL_STATE_MS))
      sendState();
    if (rxSt == AUDIO_RECEIVING) appState = RECEIVING;

  } else if (appState == RECEIVING) {
    if (rxSt == AUDIO_RECEIVED) {
      playerStart(audioRxGetData(), audioRxGetSize());
      appState = PLAYING; playStartMs = now;
    } else if (rxSt == AUDIO_IDLE) {
      // 수신 오류 — audioRxReset이 READY 전송, 센서 감지 재개
      appState = SENSING; sendState();
    }

  } else if (appState == PLAYING) {
    playerUpdate(now);
    bool timeout = (now - playStartMs > PLAY_TIMEOUT_MS);
    if (timeout) {
      playerStop();
      if (ERR_REPORT_ENABLED) linkSendLine("ERR,PLAY");
    }
    if (timeout || !playerIsPlaying()) {
      audioRxReset();  // READY 전송 + 버퍼 초기화
      appState = SENSING; sendState();
    }
  }
}

void setup() {
  linkBegin(SERIAL_BAUD);
  sensorsBegin();
  audioRxBegin(); // IDLE 진입 + 최초 READY 전송
  playerBegin();
}

void loop() {
  unsigned long now = millis();
  sensorsUpdate(now);
  audioRxUpdate(now);
  runStateMachine(now);
}
