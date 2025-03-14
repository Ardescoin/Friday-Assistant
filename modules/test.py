import asyncio
import aiohttp

BASE_URL = "http://147.45.78.163:8000"

async def get_last_context_messages():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{BASE_URL}/db/get_interactions", timeout=5) as response:
                if response.status == 200:
                    context_data = await response.json()
                    message_context = context_data.get("context", "Контекст пуст")
                    
                    
                    if isinstance(message_context, str):
                        context_lines = message_context.strip().split("\n")
                        last_n_lines = context_lines[-5:]  
                        print("Последние сообщения из контекста:")
                        for line in last_n_lines:
                            print(line)
                    else:
                        print("Контекст в неожиданном формате:", message_context)
                else:
                    print(f"Ошибка получения контекста: статус {response.status}, текст {await response.text()}")
    except aiohttp.ClientError as e:
        print(f"Не удалось связаться с сервером: {str(e)}")


if __name__ == "__main__":
    asyncio.run(get_last_context_messages())