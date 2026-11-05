#include "link.h"
#include "Arduino_RouterBridge.h"
#include <vector>

// Python이 Bridge로 보낸 소리 출력 여부를 받는다.
// 스피커가 아직 연결되지 않아서 실제 재생은 하지 않고 Monitor로만 출력한다 (추후 실제 재생과 연결 예정).
static void onSoundDecision(int shouldPlay) {
  Monitor.println(shouldPlay ? "SOUND,1" : "SOUND,0");
}

// Bridge 초기화 + Python → MCU 핸들러 등록 (baud는 더 이상 쓰지 않음)
void linkBegin(long baud) {
  (void)baud;
  Monitor.begin(115200);
  Bridge.begin();
  Bridge.provide("sound_decision", onSoundDecision);
}

// STATE를 Bridge로 Python에 전달 (Python 쪽 Bridge.provide("state", ...)가 받음)
void linkSendState(unsigned long timeMs, int fsr, bool doorOpen, bool umbrellaPresent) {
  std::vector<int> payload = { (int)timeMs, fsr, doorOpen ? 1 : 0, umbrellaPresent ? 1 : 0 };
  Bridge.notify("state", payload);
}

// 디버그/음성 프로토콜 줄 출력 — Monitor로만 보임 (리눅스로의 실제 전달은 Bridge로 대체됨)
void linkSendLine(const char* line) {
  Monitor.println(line);
}

// Bridge로 전환되어 더 이상 실제 바이트를 받지 않음 — 음성 수신 코드는 항상 "수신 없음"으로 보고 휴면 상태를 유지한다
bool linkReadLine(char* buf, int maxLen) {
  (void)buf; (void)maxLen;
  return false;
}

bool linkAvailable() {
  return false;
}

uint8_t linkReadByte() {
  return 0;
}
