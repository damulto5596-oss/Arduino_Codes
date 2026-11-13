# Umbrella Alarm — 구조 요약 (AI 참고용)

> 코드를 손볼 때 전체를 다시 읽지 않도록 만든 요약본.
> **코드를 바꾸면 이 문서도 같이 갱신한다.** 문서와 코드가 다르면 코드가 정답.
> 마지막 갱신: 2026-11-14

## 1. 한 줄 요약

문이 닫힘→열림으로 바뀐 순간에 "비 예보 있음 + 우산 거치대에 있음"이면 우산을 챙기라고 알리는 장치.
MCU(스케치)가 센서를 읽고, Linux(Python)가 기상청 API로 판단하고, 결과를 MCU로 돌려보낸다.

## 2. 좌표

| 항목 | 값 |
| :--- | :--- |
| 앱 ID | `dXNlcjp1bWJyZWxsYV9hbGFybV9hcHA` |
| 보드 경로 | `/home/arduino/ArduinoApps/umbrella_alarm_app` |
| 로컬 체크아웃 | `...\ai-mirror\3265164066__user-umbrella_alarm_app-8b2a9c` |
| GitHub | `https://github.com/damulto5596-oss/Arduino_Codes.git` (사용자가 수동 push) |
| 보드 | Arduino UNO Q (aarch64) |
| 앱 bricks | **없음** (app.yaml에 bricks 항목 자체가 없음) |

## 3. 데이터 흐름 (현재 실제로 동작하는 경로)

```
[MCU] sensors.cpp         FSR(A0) + 자기센서(D3) 읽기
   ↓ linkSendState()      변화 시 즉시 / 무변화 시 500ms 주기
   ↓ Bridge.notify("state", vector<int>{time_ms, fsr, door_open, umbrella_present})
[Python] main.py _on_state()
   ↓ process_sensor_state(door_open, umbrella_present)   (arduino_speaker.py)
   ↓ check_alert(door_open, umbrella_present, rain, text) (alert_logic.py)
   ↓   조건: 문 닫힘→열림 전환 AND rain==1 AND umbrella_present==1
   ↓ Bridge.notify("sound_decision", 0 또는 1)
[MCU] link.cpp onSoundDecision()  →  Monitor.println("SOUND,1"/"SOUND,0")  ← 실제 소리는 안 남

별도 경로 (Python 내부):
  refresh_weather() ─600초마다─> tts_output.write_text() ─> 기상청 API ─> (안내문장, rain_flag)
                                   └ 실제 비 예보가 없으면 virtual_roll(오늘)로 가상 비 판단(70%)
                                     날짜 시드라서 600초마다 불러도 하루 안에선 같은 값
  loop() ─0.1초마다─> csv_logger.log_row() ─> python/data/sensor_log.csv
```

## 4. 파일별 역할

### Python (`python/`) — Linux(MPU)에서 실행
| 파일 | 역할 | 상태 |
| :--- | :--- | :--- |
| `main.py` | **진입점**. Bridge 핸들러 등록 + 0.1초 루프(CSV 기록, 날씨 갱신 주기 확인) | 동작 |
| `arduino_speaker.py` | 오케스트레이터. `refresh_weather()`(날씨 갱신), `process_sensor_state()`(판단 전달). 모듈 전역 `weather_text` / `rain_flag` 보유 | 동작 |
| `alert_logic.py` | 최종 판단. 모듈 전역 `previous_door_open`으로 문 전환 감지. 조건 충족 시 로그 출력 + `True` | 동작 |
| `tts_output.py` | 기상청 단기예보 API 호출·파싱 + 가상 비 추첨. `write_text()` → `(안내문장:str, rain:bool)`. 시각은 **KST 고정**, 가상 추첨은 `virtual_roll()`로 **날짜당 1회 확정** | 동작 |
| `test_tts_output.py` | `write_text()` 단위 테스트 + `virtual_roll()` 고정값(golden) 테스트. `python -m unittest test_tts_output` | 동작 |
| `csv_logger.py` | CSV 기록. `update_sensors()` / `update_decision()`로 최신값 캐시 → `log_row()`가 한 줄 추가 | 동작 |
| `update_location.py` | 지명 → 기상청 격자(nx,ny) 변환 유틸. 대화형 `main()`, 앱 런타임에선 호출 안 됨 | 독립 유틸 |
| `config.json` | API 키 + 위치(격자 좌표). **실제 기상청 키가 평문으로 들어있음** (사용자가 GitHub 공개 선택) | — |
| `tts_player.py` | gTTS→MP3→pyserial 전송. **고아 코드** (아무도 호출 안 함, 프로토콜도 불일치) | 죽음 |
| `task_processor.py` | `tts_player.light_text()` 호출하는 얇은 래퍼. **고아 코드** | 죽음 |
| `README.md` | **내용이 낡음** (task_processor를 "스케줄러"라 설명 — 사실 아님). 신뢰하지 말 것 | 낡음 |
| `weather.md` | 원래 3단계 설계 명세서. **통신 규약 부분은 폐기됨**(Serial→Bridge로 바뀜) | 낡음 |
| `data/sensor_log.csv` | 수집 결과. 런타임 생성물 | 동작 |

