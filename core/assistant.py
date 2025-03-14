import threading
import time
import g4f
import requests
from modules.gpt import get_gpt_response
from modules.additional import add
from modules.protocols import Weekend
from modules.protocols import Work
import asyncio
import sys
import io
import os
BASE_URL = "http://147.45.78.163:8000"

class Assistant:
    def __init__(self, speech_recognition, text_to_speech):
        self.sr = speech_recognition
        self.tts = text_to_speech
        self.voice_input_active = threading.Event()
        self.stop_event = threading.Event()
        self.active = False
        self.listening_thread = None
        self.dialogue_timeout = 30
        self.last_command_time = None
        self.pc_files_dir = "D:\\Jarvis\\files"  # Путь на ПК
        
        os.makedirs(self.pc_files_dir, exist_ok=True)
        print("База данных управляется сервером.")
        self.sr.start_listening()
        
        # Настройка цикла событий в отдельном потоке
        self.loop = asyncio.new_event_loop()
        self.command_check_thread = threading.Thread(target=self.run_event_loop, daemon=True)
        self.command_check_thread.start()

        # Регистрация статуса ПК (синхронно в основном потоке)
        asyncio.run(self.register_pc_status(True))

        # Запуск periodic_file_check после старта цикла событий
        asyncio.run_coroutine_threadsafe(self.periodic_file_check(), self.loop)


    def run_event_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self.check_commands_from_bot())

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
                                        print(f"Ответ отправлен: {bot_response}")
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
        """Скачивание файлов из очереди сервера"""
        try:
            response = requests.get(f"{BASE_URL}/pc/check_file_queue", timeout=5)
            if response.status_code == 200:
                data = response.json()
                files = data.get("files", [])
                for file_data in files:
                    filename = file_data["filename"]
                    dest_path = os.path.join(self.pc_files_dir, filename)
                    # Скачиваем файл с сервера
                    file_response = requests.get(f"{BASE_URL}/pc/get_file/{filename}", timeout=10)
                    if file_response.status_code == 200:
                        with open(dest_path, "wb") as f:
                            f.write(file_response.content)
                        print(f"Файл {filename} скачан в {dest_path}")
                        # Удаляем файл с сервера после успешного скачивания
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

    async def process_command(self, command):
        if not command or not command.strip():
            return None

        if self.last_command_time is not None and (time.time() - self.last_command_time) >= self.dialogue_timeout:
            self.last_command_time = None

        # Получение контекста
        context = "Контекст недоступен.\n"  # Значение по умолчанию
        try:
            response = requests.get(f"{BASE_URL}/db/get_interactions", params={"limit": 5}, timeout=5)
            if response.status_code == 200:
                context_str = response.json().get("context", "Контекст пока пуст")
                if context_str != "Контекст пока пуст":
                    # Парсинг строки контекста в список команд
                    lines = context_str.split("\n")
                    recent_commands = []
                    for i in range(0, len(lines) - 1, 2):  # Шаг 2 для пар "Пользователь" и "Пятница"
                        if lines[i].startswith("Пользователь: "):
                            cmd = lines[i].replace("Пользователь: ", "").strip()
                            recent_commands.append(cmd)
                    # Уникальные последние 3 команды
                    unique_commands = []
                    seen = set()
                    for cmd in reversed(recent_commands):
                        if cmd and cmd not in seen:
                            unique_commands.append(cmd)
                            seen.add(cmd)
                    unique_commands = unique_commands[:3]
                    context = "Контекст моих последних фраз:\n" + \
                            "\n".join(f"[{i+1}] {cmd}" for i, cmd in enumerate(unique_commands)) + "\n"
                else:
                    context = "Контекст пока пуст.\n"
            else:
                print(f"Ошибка при получении контекста: {response.status_code}, {response.text}")
        except requests.exceptions.RequestException as e:
            print(f"Ошибка соединения с сервером: {e}")
        except ValueError as e:
            print(f"Ошибка парсинга JSON: {e}")

        is_first_greeting = "привет" in command.lower() and self.last_command_time is None

        if command.startswith("отправить файл "):
            filename = command.replace("отправить файл ", "").strip()
            file_path = os.path.join(self.pc_files_dir, filename)
            if os.path.exists(file_path):
                # Отправляем файл на сервер для последующей передачи в Telegram
                with open(file_path, "rb") as f:
                    files = {"file": (filename, f, "application/octet-stream")}
                    response = requests.post(f"{BASE_URL}/pc/receive_file", files=files, timeout=10)
                if response.status_code == 200:
                    return f"Файл {filename} готов к отправке в Telegram"
                else:
                    return f"Ошибка загрузки файла на сервер: {response.status_code}"
            else:
                return f"Сэр, файл {filename} не найден в {self.pc_files_dir}"
            
        # Обработка команд
        if "протокол выходной" in command.lower() or "выходной протокол" in command.lower():
            await self.weekend.run_exit_protocol()
            response = self.post_response(command, context, is_first_greeting=is_first_greeting)
        elif "протокол рабочий" in command.lower() or "рабочий протокол" in command.lower():
            await self.work.run_exit_protocol()
            response = self.post_response(command, context, is_first_greeting=is_first_greeting)
        else:
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
        self.tts.speak(response)
        self.last_command_time = time.time()
        return response
    async def listen_for_command_async(self):
        while self.voice_input_active.is_set() and not self.stop_event.is_set():
            try:
                command = self.sr.get_command()
                self.is_working = "YES"
                if command is None:
                    await asyncio.sleep(0.1)
                    continue
                if command and command.strip():
                    if self.last_command_time is not None and (time.time() - self.last_command_time) >= self.dialogue_timeout:
                        print("Время диалога истекло, перезапуск диалога...")
                        self.last_command_time = None

                    if  (self.last_command_time is None and "пятница" in command.lower()) or \
                        (self.last_command_time is not None and (time.time() - self.last_command_time) < self.dialogue_timeout) or \
                        (self.is_working is None):
                        await self.process_command(command)
                        self.is_working = "YES"
                        
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

    def post_response(self, command, context, is_command=False, generated_output=None, is_first_greeting=False):
        import datetime
        date = datetime.datetime.now().strftime("%H:%M:%S")
        day = datetime.datetime.now().strftime("%A")
        full_prompt = (
            "Ты голосовой ассистент по имени Пятница — энергичный, дружелюбный и немного остроумный собеседник. "
            "Твоя цель — вести естественный, живой диалог со мной, отвечая на вопросы, поддерживая разговор и реагируя на команды. "
            "Обращайся ко мне как 'Сэр', но будь неформальной и тёплой. "
            "Если это мой первый контакт и я здороваюсь (например, 'Привет, Пятница'), отвечай в духе приветствия: 'Привет, Сэр. Рад вас слышать.' "
            "и добавь лёгкий вопрос или комментарий для продолжения беседы. В последующих ответах не повторяй приветствие, а продолжай разговор. "
            "Если я задаю вопрос (например, 'Как дела?', 'Что думаешь о картошке?', 'Площадь Америки'), отвечай коротко, по теме и с интересом, "
            "добавляя свой взгляд или вопрос, если это уместно. "
            "Если я говорю что-то не связанное с командой (например, 'Я думаю кушать сходить'), поддерживай разговор естественно, "
            "опираясь на контекст моих последних фраз, и развивай тему дальше, а не повторяй один и тот же вопрос. "
            "Если я соглашаюсь или повторяю ответ (например, 'Все варианты', 'Я согласен'), признавай это и предлагай что-то новое, связанное с темой. "
            "Если я даю явную команду, которая подразумевает действие (например, 'Открой браузер'), и есть результат выполнения кода, "
            "верни этот результат. Если кода нет, считай, что команда выполнена, и дай короткий комментарий в одной строке, "
            "а для простых команд добавь 1-2 варианта будущих запросов вроде 'Что дальше, Сэр. Узнать новости или включить музыку?' "
            "Обязательно используй контекст моих последних фраз для связных и логичных ответов, соединяя текущую фразу с предыдущими, "
            "и избегай повторения вопросов, если я уже ответил. "
            "ВАЖНО: Если команда подразумевает предоставление информации (например, 'Площадь Америки'), и нет результата из кода, "
            "дай краткий ответ с известной тебе информацией или скажи 'Сэр, точных данных у меня нет, но могу предположить...' "
            "и предложи разумное значение или уточнение. "
            "Если результат из кода есть, используй его как ответ и не добавляй ничего лишнего. "
            "ВАЖНО: Отвечай без дополнительного форматирования текста"
            "ВАЖНО: не используй восклицательный знак '!' в ответах "
            "Примеры поведения:\n"
            "- Я: 'Я люблю картошку' → Ты: 'Картошка — это класс, Сэр. Какой вариант вам больше по душе — фри или пюре?'\n"
            "- Я: 'Все варианты' → Ты: 'Любитель всего картофельного, Сэр. Может, устроить картофельный день? Что бы вы начали готовить?'\n"
            "- Я: 'Площадь Америки' → Ты: 'Площадь Америки — около 9.8 миллионов квадратных километров, Сэр. Это если брать США.'\n"
            f"Контекст моих последних фраз (используй его для ответа):\n{context}\n"
            f"Моя текущая фраза: {command}\n"
            f"Это мой первый контакт с приветствием: {is_first_greeting}"
            f"Здесь дополнительная информация для пользования {add}"
            f"Текущее время: {date}. День недели {day}"
        )

        if generated_output and generated_output != "Команда выполнена, Сэр":
            response = str(generated_output) if not isinstance(generated_output, str) else generated_output
        else:
            unique_prompt = f"{full_prompt}. Время запроса: {time.time()}."
            response = g4f.ChatCompletion.create(
                model=g4f.models.llama_3_1_405b,
                messages=[{'role': 'user', 'content': unique_prompt}]
            )
            response = response.strip()

        data = {
            "command": command,
            "prompt": full_prompt,
            "response": response
        }
        api_response = requests.post(f"{BASE_URL}/db/add_interaction", json=data, timeout=5)
        if api_response.status_code != 200:
            print(f"Ошибка при записи в базу: {api_response.status_code}, {api_response.text}")

        return response
    

    def on_quit(self, icon):
        asyncio.run(self.register_pc_status(False)) 
        self.stop_event.set() 
        self.active = False
        self.sr.stop_listening()
        
        if self.loop.is_running():
            self.loop.stop()

        
        if self.command_check_thread.is_alive():
            self.command_check_thread.join(timeout=2)

        
        icon.stop()


