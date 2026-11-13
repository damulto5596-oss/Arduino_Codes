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

    @patch("tts_output.random.randint", return_value=7)
    def test_virtual_rain_sets_rain_flag(self, _randint):
        text, rain = tts_output.write_text("test-key")

        self.assertIn("가상실험에서 비가 오고 있습니다", text)
        self.assertTrue(rain)

    @patch("tts_output.random.randint", return_value=8)
    def test_virtual_no_rain_keeps_rain_flag_false(self, _randint):
        text, rain = tts_output.write_text("test-key")

        self.assertEqual(text, "")
        self.assertFalse(rain)


def _weather_response():
    response = MagicMock()
    response.__enter__.return_value.read.return_value = json.dumps(
        {"response": {"body": {"items": {"item": []}}}}
    ).encode("utf-8")
    return response


if __name__ == "__main__":
    unittest.main()
