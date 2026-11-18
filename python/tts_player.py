"""안내 문장을 음성으로 만들어 아두이노(MCU)로 보내 재생시킨다.

흐름: (캐시 확인) → gTTS로 MP3 생성 → ffmpeg로 PCM(8kHz, unsigned 8bit, mono) 변환
      → 캐시에 저장 → Bridge RPC로 MCU에 전송 → MCU가 D5 PWM으로 재생

캐싱: gTTS는 구글 서버에 접속하는 온라인 TTS라서 인터넷이 끊기면 음성을 못 만든다.
      한 번 만든 PCM을 파일로 저장해두고 같은 문장이면 재사용하므로,
      두 번째부터는 **인터넷 없이도** 알림이 울린다.
      안내 문장 종류가 몇 가지뿐이라 효과가 크다.

주의: 시리얼(pyserial)을 직접 쓰지 않는다. /dev/ttyGS0은 arduino-router-serial
      서비스가 점유하고 있어 직접 열면 충돌한다. 통신은 Bridge만 사용한다.
"""

import hashlib
import io
import subprocess
import threading
from pathlib import Path

from arduino.app_utils import Bridge


# Bridge RPC 1회 페이로드 상한이 약 256바이트(DECODER_BUFFER_SIZE 1024 / 4)이고
# msgpack 프레이밍(타입태그 + 메서드명 + bin 헤더)에 약 16바이트가 쓰인다.
# 임의의 값: 안전 마진을 둔 청크 크기. 이론상 ~240까지 올릴 수 있고, 올리면 전송이 빨라진다.
#            BUFFER_LIMIT_EXCEEDED 오류가 나면 내려야 한다.
AUDIO_CHUNK_BYTES = 128

# MCU의 config.h(PCM_SAMPLE_RATE)와 반드시 일치해야 하는 PCM 포맷
PCM_SAMPLE_RATE = 8000

# MCU의 config.h(AUDIO_MAX_BYTES)와 반드시 일치시켜야 한다.
# 넘으면 아두이노가 audio_begin에서 거절하므로, 보내기 전에 여기서 걸러 원인을 분명히 남긴다.
AUDIO_MAX_BYTES = 8000 * 8  # = 64,000바이트 (8초)

# 임의의 값: ffmpeg 변환 제한 시간(초)
FFMPEG_TIMEOUT_S = 30

# 음량 보정 필터 (ffmpeg -af). gTTS 음성은 진폭이 작아서 0~255 범위를 다 쓰지 못하는데,
# PWM 듀티가 그만큼 덜 흔들려 소리가 작게 들린다. 여기서 진폭을 끌어올려 범위를 채운다.
#   speechnorm : 음성 전용 정규화. 압축기 특유의 출렁임 없이 작은 구간을 끌어올린다
#     e(expansion)=50이 최대 증폭 배수, l=1이면 피크를 한계까지 올린다
#   alimiter   : 클리핑 방지용 리미터. 0.95까지만 허용해 찌그러짐을 막는다
# 임의의 값: 너무 키우면 찌그러지고 노이즈도 같이 커진다. 들어보고 e= 값을 조정할 것.
#            빈 문자열("")로 두면 보정을 끈다.
PCM_GAIN_FILTER = "speechnorm=e=12.5:r=0.0001:l=1,alimiter=limit=0.95"

# 만들어둔 PCM을 보관하는 곳. 앱이 재시작되거나 인터넷이 끊겨도 남아 있다
CACHE_DIR = Path(__file__).resolve().parent / "data" / "tts_cache"
# 임의의 값: 보관할 음성 파일 수 상한. 상황 2 문장은 시각·확률이 들어가 조금씩 달라지므로
#            무한히 쌓이지 않게 오래된 것부터 지운다
CACHE_MAX_FILES = 20

audio_lock = threading.Lock()

# 아두이노에 이미 올려둔 문장. 같은 문장이면 다시 올리지 않는다
_prepared_text = None


def _cache_path(text):
    """문장에 대응하는 캐시 파일 경로. 파일명은 해시라서 어떤 문자든 안전하다.

    해시에 음량 필터와 샘플레이트까지 섞는다 — 그래야 설정을 바꿨을 때
    옛 캐시(옛 음량)가 재사용되지 않고 새로 만들어진다.
    """
    key = f"{text}|{PCM_GAIN_FILTER}|{PCM_SAMPLE_RATE}"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
    return CACHE_DIR / f"{digest}.pcm"


