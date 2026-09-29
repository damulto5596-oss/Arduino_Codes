import requests
import sqlite3


# ========================================
# 1. DB 연결
# ========================================

conn = sqlite3.connect("contest.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS contests (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    dday TEXT,
    detected_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")

conn.commit()


# ========================================
# 2. 올포영 API에서 공모전 가져오기
# ========================================

url = "https://api.allforyoung.com/api/v2/feed/"

params = {
    "category": "공모전",
    "tags": 28,          # IT/AI/데이터
    "order": "latest",
    "page": 1,
    "per_page": 24
}

response = requests.get(url, params=params)

print("상태 코드:", response.status_code)

data = response.json()


# ========================================
# 3. IT/AI/데이터 공모전만 추출
# ========================================

contests = []

for item in data["data"]:

    # 광고 제외
    if item["type"] != "post":
        continue

    contest = item["data"]

    contests.append(contest)


print(f"\nIT/AI/데이터 공모전: {len(contests)}개\n")


# ========================================
# 4. DB와 비교
# ========================================

for contest in contests:

    contest_id = contest["id"]
    title = contest["title"]

    # DB에 이미 있는지 확인
    cursor.execute(
        "SELECT id FROM contests WHERE id = ?",
        (contest_id,)
    )

    result = cursor.fetchone()

    if result:

        # 이미 본 공모전
        print("기존 공모전:", title)

    else:

        # 처음 발견한 공모전
        print("새로운 공모전:", title)

        cursor.execute(
            """
            INSERT INTO contests (id, title)
            VALUES (?, ?)
            """,
            (contest_id, title)
        )


# ========================================
# 5. 변경사항 저장
# ========================================

conn.commit()
conn.close()