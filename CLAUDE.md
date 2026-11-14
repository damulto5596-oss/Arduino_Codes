# CLAUDE.md

## 응답 언어
- 사용자에게 대답할 때는 항상 한국어로 말한다.

## 가상 날씨 (`/가상날씨`) — 우산 알람 보드와 결과가 같아야 한다
- 의도: 디스코드 봇과 우산 알람 보드(같은 저장소의 `fix/virtual-rain-daily-seed`/`main` 브랜치, `python/tts_output.py`)가
  **같은 날에는 반드시 같은 가상 날씨**(비 옴 / 비 안 옴)를 말해야 한다. 가상 비 확률은 양쪽 모두 70%다.
- 두 기기는 서로 통신하지 않는다. 대신 **날짜(KST)를 시드로 같은 주사위를 각자 굴린다**:
  `sha256("<YYYY-MM-DD>:umbrella-virtual")` 앞 8바이트 % 10 + 1, 7 이하면 비.
- 아래를 바꾸면 보드 `python/tts_output.py`도 **반드시 같이** 바꿔야 한다. 한쪽만 바꾸면 겉으로는 티가 안 나고 결과만 어긋난다.
  - `virtual_weather.py`의 `VIRTUAL_SEED_SALT`, `VIRTUAL_RAIN_DICE`, `VIRTUAL_RAIN_THRESHOLD`, `virtual_roll()`
  - 비 판단 규칙 `judge_rain()` (PTY 1/2/4 또는 POP ≥ 60, 오늘·현재 시각 이후) 과 판단 순서(지금 비 → 오늘 예보 → 가상 추첨)
  - 날짜 기준 시간대 `KST` (서버는 UTC라서 KST가 아니면 아침 알림 날짜가 하루 어긋난다)
  - `.env`의 `KMA_API_KEY`/`KMA_NX`/`KMA_NY` = 보드 `python/config.json`의 `api_key`/`grid_nx`/`grid_ny`
- `random` 모듈은 쓰지 않는다: 문자열 시드 변환이 파이썬 버전마다 달라질 수 있다.
- 2026-11-14 확인: 2026-01-01부터 3,650일 동안 보드와 봇의 `virtual_roll()` 불일치 0건, 가상 비 비율 70.7%.
  값 확인: `python virtual_weather.py 2026-11-14` (API 호출 없이 그날 주사위만 출력)
- 디스코드 출력은 한 줄만 보낸다: `🌧️ 비 옴`(실제 예보) / `🌧️ 비 옴(가상)`(가상 추첨) / `☀️ 비 안 옴`.
  `/가상날씨`로 채널을 지정하면 그 채널을 기억하고, 매일 08:00 KST 식단·날씨 알림 뒤에 자동으로 보낸다
  (`send_today_virtual_weather`). 채널을 지정한 적이 없으면 기본 `CHANNEL_ID`로 보내지 않고 건너뛴다.
- 서버(Oracle): `~/alertbot` 에 이 브랜치(`discord`)가 git clone 되어 있고, 서비스 이름은 `alertbot`이다
  (`DEPLOY.md`의 `~/contest_alert`/`contest-bot`은 옛 이름). 갱신: `git pull` 후 `sudo systemctl restart alertbot`.
