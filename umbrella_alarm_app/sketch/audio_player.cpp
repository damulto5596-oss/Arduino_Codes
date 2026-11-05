#include "audio_player.h"
#include "config.h"

static bool          playing_    = false;
static unsigned long beepTimer   = 0;
static int           beepsDone   = 0;
static bool          beepOn      = false;
static unsigned long stubStart   = 0;
static unsigned long stubDuration= 0;

// 핀 초기화 (setup에서 1회 호출)
void playerBegin() {
  if (AUDIO_OUTPUT_MODE == AUDIO_MODE_BUZZER) pinMode(BUZZER_PIN, OUTPUT);
}

// 재생 시작 — BUZZER: 비프 패턴 시작 / PCM_STUB: 크기로 재생 시간 흉내
void playerStart(const uint8_t* data, int size) {
  playing_ = true;
  if (AUDIO_OUTPUT_MODE == AUDIO_MODE_BUZZER) {
    beepsDone = 0; beepOn = true; beepTimer = millis();
    tone(BUZZER_PIN, BEEP_FREQ);
  } else {
    // TODO: 실제 디코더 연결 (DAC/I2S/PWM — README 참고)
    stubDuration = (unsigned long)size * 1000UL / PCM_STUB_BYTES_PER_SEC;
    stubStart = millis();
    (void)data;
  }
}

// 매 loop()에서 호출 — 비프 패턴 진행 또는 스텁 타이머 확인 (블로킹 금지)
void playerUpdate(unsigned long now) {
  if (!playing_) return;

  if (AUDIO_OUTPUT_MODE == AUDIO_MODE_BUZZER) {
    if (beepOn) {
      if (now - beepTimer >= BEEP_ON_MS) {
        noTone(BUZZER_PIN); beepOn = false; beepsDone++; beepTimer = now;
        if (beepsDone >= BEEP_COUNT) { playing_ = false; }
      }
    } else {
      if (now - beepTimer >= BEEP_OFF_MS) {
        tone(BUZZER_PIN, BEEP_FREQ);
        beepOn = true; beepTimer = now;
      }
    }
  } else {
    if (now - stubStart >= stubDuration) playing_ = false;
  }
}

bool playerIsPlaying() { return playing_; }

// 재생 강제 중단
void playerStop() {
  if (AUDIO_OUTPUT_MODE == AUDIO_MODE_BUZZER) noTone(BUZZER_PIN);
  playing_ = false;
}
