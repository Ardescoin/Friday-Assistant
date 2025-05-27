import json
import os
import subprocess

def load_paths_from_json(f):
    if not os.path.exists(f):
        return {}
    with open(f, "r", encoding="utf-8") as f:
        return json.load(f)

def find_program_path(n, p):
    n = n.lower().strip()
    if n in p:
        return p[n]
    for k, v in p.items():
        if n in k.lower():
            return v
    return None

file_paths = "file_paths.json"
paths = load_paths_from_json(file_paths)
program_name = "browser"
program_path = find_program_path(program_name, paths)

if program_path and os.path.exists(program_path):
    os.startfile(program_path)
else:
    print("Программа не найдена")