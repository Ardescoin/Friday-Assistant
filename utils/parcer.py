import os
import json


SEARCH_DIRS = [
    "C:\\Program Files",
    "C:\\Program Files (x86)",
    f"C:\\Users\\diluc\\AppData\\Local",
    f"C:\\Users\\diluc\\AppData\\Roaming",
    f"C:\\Users\\diluc\\Desktop",
    f"C:\\Users\\diluc\\Documents",
    "D:\\timely",
]


OUTPUT_JSON = "file_paths.json"

def scan_directories(dirs):
    """Сканирует директории и собирает пути к .exe файлам"""
    paths = {}
    for directory in dirs:
        if not os.path.exists(directory):
            print(f"Папка {directory} не существует")
            continue
        for root, _, files in os.walk(directory):
            for file in files:
                if file.endswith(".exe"):
                    
                    program_name = os.path.splitext(file)[0].lower()
                    full_path = os.path.join(root, file)
                    paths[program_name] = full_path
    return paths

def save_paths_to_json(paths, output_file):
    """Сохраняет пути в JSON-файл"""
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(paths, f, ensure_ascii=False, indent=4)
    print(f"Пути сохранены в {output_file}")

def load_paths_from_json(input_file):
    """Загружает пути из JSON-файла"""
    if not os.path.exists(input_file):
        print(f"Файл {input_file} не найден")
        return {}
    with open(input_file, "r", encoding="utf-8") as f:
        return json.load(f)

def find_program_path(program_name, paths):
    """Ищет путь к программе по имени"""
    program_name = program_name.lower().strip()
    
    if program_name in paths:
        return paths[program_name]
    
    for name, path in paths.items():
        if program_name in name:
            return path
    return None

def main():
    
    
    other_programs = scan_directories(SEARCH_DIRS)
    
    
    all_paths = {**other_programs}
    
    
    save_paths_to_json(all_paths, OUTPUT_JSON)
    


if __name__ == "__main__":
    main()