#pragma once
#include <Arduino.h>

struct SystemState {
  int  fsr;             // FSR 이동 평균값 (0~1023)
  bool doorOpen;        // 문 열림 여부
  bool umbrellaPresent; // 우산 있음 여부
};

void        sensorsBegin();
void        sensorsUpdate(unsigned long now);
SystemState sensorsGetState();
