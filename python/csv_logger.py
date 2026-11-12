import csv
import datetime
from pathlib import Path


CSV_PATH = Path(__file__).resolve().parent / "data" / "sensor_log.csv"
HEADER = ["time", "fsr", "door_open", "rain", "umbrella_taken", "alert"]

_latest_fsr = 0
_latest_door_open = 0
_latest_umbrella_taken = 0
_latest_rain = 0
_latest_alert = 0


def _ensure_file():
    """CSV 파일과 상위 폴더, 헤더 줄이 없으면 만든다."""
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not CSV_PATH.exists():
        with CSV_PATH.open("w", newline="", encoding="utf-8") as file:
            csv.writer(file).writerow(HEADER)


def update_sensors(fsr, door_open, umbrella_taken):
    """아두이노에서 받은 센서 값(fsr, door_open, umbrella_taken)을 최신 값으로 저장한다."""
    global _latest_fsr, _latest_door_open, _latest_umbrella_taken
    _latest_fsr = fsr
    _latest_door_open = door_open
    _latest_umbrella_taken = umbrella_taken


def update_decision(rain, alert):
    """날씨 판단(rain)과 최종 알림 판단(alert) 결과를 최신 값으로 저장한다."""
    global _latest_rain, _latest_alert
    _latest_rain = rain
    _latest_alert = alert


def log_row():
    """현재까지의 최신 값을 한 줄로 CSV에 추가한다. 0.1초 간격으로 호출한다."""
    _ensure_file()

    now = datetime.datetime.now()
    time_text = now.strftime("%Y-%m-%d %H:%M:%S") + f".{now.microsecond // 100000}"

    row = [time_text, _latest_fsr, _latest_door_open, _latest_rain, _latest_umbrella_taken, _latest_alert]
    with CSV_PATH.open("a", newline="", encoding="utf-8") as file:
        csv.writer(file).writerow(row)
