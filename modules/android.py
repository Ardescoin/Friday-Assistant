import threading
import queue
import asyncio
import aiohttp
import json
import time
import os
import logging
import numpy as np
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.clock import Clock
from jnius import autoclass
from vosk import Model, KaldiRecognizer
import g4f
from kivy.utils import platform

# Android-specific imports
AudioRecord = autoclass('android.media.AudioRecord')
AudioFormat = autoclass('android.media.AudioFormat')
MediaRecorder = autoclass('android.media.MediaRecorder')
MediaPlayer = autoclass('android.media.MediaPlayer')
TextToSpeech = autoclass('android.speech.tts.TextToSpeech')
Locale = autoclass('java.util.Locale')
Environment = autoclass('android.os.Environment')

BASE_URL = "http://46.29.160.114:8000"
MODEL_PATH = "vosk"
CHUNK = 1024
RATE = 16000
VOLUME_THRESHOLD = 0.01

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def resource_path(relative_path):
    if platform == 'android':
        base_path = Environment.getExternalStorageDirectory().getPath()
        return os.path.join(base_path, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

# STT (Speech-to-Text) class
class SpeechRecognition:
    def __init__(self, result_queue, sample_rate=RATE):
        self.model_path = resource_path(MODEL_PATH)
        if not os.path.exists(self.model_path):
            logger.error(f"Путь к модели '{self.model_path}' не найден.")
            raise FileNotFoundError(f"Модель Vosk не найдена: {self.model_path}")
        try:
            self.model = Model(self.model_path)
        except Exception as e:
            logger.error(f"Ошибка загрузки модели: {e}")
            raise
        self.rec = KaldiRecognizer(self.model, sample_rate)
        self.command_result_queue = result_queue
        self.sample_rate = sample_rate
        self.chunk_size = CHUNK
        self.running = False
        self.audio_record = None
        self.command_queue = queue.Queue()

    def _initialize_audio(self):
        channel_config = AudioFormat.CHANNEL_IN_MONO
        audio_format = AudioFormat.ENCODING_PCM_16BIT
        buffer_size = AudioRecord.getMinBufferSize(self.sample_rate, channel_config, audio_format)
        self.audio_record = AudioRecord(
            MediaRecorder.AudioSource.MIC,
            self.sample_rate,
            channel_config,
            audio_format,
            buffer_size
        )

    def _calculate_rms(self, data):
        try:
            if not data:
                return 0.0
            audio_data = np.frombuffer(data, dtype=np.int16)
            if audio_data.size == 0:
                return 0.0
            mean_square = np.mean(audio_data**2)
            if np.isnan(mean_square) or mean_square < 0:
                return 0.0
            return np.sqrt(mean_square)
        except Exception as e:
            logger.error(f"Ошибка при вычислении RMS: {e}")
            return 0.0

    def _listen_loop(self, dt):
        if not self.running:
            return
        try:
            buffer = bytearray(self.chunk_size * 2)  # 16-bit audio
            bytes_read = self.audio_record.read(buffer, 0, len(buffer))
            if bytes_read > 0:
                data = bytes(buffer[:bytes_read])
                rms = self._calculate_rms(data)
                if rms < VOLUME_THRESHOLD:
                    return
                if self.rec.AcceptWaveform(data):
                    result = json.loads(self.rec.Result())
                    text = result.get("text", "").strip()
                    if text:
                        logger.info(f"Распознано: {text}")
                        if text.lower() == "стоп":
                            self.command_queue.put(None)
                            self.stop_listening()
                            return
                        self.command_queue.put(text)
                        self.command_result_queue.put(text)
                else:
                    partial_result = json.loads(self.rec.PartialResult())
                    partial_text = partial_result.get("partial", "").strip()
                    if partial_text:
                        logger.debug(f"Частично: {partial_text}")
        except Exception as e:
            logger.error(f"Ошибка в цикле прослушивания: {e}")
            self.stop_listening()

    def start_listening(self):
        if not self.running:
            self._initialize_audio()
            self.audio_record.startRecording()
            self.running = True
            Clock.schedule_interval(self._listen_loop, 0.01)
            logger.info("Прослушивание начато")
        else:
            logger.warning("Прослушивание уже запущено")

    def stop_listening(self):
        if self.running:
            self.running = False
            Clock.unschedule(self._listen_loop)
            if self.audio_record:
                self.audio_record.stop()
                self.audio_record.release()
                self.audio_record = None
            self.command_queue.put(None)
            logger.info("Прослушивание остановлено")

    def get_command(self):
        try:
            return self.command_queue.get_nowait()
        except queue.Empty:
            return None

# TTS (Text-to-Speech) class
class TextToSpeech:
    def __init__(self):
        self.lock = threading.Lock()
        self.is_speaking = False
        self.speech_queue = queue.Queue()
        self.current_thread = None
        self.media_player = None

    async def speak(self, text, use_server=True):
        with self.lock:
            while not self.speech_queue.empty():
                try:
                    self.speech_queue.get_nowait()
                except queue.Empty:
                    break
            self.speech_queue.put((text, use_server))

            if self.is_speaking and self.current_thread and self.current_thread.is_alive():
                return

        async def run_speech():
            try:
                while not self.speech_queue.empty():
                    with self.lock:
                        current_text, server_mode = self.speech_queue.get()

                    if not isinstance(current_text, str) or not current_text.strip():
                        logger.error(f"Ошибка: текст должен быть строкой, получено: {current_text}")
                        continue

                    if server_mode:
                        filename = resource_path("output.mp3")
                        async with aiohttp.ClientSession() as session:
                            try:
                                async with session.post(f"{BASE_URL}/tts", json={"text": current_text}, timeout=10) as response:
                                    if response.status == 200:
                                        with open(filename, "wb") as f:
                                            f.write(await response.read())
                                        self.media_player = MediaPlayer()
                                        self.media_player.setDataSource(filename)
                                        self.media_player.prepare()
                                        self.media_player.start()
                                        while self.media_player.isPlaying():
                                            await asyncio.sleep(0.1)
                                        self.media_player.stop()
                                        self.media_player.release()
                                        self.media_player = None
                                        try:
                                            os.remove(filename)
                                        except Exception as e:
                                            logger.error(f"Не удалось удалить {filename}: {e}")
                                    else:
                                        logger.error(f"Ошибка генерации речи через сервер: {response.status}")
                                        await self.speak_offline(current_text)
                            except aiohttp.ClientError as e:
                                logger.error(f"Ошибка соединения с сервером TTS: {e}")
                                await self.speak_offline(current_text)
                    else:
                        await self.speak_offline(current_text)
            except Exception as e:
                logger.error(f"Ошибка при озвучке: {e}")
            finally:
                with self.lock:
                    self.is_speaking = False
                if self.media_player:
                    self.media_player.stop()
                    self.media_player.release()
                    self.media_player = None

        with self.lock:
            self.is_speaking = True
            self.current_thread = threading.Thread(target=lambda: asyncio.run(run_speech()), daemon=True)
            self.current_thread.start()

    async def speak_offline(self, text):
        try:
            tts = TextToSpeech(App.get_running_app().context, None)
            tts.setLanguage(Locale('ru_RU'))
            tts.speak(text, TextToSpeech.QUEUE_FLUSH, None, None)
        except Exception as e:
            logger.error(f"Ошибка оффлайн-TTS: {e}")

# Assistant class
class Assistant:
    def __init__(self, speech_recognition, text_to_speech):
        self.sr = speech_recognition
        self.tts = text_to_speech
        self.stop_event = threading.Event()
        self.active = False
        self.last_command_time = None
        self.dialogue_timeout = 10
        self.pc_files_dir = resource_path("files")
        os.makedirs(self.pc_files_dir, exist_ok=True)
        self.loop = asyncio.new_event_loop()
        self.command_check_thread = threading.Thread(target=self.run_event_loop, daemon=True)
        self.command_check_thread.start()
        asyncio.run_coroutine_threadsafe(self.register_pc_status(True), self.loop)
        asyncio.run_coroutine_threadsafe(self.periodic_file_check(), self.loop)
        self.sr.start_listening()

    def run_event_loop(self):
        asyncio.set_event_loop(self.loop)
        asyncio.ensure_future(self.check_commands_from_bot(), loop=self.loop)
        self.loop.run_forever()
        pending = asyncio.all_tasks(self.loop)
        for task in pending:
            task.cancel()
        try:
            self.loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        except asyncio.CancelledError:
            pass
        self.loop.close()

    async def register_pc_status(self, active):
        async with aiohttp.ClientSession() as session:
            for attempt in range(5):
                try:
                    async with session.post(f"{BASE_URL}/pc/status", json={"active": active}, timeout=5) as response:
                        if response.status == 200:
                            logger.info(f"Статус устройства зарегистрирован: {active}, ответ: {await response.text()}")
                            if active:
                                await self.fetch_pending_files()
                            break
                        else:
                            logger.error(f"Ошибка регистрации статуса: {response.status}")
                    break
                except aiohttp.ClientError as e:
                    logger.error(f"Ошибка регистрации статуса (попытка {attempt + 1}/5): {e}")
                    if attempt < 4:
                        await asyncio.sleep(2)
            else:
                logger.error("Не удалось зарегистрировать статус после 5 попыток")

    async def check_commands_from_bot(self):
        logger.info("Прослушивание команд от бота запущено")
        async with aiohttp.ClientSession() as session:
            while not self.stop_event.is_set():
                retries = 5
                for attempt in range(retries):
                    try:
                        async with session.post(f"{BASE_URL}/pc/command", json={"command": "check"}, timeout=10) as response:
                            if response.status == 200:
                                command_data = await response.json()
                                command_id = command_data.get("command_id")
                                command = command_data.get("command")
                                if command and command != "check":
                                    logger.info(f"Получена команда: {command} (command_id: {command_id})")
                                    bot_response = await self.process_command(command)
                                    if bot_response:
                                        for retry in range(5):
                                            try:
                                                async with session.post(f"{BASE_URL}/pc/response", json={"command_id": command_id, "response": bot_response}, timeout=10):
                                                    break
                                            except aiohttp.ClientError:
                                                if retry < 4:
                                                    await asyncio.sleep(1)
                                break
                            else:
                                break
                    except aiohttp.ClientError:
                        if attempt < retries - 1:
                            await asyncio.sleep(1)
                await asyncio.sleep(1)

    async def fetch_pending_files(self):
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(f"{BASE_URL}/pc/check_file_queue", timeout=5) as response:
                    if response.status == 200:
                        data = await response.json()
                        files = data.get("files", [])
                        for file_data in files:
                            filename = file_data["filename"]
                            dest_path = os.path.join(self.pc_files_dir, filename)
                            async with session.get(f"{BASE_URL}/pc/get_file/{filename}", timeout=10) as file_response:
                                if file_response.status == 200:
                                    with open(dest_path, "wb") as f:
                                        f.write(await file_response.read())
                                    logger.info(f"Файл {filename} скачан в {dest_path}")
                                    async with session.delete(f"{BASE_URL}/pc/remove_file/{filename}", timeout=5) as remove_response:
                                        if remove_response.status == 200:
                                            logger.info(f"Файл {filename} удалён с сервера")
                                        else:
                                            logger.error(f"Ошибка удаления файла с сервера: {remove_response.status}")
                                else:
                                    logger.error(f"Ошибка скачивания файла {filename}: {file_response.status}")
                    else:
                        logger.error(f"Ошибка проверки очереди файлов: {response.status}")
            except aiohttp.ClientError as e:
                logger.error(f"Ошибка получения файлов: {e}")

    async def periodic_file_check(self):
        while not self.stop_event.is_set():
            await self.fetch_pending_files()
            await asyncio.sleep(10)

    async def send_file_to_server(self, filename):
        file_path = os.path.join(self.pc_files_dir, filename)
        if os.path.exists(file_path):
            async with aiohttp.ClientSession() as session:
                try:
                    with open(file_path, "rb") as f:
                        data = aiohttp.FormData()
                        data.add_field("file", f, filename=filename, content_type="application/octet-stream")
                        async with session.post(f"{BASE_URL}/pc/upload_file", data=data, timeout=10) as response:
                            if response.status == 200:
                                logger.info(f"Файл {filename} успешно отправлен на сервер")
                                return f"Файл {filename} загружен на сервер"
                            else:
                                logger.error(f"Ошибка отправки файла: {response.status}")
                                return f"Ошибка загрузки файла на сервер: {response.status}"
                except aiohttp.ClientError as e:
                    logger.error(f"Ошибка соединения при отправке файла: {e}")
                    return f"Ошибка соединения: {str(e)}"
        else:
            logger.error(f"Файл {filename} не найден в {self.pc_files_dir}")
            return f"Сэр, файл {filename} не найден в {self.pc_files_dir}"

    async def process_command(self, command):
        if not command or not command.strip():
            return None

        self.last_command_time = time.time()

        context = "Контекст недоступен.\n"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(f"{BASE_URL}/db/get_interactions", params={"limit": 10}, timeout=5) as response:
                    if response.status == 200:
                        context_data = await response.json()
                        context_str = context_data.get("context", "Контекст пока пуст")
                        if context_str != "Контекст пока пуст":
                            lines = context_str.split("\n")
                            recent_interactions = []
                            i = 0
                            while i < len(lines) - 1:
                                user_cmd = None
                                assistant_resp = None
                                if lines[i].startswith("Пользователь: "):
                                    user_cmd = lines[i].replace("Пользователь: ", "").strip()
                                    i += 1
                                    if i < len(lines) and lines[i].startswith("Пятница: "):
                                        assistant_resp = lines[i].replace("Пятница: ", "").strip()
                                if user_cmd and assistant_resp:
                                    recent_interactions.append((user_cmd, assistant_resp))
                                i += 1
                            unique_interactions = []
                            seen_commands = set()
                            for cmd, resp in recent_interactions[::-1]:
                                if cmd not in seen_commands:
                                    unique_interactions.append((cmd, resp))
                                    seen_commands.add(cmd)
                            unique_interactions = unique_interactions[:5]
                            context = "Контекст последних взаимодействий:\n" + \
                                    "\n".join(f"[{i+1}] Вы: {cmd} | Я: {resp}" for i, (cmd, resp) in enumerate(unique_interactions)) + "\n"
                        else:
                            context = "Контекст пока пуст.\n"
                        logger.info(f"Обработанный контекст: {context}")
                    else:
                        logger.error(f"Ошибка при получении контекста: {response.status}")
            except aiohttp.ClientError as e:
                logger.error(f"Ошибка соединения с сервером при получении контекста: {e}")

        is_first_greeting = "привет" in command.lower() and self.last_command_time is None
        if command.startswith("upload_file:") or command.startswith("отправить файл "):
            filename = command.replace("upload_file:", "").replace("отправить файл ", "").strip()
            response = await self.send_file_to_server(filename)
            await self.tts.speak(response)
            self.dialogue_timeout = 10
            return response

        response = await self.post_response(command, context, is_first_greeting=is_first_greeting)
        await self.tts.speak(response)
        self.dialogue_timeout = 10
        return response

    async def post_response(self, command, context, is_first_greeting=False):
        import datetime
        date = datetime.datetime.now().strftime("%H:%M:%S")
        day = datetime.datetime.now().strftime("%A")

        full_prompt = f"""
        Ты голосовой ассистент Пятница, женского пола, энергичная и дружелюбная. Обращайся ко мне как 'Сэр', будь неформальной, используй женский род. Веди живой диалог, отвечая на вопросы и команды, поддерживая разговор по контексту: {context}.

        Если это первый контакт с приветствием ({is_first_greeting}), отвечай: 'Привет, Сэр. Рада вас слышать.' и добавь лёгкий вопрос. Иначе продолжай беседу.

        На вопросы (например, 'Как дела?', 'Площадь Америки') без результата кода отвечай коротко, по теме, с интересом. На разговорные фразы (например, 'Я думаю кушать сходить') реагируй естественно, развивая тему. Виртуоз — мой друг.

        На команды-действия (например, 'Открой браузер') без результата кода или с пустым результатом отвечай позитивно, предполагая успех: 'Сэр, браузер открыт, что ещё?'.

        На команды с информацией (например, 'Площадь Америки') без результата кода дай краткий ответ или: 'Сэр, точных данных нет, но могу предположить...'.

        Отвечай лаконично, без форматирования. Текущее время: {date}. День недели: {day}. Моя фраза: {command}.
        """

        try:
            final_response = g4f.ChatCompletion.create(
                model="gpt-4o",
                messages=[{'role': 'user', 'content': full_prompt}]
            )
            final_response = final_response.strip()
        except Exception as e:
            final_response = f"Сэр, возникла ошибка при генерации ответа: {e}"

        data = {
            "command": command,
            "prompt": full_prompt,
            "response": final_response
        }
        async def save_interaction():
            async with aiohttp.ClientSession() as session:
                try:
                    async with session.post(f"{BASE_URL}/db/add_interaction", json=data, timeout=5) as api_response:
                        if api_response.status != 200:
                            logger.error(f"Ошибка при записи в базу: {api_response.status}, {await api_response.text()}")
                except aiohttp.ClientError as e:
                    logger.error(f"Ошибка при записи в базу: {e}")
        asyncio.run_coroutine_threadsafe(save_interaction(), self.loop)
        return final_response

    async def listen_for_command_async(self):
        while not self.stop_event.is_set():
            try:
                command = self.sr.get_command()
                if command is None:
                    await asyncio.sleep(0.1)
                    continue
                if command and command.strip():
                    if self.last_command_time is not None and (time.time() - self.last_command_time) >= self.dialogue_timeout:
                        logger.info("Время диалога истекло, перезапуск диалога...")
                        self.last_command_time = None
                    if (self.last_command_time is None and "пятница" in command.lower()) or \
                       (self.last_command_time is not None and (time.time() - self.last_command_time) < self.dialogue_timeout):
                        await self.process_command(command)
                    else:
                        logger.info(f"Пропущено: {command} (нет ключевого слова или время диалога истекло)")
                await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"Ошибка при выполнении команды: {e}")
                await asyncio.sleep(0.1)

    def start_listener(self):
        logger.info("Ассистент включен")
        self.active = True
        asyncio.run_coroutine_threadsafe(self.listen_for_command_async(), self.loop)

    def on_quit(self):
        self.stop_event.set()
        self.active = False
        self.sr.stop_listening()
        if self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)
        asyncio.run_coroutine_threadsafe(self.register_pc_status(False), self.loop)
        if self.command_check_thread.is_alive():
            self.command_check_thread.join(timeout=2)

# Kivy App
class VoiceAssistantApp(App):
    def __init__(self):
        super().__init__()
        self.assistant = None
        self.result_queue = queue.Queue()

    def build(self):
        layout = BoxLayout(orientation='vertical')
        self.label = Label(text='Голосовой ассистент')
        self.button = Button(text='Говорить', on_press=self.toggle_listening)
        layout.add_widget(self.label)
        layout.add_widget(self.button)
        return layout

    def toggle_listening(self, instance):
        if not self.assistant:
            if platform == 'android':
                from android.permissions import request_permissions, Permission
                request_permissions([Permission.RECORD_AUDIO, Permission.WRITE_EXTERNAL_STORAGE, Permission.INTERNET])
            self.assistant = Assistant(SpeechRecognition(self.result_queue), TextToSpeech())
            self.assistant.start_listener()
            self.button.text = 'Остановить'
            Clock.schedule_interval(self.process_results, 0.1)
        else:
            self.assistant.on_quit()
            self.assistant = None
            self.button.text = 'Говорить'

    def process_results(self, dt):
        try:
            text = self.result_queue.get_nowait()
            if text:
                self.label.text = f"Распознано: {text}"
        except queue.Empty:
            pass

if __name__ == '__main__':
    VoiceAssistantApp().run()