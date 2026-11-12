#pragma once
#include <Arduino.h>

void playerBegin();
void playerStart(const uint8_t* data, int size); // 재생 시작
void playerUpdate(unsigned long now);             // 매 loop()에서 호출 (블로킹 금지)
bool playerIsPlaying();
void playerStop();
