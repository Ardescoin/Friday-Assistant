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

import os

def scan_directories(dirs):
    paths = {}
    for directory in dirs:
        if not os.path.exists(directory):
            print(f"Папка {directory} не существует")
            continue
        
        dir_name = os.path.basename(directory).lower()
        paths[dir_name] = {"path": directory, "type": "directory"} 
        
        for root, _, files in os.walk(directory):
            for file in files:
                if file.lower().endswith(".exe"):
                    program_name = os.path.splitext(file)[0].lower()
                    full_path = os.path.join(root, file)
                    if program_name not in paths:
                        paths[program_name] = {"path": full_path, "type": "file"}
    return paths


def save_paths_to_json(paths, output_file):
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(paths, f, ensure_ascii=False, indent=4)

def load_paths_from_json(input_file):
    if not os.path.exists(input_file):
        return {}
    with open(input_file, "r", encoding="utf-8") as f:
        return json.load(f)

def find_program_path(name, paths):
    name = name.lower().strip()
    if name in paths:
        return paths[name]["path"] if isinstance(paths[name], dict) and "path" in paths[name] else paths[name]
    for k, v in paths.items():
        if name in k:
            return v["path"] if isinstance(v, dict) and "path" in v else v
    return None

def main():
    
    
    other_programs = scan_directories(SEARCH_DIRS)
    
    
    all_paths = {**other_programs}
    
    
    save_paths_to_json(all_paths, OUTPUT_JSON)
    


if __name__ == "__main__":
    main()