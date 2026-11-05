#include "audio_rx.h"
#include "config.h"
#include "link.h"

// AudioBuffer 추상화 — 스트리밍 방식으로 교체 시 이 블록만 수정
static uint8_t  audioBuf[AUDIO_MAX_BYTES]; // UNO Q RAM 786KB 확인됨 — 40,000바이트 버퍼 문제 없음
static int      audioBodySize = 0;
static int      audioRecvd    = 0;

static AudioRxState  rxState      = AUDIO_IDLE;
static unsigned long chunkTimer   = 0;
static unsigned long lastReadyMs  = 0;

// 헤더 수신용 (매직 이후 10바이트)
static uint8_t hdrBuf[10];
static int     hdrRcvd = 0;
static bool    hdrDone = false;

// 매직 감지용
static int         magicIdx    = 0;
static const char  HEADER_MAGIC[] = "PCM"; // 임의의 값: 실제 헤더 매직 확정 후 교체

// 헤더 파싱 및 검증, 실패 시 ERR 전송 (임의의 값: 실제 헤더 구조 확정 후 교체)
static bool parsePcmHeader(uint32_t* bodyLen) {
  uint32_t sr = (uint32_t)hdrBuf[0] | ((uint32_t)hdrBuf[1]<<8) |
                ((uint32_t)hdrBuf[2]<<16) | ((uint32_t)hdrBuf[3]<<24);
  uint8_t  bits = hdrBuf[4], ch = hdrBuf[5];
  *bodyLen      = (uint32_t)hdrBuf[6] | ((uint32_t)hdrBuf[7]<<8) |
                  ((uint32_t)hdrBuf[8]<<16) | ((uint32_t)hdrBuf[9]<<24);
  bool fmtOk = (sr == 8000 && bits == 8 && ch == 1);
  bool szOk  = (*bodyLen > 0 && *bodyLen <= (uint32_t)AUDIO_MAX_BYTES);
  if (ERR_REPORT_ENABLED) {
    if (!fmtOk)        linkSendLine("ERR,HEADER");
    else if (!szOk)    linkSendLine("ERR,SIZE");
  }
  return fmtOk && szOk;
}

// IDLE로 돌아가며 READY 1회 전송
void audioRxReset() {
  rxState = AUDIO_IDLE; audioBodySize = 0; audioRecvd = 0;
  hdrRcvd = 0; hdrDone = false; magicIdx = 0;
  linkSendLine("READY");
  lastReadyMs = millis();
}

// 초기화 (setup에서 linkBegin 이후 호출)
void audioRxBegin() { audioRxReset(); }

// 매 loop()에서 호출 — 상태에 따라 READY 전송, 매직 감지, 헤더/본문 수신
void audioRxUpdate(unsigned long now) {

  if (rxState == AUDIO_IDLE) {
    if (READY_REPEAT_ENABLED && (now - lastReadyMs >= READY_REPEAT_MS)) {
      linkSendLine("READY");
      lastReadyMs = now;
    }
    while (linkAvailable()) {
      uint8_t b = linkReadByte();
      if (b == (uint8_t)HEADER_MAGIC[magicIdx]) {
        if (++magicIdx == 3) {                 // 매직 3바이트 완성
          magicIdx = 0; hdrRcvd = 0; hdrDone = false;
          rxState = AUDIO_RECEIVING; chunkTimer = now;
          return;
        }
      } else {
        magicIdx = (b == (uint8_t)HEADER_MAGIC[0]) ? 1 : 0;
      }
    }
    return;
  }

  if (rxState == AUDIO_RECEIVING) {
    if (now - chunkTimer > AUDIO_CHUNK_TIMEOUT_MS) {
      while (linkAvailable()) linkReadByte();  // 남은 바이트 flush
      if (ERR_REPORT_ENABLED) linkSendLine("ERR,TIMEOUT");
      audioRxReset();
      return;
    }

    if (!hdrDone) {                            // 헤더 10바이트 수신
      while (linkAvailable() && hdrRcvd < 10) {
        hdrBuf[hdrRcvd++] = linkReadByte(); chunkTimer = now;
      }
      if (hdrRcvd < 10) return;
      uint32_t bodyLen;
      if (!parsePcmHeader(&bodyLen)) { audioRxReset(); return; }
      audioBodySize = (int)bodyLen;
      hdrDone = true;
    }

    int before = audioRecvd;                   // 본문 수신
    while (linkAvailable() && audioRecvd < audioBodySize)
      audioBuf[audioRecvd++] = linkReadByte();
    if (audioRecvd > before) chunkTimer = now;

    if (audioRecvd >= audioBodySize) {
      linkSendLine("OK");
      if (DEBUG_PRINT) {
        char dbg[32];
        snprintf(dbg, sizeof(dbg), "DBG,RECV,%d", audioRecvd);
        linkSendLine(dbg);
      }
      rxState = AUDIO_RECEIVED;
    }
  }
  // AUDIO_RECEIVED: 3단계에서 audioRxReset() 호출까지 대기
}

bool           audioRxIsComplete() { return rxState == AUDIO_RECEIVED; }
const uint8_t* audioRxGetData()    { return audioBuf; }
int            audioRxGetSize()    { return audioBodySize; }
AudioRxState   audioRxGetState()   { return rxState; }
