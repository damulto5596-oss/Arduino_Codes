previous_door_open = None


def check_alert(door_open, umbrella_present, rain, text):
    """문이 닫힘→열림으로 바뀌는 순간 + 비 예보 + 우산 보유 여부로 최종 알림 여부를 판단한다.
    스피커 출력은 이 함수 밖(추후 단계)에서 연결한다."""
    global previous_door_open

    current_door_open = bool(door_open)

    # 첫 호출에서는 현재 문 상태만 저장
    if previous_door_open is None:
        previous_door_open = current_door_open
        return False

    # 닫힘 → 열림 전환 확인
    just_opened = (
        previous_door_open is False
        and current_door_open is True
    )

    previous_door_open = current_door_open

    if not just_opened:
        return False

    if rain != 1 or umbrella_present != 1:
        return False

    text = text.strip()

    if not text:
        return False

    print(f"[최종 판단] 우산을 챙기세요: {text}")
    return True