### 스케치 (`sketch/`) — MCU(Zephyr)에서 실행
| 파일 | 역할 | 상태 |
| :--- | :--- | :--- |
| `sketch.ino` | `setup()`/`loop()` + `runStateMachine()`. 상태: `SENSING`→`RECEIVING`→`PLAYING` | SENSING만 동작 |
| `sensors.cpp/.h` | FSR 이동평균+히스테리시스, 자기센서 디바운스. `SystemState{fsr, doorOpen, umbrellaPresent}` 반환 | 동작 |
| `link.cpp/.h` | **통신 계층**. Bridge 초기화, `linkSendState()`(notify), `onSoundDecision()`(provide), `linkSendLine()`(Monitor 출력) | 동작 |
| `config.h` | 모든 상수 모음. 핀 번호, 임계값, 타이밍 | 동작 |
| `audio_rx.cpp/.h` | PCM 수신 상태머신(매직"PCM"+헤더10B+본문512B단위). **영구 휴면** — `linkAvailable()`이 항상 false | 죽음 |
| `audio_player.cpp/.h` | 재생 인터페이스. BUZZER 모드=비프 패턴(진짜 음성 아님), PCM_STUB 모드=타이머 흉내만 | 미연결 |
| `sketch.yaml` | `arduino:zephyr` 플랫폼, 라이브러리 없음 | — |

## 5. 핀 / 상수 (config.h)

| 상수 | 값 | 비고 |
| :--- | :--- | :--- |
| `PIN_FSR` | `A0` | FSR402 (우산 무게) — 확정 |
| `PIN_DOOR` | `3` | 자기센서 MC-38 (문) — 확정 |
| `BUZZER_PIN` | `9` | **낡음.** 실제 스피커는 LM386이 D5에 연결됨 → 코드 미반영 |
| `DOOR_CLOSED_LEVEL` | `LOW` | NC 가정. 실측 미확인 |
| `FSR_ON/OFF_THRESHOLD` | `300` / `250` | 히스테리시스. 9주차 실측 후 교체 예정 |
| `INTERVAL_STATE_MS` | `500` | 무변화 시 STATE 전송 주기 |
| `SIMULATE_SENSORS` | `false` | true면 Serial로 센서 흉내 (f/d 토글) |
| `AUDIO_MAX_BYTES` | `40000` | 8000B/s × 5초 |
| `AUDIO_OUTPUT_MODE` | `BUZZER` | 비프음 모드 |

## 6. CSV 규칙

- 경로: `python/data/sensor_log.csv` (폴더·헤더 없으면 자동 생성)
- 헤더: `time,fsr,door_open,rain,umbrella_taken,alert`
- 간격: **0.1초** (`main.py`의 `loop()`가 `time.sleep(0.1)`)
- `time` 형식: `2026-11-04 17:06:14.9` (0.1초 단위 1자리)
- `umbrella_taken` = `umbrella_present`와 **같은 값** (1 = 거치대에 우산 있음). 이름만 다름
- `alert` = 최종 소리 출력 판단 (`should_play_sound`)
- **값은 "최신값 캐시" 방식**: 아두이노 STATE가 올 때만 갱신되고, CSV는 0.1초마다 그 캐시를 찍는다
  → STATE는 최대 500ms 간격이므로 같은 값이 최대 5줄 연속 반복될 수 있음
  → `alert=1`도 다음 STATE가 올 때까지(최대 ~0.5초, 약 5줄) 1로 유지됨

