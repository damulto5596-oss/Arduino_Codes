#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
update_location.py
- 사용자로부터 지역 이름을 입력받아 위도/경도 및 기상청 격자좌표(nx, ny)로 변환
- config.json의 location 설정 업데이트
- 유효하지 않은 입력이나 너무 넓은 범위의 지역 입력 시 안내 메시지 출력
"""

import json
import math
import os
import re
import sys
import urllib.parse
import urllib.request

# 광역 행정구역 및 전국 단위의 대표 키워드 (범위가 너무 넓은 지역 필터링)
BROAD_REGION_NAMES = {
    "대한민국", "한국", "전국", "남한", "한반도",
    "경기도", "강원도", "강원특별자치도",
    "충청도", "충청남도", "충청북도", "충남", "충북",
    "전라도", "전라남도", "전라북도", "전북특별자치도", "전남", "전북",
    "경상도", "경상남도", "경상북도", "경남", "경북",
    "제주도", "제주특별자치도"
}

# 섬 이름 등 도 단위와 혼동될 수 있는 단어 예외 처리
ISLAND_EXCEPTIONS = {"여의도", "독도", "백령도", "영종도", "완도", "진도", "거제도", "강화도", "울릉도"}


def latlon_to_grid(lat: float, lon: float):
    """
    기상청 단기예보 공식 LCC(Lambert Conformal Conic) 투영법 좌표 변환
    위도/경도 -> 기상청 격자 좌표 (nx, ny)
    """
    RE = 6371.00877     # 지구 반경(km)
    GRID = 5.0          # 격자 간격(km)
    SLAT1 = 30.0        # 투영 위도1(degree)
    SLAT2 = 60.0        # 투영 위도2(degree)
    OLON = 126.0        # 기준점 경도(degree)
    OLAT = 38.0         # 기준점 위도(degree)
    XO = 43             # 기준점 X좌표(GRID)
    YO = 136            # 기준점 Y좌표(GRID)

    DEGRAD = math.pi / 180.0
    re = RE / GRID
    slat1 = SLAT1 * DEGRAD
    slat2 = SLAT2 * DEGRAD
    olon = OLON * DEGRAD
    olat = OLAT * DEGRAD

    sn = math.tan(math.pi * 0.25 + slat2 * 0.5) / math.tan(math.pi * 0.25 + slat1 * 0.5)
    sn = math.log(math.cos(slat1) / math.cos(slat2)) / math.log(sn)
    sf = math.tan(math.pi * 0.25 + slat1 * 0.5)
    sf = (sf ** sn * math.cos(slat1)) / sn
    ro = math.tan(math.pi * 0.25 + olat * 0.5)
    ro = (re * sf) / (ro ** sn)

    ra = math.tan(math.pi * 0.25 + lat * DEGRAD * 0.5)
    ra = (re * sf) / (ra ** sn)
    theta = lon * DEGRAD - olon
    if theta > math.pi:
        theta -= 2.0 * math.pi
    if theta < -math.pi:
        theta += 2.0 * math.pi
    theta *= sn

    x = ra * math.sin(theta) + XO + 0.5
    y = ro - ra * math.cos(theta) + YO + 0.5

    return int(x), int(y)


def format_location_name(result: dict, query: str) -> str:
    """검색 결과에서 자연스러운 한국어 행정구역 명칭 조합"""
    addr = result.get("address", {})
    parts = []

    province = addr.get("province")
    city = addr.get("city")
    if province:
        parts.append(province)
    if city and city != province:
        parts.append(city)

    dist = addr.get("borough") or addr.get("city_district") or addr.get("county")
    if dist and dist not in parts:
        parts.append(dist)

    sub = addr.get("quarter") or addr.get("town") or addr.get("village") or addr.get("suburb")
    if sub and sub not in parts:
        parts.append(sub)

    name = result.get("name")
    if name and name not in parts:
        parts.append(f"({name})")

    return " ".join(parts) if parts else result.get("display_name", query)


def search_and_convert_location(query: str):
    """
    지역 이름을 입력받아 유효성을 검사하고 좌표 및 격자로 변환
    :return: (성공 여부: bool, 결과 딕셔너리 또는 오류 메시지: dict | str)
    """
    q = query.strip()
    if not q:
        return False, "[입력 오류] 지역 이름이 비어 있습니다. 지명을 입력해 주세요."

    # 숫자나 특수문자만 입력된 비정상적인 값 처리
    if re.fullmatch(r'[\d\s\W]+', q):
        return False, f"[입력 오류] '{q}'은(는) 올바른 지명 형식이 아닙니다. 숫자나 특수문자만으로는 검색할 수 없습니다."

    # 대표적인 광역/도 단위 범위 검사
    cleaned = q.replace(" ", "")
    if cleaned in BROAD_REGION_NAMES or (cleaned.endswith("도") and len(cleaned) <= 5 and cleaned not in ISLAND_EXCEPTIONS):
        return False, (
            f"[범위 초과] 입력하신 '{q}'은(는) 범위가 너무 넓습니다.\n"
            f"            기상청 동네예보는 5km 격자 단위이므로,\n"
            f"            구체적인 시·군·구 또는 읍·면·동 단위(예: '수원시 영통구', '성남시 분당구', '제주시 애월읍')로 입력해 주세요."
        )

    # OpenStreetMap Nominatim 지오코딩 API 호출
    url = f"https://nominatim.openstreetmap.org/search?q={urllib.parse.quote(q)}&format=json&countrycodes=kr&addressdetails=1"
    req = urllib.request.Request(url, headers={"User-Agent": "WeatherAppLocationUpdater/1.0 (Python)"})

    try:
        with urllib.request.urlopen(req, timeout=6) as res:
            data = json.loads(res.read().decode("utf-8"))
    except Exception as e:
        return False, f"[서버 오류] 위치 검색 중 네트워크 연결에 실패했습니다: {e}"

    if not data:
        return False, f"[검색 실패] '{q}'에 해당하는 위치를 찾을 수 없습니다. 오타나 올바른 지명인지 확인해 주세요."

    top = data[0]
    addr = top.get("address", {})
    addr_type = top.get("addresstype", "")
    place_rank = top.get("place_rank", 30)

    # 대한민국 영역 확인
    if addr.get("country_code") != "kr":
        return False, f"[범위 초과] 기상청 단기예보는 대한민국 내 지역만 지원합니다. ('{q}'은(는) 해외 지역입니다.)"

    # 광역/국가 행정단위 여부 확인 (place_rank <= 8 또는 country, state, province)
    if place_rank <= 8 or addr_type in ["country", "state", "province", "region"]:
        return False, (
            f"[범위 초과] 입력하신 '{q}'({top.get('name', '')})은(는) 광역 단위로 범위가 너무 넓습니다.\n"
            f"            구체적인 시·군·구 또는 읍·면·동 단위로 입력해 주세요."
        )

    try:
        lat = float(top["lat"])
        lon = float(top["lon"])
    except (KeyError, ValueError):
        return False, f"[오류] 좌표 정보를 올바르게 추출할 수 없습니다."

    # 기상청 단기예보 유효 격자 (nx: 1~149, ny: 1~253)
    nx, ny = latlon_to_grid(lat, lon)
    if not (1 <= nx <= 149 and 1 <= ny <= 253):
        return False, f"[범위 초과] 변환된 좌표(nx={nx}, ny={ny})가 기상청 단기예보 격자 유효 범위를 벗어납니다."

    formatted_name = format_location_name(top, q)

    return True, {
        "city_name": formatted_name,
        "use_lat_lon": True,
        "latitude": round(lat, 4),
        "longitude": round(lon, 4),
        "grid_nx": nx,
        "grid_ny": ny,
        "raw_query": q
    }


def update_config_file(location_info: dict, config_path: str = "config.json") -> bool:
    """config.json 파일의 location 항목을 업데이트"""
    config_data = {}

    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = json.load(f)
        except Exception as e:
            print(f"⚠️ 기존 설정 파일 읽기 실패 ({e}), 새 설정을 생성합니다.")

    # 기존 api_key 보존 또는 기본값 생성
    if "api_key" not in config_data:
        config_data["api_key"] = "YOUR_DATA_GO_KR_DECODING_API_KEY"

    # location 갱신
    config_data["location"] = {
        "city_name": location_info["city_name"],
        "use_lat_lon": location_info.get("use_lat_lon", True),
        "latitude": location_info["latitude"],
        "longitude": location_info["longitude"],
        "grid_nx": location_info["grid_nx"],
        "grid_ny": location_info["grid_ny"]
    }

    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"❌ 설정 파일 저장 실패: {e}")
        return False


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "config.json")

    print("=" * 60)
    print("         🌤️  날씨 예보 위치 설정 프로그램 (config 갱신)")
    print("=" * 60)

    # 명령줄 인수로 지역명이 전달된 경우 우선 처리
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        print(f"▶ 전달된 지역명: {query}")
        success, result = search_and_convert_location(query)
        if success:
            if update_config_file(result, config_path):
                print(f"\n✅ config.json 위치가 성공적으로 업데이트되었습니다!")
                print(f"   - 설정된 지역명 : {result['city_name']}")
                print(f"   - 위도 / 경도   : {result['latitude']}, {result['longitude']}")
                print(f"   - 기상청 격자   : nx={result['grid_nx']}, ny={result['grid_ny']}")
        else:
            print(f"\n{result}")
        return

    # 대화형 input() 모드
    print("설정하고자 하는 지역명이나 주소를 입력하세요.")
    print("예: '서울 강남구 역삼동', '수원시 팔달구', '제주시 애월읍', '해운대구'")
    print("종료하려면 'q' 또는 'exit'를 입력하세요.\n")

    while True:
        try:
            query = input(">> 지역 이름 입력: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n프로그램을 종료합니다.")
            break

        if not query:
            print("⚠️ 지명을 입력해 주세요.\n")
            continue

        if query.lower() in ["q", "exit", "quit", "종료"]:
            print("프로그램을 종료합니다.")
            break

        success, result = search_and_convert_location(query)

        if success:
            if update_config_file(result, config_path):
                print("-" * 60)
                print(f"✅ 위치 설정이 성공적으로 저장되었습니다!")
                print(f"   • 지역 명칭 : {result['city_name']}")
                print(f"   • 위도/경도 : {result['latitude']}°, {result['longitude']}°")
                print(f"   • 격자 좌표 : nx={result['grid_nx']}, ny={result['grid_ny']}")
                print(f"   • 갱신 파일 : {config_path}")
                print("-" * 60)
                break
        else:
            print("-" * 60)
            print(f"{result}")
            print("-" * 60 + "\n")


if __name__ == "__main__":
    main()
