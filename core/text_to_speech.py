import speech_recognition as sr
import threading
import queue
import requests
import os
from pygame import mixer
import time
import sys

BASE_URL = "http://147.45.78.163:8000"  

def format_for_speech(data):
    if isinstance(data, dict):
        lines = []
        for key, value in data.items():
            if isinstance(value, (tuple, list)):
                value_str = ", ".join(str(v) for v in value)
            else:
                value_str = str(value)
            lines.append(f"{key}: {value_str}")
        return ". ".join(lines) + "."
    elif isinstance(data, (list, tuple)):
        return ", ".join(str(item) for item in data) + "."
    else:
        return str(data) + "."

class TextToSpeech:
    def __init__(self):
        self.lock = threading.Lock()
        self.recognizer = sr.Recognizer()
        self.is_speaking = False
        self.speech_queue = queue.Queue()
        self.current_thread = None
        mixer.init()
        self.original_stdout = sys.stdout

    def speak(self, text):
        with self.lock:
            while not self.speech_queue.empty():
                try:
                    self.speech_queue.get_nowait()
                except queue.Empty:
                    break
            self.speech_queue.put(text)

            if self.is_speaking and self.current_thread and self.current_thread.is_alive():
                return

        def run_speech():
            try:
                while not self.speech_queue.empty():
                    with self.lock:
                        current_text = self.speech_queue.get()

                    if not isinstance(current_text, str) or not current_text.strip():
                        print(f"Ошибка: text должен быть непустой строкой, получено: {current_text}")
                        continue

                    
                    filename = f"output.mp3"
                    response = requests.post(f"{BASE_URL}/tts/generate", json={"text": current_text}, stream=True)
                    if response.status_code == 200:
                        with open(filename, "wb") as f:
                            f.write(response.content)
                        mixer.music.load(filename)
                        mixer.music.play()
                        while mixer.music.get_busy():
                            time.sleep(0.1)
                        mixer.music.stop()
                        mixer.music.unload()
                        time.sleep(0.1)  
                        try:
                            os.remove(filename)
                        except PermissionError as e:
                            print(f"Не удалось удалить файл сразу: {e}. Пробую снова...")
                            time.sleep(1)  
                            try:
                                os.remove(filename)
                            except PermissionError as e:
                                print(f"Не удалось удалить {filename} после повторной попытки: {e}")
                    else:
                        print(f"Ошибка генерации речи через сервер: {response.status_code}, {response.text}")
            except Exception as e:
                print(f"Ошибка при озвучке: {e}")
            finally:
                with self.lock:
                    self.is_speaking = False
                mixer.music.stop()
                mixer.music.unload()

        with self.lock:
            self.is_speaking = True
            self.current_thread = threading.Thread(target=run_speech, daemon=True)
            self.current_thread.start()

    def speak_response(self, response):
        if response:
            self.speak(response)

    def listen(self):
        with sr.Microphone() as source:
            self.recognizer.adjust_for_ambient_noise(source)
            try:
                audio = self.recognizer.listen(source, timeout=5)
                command = self.recognizer.recognize_google(audio, language='ru-RU')
                print(f"Вы сказали: {command}")
                return command.lower()
            except sr.UnknownValueError:
                print("Не удалось распознать речь")
                return None
            except sr.RequestError:
                print("Ошибка при обращении к сервису распознавания")
                return None
            
    def redirect_output(self):
        self.output_handler = TTSOutput(self, self.original_stdout)
        sys.stdout = self.output_handler

    def restore_output(self):
        has_spoken = False
        if hasattr(self, 'output_handler') and self.output_handler:
            self.output_handler.flush()
            has_spoken = self.output_handler.has_spoken
        sys.stdout = self.original_stdout
        return has_spoken  

class TTSOutput:
    def __init__(self, tts, original_stdout):
        self.tts = tts
        self.original_stdout = original_stdout
        self.buffer = ""
        self.has_spoken = False  

    def write(self, text):
        self.original_stdout.write(text)
        self.buffer += text

    def flush(self):
        if self.buffer.strip():
            try:
                import ast
                data = ast.literal_eval(self.buffer.strip())
                formatted_text = format_for_speech(data)
            except (ValueError, SyntaxError):
                formatted_text = self.buffer.strip()
            self.tts.speak_response(formatted_text)
            self.has_spoken = True  
            self.buffer = ""

    def __getattr__(self, attr):
        return getattr(self.original_stdout, attr)