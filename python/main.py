import time

from arduino.app_utils import App, Bridge
import arduino_speaker
from arduino_speaker import refresh_weather, process_sensor_state
import csv_logger


WEATHER_REFRESH_INTERVAL_S = 600  # 임의의 값: 10분마다 날씨 재조회
CSV_LOG_INTERVAL_S = 0.1  # CSV 수집 간격

_last_weather_refresh = 0.0


def _on_state(values):
    """아두이노가 Bridge로 보낸 STATE(time_ms, fsr, door_open, umbrella_present)를 받아
    최종 판단까지 전달하고, 결과(소리 출력 여부)를 Bridge로 아두이노에 다시 알린다.
    스피커 프로그램은 호출하지 않는다. CSV 기록용 최신 값도 갱신한다."""
    _time_ms, fsr, door_open, umbrella_present = values

    should_play_sound = process_sensor_state(door_open, umbrella_present)

    csv_logger.update_sensors(fsr, door_open, umbrella_present)
    csv_logger.update_decision(1 if arduino_speaker.rain_flag else 0, 1 if should_play_sound else 0)

    weather_text = "비 예보 있음" if arduino_speaker.rain_flag else "비 예보 없음"
    door_text = "열림" if door_open else "닫힘"
    umbrella_text = "있음" if umbrella_present else "없음"
    print(f"[센서] 날씨: {weather_text} | 문: {door_text} | 우산: {umbrella_text}")

    Bridge.notify("sound_decision", 1 if should_play_sound else 0)
    print(f"[Bridge 전송] {'소리 출력' if should_play_sound else '소리 출력 X'}")


Bridge.provide("state", _on_state)  # 아두이노가 보내는 STATE를 받는 핸들러 등록


def loop():
    """날씨 갱신(주기) + CSV 기록(0.1초 간격)을 담당한다. 센서 STATE는 Bridge 콜백(_on_state)이 비동기로 처리한다."""
    global _last_weather_refresh

    now = time.monotonic()
    if now - _last_weather_refresh >= WEATHER_REFRESH_INTERVAL_S:
        refresh_weather()
        _last_weather_refresh = now

    csv_logger.log_row()
    time.sleep(CSV_LOG_INTERVAL_S)


App.run(user_loop=loop)
