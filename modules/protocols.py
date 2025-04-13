import threading
import time
import os
import subprocess
import psutil
import screen_brightness_control as sbc
import win32gui
import win32con
import win32process



SAFE_PROCESSES = ["python.exe", "explorer.exe", "Spotify.exe"]

class Weekend:
    def __init__(self, text_to_speech):
        self.tts = text_to_speech

    def close_all_programs(self):
        hwnd_list = []
        win32gui.EnumWindows(lambda hwnd, param: param.append(hwnd), hwnd_list)

        for hwnd in hwnd_list:
            if win32gui.IsWindowVisible(hwnd):
                try:
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    process = psutil.Process(pid)
                    process_name = process.name()

                    if process_name not in SAFE_PROCESSES:
                        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                    print(f"Ошибка при закрытии окна: {e}")

    def set_brightness(self, level):
        sbc.set_brightness(level)
        self.speak_async(f"Яркость установлена на {level}%")
        
    def wait(self):
        time.sleep(10)

    def open_browser(self):
        kinopoisk_url = "https://www.kinopoisk.ru/"
        browser_path = r"C:\Program Files\Yandex\YandexBrowser\Application\browser.exe"
        if os.path.exists(browser_path):
            subprocess.Popen([browser_path, kinopoisk_url])
        else:
            print("Браузер не найден по указанному пути.")


    def speak_async(self, text):
        threading.Thread(target=self.tts.speak, args=(text,), daemon=True).start()

    async def run_exit_protocol(self):
        try:
            self.speak_async("Запускаю выходной протокол.")

            self.close_all_programs()
            self.wait()
            self.open_browser()
            self.set_brightness(70)

        except Exception as e:
            print(f"Ошибка при выполнении протокола выхода: {e}")


class Work:
    def __init__(self, text_to_speech):
        self.tts = text_to_speech

    def close_all_programs(self):
        hwnd_list = []
        win32gui.EnumWindows(lambda hwnd, param: param.append(hwnd), hwnd_list)

        for hwnd in hwnd_list:
            if win32gui.IsWindowVisible(hwnd):
                try:
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    process = psutil.Process(pid)
                    process_name = process.name()

                    if process_name not in SAFE_PROCESSES:
                        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                    print(f"Ошибка при закрытии окна: {e}")

    def set_brightness(self, level):
        sbc.set_brightness(level)
        self.speak_async(f"Яркость установлена на {level}%")

    def open_vs(self):
        browser_path = r"C:\Users\diluc\AppData\Local\Programs\Microsoft VS Code\Code.exe"
        if os.path.exists(browser_path):
            subprocess.Popen([browser_path])
        else:
            print("Браузер не найден по указанному пути.")


    def speak_async(self, text):
        threading.Thread(target=self.tts.speak, args=(text,), daemon=True).start()

    async def run_exit_protocol(self):
        try:
            self.speak_async("Запускаю рабочий протокол.")

            self.close_all_programs()
            self.open_vs()
            self.set_brightness(80)

        except Exception as e:
            print(f"Ошибка при выполнении протокола выхода: {e}")
