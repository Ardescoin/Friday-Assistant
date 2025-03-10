import requests

BASE_URL = "http://147.45.78.163:8000"

# Регистрация статуса
response = requests.post(f"{BASE_URL}/pc/status", json={"active": True}, timeout=10)
print(f"Статус ПК: {response.status_code} {response.text}")

# Проверка команды
response = requests.post(f"{BASE_URL}/pc/command", json={"command": "check"}, timeout=10)
print(f"Проверка команды: {response.status_code} {response.text}")