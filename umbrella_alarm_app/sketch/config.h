#pragma once

// ── 1단계: 센서 · 시리얼 ──────────────────────────────────────────────────────
const int          PIN_FSR            = A0;     // 실제 값: FSR402 핀
const int          PIN_DOOR           = 3;      // 실제 값: 자기 센서(MC-38) 핀
const long         SERIAL_BAUD        = 115200; // 임의의 값: 리눅스 측과 맞춰야 함

const unsigned long INTERVAL_FSR_MS   = 50;    // 임의의 값: FSR 읽기 주기(ms)
const unsigned long INTERVAL_DOOR_MS  = 20;    // 임의의 값: MC-38 읽기 주기(ms)
const int          FSR_SAMPLE_COUNT   = 5;     // 임의의 값: FSR 이동 평균 샘플 수
const int          FSR_ON_THRESHOLD   = 300;   // 임의의 값: 우산 있음 판정 기준. 9주차 실측 후 교체
const int          FSR_OFF_THRESHOLD  = 250;   // 임의의 값: 우산 없음 판정 기준. 9주차 실측 후 교체
const unsigned long DOOR_DEBOUNCE_MS  = 30;    // 임의의 값: MC-38 디바운스 시간(ms). 실측 후 조정
const unsigned long INTERVAL_STATE_MS = 500;   // 임의의 값: 변화 없을 때 STATE 전송 주기(ms)

// 임의의 값: NC 타입이므로 LOW=닫힘. 실제 극성 확인 후 HIGH로 변경 가능
const int          DOOR_CLOSED_LEVEL  = LOW;

// 임의의 값: true이면 시리얼 입력으로 센서 흉내(f=우산 토글, d=문 토글). 기본 false
// 주의: SIMULATE_SENSORS=true 상태에서 2단계 음성 수신과 Serial이 충돌함. 동시에 쓰지 말 것
const bool         SIMULATE_SENSORS   = false;

// ── 2단계: 음성 수신 ──────────────────────────────────────────────────────────
// 임의의 값: IDLE 중 READY 반복 전송 주기(ms). 리눅스 재시작 대응용
const unsigned long READY_REPEAT_MS      = 3000;
// 임의의 값: READY 반복 전송 여부. 리눅스가 READY를 하나만 기대하면 false로
const bool          READY_REPEAT_ENABLED = true;

// 임의의 값: 허용 최대 PCM 길이(초). 버퍼 = 8000바이트/초 x 이 값
// UNO Q RAM = 786KB(확인됨) → 현재 40,000바이트는 충분. 최대 ~97초(776,000바이트)까지 가능
const int           AUDIO_MAX_SECONDS    = 5;
const int           AUDIO_MAX_BYTES      = 8000 * AUDIO_MAX_SECONDS; // = 40,000바이트

const int           CHUNK_SIZE           = 512;  // 흐름도 기준 고정값
// 임의의 값: 청크 사이 최대 대기 시간(ms)
const unsigned long AUDIO_CHUNK_TIMEOUT_MS = 3000;

// 임의의 값: ERR 줄을 리눅스에 전송할지 여부. 리눅스가 ERR를 처리하면 true로 변경
const bool          ERR_REPORT_ENABLED   = false;
// 임의의 값: DBG 줄 출력 여부. 운용 시 false로 변경
const bool          DEBUG_PRINT          = false;

// ── 3단계: 음성 재생 ──────────────────────────────────────────────────────────
#define AUDIO_MODE_BUZZER   0
#define AUDIO_MODE_PCM_STUB 1
// 임의의 값: 0=부저 비프 패턴, 1=PCM 스텁(시간 흉내). PCM 재생 구현 확정 후 교체
const int           AUDIO_OUTPUT_MODE       = AUDIO_MODE_BUZZER;

const int           BUZZER_PIN              = 9;    // 임의의 값: 부저 연결 핀. 실제 배선 확정 후 교체
const int           BEEP_FREQ               = 1000; // 임의의 값: 비프 주파수(Hz)
const int           BEEP_COUNT              = 3;    // 임의의 값: 비프 횟수. 사용자 테스트 후 조정
const unsigned long BEEP_ON_MS              = 200;  // 임의의 값: 비프 켜짐 시간(ms)
const unsigned long BEEP_OFF_MS             = 150;  // 임의의 값: 비프 꺼짐 간격(ms)

// 임의의 값: PCM 스텁에서 1초로 볼 바이트 수(= 8000Hz × 1바이트/샘플)
const int           PCM_STUB_BYTES_PER_SEC  = 8000;
// 임의의 값: 재생 최대 허용 시간(ms). 초과 시 ERR,PLAY 후 복귀
const unsigned long PLAY_TIMEOUT_MS         = 30000;
