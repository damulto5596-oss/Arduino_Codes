#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
[파일 1] weather_fetcher.py
- 공공데이터포털 기상청 단기예보 API 호출
- 우산 챙김 판단에 꼭 필요한 정보만 분석하여 간결한 TTS 음성 문자열 반환
"""

import datetime
import hashlib
import json
import urllib.request
import urllib.parse

# 한국 표준시. 앱이 도커 컨테이너로 돌고 컨테이너 시간대가 UTC인 경우가 있어,
# "오늘"이 디스코드 봇과 어긋나지 않도록 고정해 둔다. (한국은 DST가 없어 +9가 항상 정확)
KST = datetime.timezone(datetime.timedelta(hours=9), "KST")

# 가상 비 추첨: 주사위(1~10)가 7 이하면 비 → 70%
VIRTUAL_RAIN_DICE = 10
VIRTUAL_RAIN_THRESHOLD = 7
VIRTUAL_SEED_SALT = "umbrella-virtual"


def virtual_roll(day):
    """날짜만으로 가상 주사위(1~10)를 굴린다. 같은 날이면 어디서 돌려도 같은 값이 나온다.

    디스코드 봇(discord 브랜치)의 virtual_weather.py에 **글자까지 같은 함수**가 있다.
    보드와 봇은 서로 통신하지 않고 이 함수만으로 같은 "오늘의 가상 날씨"에 도달하므로,
    한쪽만 고치면 두 기기가 다른 날씨를 말하고 겉으로는 티가 나지 않는다.

    random 모듈을 쓰지 않는 이유: random.Random(문자열)의 시드 변환은 CPython 구현
    세부사항이라 파이썬 버전이 다르면 같은 값을 보장하지 않는다. 보드(aarch64)와
    봇 서버(x86_64)는 파이썬 버전이 다를 수 있다.
    """
    digest = hashlib.sha256(f"{day.isoformat()}:{VIRTUAL_SEED_SALT}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % VIRTUAL_RAIN_DICE + 1


def _get_base_datetime():
    """기상청 단기예보 발표 시각(02, 05, 08, 11, 14, 17, 20, 23시) 계산"""
    now = datetime.datetime.now(KST)
    cur_mins = now.hour * 60 + now.minute
    slots = [
        ("0200", 2 * 60 + 10),
        ("0500", 5 * 60 + 10),
        ("0800", 8 * 60 + 10),
        ("1100", 11 * 60 + 10),
        ("1400", 14 * 60 + 10),
        ("1700", 17 * 60 + 10),
        ("2000", 20 * 60 + 10),
        ("2300", 23 * 60 + 10)
    ]
    for time_str, min_val in reversed(slots):
        if cur_mins >= min_val:
            return now.strftime("%Y%m%d"), time_str
    # 새벽 2시 10분 이전이면 전날 23시 자료 사용
    yesterday = now - datetime.timedelta(days=1)
    return yesterday.strftime("%Y%m%d"), "2300"


def write_text(service_key: str, nx: int = 60, ny: int = 127):
    """
    우산을 챙겨야 하는지 판단하여 안내 텍스트와 비 예보 여부를 반환하는 함수
    :param service_key: 공공데이터포털 일반 인증키 (Decoding)
    :param nx: 기상청 X 격자 (기본값: 서울 60)
    :param ny: 기상청 Y 격자 (기본값: 서울 127)
    :return: (안내 문자열, 비 예보 여부(bool)) 튜플
    """
    base_date, base_time = _get_base_datetime()
    url = "http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"

    params = {
        "serviceKey": urllib.parse.unquote(service_key),
        "pageNo": "1",
        "numOfRows": "1000",
        "dataType": "JSON",
        "base_date": base_date,
        "base_time": base_time,
        "nx": str(nx),
        "ny": str(ny)
    }

    req_url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(req_url, headers={"User-Agent": "WeatherApp/1.0"})

    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            data = json.loads(res.read().decode('utf-8'))
        items = data["response"]["body"]["items"]["item"]
    except Exception as e:
        return f"날씨 정보를 불러오지 못했습니다. 오류: {e}", False

    # 오늘 남은 시간대의 비 예보 분석
    now = datetime.datetime.now(KST)
    today_str = now.strftime("%Y%m%d")
    cur_hour = now.hour

    is_raining_now = False
    rain_hours = []
    max_pop = 0

    for item in items:
        if item.get("fcstDate") != today_str:
            continue
        try:
            fcst_hour = int(item.get("fcstTime")[:2])
        except (ValueError, TypeError):
            continue

        category = item.get("category")
        val = item.get("fcstValue")

        # 1. 강수형태 (PTY: 1 비, 2 비/눈, 4 소나기)
        if category == "PTY":
            pty = int(val)
            if fcst_hour == cur_hour and pty in [1, 2, 4]:
                is_raining_now = True
            if fcst_hour >= cur_hour and pty in [1, 2, 4]:
                if fcst_hour not in rain_hours:
                    rain_hours.append(fcst_hour)

        # 2. 강수확률 (POP)
        elif category == "POP":
            pop = int(val)
            if fcst_hour >= cur_hour:
                if pop > max_pop:
                    max_pop = pop
                # 비 예보 코드가 없더라도 확률 60% 이상이면 포함
                if pop >= 60 and fcst_hour not in rain_hours:
                    rain_hours.append(fcst_hour)

    rain_hours.sort()
    rain = is_raining_now or bool(rain_hours)  # 비 예보 여부: 현재 비 또는 오늘 중 예보 있음

    # --- 우산 안내 텍스트 생성 ---
    # 상황 1: 지금 당장 비가 오는 경우
    if is_raining_now:
        return "현재 바깥에 비가 내리고 있습니다. 외출하실 때 우산을 꼭 챙기세요.", rain

    # 상황 2: 오늘 남은 시간 중 비 예보가 있는 경우
    if rain_hours:
        first_h = rain_hours[0]
        time_text = f"오후 {first_h - 12}시" if first_h >= 12 else f"오전 {first_h}시"
        return f"현재는 비가 오지 않지만, 오늘 {time_text}경부터 비 예보가 있습니다. 최고 강수확률은 {max_pop}퍼센트입니다. 우산을 챙기시기 바랍니다.", rain

    # 가상실험: 하루에 한 번만 정해지는 값이다. main.py가 600초마다 이 함수를 다시
    # 불러도 같은 날이면 결과가 바뀌지 않는다.
    if virtual_roll(now.date()) <= VIRTUAL_RAIN_THRESHOLD:
        return "가상실험에서 비가 오고 있습니다. 우산을 챙기시기 바랍니다.", True

    # 상황 3: 오늘 하루 동안 비 예보가 없는 경우
    return "", rain


# 단독 테스트용
if __name__ == "__main__":
    test_key = "38425da5bc3a0f1551dd6789eba56932b5f1570aaa1824d6debb596f77e980ea"
    print("생성된 문장:", write_text(test_key))
