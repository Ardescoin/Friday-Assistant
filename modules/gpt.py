import sqlite3
import g4f
from modules.prompt import main_prompt

def get_gpt_response(command):
    try:
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

        previous_interactions = get_previous_interactions(limit=10, cursor=cursor)

        prompt = main_prompt + "\n\n"  
        prompt += "История предыдущих взаимодействий (важно учитывать контекст):\n" 
        if previous_interactions: 
            for i, interaction in enumerate(previous_interactions):
                prompt += f"--- Взаимодействие {i+1} ---\n"
                prompt += f"Команда: {interaction[0]}\n"
                prompt += f"Ответ: {interaction[2]}\n"
        else:
            prompt += "История взаимодействий отсутствует.\n"

        prompt += f"\nТекущая команда: {command}\n"
        prompt += "Твое имя Пятница. Сгенерируй только Python код, который выполняет текущую команду, учитывая историю. Код должен быть безопасным и соответствовать моим инструкциям. Не добавляй никаких объяснений, комментариев или форматирование" 

        response = g4f.ChatCompletion.create(
            model=g4f.models.llama_3_1_405b,
            messages=[{
                'role': 'user',
                'content': prompt
            }]
        )

        if isinstance(response, str) and response.strip():
            save_code_to_file(response)
            store_interaction(command, main_prompt, response, cursor, connection)
        else:
            print("Сгенерированный код пуст или имеет неверный формат.")

        connection.close()
        return response

    except Exception as e:
        print(f"Ошибка при генерации ответа GPT: {e}")
        return ""

def save_code_to_file(code):
    try:
        with open("generated_code.py", "w", encoding="utf-8") as file:
            file.write(code)
    except Exception as e:
        print(f"Ошибка при сохранении кода в файл: {e}")

def store_interaction(command, prompt, response, cursor, connection):
    cursor.execute('''
        INSERT INTO interactions (command, prompt, response)
        VALUES (?, ?, ?)
    ''', (command, prompt, response))

def get_previous_interactions(limit, cursor):
    cursor.execute('SELECT command, prompt, response FROM interactions ORDER BY id DESC LIMIT ?', (limit,))
    return cursor.fetchall()