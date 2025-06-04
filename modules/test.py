import requests
from requests.exceptions import RequestException
import spotipy
from spotipy.exceptions import SpotifyException

# Параметры авторизации
client_id = '3bfa4fdfd4484c27b5d6a56abe12f40d'
client_secret = 'd21fa853a4b54e4393c4cf2c71fd830b'
refresh_token = 'YOUR_REFRESH_TOKEN'  # Замените на ваш refresh_token
scope = 'user-modify-playback-state user-read-playback-state'

# Функция для обновления access_token
def refresh_access_token():
    url = 'https://accounts.spotify.com/api/token'
    data = {
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token,
        'client_id': client_id,
        'client_secret': client_secret
    }
    try:
        response = requests.post(url, data=data)
        response.raise_for_status()
        tokens = response.json()
        return tokens.get('access_token')
    except RequestException as e:
        print(f"Ошибка при обновлении токена: {e}")
        return None

# Получаем access_token
access_token = refresh_access_token()
if not access_token:
    print("Не удалось получить access_token. Проверьте refresh_token.")
    exit()

# Создаем объект Spotify с полученным access_token
sp = spotipy.Spotify(auth=access_token)

try:
    # Проверяем текущее воспроизведение
    current = sp.current_playback()
    if current and current['item']:
        print(f"Текущий трек: {current['item']['name']}")
    else:
        print("Нет активного воспроизведения или устройства.")

    # Пауза воспроизведения
    sp.pause_playback()
    print("Воспроизведение приостановлено.")
except SpotifyException as e:
    if e.http_status == 401:
        print("Токен истек или недействителен. Попробуйте обновить refresh_token.")
    elif e.http_status == 403:
        print("Ошибка: Недостаточно прав или требуется Spotify Premium.")
    elif e.http_status == 404:
        print("Ошибка: Нет активного устройства.")
    else:
        print(f"Ошибка Spotify: {e}")
except Exception as e:
    print(f"Общая ошибка: {e}")


sp.next_track()