import asyncio
import time
import pytz
from datetime import datetime
import g4f
import requests
import aiohttp
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from additional import add
import os

BASE_URL = "http://147.45.78.163:8000"

print("Импорт модулей завершён")

class TelegramBot:
    def __init__(self):
        print("Начало инициализации TelegramBot")
        self.application = Application.builder().token(TOKEN).build()
        self.pc_active = False
        print("Application создан")
        
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        self.application.add_handler(MessageHandler(filters.Document.ALL, self.handle_file))
        print("Telegram-бот запущен")
        
        self.application.job_queue.run_once(self.start_background_tasks, 0)
        

    async def start_background_tasks(self, context: ContextTypes.DEFAULT_TYPE):
        asyncio.create_task(self.background_pc_status_check())

    async def background_pc_status_check(self):
        async with aiohttp.ClientSession() as session:
            while True:
                try:
                    async with session.get(f"{BASE_URL}/pc/status", timeout=10) as response:
                        if response.status == 200:
                            self.pc_active = (await response.json()).get("active", False)
                        else:
                            self.pc_active = False
                except aiohttp.ClientError:
                    self.pc_active = False
                await asyncio.sleep(5)

    async def fetch_web_data(self, query):
        async with aiohttp.ClientSession() as session:
            if "погода" in query.lower():
                city = "Kazan"
                url = f"https://wttr.in/{city}?format=%C+%t+%w"
                try:
                    async with session.get(url, timeout=5) as response:
                        if response.status == 200:
                            result = await response.text()
                            return result.strip()
                        return "Не удалось получить данные о погоде"
                except aiohttp.ClientError as e:
                    return f"Ошибка подключения: {str(e)}"
            return None

    async def get_context(self):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{BASE_URL}/db/get_interactions", timeout=5) as response:
                    if response.status == 200:
                        context_data = await response.json()
                        context_str = context_data.get("context", "Контекст пока пуст")
                        if context_str == "Контекст пока пуст":
                            return "Контекст пока пуст"
                        lines = context_str.split("\n")
                        user_commands = []
                        for i in range(0, len(lines), 2):
                            if i < len(lines) and lines[i].startswith("Пользователь: "):
                                cmd = lines[i].replace("Пользователь: ", "").strip()
                                user_commands.append(cmd)
                        unique_commands = []
                        seen = set()
                        for cmd in reversed(user_commands):
                            if cmd and cmd not in seen:
                                unique_commands.append(cmd)
                                seen.add(cmd)
                            if len(unique_commands) >= 5:
                                break
                        return "\n".join(f"[{i+1}] {cmd}" for i, cmd in enumerate(reversed(unique_commands))) if unique_commands else "Контекст пока пуст"
                    return f"Ошибка получения контекста: {response.status}"
        except aiohttp.ClientError:
            print("Ошибка подключения к серверу для контекста")
            return "Не удалось получить контекст из базы данных"

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.message.chat_id
        command = update.message.text.strip().lower()
        print(f"Получена команда от {chat_id}: {command}")
        print(f"Текущий статус ПК: {self.pc_active}")

        message_context = await self.get_context()

        if self.pc_active:
            print(f"ПК активен, отправляю команду: {command}")
            if command.startswith("отправить файл "):
                filename = command.replace("отправить файл ", "").strip()
                try:
                    response = requests.post(f"{BASE_URL}/pc/send_file", json={"filename": filename}, timeout=5)
                    if response.status_code == 200:
                        with open("temp_file", "wb") as f:
                            f.write(response.content)
                        with open("temp_file", "rb") as f:
                            await context.bot.send_document(chat_id=chat_id, document=f, filename=filename)
                        os.remove("temp_file")
                        await update.message.reply_text(f"Файл {filename} отправлен")
                    else:
                        await update.message.reply_text(f"Ошибка: {response.status_code}, {response.text}")
                except Exception as e:
                    await update.message.reply_text(f"Ошибка отправки файла: {str(e)}")
            else:
                try:
                    response = requests.post(f"{BASE_URL}/pc/command", json={"command": command}, timeout=5)
                    if response.status_code == 200:
                        response_data = response.json()
                        if "command_id" in response_data:
                            command_id = response_data["command_id"]
                            for _ in range(15):
                                try:
                                    resp = requests.get(f"{BASE_URL}/pc/response/{command_id}", timeout=5)
                                    if resp.status_code == 200:
                                        bot_response = resp.json()["response"]
                                        await update.message.reply_text(bot_response)
                                        return
                                except requests.exceptions.RequestException:
                                    pass
                                await asyncio.sleep(1)
                            await update.message.reply_text("Выполнено")
                        else:
                            await update.message.reply_text("Ошибка: нет command_id от сервера")
                    else:
                        await update.message.reply_text(f"Ошибка сервера: {response.status_code}")
                except requests.exceptions.RequestException:
                    await update.message.reply_text("Не удалось связаться с ПК")
        else:
            print("ПК не активен, переключаюсь в автономный режим")
            if command.startswith("отправить файл "):
                await update.message.reply_text("Сэр, ПК не активен, не могу отправить файл")
            else:
                needs_internet = "погода" in command
                web_data = None
                
                if needs_internet:
                    web_data = await self.fetch_web_data(command)
                response = await self.post_response(command, message_context, web_data=web_data, is_first_greeting="привет" in command)
                await update.message.reply_text(response)

    async def handle_file(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.message.chat_id
        file = update.message.document
        print(f"Получен файл от {chat_id}: {file.file_name}")

        
        temp_file = f"temp_{file.file_name}"
        try:
            file_info = await context.bot.get_file(file.file_id)
            await file_info.download_to_drive(temp_file)  
            print(f"Файл успешно скачан локально: {temp_file}")
        except Exception as e:
            await update.message.reply_text(f"Ошибка скачивания файла из Telegram: {str(e)}")
            return

        
        try:
            with open(temp_file, "rb") as f:
                files = {"file": (file.file_name, f, "application/octet-stream")}
                response = requests.post(f"{BASE_URL}/pc/receive_file", files=files, timeout=10)
            if response.status_code == 200:
                response_data = response.json()
                await update.message.reply_text(response_data["status"])
            else:
                await update.message.reply_text(f"Ошибка сохранения файла: {response.status_code}, {response.text}")
        except requests.exceptions.RequestException as e:
            await update.message.reply_text(f"Ошибка при отправке файла на сервер: {str(e)}")
        finally:
            if os.path.exists(temp_file):
                os.remove(temp_file)

    async def post_response(self, command, context, web_data=None, is_command=False, generated_output=None, is_first_greeting=False):
        timezone = pytz.timezone('Europe/Moscow')
        moscow_time = datetime.now(timezone)
        full_prompt = (
            "Ты голосовой ассистент по имени Пятница — энергичный, дружелюбный и немного остроумный собеседник. "
            "Твоя цель — вести естественный, живой диалог со мной, отвечая на вопросы, поддерживая разговор и реагируя на команды. "
            "Обращайся ко мне как 'Сэр', но будь неформальной и тёплой. "
            "Если мой запрос требует актуальной информации о погоде (например, 'погода сейчас'), "
            "у тебя есть свежие данные в web_data. Используй их как источник истины и структурируй ответ логично и понятно: "
            "для погоды — температура и условия. "
            f"Контекст моих последних фраз (используй его для ответа):\n{context}\n"
            f"Моя текущая фраза: {command}\n"
            f"Свежие данные из интернета (если есть): {web_data}\n"
            f"Это мой первый контакт с приветствием: {is_first_greeting}\n"
            f"Здесь дополнительная информация для пользования: {add}\n"
            f"Текущие дата и время: {moscow_time}"
        )

        if generated_output:
            response = str(generated_output)
        else:
            unique_prompt = f"{full_prompt}. Время запроса: {time.time()}."
            try:
                gpt_response = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: g4f.ChatCompletion.create(
                        model=g4f.models.llama_3_1_405b,
                        messages=[{'role': 'user', 'content': unique_prompt}]
                    )
                )
                if isinstance(gpt_response, str):
                    response = gpt_response.strip()
                elif isinstance(gpt_response, list) and gpt_response:
                    response = gpt_response[0].strip()
                else:
                    response = "Сэр, ответ от GPT пустой. Чем ещё могу помочь?"
            except Exception as e:
                response = f"Ошибка генерации ответа через g4f: {str(e)}"

        data = {
            "command": command,
            "prompt": full_prompt,
            "response": response
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(f"{BASE_URL}/db/add_interaction", json=data, timeout=5) as api_response:
                    if api_response.status != 200:
                        print(f"Ошибка при записи в базу: {api_response.status}, {await api_response.text()}")
            except aiohttp.ClientError as e:
                print(f"Ошибка при записи в базу: {str(e)}")

        return response

    def run(self):
        print("Запускаю run_polling")
        self.application.run_polling()
        print("run_polling завершён (это не должно появиться)")

if __name__ == "__main__":
    print("Запуск основного блока")
    bot = TelegramBot()
    bot.run()
