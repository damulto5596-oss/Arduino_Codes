import datetime
import json
import unittest
from unittest.mock import MagicMock, patch

import tts_output


class WriteTextTests(unittest.TestCase):
    def _mock_api(self, items):
        response = patch(
            "tts_output.urllib.request.urlopen",
            return_value=_weather_response(items),
        )
        self.urlopen = response.start()
        self.addCleanup(response.stop)

    def setUp(self):
        self._mock_api([])

    # ── 모드 2: 실제 비 OR 가상 비 ────────────────────────────────────────────
    @patch("tts_output.FORCE_RAIN_FOR_TEST", 2)
    @patch("tts_output.virtual_roll", return_value=7)
    def test_virtual_rain_sets_rain_flag(self, _roll):
        text, rain = tts_output.write_text("test-key")

        self.assertEqual(text, tts_output.RAIN_EXPECTED_TEXT)
        self.assertTrue(rain)

    @patch("tts_output.FORCE_RAIN_FOR_TEST", 2)
    @patch("tts_output.virtual_roll", return_value=8)
    def test_virtual_no_rain_keeps_rain_flag_false(self, _roll):
        text, rain = tts_output.write_text("test-key")

        self.assertEqual(text, "")
        self.assertFalse(rain)

    @patch("tts_output.FORCE_RAIN_FOR_TEST", 2)
    @patch("tts_output.virtual_roll", return_value=8)
    def test_real_rain_alerts_even_when_virtual_misses(self, _roll):
        self._mock_api([_rain_now_item()])

        text, rain = tts_output.write_text("test-key")

        self.assertIn("현재 바깥에 비가 내리고 있습니다", text)
        self.assertTrue(rain)

    @patch("tts_output.FORCE_RAIN_FOR_TEST", 2)
    @patch("tts_output.virtual_roll", return_value=3)
    def test_virtual_rain_applies_when_api_fails(self, _roll):
        self.urlopen.side_effect = OSError("network down")

        text, rain = tts_output.write_text("test-key")

        self.assertEqual(text, tts_output.RAIN_EXPECTED_TEXT)
        self.assertTrue(rain)

    # ── 모드 0 / 1 ───────────────────────────────────────────────────────────
    @patch("tts_output.FORCE_RAIN_FOR_TEST", 0)
    @patch("tts_output.virtual_roll", return_value=1)
    def test_mode0_ignores_virtual_rain(self, _roll):
        text, rain = tts_output.write_text("test-key")

        self.assertEqual(text, "")
        self.assertFalse(rain)

    @patch("tts_output.FORCE_RAIN_FOR_TEST", 1)
    def test_mode1_forces_rain_without_api(self):
        text, rain = tts_output.write_text("test-key")

        self.assertEqual(text, tts_output.RAIN_EXPECTED_TEXT)
        self.assertTrue(rain)
        self.urlopen.assert_not_called()


class VirtualDayTests(unittest.TestCase):
    KST = tts_output.KST

    def test_before_5am_uses_previous_day(self):
        now = datetime.datetime(2026, 11, 19, 4, 59, tzinfo=self.KST)
        self.assertEqual(tts_output.virtual_day(now), datetime.date(2026, 11, 18))

    def test_from_5am_uses_today(self):
        now = datetime.datetime(2026, 11, 19, 5, 0, tzinfo=self.KST)
        self.assertEqual(tts_output.virtual_day(now), datetime.date(2026, 11, 19))

    def test_roll_is_fixed_within_a_day(self):
        early = tts_output.virtual_day(datetime.datetime(2026, 11, 19, 5, 0, tzinfo=self.KST))
        late = tts_output.virtual_day(datetime.datetime(2026, 11, 20, 4, 59, tzinfo=self.KST))
        self.assertEqual(tts_output.virtual_roll(early), tts_output.virtual_roll(late))

    def test_roll_range(self):
        for offset in range(400):
            roll = tts_output.virtual_roll(datetime.date(2026, 1, 1) + datetime.timedelta(days=offset))
            self.assertTrue(1 <= roll <= tts_output.VIRTUAL_RAIN_DICE)


def _rain_now_item():
    now = datetime.datetime.now()
    return {
        "fcstDate": now.strftime("%Y%m%d"),
        "fcstTime": f"{now.hour:02d}00",
        "category": "PTY",
        "fcstValue": "1",
    }


def _weather_response(items):
    response = MagicMock()
    response.__enter__.return_value.read.return_value = json.dumps(
        {"response": {"body": {"items": {"item": items}}}}
    ).encode("utf-8")
    return response


if __name__ == "__main__":
    unittest.main()
