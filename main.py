import time
import threading
import asyncio
import pystray
from PIL import Image
from core.icon import update_icon_color
from core.assistant import Assistant
from core.speech_recognition import SpeechRecognition
from core.text_to_speech import TextToSpeech


def main():
    sr = SpeechRecognition(device_index=2)
    tts = TextToSpeech()

    assistant = Assistant(sr, tts)

    
    listener_thread = threading.Thread(target=assistant.start_listener, daemon=True)
    listener_thread.start()

    
    icon_image = Image.open("ico/inactive.ico") 
    icon = pystray.Icon("test_icon", icon_image, "Voice Assistant", menu=pystray.Menu( 
        pystray.MenuItem("Quit", lambda icon_obj, item: assistant.on_quit(icon_obj))
    ))

    
    color_thread = threading.Thread(target=update_icon_color, args=(icon, assistant.stop_event, assistant.voice_input_active), daemon=True)
    color_thread.start()

    
    icon_thread = threading.Thread(target=icon.run, daemon=True)
    icon_thread.start()

    try:
        while not assistant.stop_event.is_set():
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nПрограмма завершена пользователем.")
        assistant.stop_event.set()
        icon.stop()

    
    asyncio.run(assistant.register_pc_status(False))

    
    listener_thread.join()
    color_thread.join()
    icon_thread.join()
    print("Все потоки завершены. Программа завершена.")


if __name__ == "__main__":
    main()
