import subprocess
import sys

def run_command(command):
    try:
        result = subprocess.run(command, check=True, shell=True, capture_output=True, text=True)
        print(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"Ошибка при выполнении {command}: {e.stderr}")

def uninstall_packages():
    packages = [
        "openai-whisper",  # На случай, если всё ещё установлена
        "tiktoken",
        "tqdm",
        "more-itertools",
        # "torch",  # Раскомментируйте, если уверены, что torch не нужен
        # "numpy",  # Не удаляйте, нужен для faster-whisper
        # "scipy",  # Не удаляйте, нужен для faster-whisper
        # "sounddevice",  # Не удаляйте, нужен для faster-whisper
    ]
    
    for pkg in packages:
        print(f"Удаление {pkg}...")
        run_command(f"pip uninstall {pkg} -y")
    
    print("Проверка оставшихся библиотек...")
    run_command("pip list")

if __name__ == "__main__":
    uninstall_packages()