def _read_cache(path):
    """캐시된 PCM을 읽는다. 없거나 쓸 수 없는 상태면 None."""
    try:
        if not path.exists():
            return None

        pcm_data = path.read_bytes()

        # 깨진 캐시(0바이트, 또는 버퍼 초과)는 버리고 새로 만든다
        if not pcm_data or len(pcm_data) > AUDIO_MAX_BYTES:
            print(f"캐시 무시: 크기가 올바르지 않음 ({len(pcm_data)}바이트)")
            path.unlink(missing_ok=True)
            return None

        return pcm_data

    except Exception as error:
        print(f"캐시 읽기 실패: {error}")
        return None


def _write_cache(path, pcm_data):
    """PCM을 캐시에 저장한다. 실패해도 재생 자체는 계속되므로 경고만 남긴다.

    같은 이름의 임시 파일에 먼저 쓰고 바꿔치기해서, 도중에 끊겨도 깨진 캐시가 남지 않게 한다.
    """
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(".pcm.tmp")
        temp_path.write_bytes(pcm_data)
        temp_path.replace(path)
        _prune_cache()
    except Exception as error:
        print(f"캐시 저장 실패(재생은 계속): {error}")


def _prune_cache():
    """캐시 파일이 CACHE_MAX_FILES를 넘으면 오래된 것부터 지운다."""
    try:
        files = sorted(CACHE_DIR.glob("*.pcm"), key=lambda p: p.stat().st_mtime)
        for old in files[:-CACHE_MAX_FILES]:
            old.unlink(missing_ok=True)
    except Exception as error:
        print(f"캐시 정리 실패: {error}")


def _get_pcm(text):
    """문장의 PCM을 얻는다 — 캐시에 있으면 그대로, 없으면 만들어서 캐시에 넣는다.

    캐시가 있으면 gTTS를 호출하지 않으므로 인터넷이 필요 없다.
    """
    path = _cache_path(text)

    cached = _read_cache(path)
    if cached:
        print(f"음성 캐시 사용: {len(cached)}바이트 ({len(cached) / PCM_SAMPLE_RATE:.1f}초)")
        return cached

    mp3_data = _make_mp3(text)
    if not mp3_data:
        return None

    pcm_data = _mp3_to_pcm(mp3_data)
    if not pcm_data:
        return None

    _write_cache(path, pcm_data)
    return pcm_data


def _make_mp3(text):
    """문자열을 gTTS로 MP3 바이트로 만든다. 실패 시 None."""
    try:
        from gtts import gTTS
    except ImportError:
        print(
            "음성 생성 실패: gTTS가 설치되지 않았습니다. "
            "앱 venv에 'uv pip install gTTS'가 필요합니다."
        )
        return None

    try:
        buffer = io.BytesIO()
        gTTS(text=text, lang="ko").write_to_fp(buffer)
        return buffer.getvalue()
    except Exception as error:
        print(f"음성 생성 실패(gTTS): {error}")
        return None


