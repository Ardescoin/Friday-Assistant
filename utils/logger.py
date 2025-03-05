# logger.py
import datetime

def log_message(role, message):
    with open("assistant_log.txt", "a", encoding="utf-8") as log_file:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_file.write(f"[{timestamp}] [{role}] {message}\n")
