import requests
import base64

CLIENT_ID = '3bfa4fdfd4484c27b5d6a56abe12f40d'
CLIENT_SECRET = 'd21fa853a4b54e4393c4cf2c71fd830b'
REDIRECT_URI = 'http://localhost'
AUTH_URL = 'https://accounts.spotify.com/authorize'
TOKEN_URL = 'https://accounts.spotify.com/api/token'

# Шаг 1: Получение кода авторизации
auth_params = {
    'client_id': CLIENT_ID,
    'response_type': 'code',
    'redirect_uri': REDIRECT_URI,
    'scope': 'user-read-private user-read-email user-modify-playback-state user-read-playback-state user-read-currently-playing'
}

auth_request = requests.get(AUTH_URL, params=auth_params)
print(f"Перейдите по следующей ссылке для авторизации: {auth_request.url}")

# После перехода по ссылке и подтверждения, вы получите код авторизации в URL перенаправления

# Шаг 2: Обмен кода авторизации на токен доступа
auth_code = input('Введите код авторизации из URL перенаправления: ')

token_data = {
    'grant_type': 'authorization_code',
    'code': auth_code,
    'redirect_uri': REDIRECT_URI
}

client_credentials = f"{CLIENT_ID}:{CLIENT_SECRET}"
client_credentials_b64 = base64.b64encode(client_credentials.encode()).decode()

token_headers = {
    'Authorization': f"Basic {client_credentials_b64}"
}

token_request = requests.post(TOKEN_URL, data=token_data, headers=token_headers)
token_response = token_request.json()

if 'access_token' in token_response:
    access_token = token_response['access_token']
    refresh_token = token_response['refresh_token']
    print(f"Токен доступа: {access_token}")
    print(f"Токен обновления: {refresh_token}")
else:
    print(f"Ошибка получения токена: {token_response}")


# Токен доступа: BQAL88WpfB8L3768UwUcxhAPLsu9Veqv77eZP815dCzQ5xuwzT9NW0thoJciguxNeICaQRLix2q0veuxS0FosXSnDExzrZPdzms4GcMP7igtgNh0NmctMYUyJ9JQaaeXN_kX97sI2KnVRez6079nbjz7Lfuo6Ry8oKeD-lNWLj89Nan1wLkfxelkq_70FCTqJmRQzO5Rq-agRnDVpb54R5KhAqJCoSOh73Q1ExsGKsJGGLTx0jQ2tWbwiSky3vWT
# Токен обновления: AQDQHcOyivHnCJ-EnyEzT0YGr6S7vSmNGlzABia_HxPu8Ei9cw_YfY09597bAQZwBWYqckRAACDLCPGToDHJc3L4tTixvsVoD2jOyn481Z0JFhlk5wsAmLGa77L4ydRG7_E