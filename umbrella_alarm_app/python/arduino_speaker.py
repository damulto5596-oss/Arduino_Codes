import json
from pathlib import Path

from tts_output import write_text
from alert_logic import check_alert


CONFIG_PATH = Path(__file__).resolve().parent / "config.json"

weather_text = ""
rain_flag = False


def refresh_weather():
    """날씨 API에서 안내 문장과 비 예보 여부를 받아 저장한다."""
    global weather_text, rain_flag

    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        config = json.load(file)

    location = config["location"]

    weather_text, rain_flag = write_text(
        service_key=config["api_key"],
        nx=int(location["grid_nx"]),
        ny=int(location["grid_ny"]),
    )

    print(f"날씨 안내 문장: {weather_text} (비 예보: {rain_flag})")
    return weather_text, rain_flag


def process_sensor_state(door_open, umbrella_present):
    """아두이노가 보낸 센서 상태를 최신 날씨 판단(rain_flag)과 함께 알림 판단 함수에 전달한다."""
    if not weather_text:
        print("날씨 문장을 먼저 갱신해야 합니다.")
        return False

    return check_alert(
        door_open=door_open,
        umbrella_present=umbrella_present,
        rain=1 if rain_flag else 0,
        text=weather_text,
    )
