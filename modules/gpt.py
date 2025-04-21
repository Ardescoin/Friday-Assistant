import requests
import g4f
import time
import sys
import os

def resource_path(relative_path):
    """ Получить путь к ресурсу (работает и в .py, и в .exe) """
    if getattr(sys, 'frozen', False):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

with open(resource_path('modules/prompt.txt'), 'r', encoding='utf-8') as file:
    main_prompt = file.read()


BASE_URL = "http://46.29.160.114:8000"

def get_gpt_response(command):
    try:
        
        response = requests.get(f"{BASE_URL}/db/get_interactions", params={"limit": 10}, timeout=5)
        if response.status_code != 200:
            print(f"Ошибка при получении предыдущих взаимодействий: {response.status_code}")
            previous_interactions = []
        else:
            context_str = response.json().get("context", "Контекст пока пуст")
            if context_str == "Контекст пока пуст":
                previous_interactions = []
            else:
                
                lines = context_str.split("\n")
                previous_interactions = []
                for i in range(0, len(lines) - 1, 2):  
                    if lines[i].startswith("Пользователь: ") and lines[i + 1].startswith("Пятница: "):
                        cmd = lines[i].replace("Пользователь: ", "").strip()
                        resp = lines[i + 1].replace("Пятница: ", "").strip()
                        previous_interactions.append([time.time(), cmd, resp])  

        
        prompt = main_prompt + "\n\n"
        prompt += "История предыдущих взаимодействий (важно учитывать контекст):\n"
        if previous_interactions:
            for i, interaction in enumerate(previous_interactions):
                prompt += f"--- Взаимодействие {i+1} ---\n"
                prompt += f"Команда: {interaction[1]}\n"
                prompt += f"Ответ: {interaction[2]}\n"
        else:
            prompt += "История взаимодействий отсутствует.\n"

        prompt += f"\nТекущая команда: {command}\n"
        prompt += "Твое имя Пятница. Сгенерируй только Python код, который выполняет текущую команда, учитывая историю. Код должен быть безопасным и соответствовать моим инструкциям. Не добавляй никаких объяснений, комментариев или форматирование"

        
        gpt_response = g4f.ChatCompletion.create(
            model=g4f.models.gpt_4o,
            messages=[{'role': 'user', 'content': prompt}]
        )

        
        if isinstance(gpt_response, str) and gpt_response.strip():
            response = gpt_response
        elif isinstance(gpt_response, list) and gpt_response:
            response = gpt_response[0].strip()
        else:
            print("Сгенерированный код пуст или имеет неверный формат.")
            return ""

        
        save_code_to_file(response)

        
        data = {
            "command": command,
            "prompt": prompt,
            "response": response
        }
        api_response = requests.post(f"{BASE_URL}/db/add_interaction", json=data, timeout=5)
        if api_response.status_code != 200:
            print(f"Ошибка при сохранении взаимодействия: {api_response.status_code}, {api_response.text}")

        return response

    except Exception as e:
        print(f"Ошибка при генерации ответа GPT: {str(e)}")
        return ""

def save_code_to_file(code):
    try:
        with open(resource_path("generated_code.py"), "w", encoding="utf-8") as file:
            file.write(code)
    except Exception as e:
        print(f"Ошибка при сохранении кода в файл: {e}")