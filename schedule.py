import re
import sqlite3
from datetime import date, datetime, time

from main import db

TITLE_MAX = 200


def init_schedule_db():
    """일정 전용 테이블 (공모전/설정 테이블과 별개)"""

    with db() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            event_date TEXT NOT NULL,   -- YYYY-MM-DD (한국 시간)
            event_time TEXT NOT NULL,   -- HH:MM
            notified INTEGER NOT NULL DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)


def parse_date(text, today):
    """
    '2026-10-20', '2026.10.20', '2026/10/20', '10-20'(올해, 지났으면 내년) 형식을 읽는다.
    형식이 틀리면 ValueError
    """

    text = text.strip()
    match = re.fullmatch(r"(?:(\d{4})[-./])?(\d{1,2})[-./](\d{1,2})", text)
    if not match:
        raise ValueError("날짜 형식 오류")

    year, month, day = match.groups()
    if year:
        return date(int(year), int(month), int(day))

    result = date(today.year, int(month), int(day))
    if result < today:
        result = date(today.year + 1, int(month), int(day))
    return result


def parse_time(text):
    """'14:30', '9:05', '1430' 형식을 읽는다. 형식이 틀리면 ValueError"""

    text = text.strip()
    match = re.fullmatch(r"(\d{1,2}):(\d{2})|(\d{2})(\d{2})", text)
    if not match:
        raise ValueError("시간 형식 오류")

    hour, minute = (match.group(1), match.group(2)) if match.group(1) else (match.group(3), match.group(4))
    return time(int(hour), int(minute))


def add_schedule(user_id, channel_id, title, event_date, event_time):
    with db() as conn:
        conn.execute(
            """
            INSERT INTO schedules (user_id, channel_id, title, event_date, event_time)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, channel_id, title[:TITLE_MAX],
             event_date.isoformat(), event_time.strftime("%H:%M"))
        )


def purge_past(today):
    """날짜가 지난 일정을 삭제한다."""

    with db() as conn:
        conn.execute("DELETE FROM schedules WHERE event_date < ?", (today.isoformat(),))


def load_upcoming(user_id, now):
    """user_id가 입력한 일정 중 지금 이후의 것을 시간순으로 가져온다. (now: 한국 시간 datetime)"""

    with db() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, channel_id, title, event_date, event_time
            FROM schedules
            WHERE user_id = ? AND (event_date || ' ' || event_time) >= ?
            ORDER BY event_date, event_time, id
            """,
            (user_id, now.strftime("%Y-%m-%d %H:%M"))
        ).fetchall()

    return [dict(row) for row in rows]


def get_schedule(user_id, schedule_id):
    """user_id 본인의 일정 하나. 없거나 남의 것이면 None"""

    with db() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT id, user_id, channel_id, title, event_date, event_time
            FROM schedules
            WHERE id = ? AND user_id = ?
            """,
            (schedule_id, user_id)
        ).fetchone()

    return dict(row) if row else None


def update_schedule(user_id, schedule_id, title, event_date, event_time, channel_id):
    """일정을 수정한다. 날짜가 바뀌면 새 날짜에 다시 알리도록 알림 여부를 초기화. 수정됐으면 True"""

    with db() as conn:
        cursor = conn.execute(
            """
            UPDATE schedules
            SET title = ?,
                notified = CASE WHEN event_date != ? THEN 0 ELSE notified END,
                event_date = ?,
                event_time = ?,
                channel_id = ?
            WHERE id = ? AND user_id = ?
            """,
            (title[:TITLE_MAX], event_date.isoformat(), event_date.isoformat(),
             event_time.strftime("%H:%M"), channel_id, schedule_id, user_id)
        )
        return cursor.rowcount > 0


def delete_schedule(user_id, schedule_id):
    """본인의 일정을 삭제한다. 삭제됐으면 True"""

    with db() as conn:
        cursor = conn.execute(
            "DELETE FROM schedules WHERE id = ? AND user_id = ?", (schedule_id, user_id)
        )
        return cursor.rowcount > 0


def load_due(today):
    """오늘 알림을 보내야 하는데 아직 안 보낸 일정"""

    with db() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, user_id, channel_id, title, event_date, event_time
            FROM schedules
            WHERE event_date = ? AND notified = 0
            ORDER BY event_time, id
            """,
            (today.isoformat(),)
        ).fetchall()

    return [dict(row) for row in rows]


def mark_notified(schedule_id):
    with db() as conn:
        conn.execute("UPDATE schedules SET notified = 1 WHERE id = ?", (schedule_id,))
