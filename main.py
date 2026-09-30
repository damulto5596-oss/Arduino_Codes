import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import requests
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

# bot.py보다 먼저 불러와질 수 있으므로 DB_PATH를 읽기 전에 .env를 읽는다
load_dotenv(BASE_DIR / ".env")

DB_PATH = Path(os.getenv("DB_PATH", BASE_DIR / "contest.db"))

FEED_URL = "https://api.allforyoung.com/api/v2/feed/"
POST_URL = "https://api.allforyoung.com/api/v2/posts/{}/"

REQUEST_TIMEOUT = 10  # 초
FETCH_COUNT = 20      # /공모전 때 가져올 최신 공모전 수
MAX_STORED = 35       # DB에 보관할 최대 공모전 수


@contextmanager
def db():
    """성공하면 커밋, 어떤 경우든 연결을 닫는다."""
    conn = sqlite3.connect(DB_PATH)
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init_db():
    with db() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS contests (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            dday TEXT,
            organization TEXT,
            poster_url TEXT,
            thumbnail_url TEXT,
            detected_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # 예전 버전에서 만든 DB에는 없는 컬럼 추가
        columns = {row[1] for row in conn.execute("PRAGMA table_info(contests)")}
        for column in ("organization", "poster_url", "thumbnail_url"):
            if column not in columns:
                conn.execute(f"ALTER TABLE contests ADD COLUMN {column} TEXT")

        # 자동 알림 채널 등 봇 설정 저장용
        conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """)


def get_setting(key):
    with db() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def set_setting(key, value):
    with db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, str(value))
        )


def fetch_period(contest_id):
    """
    상세 API에서 접수 기간(start_date ~ end_at)을 가져온다.
    실패하면 None
    """

    try:
        res = requests.get(POST_URL.format(contest_id), timeout=REQUEST_TIMEOUT)
        if res.status_code != 200:
            return None

        detail = res.json().get("data", {})
        start_date = detail.get("start_date")
        end_at = detail.get("end_at")

        if start_date and end_at:
            return f"{start_date} ~ {end_at}"
        if end_at:
            return f"~ {end_at}"
    except Exception:
        pass

    return None


def fetch_contests():
    """
    AllForYoung에서 최신 공모전 FETCH_COUNT개를 가져오고
    새로운 공모전은 SQLite에 저장, 기존 공모전은 정보를 갱신한다.

    반환값:
        (최신 공모전 목록, 새로운 공모전 목록)
    """

    params = {
        "category": "공모전",
        "tags": 28,
        "order": "latest",
        "page": 1,
        "per_page": 24
    }

    response = requests.get(FEED_URL, params=params, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()

    posts = [item["data"] for item in response.json()["data"] if item["type"] == "post"]
    latest_contests = posts[:FETCH_COUNT]
    new_contests = []

    with db() as conn:
        saved = dict(conn.execute("SELECT id, dday FROM contests"))

        for contest in latest_contests:
            contest_id = contest["id"]
            fields = (
                contest.get("organization"),
                contest.get("poster_url"),
                contest.get("thumbnail_url")
            )

            if contest_id in saved:
                # 이미 저장된 공모전: 저장해 둔 접수 기간을 사용하고
                # (예전 버전에서 기간 없이 저장됐다면 이번에 채워 넣고)
                # 주최/포스터 정보만 최신 값으로 갱신
                period = saved[contest_id] or fetch_period(contest_id)

                if period:
                    contest["dday"] = period

                conn.execute(
                    """
                    UPDATE contests
                    SET dday = ?, organization = ?, poster_url = ?, thumbnail_url = ?
                    WHERE id = ?
                    """,
                    (period, *fields, contest_id)
                )
                continue

            # 상세 조회 실패 시 기존 feed의 dday (D-xx) 사용
            contest["dday"] = fetch_period(contest_id) or contest.get("dday", "정보 없음")

            conn.execute(
                """
                INSERT INTO contests (id, title, dday, organization, poster_url, thumbnail_url)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (contest_id, contest["title"], contest["dday"], *fields)
            )
            new_contests.append(contest)

        # 보관 개수를 넘으면 오래된 것부터 삭제
        conn.execute(
            """
            DELETE FROM contests
            WHERE id IN (
                SELECT id
                FROM contests
                ORDER BY detected_at ASC
                LIMIT MAX(0, (SELECT COUNT(*) FROM contests) - ?)
            )
            """,
            (MAX_STORED,)
        )

    return latest_contests, new_contests


def load_all_contests():
    """
    DB에 저장된 공모전을 최신순으로 모두 가져온다.
    """

    with db() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
        SELECT id, title, dday, organization, poster_url, thumbnail_url
        FROM contests
        ORDER BY detected_at DESC, id DESC
        """).fetchall()

    return [dict(row) for row in rows]