def _mp3_to_pcm(mp3_data):
    """MP3를 PCM(8kHz, unsigned 8bit, mono)으로 변환한다. 실패 시 None.

    ffmpeg 바이너리가 앱 이미지에 없으므로, pip로 설치되는 imageio-ffmpeg의
    동봉 바이너리를 쓴다.
    """
    try:
        import imageio_ffmpeg

        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        print(
            "PCM 변환 실패: imageio-ffmpeg가 설치되지 않았습니다. "
            "앱 venv에 'uv pip install imageio-ffmpeg'가 필요합니다."
        )
        return None
    except Exception as error:
        print(f"PCM 변환 실패(ffmpeg 경로): {error}")
        return None

    command = [
        ffmpeg,
        "-hide_banner", "-loglevel", "error",
        "-i", "pipe:0",          # 입력: stdin의 MP3
    ]

    if PCM_GAIN_FILTER:
        command += ["-af", PCM_GAIN_FILTER]  # 음량 보정 (리샘플링 전에 적용)

    command += [
        "-ar", str(PCM_SAMPLE_RATE),
        "-ac", "1",              # 모노
        "-f", "u8",              # unsigned 8bit raw
        "pipe:1",                # 출력: stdout
    ]

    try:
        result = subprocess.run(
            command,
            input=mp3_data,
            capture_output=True,
            timeout=FFMPEG_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        print("PCM 변환 실패: ffmpeg 시간 초과")
        return None
    except Exception as error:
        print(f"PCM 변환 실패(ffmpeg 실행): {error}")
        return None

    if result.returncode != 0:
        print(f"PCM 변환 실패(ffmpeg): {result.stderr.decode('utf-8', 'ignore')}")
        return None

    return result.stdout


def _send_pcm(pcm_data):
    """PCM을 Bridge RPC로 MCU에 보내 **보관**시킨다 (재생은 하지 않는다).

    Bridge.call은 MCU 응답을 기다리므로 자동으로 흐름 제어가 되어 MCU 버퍼가 넘치지 않는다.
    주의: Bridge.provide 핸들러 안에서는 call을 쓸 수 없으므로(중첩 호출 금지)
          이 함수는 반드시 user_loop(main.py의 loop) 쪽에서 호출해야 한다.
    """
    total = len(pcm_data)

    # 아두이노 버퍼를 넘는지 먼저 확인한다 (초 단위로 찍어야 원인이 바로 보인다)
    if total > AUDIO_MAX_BYTES:
        print(
            f"음성 전송 생략: 문장이 너무 깁니다 — "
            f"{total}바이트({total / PCM_SAMPLE_RATE:.1f}초) > "
            f"한계 {AUDIO_MAX_BYTES}바이트({AUDIO_MAX_BYTES / PCM_SAMPLE_RATE:.0f}초). "
            f"문장을 줄이거나 config.h의 AUDIO_MAX_SECONDS를 올리세요."
        )
        return False

    try:
        if Bridge.call("audio_begin", total) != 0:
            print(f"음성 전송 실패: 아두이노가 수신을 거절했습니다 (크기 {total})")
            return False

        for start in range(0, total, AUDIO_CHUNK_BYTES):
            chunk = pcm_data[start:start + AUDIO_CHUNK_BYTES]
            if Bridge.call("audio_chunk", chunk) < 0:
                print(f"음성 전송 실패: 청크 거절 (offset {start})")
                return False

        # 보관만 하고 재생은 하지 않는다 — 재생은 알림 순간에 request_play()가 지시한다
        if Bridge.call("audio_commit") != 0:
            print("음성 전송 실패: 아두이노가 보관에 실패했습니다")
            return False

    except Exception as error:
        print(f"음성 전송 실패(Bridge): {error}")
        return False

    print(f"음성 준비 완료: {total}바이트 ({total / PCM_SAMPLE_RATE:.1f}초) — 아두이노에 보관됨")
    return True


def prepare_text(text):
    """안내 문장을 음성으로 만들어 아두이노에 **미리** 올려둔다. 성공 시 True.

    문이 열린 뒤에 생성·전송을 시작하면 gTTS 네트워크 호출과 수백 회의 Bridge RPC 때문에
    수 초가 걸려 늦는다. 그래서 날씨 문장이 정해진 시점에 여기까지 끝내두고,
    알림 순간에는 request_play()로 재생 신호만 보낸다.

    같은 문장은 다시 준비하지 않는다(이미 올려둔 것을 그대로 쓴다).
    한 번 만든 음성은 캐시에 남으므로, 두 번째부터는 인터넷 없이도 준비된다.
    """
    global _prepared_text

    text = text.strip()
    if not text:
        return False

    if text == _prepared_text:
        return True  # 이미 올려둠

    if not audio_lock.acquire(blocking=False):
        return False

    try:
        pcm_data = _get_pcm(text)
        if not pcm_data:
            return False

        if not _send_pcm(pcm_data):
            _prepared_text = None
            return False

        _prepared_text = text
        return True

    finally:
        audio_lock.release()


def is_prepared():
    """재생할 음성이 아두이노에 올라가 있는지."""
    return _prepared_text is not None


def request_play():
    """알림 순간에 재생을 지시한다. RPC 1회라 즉시 시작된다.

    notify를 쓰는 이유: 이 함수는 Bridge.provide 핸들러(_on_state) 안에서 호출되는데,
    핸들러 안에서는 Bridge.call이 금지(중첩 호출 불가)되어 있다.
    """
    if _prepared_text is None:
        print("재생 생략: 아두이노에 올려둔 음성이 없습니다")
        return False

    try:
        Bridge.notify("audio_play")
        return True
    except Exception as error:
        print(f"재생 지시 실패(Bridge): {error}")
        return False


def light_text(text):
    """준비와 재생을 한 번에 — 미리 준비되지 않은 경우의 대비용 경로.
    느리므로(수 초) user_loop에서만 호출해야 한다."""
    if not prepare_text(text):
        return False
    return request_play()
