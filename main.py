import os
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'

# from vosk import SetLogLevel
# SetLogLevel(-1)
import threading
import pystray
from PIL import Image
from core.icon import update_icon_color
from core.assistant import Assistant
from core.speech_recognition import SpeechRecognition
from core.text_to_speech import TextToSpeech
import customtkinter as ctk
import sys
import ctypes
import queue


def resource_path(relative_path):
    if getattr(sys, 'frozen', False):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

def hide_console():
    hwnd = ctypes.windll.kernel32.GetConsoleWindow()
    if hwnd:
        ctypes.windll.user32.ShowWindow(hwnd, 0)

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

if not is_admin():
    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, f'"{sys.argv[0]}" --hide-console', None, 1)
    sys.exit()

def main():
    # hide_console()
    command_result_queue = queue.Queue()
    

    sr = SpeechRecognition( command_result_queue, device_index=1)
    tts = TextToSpeech()
    assistant = Assistant(sr, tts)

    listener_thread = threading.Thread(target=assistant.start_listener, daemon=True)
    listener_thread.start()

    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("green")
    
    root = ctk.CTk()
    root.title("Friday")
    root.geometry("400x200")
    
    root.resizable(width=False, height=False)

    status_label = ctk.CTkLabel(master=root, text="Ассистент запущен", font=("Arial", 16))
    status_label.pack(pady=20)
    
    output_text = ctk.CTkTextbox(master=root, width=350, height=100, font=("Arial", 12), state="disabled")
    output_text.pack(pady=10)
    
    
    
    def update_output(text):
        output_text.configure(state="normal")
        output_text.delete("1.0", "end")
        output_text.insert("1.0", text)
        output_text.configure(state="disabled")

    def poll_queue():
        try:
            while True:
                response = command_result_queue.get_nowait()
                update_output(response)
        except queue.Empty:
            pass
        root.after(100, poll_queue)

    poll_queue()

    assistant.app = type('App', (), {'update_output': lambda text: [
        output_text.configure(state="normal"),
        output_text.delete("1.0", "end"),
        output_text.insert("1.0", text),
        output_text.configure(state="disabled")
    ]})()
    

    minimize_to_tray= [False]
    
    def on_closing():
        dialog = ctk.CTkToplevel(root)
        dialog.title("Friday")
        dialog.geometry("300x150")
        dialog.transient(root)
        dialog.grab_set()
        
        label = ctk.CTkLabel(dialog, text="Свернуться в трей?", font=("Ariel", 14))
        label.pack(pady=20)
        
        def minimize():
            minimize_to_tray[0] = True
            dialog.destroy()
            root.destroy()
            
        def exit_app():
            minimize_to_tray[0] = False
            dialog.destroy()
            root.destroy()
            
        minimize_button = ctk.CTkButton(dialog, text="Да",command=minimize)  
        minimize_button.pack(pady=5)
        
        exit_button = ctk.CTkButton(dialog, text="Нет", command=exit_app)  
        exit_button.pack(pady=5)
    
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()

    if minimize_to_tray[0]:
        icon_image = Image.open(resource_path("ico/inactive.ico"))
        icon = pystray.Icon("test_icon", icon_image, "Voice Assistant", menu=pystray.Menu( 
            pystray.MenuItem("Quit", lambda icon_obj, item: assistant.on_quit(icon_obj))
        ))
        
        color_thread = threading.Thread(target=update_icon_color, args=(icon, assistant.stop_event, assistant.voice_input_active), daemon=True)
        color_thread.start()
        icon_thread = threading.Thread(target=icon.run, daemon=True)
        icon_thread.start()
        color_thread.join()
        icon_thread.join()
    else:
        assistant.on_quit(None)
        
    listener_thread.join()
    print("Все потоки завершены. Программа завершена.")

if __name__ == "__main__":
    main()