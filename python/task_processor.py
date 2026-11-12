from tts_player import light_text


def run_my_task(input_text):
    output_text = input_text.strip()

    if not output_text:
        return False

    return light_text(output_text)