## 7. 플랫폼 제약 — 반드시 기억할 것

### MCU↔Linux 통신은 **Bridge만** 가능
- `/dev/ttyGS0`은 `arduino-router-serial.service`가 이미 점유 중
  (`socat file:/dev/ttyGS0,raw,b9600 tcp:127.0.0.1:7500`)
- pyserial로 직접 열면 충돌 + 보율도 다름(9600 vs 115200) → **절대 하지 말 것**
- `/dev/ttyUSB0`은 이 보드에 존재하지 않음
- 스케치: `#include "Arduino_RouterBridge.h"`, `Bridge.begin()`, `Monitor.begin(115200)`

### Python `Bridge.provide` 핸들러 안에서 `Bridge.call` 금지
```
RuntimeError: Cannot call 'X' from a provided handler: nested bridge calls are not supported.
```
→ 핸들러 안에서는 **`Bridge.notify`만** 사용. (이것 때문에 무한 에러 반복 겪음)

### 앱 venv에 pip 패키지 설치하는 방법
앱은 도커 컨테이너로 실행됨. venv는 `/app/.cache/.venv`(호스트: `<앱경로>/.cache/.venv`),
`uv venv --system-site-packages`로 생성되고 **존재하면 재사용**(설치 결과 유지됨).
호스트 쉘에는 python/uv/pip이 없으므로 **같은 이미지로 1회용 컨테이너**를 띄워야 함:

```sh
docker run --rm --network umbrella_alarm_app_default --entrypoint sh \
  -v /home/arduino/ArduinoApps/umbrella_alarm_app:/app \
  ghcr.io/arduino/app-bricks/python-apps-base:0.13.1 \
  -c "uv pip install --python /app/.cache/.venv/bin/python <패키지>"
```
- 이미지 태그는 변할 수 있음 → `docker inspect umbrella_alarm_app-main-1 --format '{{.Config.Image}}'`로 확인
- `--network` 없으면 DNS 실패. 보드 인터넷도 필요(`wifi_status`로 확인 — **자주 끊김**)
- 참고: `python/requirements.txt`를 두면 `/run.sh`가 기동 시 자동 설치해줌 (아직 안 씀)

### 설치 현황 (앱 venv)
| 패키지 | 상태 |
| :--- | :--- |
| `pyserial` 3.5 | 설치됨 (단, 현재 코드는 안 씀) |
| `gTTS` | **없음** |
| `ffmpeg` (바이너리) | **이미지에 없음**. `imageio-ffmpeg`도 미설치 |

### 체크아웃 함정 (실제로 당했음)
다른 앱/예제를 체크아웃하면 이전 체크아웃 폴더가 **비활성**이 되고,
그 폴더에 편집해도 **보드에 전혀 반영되지 않는다**(경고만 뜸).
→ 작업 전 `apps_checkout`으로 받은 **최신 경로**인지 확인. 증상: 고친 코드인데 옛 에러가 계속 남.

### 디스코드 봇과 공유하는 가상 날씨 규칙 (통신 없음)

같은 저장소 `discord` 브랜치의 디스코드 봇에 `/가상날씨` 명령이 있고, 보드와 **같은 날씨**를 말해야 한다.
두 기기는 서로 통신하지 않는다 — 보드는 공유기 뒤에 있고 WiFi가 자주 끊기며, 봇 서버(Oracle Cloud)는
인바운드 포트를 열지 않았다. 대신 **날짜를 시드로 같은 주사위를 각자 굴린다.**

