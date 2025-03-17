import subprocess
subprocess.Popen(r'"C:\Users\diluc\AppData\Roaming\Spotify\Spotify.exe"')
import pygetwindow as gw
windows = gw.getWindowsWithTitle('Spotify')
if windows: print(f"[Текущая песня]: {windows[0].title}")
else: print("[Текущая песня]: Spotify не открыт")