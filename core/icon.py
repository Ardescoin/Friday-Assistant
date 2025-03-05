import time
from PIL import Image

ICON_ACTIVE = "ico/active.ico"
ICON_INACTIVE = "ico/inactive.ico"

def update_icon_color(icon, stop_event, voice_input_active):
    try:
        active_icon = Image.open(ICON_ACTIVE)
        inactive_icon = Image.open(ICON_INACTIVE)

        while not stop_event.is_set():
            if voice_input_active.is_set():
                icon.icon = active_icon
            else:
                icon.icon = inactive_icon
            time.sleep(0.5) 

    except FileNotFoundError as e:
        print(f"Ошибка: Не найден файл иконки: {e}")
        stop_event.set()
        icon.stop()
    except Exception as e:
        print(f"Произошла непредвиденная ошибка: {e}")
        stop_event.set()
        icon.stop()
