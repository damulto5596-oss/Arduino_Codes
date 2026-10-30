"""숭실대 기숙사 식단 조회.

사용법:
    python dorm_menu.py              # 오늘 식단
    python dorm_menu.py 2026-10-03   # 특정 날짜 식단
"""

import logging
import re
import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

URL = "https://ssudorm.ssu.ac.kr:444/SShostel/mall_main.php"
KST = ZoneInfo("Asia/Seoul")
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"}
log = logging.getLogger(__name__)
NONE_TEXT = "없음"
# 셀에 이 값만 있으면 식단이 없는 것으로 간주
EMPTY_MARKERS = {"", "미운영", "-"}

# 표 열 순서: 날짜 | 조식 | 중식 | 석식 | 중.석식
LUNCH_COL = 1
DINNER_COL = 2


def fetch_week_html(target: date) -> str:
    """target 날짜가 포함된 주의 식단 페이지 HTML을 가져온다."""
    params = {
        "viewform": "B0001_foodboard_list",
        "board_no": "1",
        "gyear": f"{target.year}",
        "gmonth": f"{target.month:02d}",
        "gday": f"{target.day:02d}",
    }
    resp = requests.get(URL, params=params, headers=HEADERS, timeout=10)
    resp.raise_for_status()
    return resp.content.decode("cp949", errors="replace")


def _cell_items(td) -> list[str]:
    lines = [line.strip() for line in td.get_text("\n").splitlines()]
    items = [line for line in lines if line]
    if not items or (len(items) == 1 and items[0] in EMPTY_MARKERS):
        return []
    return items


def parse_week(html: str) -> dict[date, dict[str, list[str]]]:
    """{날짜: {"점심": [...], "저녁": [...]}} 형태로 파싱한다."""
    soup = BeautifulSoup(html, "html.parser")
    week: dict[date, dict[str, list[str]]] = {}
    for tr in soup.select("table.boxstyle02 tbody tr"):
        th = tr.find("th")
        tds = tr.find_all("td")
        if th is None or len(tds) <= DINNER_COL:
            continue
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", th.get_text())
        if not m:
            continue
        day = date(*map(int, m.groups()))
        week[day] = {
            "점심": _cell_items(tds[LUNCH_COL]),
            "저녁": _cell_items(tds[DINNER_COL]),
        }
    return week


def get_week_menu(target: date) -> dict[date, dict[str, list[str]]]:
    """target 날짜가 포함된 주(월~일)의 식단."""
    html = fetch_week_html(target)
    week = parse_week(html)
    if not week:
        # 서버에서만 빈 결과가 나오는 경우(차단 페이지, 레이아웃 변경 등)를 추적하기 위한 로그
        snippet = re.sub(r"\s+", " ", html[:300])
        log.warning(f"식단 파싱 결과가 비어 있습니다 (HTML {len(html)}자, boxstyle02={'boxstyle02' in html}): {snippet}")
    return week


def get_menu(target: date) -> dict[str, list[str]]:
    """target 날짜의 점심/저녁 식단. 식단이 없으면 빈 리스트."""
    return get_week_menu(target).get(target, {"점심": [], "저녁": []})


def format_menu(target: date, menu: dict[str, list[str]]) -> str:
    weekday = "월화수목금토일"[target.weekday()]
    lines = [f"[{target.isoformat()} ({weekday}) 기숙사 식단]"]
    for meal in ("점심", "저녁"):
        items = menu.get(meal) or []
        lines.append(f"\n■ {meal}")
        lines.append("\n".join(f"- {item}" for item in items) if items else NONE_TEXT)
    return "\n".join(lines)


def main() -> None:
    if len(sys.argv) > 1:
        target = datetime.strptime(sys.argv[1], "%Y-%m-%d").date()
    else:
        target = datetime.now(KST).date()
    print(format_menu(target, get_menu(target)))


if __name__ == "__main__":
    main()
