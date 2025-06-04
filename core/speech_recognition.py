import queue
import threading
import requests
import pyaudio
import wave
import os
import logging
import time
import numpy as np
import sys

def resource_path(relative_path):
    """Получает абсолютный путь к ресурсу, работает для PyInstaller."""
    if getattr(sys, 'frozen', False):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


API_TOKEN = "" 
API_URL = "https://api-inference.huggingface.co/models/openai/whisper-large-v3"
headers = {
    "Authorization": f"Bearer {API_TOKEN}",
    "Content-Type": "audio/wav"  
}


CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
AUDIO_DURATION = 5  

class SpeechRecognition:
    def __init__(self, result_queue: queue.Queue, device_index=0):
        self.command_result_queue = result_queue
        self.p = pyaudio.PyAudio()
        self.stream = None
        self.device_index = device_index
        self.command_queue = queue.Queue()
        self.running = threading.Event()
        self.listen_thread = None
        self.VOLUME_THRESHOLD = 1
        self._initialize_stream()

    def _calculate_rms(self, data):
        try:
            if not data:
                logger.debug("Пустой аудиофрейм, RMS не вычислен")
                return 0.0
            audio_data = np.frombuffer(data, dtype=np.int16)
            if audio_data.size == 0:
                logger.debug("Пустой массив аудиоданных, RMS не вычислен")
                return 0.0
            mean_square = np.mean(audio_data**2)
            if np.isnan(mean_square) or mean_square < 0:
                logger.debug(f"Некорректное значение mean_square: {mean_square}")
                return 0.0
            return np.sqrt(mean_square)
        except Exception as e:
            logger.error(f"Ошибка при вычислении RMS: {e}")
            return 0.0

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

    def _save_audio(self, frames, filename="temp.wav"):
        wf = wave.open(filename, 'wb')
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(self.p.get_sample_size(FORMAT))
        wf.setframerate(RATE)
        wf.writeframes(b''.join(frames))
        wf.close()
        return filename

    def _recognize_speech(self, audio_file):
        try:
            with open(audio_file, "rb") as f:
                data = f.read()
            response = requests.post(API_URL, headers=headers, data=data)
            response.raise_for_status()
            result = response.json()
            text = result.get("text", "").strip()
            return text
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP Error: {e.response.status_code}, {e.response.text}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Request Error: {e}")
            return None

    def _listen_loop(self):
        self.running.set()
        frames = []
        start_time = time.time()
        while self.running.is_set():
            try:
                data = self.stream.read(CHUNK, exception_on_overflow=False)
                rms = self._calculate_rms(data)
                if rms < self.VOLUME_THRESHOLD:
                    continue
                frames.append(data)
                
                if time.time() - start_time >= AUDIO_DURATION:
                    audio_file = self._save_audio(frames)
                    text = self._recognize_speech(audio_file)
                    if text:
                        logger.info(f"Распознано: {text}")
                        if text.lower() == "стоп":
                            self.command_queue.put(None)
                            self.command_result_queue.put("стоп")
                            break
                        self.command_queue.put(text)
                        self.command_result_queue.put(text)
                    
                    frames = []
                    start_time = time.time()
            except Exception as e:
                logger.error(f"Ошибка в цикле прослушивания: {e}")
                self.running.clear()
                break
        
        self.running.clear()

    def start_listening(self):
        if not self.running.is_set():
            try:
                if not self.stream or not self.stream.is_active():
                    self._initialize_stream()
                self.listen_thread = threading.Thread(target=self._listen_loop, daemon=True)
                self.listen_thread.start()
                logger.info("Прослушивание запущено")
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