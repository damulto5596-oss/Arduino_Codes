import io
import threading

import serial
from gtts import gTTS


# Linux 담당이 실제 연결 포트로 변경
SERIAL_PORT = "실제 시리얼 포트 입력"
BAUD_RATE = 115200

audio_lock = threading.Lock()


def light_text(text):
    text = text.strip()

    if not text:
        return False

    if not audio_lock.acquire(blocking=False):
        return False

    try:
        # 1. 문자열을 MP3 데이터로 변환
        audio_buffer = io.BytesIO()

        tts = gTTS(text=text, lang="ko")
        tts.write_to_fp(audio_buffer)

        mp3_data = audio_buffer.getvalue()

        # 2. 시리얼 연결
        with serial.Serial(
            port=SERIAL_PORT,
            baudrate=BAUD_RATE,
            timeout=10,
            write_timeout=30,
        ) as connection:

            # 3. 아두이노의 수신 준비 응답 확인
            ready = connection.read_until(b"\n")

            if ready.strip() != b"READY":
                raise RuntimeError(
                    "아두이노의 READY 응답이 없습니다."
                )

            # 4. 시작 표시와 파일 크기 전송
            connection.write(b"MP3")
            connection.write(
                len(mp3_data).to_bytes(4, "big")
            )

            # 5. MP3 본문 전송
            for start in range(0, len(mp3_data), 512):
                connection.write(
                    mp3_data[start:start + 512]
                )

            connection.flush()

            # 6. 수신 완료 응답 확인
            response = connection.read_until(b"\n")

            if response.strip() != b"OK":
                raise RuntimeError(
                    "MP3 수신 완료 응답이 없습니다."
                )

        print("MP3 전송 완료: 아두이노 수신 응답 확인")
        return True

    except Exception as error:
        print(f"음성 생성·전송 실패: {error}")
        return False

    finally:
        audio_lock.release()
