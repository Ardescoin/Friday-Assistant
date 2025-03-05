
import queue
import threading
import wave
import os
import json
from vosk import Model, KaldiRecognizer
import pyaudio

MODEL_PATH = r"D:\AModel\vosk-model-ru-0.42"

CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000  


try:
    model = Model(MODEL_PATH)
except Exception as e:
    print(f"Ошибка загрузки модели: {e}")
    exit(1)

class SpeechRecognition:
    def __init__(self, device_index=1):  
        self.rec = KaldiRecognizer(model, RATE)
        self.p = pyaudio.PyAudio()
        self.stream = None
        self.device_index = device_index
        self.command_queue = queue.Queue()  
        self.running = threading.Event()  
        self._initialize_stream()

    def _initialize_stream(self):
        if self.stream is None:
            try:
                self.stream = self.p.open(format=FORMAT,
                                        channels=CHANNELS,
                                        rate=RATE,
                                        input=True,
                                        frames_per_buffer=CHUNK,
                                        input_device_index=self.device_index)
                print(f"Микрофон инициализирован: {self.p.get_device_info_by_index(self.device_index)['name']}")
            except Exception as e:
                print(f"Ошибка инициализации микрофона (устройство {self.device_index}): {e}")
                raise

    def _listen_loop(self):
        self.running.set()
        try:
            while self.running.is_set():
                if not self.stream.is_active():
                    print("Микрофон не активен, переинициализация...")
                    self.stream.close()
                    self._initialize_stream()
                
                data = self.stream.read(CHUNK, exception_on_overflow=False)
                if self.rec.AcceptWaveform(data):
                    result = json.loads(self.rec.Result())
                    text = result.get("text", "").strip()
                    if text:
                        print(f"Распознано: {text}")
                        if text.lower() == "стоп":
                            self.command_queue.put(None)  
                            break
                        self.command_queue.put(text)  
                else:
                    partial_result = json.loads(self.rec.PartialResult())
                    partial_text = partial_result.get("partial", "").strip()
                    if partial_text:
                        print(f"Частично: {partial_text}", end="\r")
        except Exception as e:
            print(f"Ошибка в потоке прослушивания: {e}")
        finally:
            if self.stream is not None:
                self.stream.stop_stream()
                self.stream.close()
                self.stream = None
                self.p.terminate()

    def start_listening(self):
        if not self.running.is_set():
            self.listen_thread = threading.Thread(target=self._listen_loop, daemon=True)
            self.listen_thread.start()
            print("Прослушивание запущено в фоновом режиме.")

    def stop_listening(self):
        self.running.clear()
        if hasattr(self, 'listen_thread'):
            self.listen_thread.join(timeout=2)
        self.command_queue.put(None)  

    def get_command(self):
        try:
            return self.command_queue.get(timeout=1)  
        except queue.Empty:
            return None

    def __del__(self):
        self.stop_listening()
        if hasattr(self, 'p') and self.p is not None:
            self.p.terminate()