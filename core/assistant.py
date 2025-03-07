# core/assistant.py
import threading
import time
import g4f
import sqlite3
from modules.gpt import get_gpt_response
from modules.protocols import Weekend
import sys
from io import StringIO
import importlib
import asyncio

class Assistant:
    def __init__(self, speech_recognition, text_to_speech):
        self.sr = speech_recognition
        self.tts = text_to_speech
        self.voice_input_active = threading.Event()
        self.stop_event = threading.Event()
        self.active = False
        self.listening_thread = None
        self.weekend = Weekend(self.tts)
        
        self.dialogue_timeout = 60
        self.last_command_time = None
        
        self._initialize_database()
        self.sr.start_listening()  # Запускаем прослушивание при инициализации

    def _initialize_database(self):
        connection = sqlite3.connect('./db/neural_network_memory.db', isolation_level=None)
        connection.execute('PRAGMA journal_mode = WAL;')
        connection.execute('PRAGMA cache_size = -10000;')
        cursor = connection.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS interactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                command TEXT,
                prompt TEXT,
                response TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON interactions(timestamp)')
        connection.commit()
        connection.close()
        print("База данных и таблица interactions инициализированы.")
        
    def start_listening_task(self):
        asyncio.run(self.listen_for_command_async())  
    
    def start_listener(self):
        print("ВКЛ")
        self.voice_input_active.set()
        self.active = True
        self.listening_thread = threading.Thread(target=self.start_listening_task, daemon=False)
        self.listening_thread.start()
        
    async def listen_for_command_async(self):
        while self.voice_input_active.is_set() and not self.stop_event.is_set():
            try:
                command = self.sr.get_command()  # Получаем команду из очереди
                if command is None:  # Сигнал остановки или таймаут
                    await asyncio.sleep(0.1)
                    continue
                if command and command.strip():
                    if (self.last_command_time is None and "пятница" in command.lower()) or \
                    (self.last_command_time is not None and (time.time() - self.last_command_time) < self.dialogue_timeout):
                        
                        connection = sqlite3.connect('./db/neural_network_memory.db', isolation_level=None)
                        cursor = connection.cursor()
                        
                        cursor.execute('SELECT DISTINCT command FROM interactions ORDER BY id DESC')
                        all_commands = cursor.fetchall()
                        recent_commands = all_commands[:3]
                        context = "Контекст моих последних фраз:\n" + \
                                "\n".join(f"[{i+1}] {cmd[0]}" for i, cmd in enumerate(reversed(recent_commands))) + "\n"
                        connection.close()
                        print(f"Контекст: {context}")
                        
                        is_first_greeting = "привет" in command.lower() and self.last_command_time is None

                        if "протокол выходной" in command.lower() or "выходной протокол" in command.lower():
                            await self.weekend.run_exit_protocol()
                            response = self.post_response(command, context, is_first_greeting=is_first_greeting)
                            print(f"Ответ: {response}")
                            self.tts.speak(response)
                        else:
                            generated_code = get_gpt_response(command)  
                            if generated_code and generated_code.strip():
                                try:
                                    output = self.execute_generated_code(generated_code)
                                    print(f"Сгенерированный код: {generated_code}")
                                    if output is not None and output != "Команда выполнена, Сэр":
                                        response = self.post_response(command, context, generated_output=output, is_first_greeting=is_first_greeting)
                                    else:
                                        response = self.post_response(command, context, generated_output="Команда выполнена, Сэр", is_first_greeting=is_first_greeting)
                                    print(f"Ответ: {response}")
                                    has_spoken = self.tts.restore_output()  
                                    if not has_spoken:
                                        self.tts.speak(response)
                                except Exception as e:
                                    print(f"Ошибка при выполнении кода: {e}")
                                    response = self.post_response(command, context, generated_output=f"Ошибка: {str(e)}", is_first_greeting=is_first_greeting)
                                    print(f"Ответ: {response}")
                                    self.tts.speak(response)
                            else:
                                response = self.post_response(command, context, is_first_greeting=is_first_greeting)
                                print(f"Ответ: {response}")
                                self.tts.speak(response)
                        
                        self.last_command_time = time.time()
                    else:
                        print(f"Пропущено: {command} (нет ключевого слова)")
                await asyncio.sleep(0.1)  # Короткая пауза перед следующим циклом
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
            
            self.tts.redirect_output()
            
            exec_globals = {}
            exec(code, exec_globals)
            
            self.tts.restore_output()

            return "Команда выполнена, Сэр"
        except Exception as e:
            self.tts.restore_output()
            raise e

    def post_response(self, command, context, is_command=False, generated_output=None, is_first_greeting=False):
        connection = sqlite3.connect('./db/neural_network_memory.db', isolation_level=None)
        cursor = connection.cursor()

        full_prompt = (
            "Ты голосовой ассистент по имени Пятница — энергичный, дружелюбный и немного остроумный собеседник. "
            "Твоя цель — вести естественный, живой диалог со мной, отвечая на вопросы, поддерживая разговор и реагируя на команды. "
            "Обращайся ко мне как 'Сэр', но будь неформальной и тёплой. "
            "Если это мой первый контакт и я здороваюсь (например, 'Привет, Пятница'), отвечай в духе приветствия: 'Привет, Сэр! Рад вас слышать!' "
            "и добавь лёгкий вопрос или комментарий для продолжения беседы. В последующих ответах не повторяй приветствие, а продолжай разговор. "
            "Если я задаю вопрос (например, 'Как дела?', 'Что думаешь о картошке?', 'Площадь Америки'), отвечай коротко, по теме и с интересом, "
            "добавляя свой взгляд или вопрос, если это уместно. "
            "Если я говорю что-то не связанное с командой (например, 'Я думаю кушать сходить'), поддерживай разговор естественно, "
            "опираясь на контекст моих последних фраз, и развивай тему дальше, а не повторяй один и тот же вопрос. "
            "Если я соглашаюсь или повторяю ответ (например, 'Все варианты', 'Я согласен'), признавай это и предлагай что-то новое, связанное с темой. "
            "Если я даю явную команду, которая подразумевает действие (например, 'Открой браузер'), и есть результат выполнения кода, "
            "верни этот результат. Если кода нет, считай, что команда выполнена, и дай короткий комментарий в одной строке, "
            "а для простых команд добавь 1-2 варианта будущих запросов вроде 'Что дальше, Сэр? Узнать новости или включить музыку?' "
            "Обязательно используй контекст моих последних фраз для связных и логичных ответов, соединяя текущую фразу с предыдущими, "
            "и избегай повторения вопросов, если я уже ответил. "
            "ВАЖНО: Если команда подразумевает предоставление информации (например, 'Площадь Америки'), и нет результата из кода, "
            "дай краткий ответ с известной тебе информацией или скажи 'Сэр, точных данных у меня нет, но могу предположить...' "
            "и предложи разумное значение или уточнение. "
            "Если результат из кода есть, используй его как ответ и не добавляй ничего лишнего. "
            "Отвечай только текстом, без ** "
            "ВАЖНО: ЕСЛИ ТЕБЯ ПРОСЯТ СКАЗАТЬ КАКУЮ-ТО УСТНУЮ ИНФОРМАЦИЮ, КОТОРУЮ ТЫ НЕ ЗНАЕШЬ, ТО Верни \"Сэр, этой информации у меня нет.\" "
            "Примеры поведения:\n"
            "- Я: 'Я люблю картошку' → Ты: 'Картошка — это класс, Сэр! Какой вариант вам больше по душе — фри или пюре?'\n"
            "- Я: 'Все варианты' → Ты: 'Любитель всего картофельного, Сэр! Может, устроить картофельный день? Что бы вы начали готовить?'\n"
            "- Я: 'Площадь Америки' → Ты: 'Площадь Америки — около 9.8 миллионов квадратных километров, Сэр! Это если брать США.'\n"
            f"Контекст моих последних фраз (используй его для ответа):\n{context}\n"
            f"Моя текущая фраза: {command}\n"
            f"Это мой первый контакт с приветствием: {is_first_greeting}"
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

        cursor.execute('INSERT INTO interactions (command, prompt, response) VALUES (?, ?, ?)',
                       (command, full_prompt, response))
        connection.commit()
        connection.close()

        return response

    def on_quit(self, icon, item):
        self.stop_event.set()
        self.active = False
        self.sr.stop_listening()  # Останавливаем прослушивание
        icon.stop()