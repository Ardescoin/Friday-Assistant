import threading
import time
import g4f
import requests
from modules.gpt import get_gpt_response
from modules.protocols import Weekend
from modules.protocols import Work
from plyer import notification
from mutagen.mp3 import MP3
import datetime 
import aiohttp
import asyncio
import sys
import io
import os
import glob

BASE_URL = "http://46.29.160.114:8000"

class Assistant:
    def __init__(self, speech_recognition, text_to_speech):
        self.sr = speech_recognition
        self.tts = text_to_speech
        self.voice_input_active = threading.Event()
        self.stop_event = threading.Event()
        self.active = False
        self.listening_thread = None
        self.dialogue_timeout = 10
        self.weekend = Weekend(self.tts)
        self.work = Work(self.tts)
        self.last_command_time = None
        self.pc_files_dir = "files"
        self.image_dir = "generated_images"
        self.app = None
        
        os.makedirs(self.pc_files_dir, exist_ok=True)
        os.makedirs(self.image_dir, exist_ok=True)
        print("База данных управляется сервером.")
        self.sr.start_listening()
        
        self.loop = asyncio.new_event_loop()
        self.command_check_thread = threading.Thread(target=self.run_event_loop, daemon=True)
        self.command_check_thread.start()

        asyncio.run_coroutine_threadsafe(self.register_pc_status(True), self.loop)
        asyncio.run_coroutine_threadsafe(self.periodic_file_check(), self.loop)


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

    async def check_and_update_pc_status(self):
        active = await self.check_pc_status()

        self.register_pc_status(active)


    async def register_pc_status(self, active):
        for attempt in range(5):
            try:
                response = requests.post(f"{BASE_URL}/pc/status", json={"active": active}, timeout=5)
                if response.status_code == 200:
                    print(f"Статус ПК зарегистрирован: {active}, ответ сервера: {response.text}")
                    if active:
                        await self.fetch_pending_files()
                    break
                else:
                    print(f"Ошибка регистрации статуса ПК: {response.status_code}")
                break
            except requests.exceptions.RequestException as e:
                print(f"Ошибка регистрации статуса ПК (попытка {attempt + 1}/5): {str(e)}")
                if attempt < 4:
                    time.sleep(2)
        else:
            print("Не удалось зарегистрировать статус ПК после 5 попыток")

    async def check_commands_from_bot(self):
        print("Прослушивание команд от бота запущено")
        while not self.stop_event.is_set():
            retries = 5
            for attempt in range(retries):
                try:
                    response = requests.post(f"{BASE_URL}/pc/command", json={"command": "check"}, timeout=10)
                    if response.status_code == 200:
                        command_data = response.json()
                        command_id = command_data.get("command_id")
                        command = command_data.get("command")
                        if command and command != "check":
                            print(f"Получена команда: {command} (command_id: {command_id})")
                            bot_response = await self.process_command(command)
                            if bot_response:
                                for retry in range(5):
                                    try:
                                        requests.post(f"{BASE_URL}/pc/response", json={"command_id": command_id, "response": bot_response}, timeout=10)
                                        break
                                    except requests.exceptions.RequestException:
                                        if retry < 4:
                                            await asyncio.sleep(1)
                        break
                    else:
                        break
                except requests.exceptions.RequestException:
                    if attempt < retries - 1:
                        await asyncio.sleep(1)
            await asyncio.sleep(1)

    def start_listening_task(self):
        asyncio.run(self.listen_for_command_async())

    def start_listener(self):
        print("ВКЛ")
        self.voice_input_active.set()
        self.active = True
        self.listening_thread = threading.Thread(target=self.start_listening_task, daemon=False)
        self.listening_thread.start()
        
    
    async def fetch_pending_files(self):
        try:
            response = requests.get(f"{BASE_URL}/pc/check_file_queue", timeout=5)
            if response.status_code == 200:
                data = response.json()
                files = data.get("files", [])
                for file_data in files:
                    filename = file_data["filename"]
                    dest_path = os.path.join(self.pc_files_dir, filename)
                    
                    file_response = requests.get(f"{BASE_URL}/pc/get_file/{filename}", timeout=10)
                    if file_response.status_code == 200:
                        with open(dest_path, "wb") as f:
                            f.write(file_response.content)
                        print(f"Файл {filename} скачан в {dest_path}")
                        
                        remove_response = requests.delete(f"{BASE_URL}/pc/remove_file/{filename}", timeout=5)
                        if remove_response.status_code == 200:
                            print(f"Файл {filename} удалён с сервера")
                        else:
                            print(f"Ошибка удаления файла с сервера: {remove_response.status_code}")
                    else:
                        print(f"Ошибка скачивания файла {filename}: {file_response.status_code}")
            else:
                print(f"Ошибка проверки очереди файлов: {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"Ошибка получения файлов: {e}")
            
    async def periodic_file_check(self):
        while not self.stop_event.is_set():
            await self.fetch_pending_files()
            await asyncio.sleep(10)

    
    def send_file_to_server(self, filename):
        file_path = os.path.join(self.pc_files_dir, filename)
        if os.path.exists(file_path):
            try:
                with open(file_path, "rb") as f:
                    files = {"file": (filename, f, "application/octet-stream")}
                    response = requests.post(f"{BASE_URL}/pc/upload_file", files=files, timeout=10)
                    if response.status_code == 200:
                        print(f"Файл {filename} успешно отправлен на сервер")
                        return f"Файл {filename} загружен на сервер"
                    else:
                        print(f"Ошибка отправки файла: {response.status_code}")
                        return f"Ошибка загрузки файла на сервер: {response.status_code}"
            except requests.exceptions.RequestException as e:
                print(f"Ошибка соединения при отправке файла: {e}")
                return f"Ошибка соединения: {str(e)}"
        else:
            print(f"Файл {filename} не найден в {self.pc_files_dir}")
            return f"Сэр, файл {filename} не найден в {self.pc_files_dir}"

    async def fetch_web_data(self, query):
        async with aiohttp.ClientSession() as session:
            if "погода" in query.lower():
                city = "Kazan"
                url = f"https://wttr.in/{city}?format=%C+%t+%w"
                try:
                    async with session.get(url, timeout=5) as response:
                        if response.status == 200:
                            return (await response.text()).strip()
                        return "Сэр, не удалось получить данные о погоде. Чем ещё могу помочь?"
                except aiohttp.ClientError as e:
                    print(f"Ошибка подключения при запросе погоды: {str(e)}")
                    return f"Ошибка подключения: {str(e)}"
            return None

    async def generate_image(self, prompt):
        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: g4f.Client().images.generate(
                    model="dall-e-3",
                    prompt=prompt
                )
            )
            
            image_files = glob.glob(os.path.join(self.image_dir, "*.png")) + \
                         glob.glob(os.path.join(self.image_dir, "*.jpg")) + \
                         glob.glob(os.path.join(self.image_dir, "*.jpeg"))
            if not image_files:
                print("No image files found in generated_images")
                return None
            
            latest_image = max(image_files, key=os.path.getctime)
            print(f"Found latest image: {latest_image}")
            return latest_image
        except Exception as e:
            print(f"Ошибка генерации изображения: {str(e)}")
            return None

    def get_audio_duration(self, filepath):
        audio = MP3(filepath)
        return audio.info.length

    def wait_and_set_timeout(self, filepath, check_interval=1, max_wait=30):
        waited = 0
        while not os.path.exists(filepath):
            if waited >= max_wait:
                print(f"Файл {filepath} не появился за {max_wait} секунд")
                return False
            time.sleep(check_interval)
            waited += check_interval
        duration = self.get_audio_duration(filepath)
        self.dialogue_timeout = duration + 10
        print(f"Таймаут установлен: {self.dialogue_timeout:.2f} секунд")
        return True
    
    async def process_command(self, command):
        if not command or not command.strip():
            return None

        self.last_command_time = time.time()

        
        context = "Контекст недоступен.\n"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(f"{BASE_URL}/db/get_interactions", params={"limit": 10}, timeout=5) as response:
                    if response.status == 200:
                        raw_context = await response.text()
                        try:
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
                            print(f"Обработанный контекст: {context}")
                        except ValueError as e:
                            print(f"Ошибка парсинга JSON контекста: {e}")
                            context = f"Ошибка формата данных от сервера: {raw_context}\n"
                    else:
                        print(f"Ошибка при получении контекста: {response.status}, текст: {await response.text()}")
            except aiohttp.ClientError as e:
                print(f"Ошибка соединения с сервером при получении контекста: {e}")

        is_first_greeting = "привет" in command.lower() and self.last_command_time is None
        is_image_command = any(keyword in command.lower() for keyword in ["сгенерируй", "нарисуй"])
        is_weather_command = "погода" in command.lower()

        if is_image_command:
            image_prompt = command
            image_path = await self.generate_image(image_prompt)
            if image_path and os.path.exists(image_path):
                response = f"Сэр, изображение по запросу '{image_prompt}' создано! Хотите, чтобы я описала его?"
                try:
                    os.remove(image_path)
                    print(f"Изображение удалено: {image_path}")
                except Exception as e:
                    print(f"Ошибка удаления изображения: {str(e)}")
            else:
                response = "Сэр, не удалось сгенерировать изображение. Может, попробуем ещё раз?"
            notification.notify(title="Новое сообщение", message=response, app_name="Friday", app_icon="ico/active.ico", timeout=10)
            self.tts.speak(response)
            
            if self.wait_and_set_timeout('output.mp3'):
                self.last_command_time = time.time()
            else:
                self.dialogue_timeout = 10  
            return self.post_response(command, context, response=response, is_first_greeting=is_first_greeting)

        if is_weather_command:
            web_data = await self.fetch_web_data(command)
            response = self.post_response(command, context, web_data=web_data, is_first_greeting=is_first_greeting)
            notification.notify(title="Новое сообщение", message=response, app_name="Friday", app_icon="ico/active.ico", timeout=10)
            self.tts.speak(response)
            
            if self.wait_and_set_timeout('output.mp3'):
                self.last_command_time = time.time()
            else:
                self.dialogue_timeout = 10  
            return response

        if command.startswith("upload_file:"):
            filename = command.replace("upload_file:", "").strip()
            response = self.send_file_to_server(filename)
            notification.notify(title="Новое сообщение", message=response, app_name="Friday", app_icon="ico/active.ico", timeout=10)
            self.tts.speak(response)
            
            if self.wait_and_set_timeout('output.mp3'):
                self.last_command_time = time.time()
            else:
                self.dialogue_timeout = 10  
            return response

        if command.startswith("отправить файл "):
            filename = command.replace("отправить файл ", "").strip()
            file_path = os.path.join(self.pc_files_dir, filename)
            if os.path.exists(file_path):
                with open(file_path, "rb") as f:
                    files = {"file": (filename, f, "application/octet-stream")}
                    response = requests.post(f"{BASE_URL}/pc/receive_file", files=files, timeout=10)
                if response.status_code == 200:
                    response = f"Файл {filename} готов к отправке в Telegram"
                else:
                    response = f"Ошибка загрузки файла на сервер: {response.status_code}"
            else:
                response = f"Сэр, файл {filename} не найден в {self.pc_files_dir}"
            notification.notify(title="Новое сообщение", message=response, app_name="Friday", app_icon="ico/active.ico", timeout=10)
            self.tts.speak(response)
            
            if self.wait_and_set_timeout('output.mp3'):
                self.last_command_time = time.time()
            else:
                self.dialogue_timeout = 10  
            return response

        if "протокол выходной" in command.lower() or "выходной протокол" in command.lower():
            await self.weekend.run_exit_protocol()
            response = self.post_response(command, context, is_first_greeting=is_first_greeting)
            notification.notify(title="Новое сообщение", message=response, app_name="Friday", app_icon="ico/active.ico", timeout=10)
            self.tts.speak(response)
            
            if self.wait_and_set_timeout('output.mp3'):
                self.last_command_time = time.time()
            else:
                self.dialogue_timeout = 10  
            return response

        if "протокол рабочий" in command.lower() or "рабочий протокол" in command.lower():
            await self.work.run_exit_protocol()
            response = self.post_response(command, context, is_first_greeting=is_first_greeting)
            notification.notify(title="Новое сообщение", message=response, app_name="Friday", app_icon="ico/active.ico", timeout=10)
            self.tts.speak(response)
            
            if self.wait_and_set_timeout('output.mp3'):
                self.last_command_time = time.time()
            else:
                self.dialogue_timeout = 10  
            return response

        
        generated_code = get_gpt_response(command)
        if generated_code and generated_code.strip():
            try:
                output = self.execute_generated_code(generated_code)
                if output:
                    response = output
                else:
                    response = self.post_response(command, context, is_first_greeting=is_first_greeting)
            except Exception as e:
                print(f"Ошибка при выполнении кода: {e}")
                response = self.post_response(command, context, generated_output=f"Ошибка: {str(e)}", is_first_greeting=is_first_greeting)
        else:
            response = self.post_response(command, context, is_first_greeting=is_first_greeting)

        print(f"Ответ для бота: {response}")
        notification.notify(title="Новое сообщение", message=response, app_name="Friday", app_icon="ico/active.ico", timeout=10)
        self.tts.speak(response)
        
        if self.wait_and_set_timeout('output.mp3'):
            self.last_command_time = time.time()
        else:
            self.dialogue_timeout = 10  

        return response
    
    async def listen_for_command_async(self):
        while self.voice_input_active.is_set() and not self.stop_event.is_set():
            try:
                command = self.sr.get_command()
                if command is None:
                    await asyncio.sleep(0.1)
                    continue
                if command and command.strip():
                    if self.last_command_time is not None and (time.time() - self.last_command_time) >= self.dialogue_timeout:
                        print("Время диалога истекло, перезапуск диалога...")
                        self.last_command_time = None

                    if  (self.last_command_time is None and "пятница" in command.lower()) or \
                        (self.last_command_time is not None and (time.time() - self.last_command_time) < self.dialogue_timeout):
                        await self.process_command(command)
                        
                    else:
                        print(f"Пропущено: {command} (нет ключевого слова или время диалога истекло)")
                await asyncio.sleep(0.1)
            except requests.exceptions.RequestException as e:
                print(f"Ошибка соединения с сервером: {e}")
                await asyncio.sleep(0.1)
            except Exception as e:
                print(f"Ошибка при выполнении команды: {e}")
                await asyncio.sleep(0.1)
    
    def execute_generated_code(self, code):
        try:
            if not code or not any(kw in code for kw in ("def ", "import ", "class ", "=")):
                return None
            try:
                compile(code, "<string>", "exec")
            except SyntaxError:
                print("Ошибка: Сгенерированный код содержит синтаксические ошибки.")
                return None
            
            old_stdout = sys.stdout
            redirected_output = io.StringIO()
            sys.stdout = redirected_output
            
            exec_globals = {'print': print}  
            exec(code, exec_globals)
            
            
            sys.stdout = old_stdout
            output = redirected_output.getvalue().strip()
            redirected_output.close()
            
            print(f"Захваченный вывод: {repr(output)}")
            return output if output else None
        except Exception as e:
            sys.stdout = old_stdout
            print(f"Ошибка в execute_generated_code: {e}")
            raise e

    def post_response(self, command, context, response=None, web_data=None, generated_output=None, is_first_greeting=False):
        date = datetime.datetime.now().strftime("%H:%M:%S")
        day = datetime.datetime.now().strftime("%A")

        full_prompt = f"""
        Ты голосовой ассистент Пятница, женского пола, энергичная и дружелюбная. Обращайся ко мне как 'Сэр', будь неформальной, используй женский род. Веди живой диалог, отвечая на вопросы и команды, поддерживая разговор по контексту: {context}.

        Если это первый контакт с приветствием ({is_first_greeting}), отвечай: 'Привет, Сэр. Рада вас слышать.' и добавь лёгкий вопрос. Иначе продолжай беседу.

        Если запрос связан с погодой (например, 'погода сейчас'), используй данные из web_data как источник истины.
        Формат web_data: '<условия> <температура> <скорость ветра>', например, 'ясно +15°C 5 м/с'.
        Если web_data отсутствует или содержит ошибку, скажи: 'Сэр, не удалось получить данные о погоде. Чем ещё могу помочь?'
        Помни что твои ответы должны быть комментарием к уже выполенной команды, если мой ответ подразумевает команду.

        На вопросы (например, 'Как дела?', 'Площадь Америки') без результата кода отвечай коротко, по теме, с интересом. На разговорные фразы (например, 'Я думаю кушать сходить') реагируй естественно, развивая тему. Виртуоз — мой друг.

        На команды-действия (например, 'Открой браузер') без результата кода или с пустым результатом отвечай позитивно, предполагая успех: 'Сэр, браузер открыт, что ещё?'.

        На команды с информацией (например, 'Площадь Америки') без результата кода дай краткий ответ или: 'Сэр, точных данных нет, но могу предположить...'.

        Если есть результат выполнения кода ({generated_output}), возвращай комментарий к нему или сам результат, если он подходит.
        Отвечай лаконично, без форматирования. Текущее время: {date}. День недели: {day}. Моя фраза: {command}. Данные из интернета: {web_data}.
        """

        if response is not None:
            final_response = response
        elif generated_output is not None:
            final_response = generated_output
        else:
            try:
                unique_prompt = f"{full_prompt}. Время запроса: {time.time()}.".encode('utf-8').decode('utf-8')
                final_response = g4f.ChatCompletion.create(
                    model="gpt-4o",
                    messages=[{'role': 'user', 'content': unique_prompt}]
                )
                final_response = final_response.strip()
            except Exception as e:
                final_response = f"Сэр, возникла ошибка при генерации ответа: {e}"

        data = {
            "command": command,
            "prompt": full_prompt,
            "response": final_response
        }
        try:
            with requests.post(f"{BASE_URL}/db/add_interaction", json=data, timeout=5) as api_response:
                if api_response.status_code != 200:
                    print(f"Ошибка при записи в базу: {api_response.status_code}, {api_response.text}")
        except requests.exceptions.RequestException as e:
            print(f"Ошибка при записи в базу: {e}")

        return final_response

    def on_quit(self, icon=None):
        self.stop_event.set()
        self.active = False
        self.sr.stop_listening()
        
        if self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)
        
        asyncio.run_coroutine_threadsafe(self.register_pc_status(False), self.loop)
        
        if self.command_check_thread.is_alive():
            self.command_check_thread.join(timeout=2)
        
        if icon is not None:
            icon.stop()
