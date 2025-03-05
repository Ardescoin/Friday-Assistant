import time
import threading
import pystray
from PIL import Image
from core.icon import update_icon_color
from core.assistant import Assistant
from core.speech_recognition import SpeechRecognition
from core.text_to_speech import TextToSpeech

def main():
    sr = SpeechRecognition(device_index=1)
    tts = TextToSpeech()

    assistant = Assistant(sr, tts)

    threading.Thread(target=assistant.start_listener, daemon=True).start()

    icon_image = Image.open("ico/inactive.ico") 

    icon = pystray.Icon("test_icon", icon_image, "Voice Assistant", menu=pystray.Menu( 
        pystray.MenuItem("Quit", lambda icon_obj, item: assistant.on_quit(icon_obj, item))
    ))

    threading.Thread(target=update_icon_color, args=(icon, assistant.stop_event, assistant.voice_input_active), daemon=True).start()
    icon.run_detached()

    try:
        while not assistant.stop_event.is_set():
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nПрограмма завершена пользователем.")
        assistant.stop_event.set()
        icon.stop()

if __name__ == "__main__":
    main()