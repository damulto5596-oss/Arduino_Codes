"""가상 날씨 — 보드(umbrella_alarm)와 같은 규칙으로 "오늘의 가상 날씨"를 구한다.

보드의 `python/tts_output.py`와 **같은 기상청 단기예보 API**를 같은 파라미터로 호출하고,
비 판단 규칙(PTY 1/2/4, POP >= 60, 현재 시각 이후)도 그대로 옮겨 왔다.
가상 비 추첨은 '날짜'를 시드로 쓰기 때문에, 보드와 한 번도 통신하지 않아도
같은 날이면 양쪽이 반드시 같은 결과를 낸다.

이 파일이 `requests` 대신 `urllib`을 쓰는 이유: 보드의 앱 venv에는 pip 패키지를
새로 넣기가 어렵고(도커 컨테이너를 따로 띄워야 함), 두 파일을 나란히 놓고
비교할 수 있어야 규칙이 어긋나지 않는다.

⚠️ 아래 네 가지를 바꾸면 보드의 `python/tts_output.py`도 **같이** 바꿔야 한다.
   한쪽만 고치면 두 기기가 서로 다른 날씨를 말하고, 겉으로는 전혀 티가 나지 않는다.
     1. VIRTUAL_SEED_SALT       (시드 문자열)
     2. VIRTUAL_RAIN_THRESHOLD  (70% 기준값)
     3. judge_rain()            (비 판단 규칙)
     4. KST                     (날짜 기준 시간대)

사용법:
    python virtual_weather.py              # 오늘의 가상 날씨 (.env의 KMA_* 사용)
    python virtual_weather.py 2026-11-20   # 그 날짜의 추첨 결과만 (API 호출 없음)
"""

import datetime
import hashlib
import json
import os
import sys
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

# 보드는 집(한국)에 있고 봇 서버는 보통 UTC다. "오늘"이 어긋나지 않도록 양쪽 다 KST 기준.
KST = ZoneInfo("Asia/Seoul")

# 기상청 단기예보 — 보드 python/tts_output.py:47과 같은 엔드포인트
FORECAST_URL = "http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"
USER_AGENT = "WeatherApp/1.0"
TIMEOUT = 10

# 단기예보 발표 시각(02,05,08,11,14,17,20,23시)과 조회 가능해지는 시각(발표+10분)
BASE_SLOTS = [
    ("0200", 2 * 60 + 10),
    ("0500", 5 * 60 + 10),
    ("0800", 8 * 60 + 10),
    ("1100", 11 * 60 + 10),
    ("1400", 14 * 60 + 10),
    ("1700", 17 * 60 + 10),
    ("2000", 20 * 60 + 10),
    ("2300", 23 * 60 + 10),
]

RAIN_PTY = (1, 2, 4)  # 강수형태: 1 비, 2 비/눈, 4 소나기
RAIN_POP = 60         # 비 예보 코드가 없어도 강수확률이 이 값 이상이면 비로 본다

# 가상 비 추첨: randint(1, 10) <= 7 이면 비 → 70%
VIRTUAL_RAIN_DICE = 10
VIRTUAL_RAIN_THRESHOLD = 7
VIRTUAL_SEED_SALT = "umbrella-virtual"

# describe()의 source 값
SOURCE_REAL_NOW = "real_now"            # 지금 실제로 비가 내리는 중
SOURCE_REAL_FORECAST = "real_forecast"  # 오늘 남은 시간에 실제 비 예보 있음
SOURCE_VIRTUAL_RAIN = "virtual_rain"    # 실제 비는 없고 가상 추첨이 비로 나옴
SOURCE_CLEAR = "clear"                  # 실제도 가상도 비 없음


def base_datetime(now):
    """now 시각에 조회할 수 있는 가장 최근 발표 자료의 (base_date, base_time)."""
    cur_mins = now.hour * 60 + now.minute
    for time_str, ready_mins in reversed(BASE_SLOTS):
        if cur_mins >= ready_mins:
            return now.strftime("%Y%m%d"), time_str
    # 새벽 2시 10분 이전이면 전날 23시 발표 자료를 쓴다
    return (now - datetime.timedelta(days=1)).strftime("%Y%m%d"), "2300"


