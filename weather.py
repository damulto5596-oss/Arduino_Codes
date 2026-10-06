"""기상청 날씨누리 하루 날씨 조회.

사용법:
    python weather.py 상도동              # 지역의 오늘 날씨 (09시~24시, 3시간 간격)
    python weather.py 서울 동작구 상도1동
"""

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path
from threading import Lock
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

BASE = "https://www.weather.go.kr/w/"
ZONE_URL = BASE + "rest/zone/dong.do"
FORECAST_URL = BASE + "wnuri-fct2021/main/digital-forecast.do"
HEADERS = {"User-Agent": "Mozilla/5.0"}
TIMEOUT = 10

KST = ZoneInfo("Asia/Seoul")
ZONE_CACHE = Path(__file__).resolve().parent / "weather_zones.json"

# 출력할 시간대 (동네예보는 3시간 간격, 24:00은 그날 자정)
SHOW_TIMES = ["09:00", "12:00", "15:00", "18:00", "21:00", "24:00"]

MAX_MATCHES = 25  # 디스코드 자동완성 최대 개수

_zones = None
_zones_lock = Lock()


# ---------------------------------------------------------------- 지역 검색

def _get_zones(**params) -> list[dict]:
    resp = requests.get(ZONE_URL, params=params, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def _crawl_zones() -> list[dict]:
    """시/도 → 시/군/구 → 읍/면/동 전체를 받아 [{code, name, key}] 목록으로 만든다."""

    def short(zone):
        return zone.get("shortName") or zone["name"]

    def coords(zone):
        return {"lat": zone.get("lat"), "lon": zone.get("lon")}

    wides = _get_zones(type="WIDE")

    def cities_of(wide):
        return wide, _get_zones(type="CITY", wideCode=wide["code"])

    def dongs_of(args):
        wide, city = args
        return wide, city, _get_zones(type="DONG", wideCode=wide["code"], cityCode=city["code"])

    with ThreadPoolExecutor(max_workers=8) as pool:
        city_pairs = [
            (wide, city)
            for wide, cities in pool.map(cities_of, wides)
            for city in cities
        ]
        dong_rows = list(pool.map(dongs_of, city_pairs))

    entries = []
    for wide in wides:
        entries.append({"code": wide["code"], "name": wide["name"], "key": short(wide), **coords(wide)})
    for wide, city, dongs in dong_rows:
        # 세종특별자치시처럼 시/도와 시/군/구 이름이 같으면 한 번만 쓴다
        city_name = "" if city["name"] == wide["name"] else city["name"]
        if city_name:
            entries.append({
                "code": city["code"],
                "name": f"{wide['name']} {city_name}",
                "key": f"{short(wide)}{city_name}",
                **coords(city),
            })
        for dong in dongs:
            entries.append({
                "code": dong["code"],
                "name": " ".join(filter(None, [wide["name"], city_name, dong["name"]])),
                "key": f"{short(wide)}{city_name}{dong['name']}",
                **coords(dong),
            })
    return entries


def load_zones() -> list[dict]:
    """지역 목록을 반환한다. 처음에는 기상청에서 받아 파일에 저장해 두고 이후엔 파일을 쓴다."""
    global _zones
    with _zones_lock:
        if _zones is not None:
            return _zones
        if ZONE_CACHE.exists():
            try:
                cached = json.loads(ZONE_CACHE.read_text(encoding="utf-8"))
                if cached and "lat" in cached[0]:  # 좌표 없는 예전 캐시는 다시 받는다
                    _zones = cached
                    return _zones
            except (OSError, ValueError):
                pass  # 깨진 캐시는 무시하고 다시 받는다
        _zones = _crawl_zones()
        ZONE_CACHE.write_text(json.dumps(_zones, ensure_ascii=False), encoding="utf-8")
        return _zones


def zones_loaded() -> bool:
    return _zones is not None


def _norm(text: str) -> str:
    """공백을 없애고 '상도제1동'을 '상도1동'처럼 맞춰 비교하기 쉽게 한다."""
    return re.sub(r"제(?=\d)", "", re.sub(r"\s+", "", text))


def search_zones(query: str, limit: int = MAX_MATCHES) -> list[dict]:
    """
    입력과 맞는 지역을 정확도 순으로 찾는다.
    '상도동', '동작구 상도1동', '서울 동작구' 처럼 일부만 입력해도 된다.
    """
    q = _norm(query)
    if not q:
        return []
    loose = re.sub(r"\d", "", q)

    scored = []
    for zone in load_zones():
        name = _norm(zone["name"])
        key = _norm(zone["key"])
        if q in (name, key):
            score = 0
        elif name.endswith(q) or key.endswith(q):
            score = 1
        elif q in name or q in key:
            score = 2
        elif loose and re.sub(r"\d", "", key).endswith(loose):
            score = 3  # 이름의 숫자를 지운 형태로 비교 ('상도동' ↔ '상도1동')
        else:
            continue
        # 같은 점수면 상위 지역(짧은 이름)이 먼저
        scored.append((score, len(name), zone))

    scored.sort(key=lambda item: item[:2])
    return [zone for _, _, zone in scored[:limit]]


def find_zone(query: str) -> dict | None:
    """자동완성에서 고른 전체 이름이나 일부 이름으로 지역 하나를 찾는다."""
    matches = search_zones(query, 1)
    return matches[0] if matches else None


def zone_name(code: str) -> str | None:
    for zone in load_zones():
        if zone["code"] == code:
            return zone["name"]
    return None


# ---------------------------------------------------------------- 날씨 조회

def fetch_forecast_html(code: str) -> str:
    resp = requests.get(FORECAST_URL, params={"code": code}, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.text


def _clean_sky(title: str) -> str:
    return re.sub(r"^(오전|오후)?\s*날씨\s*", "", title).strip() or title


def _number(text: str) -> int | None:
    m = re.search(r"-?\d+", text or "")
    return int(m.group()) if m else None


def parse_day(html: str, target: date) -> list[dict]:
    """target 날짜의 SHOW_TIMES 예보를 [{time, sky, temp, feel}] 로 반환한다."""
    soup = BeautifulSoup(html, "html.parser")
    iso = target.isoformat()
    rows = []
    for item in soup.select("ul.item.s-item"):
        if item.get("data-date") != iso or item.get("data-time") not in SHOW_TIMES:
            continue
        cells = [li.get_text(" ", strip=True) for li in item.find_all("li", recursive=False)]
        wic = item.select_one(".wic")
        rows.append({
            "time": item["data-time"],
            "sky": _clean_sky(wic.get("title", "")) if wic else "정보 없음",
            "temp": _number(cells[2]) if len(cells) > 2 else None,
            "feel": _number(cells[3]) if len(cells) > 3 else None,
        })
    return rows


# WMO 날씨 코드 → 기상청식 표현 (지난 시간대 보충용)
def _wmo_sky(code: int) -> str:
    if code == 0:
        return "맑음"
    if code in (1, 2):
        return "구름많음"
    if code == 3:
        return "흐림"
    if code in (45, 48):
        return "안개"
    if code in (71, 73, 75, 77, 85, 86):
        return "눈"
    if code in (80, 81, 82):
        return "소나기"
    if code >= 95:
        return "뇌우"
    return "비"


def _slot_datetime(target: date, time: str) -> str:
    """'09:00' → '2026-10-06T09:00', '24:00' → 다음 날 '00:00'"""
    hour = int(time[:2])
    day = target + timedelta(days=1) if hour == 24 else target
    return f"{day.isoformat()}T{hour % 24:02d}:00"


def fetch_past_rows(zone: dict, target: date, times: list[str]) -> list[dict]:
    """기상청 페이지엔 이미 지난 시간대가 없어서 Open-Meteo 관측/분석값으로 채운다. 실패하면 빈 리스트."""
    try:
        resp = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": zone["lat"], "longitude": zone["lon"],
                "hourly": "temperature_2m,apparent_temperature,weather_code",
                "timezone": "Asia/Seoul",
                "start_date": target.isoformat(),
                "end_date": (target + timedelta(days=1)).isoformat(),
            },
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        hourly = resp.json()["hourly"]
        index = {t: i for i, t in enumerate(hourly["time"])}
        rows = []
        for time in times:
            i = index.get(_slot_datetime(target, time))
            if i is None:
                continue
            temp, feel, code = (
                hourly["temperature_2m"][i],
                hourly["apparent_temperature"][i],
                hourly["weather_code"][i],
            )
            if temp is None or code is None:
                continue
            rows.append({
                "time": time,
                "sky": _wmo_sky(int(code)),
                "temp": round(temp),
                "feel": None if feel is None else round(feel),
            })
        return rows
    except (requests.RequestException, KeyError, ValueError, TypeError):
        return []


def get_day_weather(code: str, target: date) -> list[dict]:
    """code 지역의 target 날짜 날씨. 예보가 없으면 빈 리스트."""
    rows = parse_day(fetch_forecast_html(code), target)
    if not rows:
        return rows

    have = {row["time"] for row in rows}
    missing = [t for t in SHOW_TIMES if t not in have]
    zone = next((z for z in load_zones() if z["code"] == code), None)
    if missing and zone and zone.get("lat"):
        rows += fetch_past_rows(zone, target, missing)
        rows.sort(key=lambda row: SHOW_TIMES.index(row["time"]))
    return rows


# ---------------------------------------------------------------- 출력 문자열

def hour_label(time: str) -> str:
    return f"{time[:2]}시"


def sky_emoji(sky: str) -> str:
    for word, emoji in (
        ("뇌우", "⛈️"), ("안개", "🌫️"),
        ("눈", "❄️"), ("소나기", "🌦️"), ("비", "🌧️"),
        ("흐", "☁️"), ("구름", "⛅"), ("맑", "☀️"),
    ):
        if word in sky:
            return emoji
    return "🌡️"


def format_flow(rows: list[dict]) -> str:
    """연속된 같은 날씨를 묶어서 '☀️ 맑음 (09시~15시) → 🌧️ 비 (18시~)' 로 만든다."""
    groups = []
    for row in rows:
        if groups and groups[-1]["sky"] == row["sky"]:
            groups[-1]["end"] = row["time"]
        else:
            groups.append({"sky": row["sky"], "start": row["time"], "end": row["time"]})

    parts = []
    for g in groups:
        span = hour_label(g["start"])
        if g["end"] != g["start"]:
            span += f"~{hour_label(g['end'])}"
        parts.append(f"{sky_emoji(g['sky'])} {g['sky']} ({span})")
    return " → ".join(parts)


def format_series(rows: list[dict], field: str) -> str:
    """'09시 16℃ → 12시 21℃ → ...' 형태의 시간대별 변화."""
    return " → ".join(
        f"{hour_label(row['time'])} "
        f"{'-' if row[field] is None else str(row[field]) + '℃'}"
        for row in rows
    )


def clock_label(time: str) -> str:
    """'09:00' → '🕘 오전 9시', '24:00' → '🌙 밤 12시'"""
    hour = int(time[:2])
    if hour == 24:
        return "🌙 밤 12시"
    if hour == 12:
        return "🕛 낮 12시"
    if hour < 12:
        return f"🌅 오전 {hour}시"
    return f"{'🌇' if hour < 19 else '🌃'} 오후 {hour - 12}시"


def format_graph(rows: list[dict], field: str = "temp", width: int = 14) -> str:
    """시간대별 값을 가는 선 막대그래프로 만든다. 디스코드 코드블록(고정폭)에 넣어 쓴다.

    09시 ━━━━●           16℃
    12시 ━━━━━━━━━━━●    21℃
    """
    values = [row[field] for row in rows if row[field] is not None]
    if not values:
        return "정보 없음"
    low, high = min(values), max(values)

    lines = []
    for row in rows:
        value = row[field]
        label = hour_label(row["time"])
        if value is None:
            lines.append(f"{label} {'':<{width}}    -")
            continue
        # 가장 낮은 값도 막대가 보이도록 최소 3칸
        ratio = 0.5 if high == low else (value - low) / (high - low)
        length = 3 + round(ratio * (width - 3))
        bar = "━" * (length - 1) + "●"
        lines.append(f"{label} {bar:<{width}} {value:>3}℃")
    return "\n".join(lines)


def format_weather(name: str, target: date, rows: list[dict]) -> str:
    weekday = "월화수목금토일"[target.weekday()]
    return "\n".join([
        f"[{name} {target:%m/%d} ({weekday}) 날씨]",
        f"날씨: {format_flow(rows)}",
        f"기온: {format_series(rows, 'temp')}",
        f"체감: {format_series(rows, 'feel')}",
    ])


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("사용법: python weather.py 지역이름")

    zone = find_zone(" ".join(sys.argv[1:]))
    if zone is None:
        sys.exit("지역을 찾지 못했습니다.")

    today = datetime.now(KST).date()
    rows = get_day_weather(zone["code"], today)
    if not rows:
        sys.exit("오늘 예보가 없습니다.")
    print(format_weather(zone["name"], today, rows))


if __name__ == "__main__":
    main()
