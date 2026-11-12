#pragma once
#include <Arduino.h>

// 확인 완료: UNO Q에서 MCU↔리눅스 통신은 Arduino Router Bridge(Bridge.call/notify/provide)를 쓴다.
// ttyGS0 시리얼은 arduino-router-serial 서비스(Monitor/Bridge 전용 프록시)가 이미 점유하고 있어
// 사용자 코드에서 Serial로 직접 접근하면 안 된다.

void    linkBegin(long baud); // baud는 더 이상 쓰지 않음(Bridge로 전환) — 시그니처만 유지해 호출부(sketch.ino)를 바꾸지 않음
void    linkSendState(unsigned long timeMs, int fsr, bool doorOpen, bool umbrellaPresent); // STATE를 Bridge로 Python에 전달
void    linkSendLine(const char* line); // 디버그/음성 프로토콜용 — Monitor로 출력 (READY/OK/ERR/DBG, 음성 수신 코드가 사용)
bool    linkReadLine(char* buf, int maxLen); // Bridge 전환으로 비활성화됨 — 항상 false (음성 수신 코드는 휴면 상태로 유지)
bool    linkAvailable();    // Bridge 전환으로 비활성화됨 — 항상 false
uint8_t linkReadByte();     // Bridge 전환으로 비활성화됨 — 항상 0
