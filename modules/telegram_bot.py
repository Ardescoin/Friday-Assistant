import asyncio
import time
import pytz
from datetime import datetime
import g4f
import requests
import aiohttp
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
import os
import logging
import glob

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BASE_URL = "http://46.29.160.114:8000"
TOKEN = "7295154693:AAFGkc8kzvNxMqRW8Wo5SonvMvVH_lzANw0"

logger.info("Импорт модулей завершён")

class TelegramBot:
    def __init__(self):
        logger.info("Начало инициализации TelegramBot")
        self.application = Application.builder().token(TOKEN).build()
        self.pc_active = False
        self.g4f_client = g4f.Client()  
        self.image_dir = "generated_images"  
        os.makedirs(self.image_dir, exist_ok=True)  
        logger.info("Application и g4f клиент созданы")
        
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        self.application.add_handler(MessageHandler(filters.Document.ALL, self.handle_file))
        logger.info("Telegram-бот запущен")
        
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
                except aiohttp.ClientError as e:
                    self.pc_active = False
                    logger.error(f"Ошибка подключения к серверу: {str(e)}")
                await asyncio.sleep(5)

    async def fetch_web_data(self, query):
        async with aiohttp.ClientSession() as session:
            if "погода" in query.lower():
                city = "Kazan"
                url = f"https://wttr.in/{city}?format=%C+%t+%w"
                try:
                    async with session.get(url, timeout=5) as response:
                        if response.status == 200:
                            return (await response.text()).strip()  
                        return "Не удалось получить данные о погоде"
                except aiohttp.ClientError as e:
                    logger.error(f"Ошибка подключения при запросе погоды: {str(e)}")
                    return f"Ошибка подключения: {str(e)}"
            return None

    async def get_context(self):
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
                                image_prompt = None
                                if lines[i].startswith("Пользователь: "):
                                    user_cmd = lines[i].replace("Пользователь: ", "").strip()
                                    i += 1
                                    if i < len(lines) and lines[i].startswith("Пятница: "):
                                        assistant_resp = lines[i].replace("Пятница: ", "").strip()
                                        i += 1
                                        if i < len(lines) and lines[i].startswith("ImagePrompt: "):
                                            image_prompt = lines[i].replace("ImagePrompt: ", "").strip()
                                if user_cmd and assistant_resp:
                                    recent_interactions.append((user_cmd, assistant_resp, image_prompt))
                                i += 1
                            unique_interactions = list(dict.fromkeys((cmd, resp, img_p) for cmd, resp, img_p in recent_interactions[::-1]))[:25]
                            context = "Контекст последних взаимодействий:\n"
                            for i, (cmd, resp, img_p) in enumerate(unique_interactions):
                                context += f"[{i+1}] Вы: {cmd} | Я: {resp}"
                                if img_p:
                                    context += f" | ImagePrompt: {img_p}"
                                context += "\n"
                        else:
                            context = "Контекст пока пуст.\n"
                        logger.info(f"Обработанный контекст: {context}")
                        return context
                    else:
                        logger.warning(f"Ошибка при получении контекста: {response.status}")
                        return "Ошибка получения контекста от сервера.\n"
            except aiohttp.ClientError as e:
                logger.error(f"Ошибка соединения с сервером при получении контекста: {str(e)}")
                return "Не удалось подключиться к серверу для получения контекста.\n"
            except ValueError as e:
                logger.error(f"Ошибка парсинга JSON: {str(e)}")
                return "Ошибка формата данных от сервера.\n"

    async def generate_image(self, prompt):
        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.g4f_client.images.generate(
                    model="dall-e-3",  
                    prompt=prompt
                )
            )
            
            image_files = glob.glob(os.path.join(self.image_dir, "*.png")) + \
                         glob.glob(os.path.join(self.image_dir, "*.jpg")) + \
                         glob.glob(os.path.join(self.image_dir, "*.jpeg"))
            if not image_files:
                logger.error("No image files found in generated_images")
                return None
            
            latest_image = max(image_files, key=os.path.getctime)
            logger.info(f"Found latest image: {latest_image}")
            return latest_image
        except Exception as e:
            logger.error(f"Ошибка генерации изображения: {str(e)}")
            return None

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.message.chat_id
        command = update.message.text.strip()
        command_lower = command.lower()
        logger.info(f"Получена команда от {chat_id}: {command}")

        message_context = await self.get_context()
        
        is_image_command = any(keyword in command_lower for keyword in ["сгенерируй", "нарисуй"])
        
        if is_image_command:
            image_prompt = command
            
            image_path = await self.generate_image(image_prompt)
            if image_path and os.path.exists(image_path):
                response_text = f"Сэр, вот ваше изображение! Что скажете?"
                try:
                    with open(image_path, "rb") as photo:
                        await update.message.reply_photo(photo=photo, caption=response_text)
                    logger.info(f"Изображение отправлено: {image_path}")
                    
                    os.remove(image_path)
                    logger.info(f"Изображение удалено: {image_path}")
                    
                    await self.post_response(command, message_context, image_prompt=image_prompt)
                except Exception as e:
                    logger.error(f"Ошибка отправки изображения: {str(e)}")
                    response_text = "Сэр, не удалось отправить изображение. Попробуем ещё раз?"
                    await update.message.reply_text(response_text)
                    await self.post_response(command, message_context, response=response_text)
            else:
                response_text = "Сэр, не удалось сгенерировать изображение. Может, попробуем ещё раз?"
                await update.message.reply_text(response_text)
                await self.post_response(command, message_context, response=response_text)
            return

        if self.pc_active:
            logger.info(f"ПК активен, отправляю команду: {command}")
            if command_lower.startswith("отправить файл "):
                filename = command_lower.replace("отправить файл ", "").strip()
                try:
                    response = requests.post(f"{BASE_URL}/pc/command", json={"command": f"upload_file:{filename}"}, timeout=5)
                    logger.info(f"POST /pc/command response: {response.status_code}, {response.text}")
                    if response.status_code == 200:
                        response_data = response.json()
                        if "command_id" in response_data:
                            command_id = response_data["command_id"]
                            logger.info(f"Получен command_id: {command_id}")
                            
                            for attempt in range(30):
                                try:
                                    resp = requests.get(f"{BASE_URL}/pc/response/{command_id}", timeout=5)
                                    logger.info(f"GET /pc/response/{command_id} attempt {attempt + 1}: {resp.status_code}, {resp.text}")
                                    if resp.status_code == 200:
                                        bot_response = resp.json()["response"]
                                        logger.info(f"Получен ответ от ПК: '{bot_response}'")
                                        
                                        if "загружен на сервер" in bot_response.lower():
                                            logger.info(f"Файл загружен, пытаюсь скачать: {filename}")
                                            
                                            file_response = requests.get(f"{BASE_URL}/pc/get_file/{filename}", timeout=10)
                                            logger.info(f"GET /pc/get_file/{filename} response: {file_response.status_code}, {file_response.text if file_response.status_code != 200 else 'OK'}")
                                            if file_response.status_code == 200:
                                                temp_file = f"temp_{filename}"
                                                with open(temp_file, "wb") as f:
                                                    f.write(file_response.content)
                                                logger.info(f"Файл сохранен локально: {temp_file}")
                                                
                                                with open(temp_file, "rb") as f:
                                                    await context.bot.send_document(
                                                        chat_id=chat_id,
                                                        document=f,
                                                        filename=filename,
                                                        caption="Вот ваш файл!",
                                                        parse_mode="Markdown"
                                                    )
                                                os.remove(temp_file)
                                                logger.info(f"Файл отправлен в Telegram: {filename}")
                                            else:
                                                logger.error(f"Ошибка скачивания файла: {file_response.status_code}, {file_response.text}")
                                                await update.message.reply_text(f"Ошибка скачивания файла с сервера: {file_response.status_code}, {file_response.text}")
                                            return
                                        else:
                                            logger.info(f"Ответ не указывает на успешную загрузку: {bot_response}")
                                            await update.message.reply_text(bot_response)
                                            return
                                    elif resp.status_code == 404:
                                        logger.info(f"Ответ еще не готов на попытке {attempt + 1}")
                                except requests.exceptions.RequestException as e:
                                    logger.error(f"Ошибка при запросе ответа: {str(e)}")
                                await asyncio.sleep(1)
                            logger.warning("ПК не ответил вовремя")
                            await update.message.reply_text("Сэр, ПК не ответил вовремя. Попробуйте позже")
                        else:
                            logger.error("Нет command_id в ответе сервера")
                            await update.message.reply_text("Ошибка: нет command_id от сервера")
                    else:
                        logger.error(f"Ошибка сервера: {response.status_code}, {response.text}")
                        await update.message.reply_text(f"Ошибка сервера: {response.status_code}, {response.text}")
                except requests.exceptions.RequestException as e:
                    logger.error(f"Не удалось связаться с ПК: {str(e)}")
                    await update.message.reply_text(f"Не удалось связаться с ПК: {str(e)}")
            else:
                try:
                    response = requests.post(f"{BASE_URL}/pc/command", json={"command": command}, timeout=5)
                    if response.status_code == 200:
                        response_data = response.json()
                        if "command_id" in response_data:
                            command_id = response_data["command_id"]
                            for _ in range(30):
                                try:
                                    resp = requests.get(f"{BASE_URL}/pc/response/{command_id}", timeout=5)
                                    if resp.status_code == 200:
                                        bot_response = resp.json()["response"]
                                        await update.message.reply_text(bot_response)
                                        return
                                    else:
                                        self.pc_active = False
                                except requests.exceptions.RequestException:
                                    pass
                                await asyncio.sleep(1)
                            await update.message.reply_text("Вам нужно переключиться между режимами")
                        else:
                            await update.message.reply_text("Ошибка: нет command_id от сервера")
                    else:
                        await update.message.reply_text(f"Ошибка сервера: {response.status_code}")
                except requests.exceptions.RequestException:
                    await update.message.reply_text("Не удалось связаться с ПК")
        else:
            logger.info("ПК не активен, переключаюсь в автономный режим")
            if command_lower.startswith("отправить файл "):
                await update.message.reply_text("Сэр, ПК не активен, не могу отправить файл")
            else:
                needs_internet = "погода" in command_lower
                web_data = await self.fetch_web_data(command) if needs_internet else None
                response = await self.post_response(command, message_context, web_data=web_data)
                await update.message.reply_text(response)

    async def handle_file(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.message.chat_id
        file = update.message.document
        logger.info(f"Получен файл от {chat_id}: {file.file_name}")

        temp_file = f"temp_{file.file_name}"
        try:
            file_info = await context.bot.get_file(file.file_id)
            await file_info.download_to_drive(temp_file)
            logger.info(f"Файл успешно скачан локально: {temp_file}")
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

    async def post_response(self, command, context, web_data=None, response=None, image_prompt=None):
        timezone = pytz.timezone('Europe/Moscow')
        moscow_time = datetime.now(timezone).strftime("%Y-%m-%d %H:%M:%S")
        
        if not response:  
            full_prompt = (
                "Ты голосовой ассистент по имени Пятница — энергичный, дружелюбный и немного остроумный собеседник. "
                "Твоя цель — вести естественный, живой диалог, отвечая на вопросы, поддерживая разговор и реагируя на команды. "
                "Обращайся ко мне как 'Сэр', будь неформальной и тёплой. "
                "Никогда не начинай ответ с приветствия вроде 'Привет, Сэр' или 'Здравствуйте', даже если я сказал 'привет'. "
                "Обязательно используй контекст моих последних фраз для связных и логичных ответов. "
                "ВАЖНО: Если запрос связан с погодой (например, 'погода сейчас'), используй данные из web_data как источник истины. "
                "Формат web_data: '<условия> <температура> <скорость ветра>', например, 'ясно +15°C 5 м/с'. "
                "Если web_data отсутствует или содержит ошибку, скажи: 'Сэр, не удалось получить данные о погоде. Чем ещё могу помочь?' "
                "ВАЖНО: Если я спрашиваю текущее время или дату, используй переданные текущие дату и время. "
                "ВАЖНО: Если я спрашиваю местоположение, используй переданное текущее местоположение (Казань). "
                "Если запрос не требует внешних данных, отвечай кратко и по теме, добавляя лёгкий комментарий или вопрос для продолжения беседы. "
                "Отвечай без лишнего форматирования, только текст."
                f"\nКонтекст последних взаимодействий (учитывай для ответа):\n{context}"
                f"\nМоя текущая фраза: {command}"
                f"\nДанные из интернета (используй, если есть): {web_data}"
                f"\nТекущие дата и время: {moscow_time}"
                f"\nТекущее местоположение: Казань"
            )

            try:
                gpt_response = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self.g4f_client.chat.completions.create(
                        model="gpt-4o",  
                        messages=[{'role': 'user', 'content': full_prompt}]
                    )
                )
                if isinstance(gpt_response, str):
                    response = gpt_response.strip()
                elif hasattr(gpt_response, 'choices') and gpt_response.choices:
                    response = gpt_response.choices[0].message.content.strip()
                else:
                    response = "Сэр, ответ от GPT пустой. Чем ещё могу помочь?"
            except Exception as e:
                logger.error(f"Ошибка генерации ответа через g4f: {str(e)}")
                response = "Сэр, что-то пошло не так. Чем ещё могу помочь?"

        data = {
            "command": command,
            "prompt": full_prompt if not image_prompt else f"Image generation: {image_prompt}",
            "response": response,
            "image_prompt": image_prompt,
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(f"{BASE_URL}/db/add_interaction", json=data, timeout=5) as api_response:
                    if api_response.status != 200:
                        logger.warning(f"Ошибка при записи в базу: {api_response.status}")
            except aiohttp.ClientError as e:
                logger.error(f"Ошибка при записи в базу: {str(e)}")

        return response

    def run(self):
        logger.info("Запускаю run_polling")
        self.application.run_polling()

if __name__ == "__main__":
    logger.info("Запуск основного блока")
    bot = TelegramBot()
    bot.run()