| 맞춰야 하는 것 | 보드 | 봇 |
| :--- | :--- | :--- |
| 가상 추첨 함수 | `tts_output.virtual_roll()` | `virtual_weather.virtual_roll()` |
| 시드/확률 상수 | `VIRTUAL_SEED_SALT`, `VIRTUAL_RAIN_THRESHOLD`, `VIRTUAL_RAIN_DICE` | 같은 이름·같은 값 |
| 비 판단 규칙 | `write_text()` 안의 PTY/POP 루프 | `virtual_weather.judge_rain()` |
| 기상청 API | `VilageFcstInfoService_2.0` + `urllib` | 같음 (봇도 `requests` 대신 `urllib`) |
| API 키·격자 | `config.json`의 `api_key`/`grid_nx`/`grid_ny` | `.env`의 `KMA_API_KEY`/`KMA_NX`/`KMA_NY` |
| 날짜 기준 시간대 | `KST` (고정 +9) | `KST` (`ZoneInfo("Asia/Seoul")`) |

- **한쪽만 고치면 두 기기가 다른 날씨를 말하고, 겉으로는 전혀 티가 나지 않는다.**
  `test_tts_output.py`의 `VirtualRollTests.GOLDEN`이 그 방어선이다 — 깨지면 봇 쪽도 같이 깨진 것이다.
- 봇 쪽 값 확인: `discord` 폴더에서 `python virtual_weather.py 2026-11-14`
- `random` 모듈을 안 쓰는 이유: `random.Random(문자열)`의 시드 변환은 CPython 구현 세부사항이라
  파이썬 버전이 다르면 같은 값을 보장하지 않는다. 그래서 `hashlib.sha256`을 직접 쓴다.

### 런타임 생성 파일
앱이 실행 중 만든 파일(CSV 등)은 체크아웃 미러에 자동으로 안 내려옴 → `apps_checkout` 다시 하면 내려옴.

### 이 세션의 권한
`apps_start`가 차단되어 있어 **AI가 앱을 시작할 수 없음** → 사용자가 직접 시작해야 로그 확인 가능.
로컬 터미널(git/gh) 도구도 없음 → GitHub push는 사용자가 수동으로.

## 8. 미해결 / 다음 할 일

1. **스피커 연결 (진행 중)** — LM386 아날로그 앰프가 **디지털 5번**에 연결됨
   - LM386은 프로토콜 없는 아날로그 파워 앰프 → MCU가 PWM으로 PCM 샘플을 8000Hz로 출력해야 함
   - 설계 방향: Python이 gTTS→PCM 변환 → Bridge로 512B씩 **미리 전부** 전송 → MCU가 버퍼에서 재생
     (Bridge RPC로 초당 8000회 실시간 전송은 불가 → 선수신 후재생 구조 유지)
   - **막힌 지점**: `ffmpeg`가 이미지에 없고 `gTTS` 미설치. 보드 인터넷 끊겨서 설치 중단됨
   - `config.h`의 `BUZZER_PIN = 9`를 D5로 바꾸고 `AUDIO_OUTPUT_MODE` 재검토 필요
2. `audio_rx.cpp` 되살리기 — Bridge로 바이트를 받는 구조로 고쳐야 함 (현재 `linkAvailable()` 항상 false)
3. `link.cpp`의 `onSoundDecision()`이 `playerStart()`를 호출하도록 연결 (현재 Monitor 출력만)
4. 고아 코드 정리 — `tts_player.py`, `task_processor.py` (옛 pyserial MP3 방식, 프로토콜 불일치)
5. 낡은 문서 갱신 — `README.md`, `weather.md`
6. **비 예보 없는 날 `write_text()`가 빈 문자열을 반환** → `arduino_speaker.process_sensor_state()`의
   `if not weather_text:` 가드에 걸려 "날씨 문장을 먼저 갱신해야 합니다"를 찍고 `False`를 반환한다.
   결과(알람 안 울림)는 맞지만 경로와 로그가 엉뚱하다. 디스코드 봇은 이 경우를 `clear`로 따로 표시함
6. 실측 보정 — `FSR_ON/OFF_THRESHOLD`, `DOOR_CLOSED_LEVEL` 극성

## 9. 검증 안 된 주장

- `config.h` 주석의 "UNO Q RAM = 786KB(확인됨)" — 이전 작업에서 적힌 것이며 직접 확인 안 함
- 스케치 → Python 방향 `Bridge.notify`에 `std::vector<int>` 전달 — 공식 예제에 동일 패턴은 없었으나
  실제 로그에서 `_on_state`가 정상 수신하는 것으로 **동작 확인됨**
