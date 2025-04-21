import subprocess
import time
import pyperclip
import keyboard
from win32gui import GetWindowText, GetForegroundWindow


subprocess.Popen(r'"C:\\Users\\diluc\\AppData\\Roaming\\Telegram Desktop\\Telegram.exe"')
time.sleep(2)
active_window_title = GetWindowText(GetForegroundWindow())
keyboard.press_and_release("ctrl+f")
time.sleep(0.5)
keyboard.write("unread")
time.sleep(0.5)
keyboard.press_and_release("enter")
time.sleep(1)

time.sleep(0.5)