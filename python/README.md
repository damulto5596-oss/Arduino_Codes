# 🌦️ Weather Forecast Report (날씨 예보 안내 및 알림 시스템)

기상청 초단기실황 및 단기예보 공공데이터를 기반으로 실시간 날씨 및 강수 예보를 분석하고, TTS 음성 안내와 아두이노 스피커를 통해 외출 전 우산 챙김 여부와 기상 알림을 전달하는 종합 날씨 리포트 시스템입니다.

---

## 📌 주요 기능
1. **날씨 데이터 실시간 분석 (`tts_output.py`, `alert_logic.py`)**:
   - 기상청 단기예보 및 초단기실황 API 연동
   - 현재 기온, 강수 형태(비, 눈 등), 오늘의 비/소나기 예보 구간 자동 분석
   - 친절하고 직관적인 한국어 음성 브리핑 텍스트 생성
2. **음성 및 하드웨어 알림 (`tts_player.py`, `arduino_speaker.py`)**:
   - Windows SAPI 및 Linux gTTS 음성 합성(TTS) 지원
   - 아두이노(Bridge RPC / UART Serial)를 통한 상황별 사운드 경보
3. **위치 좌표 자동 변환 및 설정 관리 (`update_location.py`, `config.json`)**:
   - 도시/동 이름 입력 시 위경도 및 기상청 격자 좌표(nx, ny) 자동 변환 및 저장
4. **자동 주기 실행 (`task_processor.py`)**:
   - 정해진 시간 또는 주기에 맞춘 날씨 브리핑 자동 실행

---

## 📂 파일 구조
| 파일명 | 설명 |
| :--- | :--- |
| **`alert_logic.py`** | 기상 조건에 따른 위험도 및 알림 분기 판단 로직 |
| **`arduino_speaker.py`** | TTS 출력 및 아두이노 MCU 신호 전송 |
| **`config.json`** | API 키, 조회 지역 및 시스템 기본 설정 파일 |
| **`task_processor.py`** | 백그라운드 스케줄러 및 작업 처리기 |
| **`tts_output.py`** | 기상청 데이터 파싱 및 음성 브리핑 텍스트 생성 |
| **`tts_player.py`** | TTS 음성 재생 모듈 |
| **`update_location.py`** | 위치 정보 검색 및 기상청 격자 좌표 업데이트 유틸리티 |

---

## 🚀 빠른 시작

### 1. 환경 설정
`config.json`에 공공데이터포털(data.go.kr) 기상청 API 일반 인증키를 설정합니다:
```json
{
  "api_key": "YOUR_DATA_GO_KR_DECODING_API_KEY",
  "location": {
    "city_name": "서울특별시청",
    "use_lat_lon": true,
    "latitude": 37.5665,
    "longitude": 126.9780,
    "grid_nx": 60,
    "grid_ny": 127
  }
}
```

### 2. 위치 변경
```bash
python update_location.py
```

### 3. 날씨 리포트 실행
```bash
python tts_output.py
# 또는 아두이노 연동 음성 출력
python arduino_speaker.py
```
