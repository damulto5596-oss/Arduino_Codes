import datetime
import json
import unittest
from unittest.mock import MagicMock, patch

import tts_output


class WriteTextTests(unittest.TestCase):
    def setUp(self):
        response = patch(
            "tts_output.urllib.request.urlopen",
            return_value=_weather_response(),
        )
        self.urlopen = response.start()
        self.addCleanup(response.stop)

    @patch("tts_output.virtual_roll", return_value=7)
    def test_virtual_rain_sets_rain_flag(self, _roll):
        text, rain = tts_output.write_text("test-key")

        self.assertIn("가상실험에서 비가 오고 있습니다", text)
        self.assertTrue(rain)

    @patch("tts_output.virtual_roll", return_value=8)
    def test_virtual_no_rain_keeps_rain_flag_false(self, _roll):
        text, rain = tts_output.write_text("test-key")

        self.assertEqual(text, "")
        self.assertFalse(rain)

    def test_same_day_gives_same_text(self):
        """하루 안에서는 몇 번 불러도 결과가 바뀌지 않는다 (main.py가 600초마다 호출한다)."""
        results = {tts_output.write_text("test-key") for _ in range(20)}

        self.assertEqual(len(results), 1)


class VirtualRollTests(unittest.TestCase):
    """가상 주사위는 디스코드 봇(discord 브랜치 virtual_weather.py)과 **같은 값**이어야 한다.

    두 기기는 서로 통신하지 않고 이 함수만으로 같은 "오늘의 가상 날씨"에 도달한다.
    아래 고정값이 깨지면 봇 쪽 virtual_weather.py도 같이 깨진 것이므로 양쪽을 맞춰야 한다.
    봇 쪽 확인: discord 폴더에서 `python virtual_weather.py 2026-11-14`
    """

    # 날짜 → 주사위 눈 (양쪽이 반드시 같아야 하는 약속)
    GOLDEN = {
        "2026-01-01": 8,
        "2026-06-15": 7,
        "2026-11-14": 7,
        "2026-11-15": 7,
        "2026-12-25": 10,
    }

    def test_matches_golden_values(self):
        for day_text, expected in self.GOLDEN.items():
            with self.subTest(day=day_text):
                day = datetime.date.fromisoformat(day_text)
                self.assertEqual(tts_output.virtual_roll(day), expected)

    def test_is_deterministic(self):
        day = datetime.date(2026, 11, 14)
        self.assertEqual(
            {tts_output.virtual_roll(day) for _ in range(50)},
            {tts_output.virtual_roll(day)},
        )

    def test_stays_in_dice_range(self):
        start = datetime.date(2026, 1, 1)
        rolls = [tts_output.virtual_roll(start + datetime.timedelta(days=i)) for i in range(365)]

        self.assertTrue(all(1 <= roll <= tts_output.VIRTUAL_RAIN_DICE for roll in rolls))

    def test_rain_rate_is_about_70_percent(self):
        start = datetime.date(1990, 1, 1)
        rolls = [tts_output.virtual_roll(start + datetime.timedelta(days=i)) for i in range(10000)]
        rate = sum(1 for roll in rolls if roll <= tts_output.VIRTUAL_RAIN_THRESHOLD) / len(rolls)

        self.assertAlmostEqual(rate, 0.70, delta=0.02)


def _weather_response():
    response = MagicMock()
    response.__enter__.return_value.read.return_value = json.dumps(
        {"response": {"body": {"items": {"item": []}}}}
    ).encode("utf-8")
    return response


if __name__ == "__main__":
    unittest.main()
