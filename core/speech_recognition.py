import queue
import threading
import json
from vosk import Model, KaldiRecognizer
import pyaudio
import os
import logging
import time
import sys
import os

def resource_path(relative_path):
    if getattr(sys, 'frozen', False):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

MODEL_PATH = resource_path("vosk") 
CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000  


if not os.path.exists(MODEL_PATH):
    logger.error(f"Путь к модели '{MODEL_PATH}' не найден. Укажите правильный путь.")
    exit(1)

try:
    model = Model(MODEL_PATH)
except Exception as e:
    logger.error(f"Ошибка загрузки модели: {e}")
    exit(1)

class SpeechRecognition:
    def __init__(self,  result_queue: queue.Queue, device_index=1):
        self.rec = KaldiRecognizer(model, RATE)
        self.command_result_queue = result_queue
        self.p = pyaudio.PyAudio()
        self.stream = None
        self.device_index = device_index
        self.command_queue = queue.Queue()
        self.running = threading.Event()
        self.listen_thread = None
        self._initialize_stream()

    def _initialize_stream(self):
        if self.stream is not None:
            self.stream.close()
            self.stream = None
        
        try:
            device_count = self.p.get_device_count()
            if self.device_index >= device_count or self.device_index < 0:
                logger.error(f"Устройство с индексом {self.device_index} не найдено. Доступные устройства:")
                for i in range(device_count):
                    logger.error(f"  {i}: {self.p.get_device_info_by_index(i)['name']}")
                raise ValueError(f"Недопустимый индекс устройства: {self.device_index}")
            
            self.stream = self.p.open(
                format=FORMAT,
                channels=CHANNELS,
                rate=RATE,
                input=True,
                frames_per_buffer=CHUNK,
                input_device_index=self.device_index
            )
        except Exception as e:
            logger.error(f"Ошибка инициализации микрофона (устройство {self.device_index}): {e}")
            raise

    def _listen_loop(self):
        self.running.set()
        while self.running.is_set():
            try:
                data = self.stream.read(CHUNK, exception_on_overflow=False)
                if self.rec.AcceptWaveform(data):
                    result = json.loads(self.rec.Result())
                    text = result.get("text", "").strip()
                    if text:
                        logger.info(f"Распознано: {text}")
                        if text.lower() == "стоп":
                            self.command_queue.put(None)
                            break
                        self.command_queue.put(text)
                    self.command_result_queue.put(text)
                else:
                    partial_result = json.loads(self.rec.PartialResult())
                    partial_text = partial_result.get("partial", "").strip()
                    if partial_text:
                        logger.debug(f"Частично: {partial_text}")
            except Exception as e:
                self.running.clear()  
                break
    

    def start_listening(self):
        if not self.running.is_set():
            try:
                if not self.stream or not self.stream.is_active():
                    self._initialize_stream()
                self.listen_thread = threading.Thread(target=self._listen_loop, daemon=True)
                self.listen_thread.start()
            except Exception as e:
                logger.error(f"Ошибка при запуске прослушивания: {e}")
        else:
            logger.warning("Прослушивание уже запущено")

    def stop_listening(self):
        if self.running.is_set():
            self.running.clear()
            if self.listen_thread and self.listen_thread.is_alive():
                self.listen_thread.join(timeout=2)
                if self.listen_thread.is_alive():
                    logger.warning("Поток прослушивания не завершился вовремя")
            if self.stream is not None:
                self.stream.stop_stream()
                self.stream.close()
                self.stream = None
            logger.info("Прослушивание остановлено")
        self.command_queue.put(None)

    def get_command(self):
        try:
            return self.command_queue.get_nowait()  
        except queue.Empty:
            return None

    def __del__(self):
        self.stop_listening()
        if hasattr(self, 'p') and self.p is not None:
            self.p.terminate()

if __name__ == "__main__":
    
    sr = SpeechRecognition(device_index=1)
    sr.start_listening()
    try:
        while True:
            command = sr.get_command()
            if command is None:
                break
            if command:
                print(f"Получена команда: {command}")
            time.sleep(0.1)  
    except KeyboardInterrupt:
        sr.stop_listening()
        print("Программа завершена")