def fetch_items(service_key, nx, ny, now):
    """기상청 단기예보 항목 목록을 받아 온다. 실패하면 예외를 그대로 던진다."""
    base_date, base_time = base_datetime(now)

    params = {
        "serviceKey": urllib.parse.unquote(service_key),
        "pageNo": "1",
        "numOfRows": "1000",
        "dataType": "JSON",
        "base_date": base_date,
        "base_time": base_time,
        "nx": str(nx),
        "ny": str(ny),
    }

    req = urllib.request.Request(
        f"{FORECAST_URL}?{urllib.parse.urlencode(params)}",
        headers={"User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
        data = json.loads(res.read().decode("utf-8"))

    return data["response"]["body"]["items"]["item"]


def judge_rain(items, now):
    """보드와 같은 규칙으로 '오늘 비가 오는가'를 판단한다. 오늘·현재 시각 이후만 본다."""
    today_str = now.strftime("%Y%m%d")
    cur_hour = now.hour

    is_raining_now = False
    rain_hours = set()
    max_pop = 0

    for item in items:
        if item.get("fcstDate") != today_str:
            continue

        category = item.get("category")
        if category not in ("PTY", "POP"):
            continue

        try:
            fcst_hour = int(item.get("fcstTime")[:2])
            value = int(item.get("fcstValue"))
        except (TypeError, ValueError):
            continue

        if category == "PTY" and value in RAIN_PTY:
            if fcst_hour == cur_hour:
                is_raining_now = True
            if fcst_hour >= cur_hour:
                rain_hours.add(fcst_hour)

        elif category == "POP" and fcst_hour >= cur_hour:
            max_pop = max(max_pop, value)
            if value >= RAIN_POP:
                rain_hours.add(fcst_hour)

    return {
        "is_raining_now": is_raining_now,
        "rain_hours": sorted(rain_hours),
        "max_pop": max_pop,
    }


def virtual_roll(day):
    """날짜만으로 가상 주사위(1~10)를 굴린다. 같은 날이면 어디서 돌려도 같은 값이 나온다.

    random 모듈을 쓰지 않고 sha256을 직접 쓴 이유: random.Random(문자열)의 시드 변환은
    CPython 구현 세부사항이라 파이썬 버전이 다르면 같은 값을 보장하지 않는다.
    보드와 봇은 서로 다른 기계(aarch64 / x86_64)에서 다른 파이썬으로 돌 수 있고,
    값이 어긋나도 겉으로는 티가 나지 않으므로 해시로 못 박아 둔다.
    """
    digest = hashlib.sha256(f"{day.isoformat()}:{VIRTUAL_SEED_SALT}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % VIRTUAL_RAIN_DICE + 1


def virtual_rain(day):
    """그 날짜의 가상 비 여부(70%)."""
    return virtual_roll(day) <= VIRTUAL_RAIN_THRESHOLD


def describe(service_key, nx, ny, now=None):
    """오늘의 (가상 포함) 날씨를 판단해 dict로 돌려준다.

    반환: date, source, rain, text, roll, rain_hours, max_pop, is_raining_now
      - source: SOURCE_* 중 하나
      - text:   보드가 TTS로 읽는 문장과 같은 문장 (SOURCE_CLEAR는 보드가 빈 문자열)
    """
    now = now or datetime.datetime.now(KST)
    day = now.date()

    judged = judge_rain(fetch_items(service_key, nx, ny, now), now)
    roll = virtual_roll(day)
    result = {"date": day, "roll": roll, **judged}

    # 보드 tts_output.write_text()와 같은 순서로 판단한다
    if judged["is_raining_now"]:
        return {
            **result,
            "source": SOURCE_REAL_NOW,
            "rain": True,
            "text": "현재 바깥에 비가 내리고 있습니다. 외출하실 때 우산을 꼭 챙기세요.",
        }

    if judged["rain_hours"]:
        first_h = judged["rain_hours"][0]
        time_text = f"오후 {first_h - 12}시" if first_h >= 12 else f"오전 {first_h}시"
        return {
            **result,
            "source": SOURCE_REAL_FORECAST,
            "rain": True,
            "text": (
                f"현재는 비가 오지 않지만, 오늘 {time_text}경부터 비 예보가 있습니다. "
                f"최고 강수확률은 {judged['max_pop']}퍼센트입니다. 우산을 챙기시기 바랍니다."
            ),
        }

    if roll <= VIRTUAL_RAIN_THRESHOLD:
        return {
            **result,
            "source": SOURCE_VIRTUAL_RAIN,
            "rain": True,
            "text": "가상실험에서 비가 오고 있습니다. 우산을 챙기시기 바랍니다.",
        }

    # 보드는 이 경우 빈 문자열을 반환한다 (python/tts_output.py:128)
    return {**result, "source": SOURCE_CLEAR, "rain": False, "text": ""}


def main():
    # 날짜만 주면 API 없이 추첨 결과만 보여 준다 (보드와 값이 맞는지 대조할 때 편하다)
    if len(sys.argv) > 1:
        day = datetime.date.fromisoformat(sys.argv[1])
        roll = virtual_roll(day)
        print(f"{day} 주사위: {roll}/{VIRTUAL_RAIN_DICE} "
              f"→ 가상 비 {'있음' if roll <= VIRTUAL_RAIN_THRESHOLD else '없음'}")
        return

    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
    except ImportError:
        pass

    key = os.getenv("KMA_API_KEY")
    if not key:
        sys.exit("KMA_API_KEY가 없습니다. .env에 넣어 주세요.")

    result = describe(key, int(os.getenv("KMA_NX") or 59), int(os.getenv("KMA_NY") or 126))
    print(f"날짜      : {result['date']}")
    print(f"판단 근거 : {result['source']}")
    print(f"비        : {'옴' if result['rain'] else '안 옴'}")
    print(f"주사위    : {result['roll']}/{VIRTUAL_RAIN_DICE}")
    print(f"안내 문장 : {result['text'] or '(없음)'}")


if __name__ == "__main__":
    main()
