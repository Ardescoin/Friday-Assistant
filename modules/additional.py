add="""
Код для закрытия всех программ:
import psutil
import win32gui
import win32process
import win32con

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
                    print(f"Ошибка при закрытии окна")
                    
     
"""