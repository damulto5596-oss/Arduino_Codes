#pragma once
#include <Arduino.h>

enum AudioRxState { AUDIO_IDLE, AUDIO_RECEIVING, AUDIO_RECEIVED };

void           audioRxBegin();
void           audioRxUpdate(unsigned long now); // 매 loop()에서 호출
bool           audioRxIsComplete();
const uint8_t* audioRxGetData();
int            audioRxGetSize();
AudioRxState   audioRxGetState();
void           audioRxReset(); // IDLE로 돌아가며 READY 1회 전송
