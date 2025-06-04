import spotipy
import requests

client_id='3bfa4fdfd4484c27b5d6a56abe12f40d'
client_secret='d21fa853a4b54e4393c4cf2c71fd830b'
refresh_token='AQCOFYo-ljUX0q9PfcysDsby8Hhfx8oaxa4I5Seo_nnjvJ10QJffif4bkwhFbuRWZSEJz0wdiipMyZPnS0gZ8Aq8qv08WC1BYrjILveXBsFs9_q8OIQ6f7pKIcNxWFbxlQI'
scope='user-modify-playback-state user-read-playback-state'

def refresh_access_token():
    url='https://accounts.spotify.com/api/token'
    data={'grant_type':'refresh_token','refresh_token':refresh_token,'client_id':client_id,'client_secret':client_secret}
    try:
        response=requests.post(url,data=data)
        response.raise_for_status()
        tokens=response.json()
        return tokens.get('access_token')
    except requests.RequestException as e:
        print(f"Ошибка при обновлении токена: {e}")
        return None

access_token=refresh_access_token()
sp=spotipy.Spotify(auth=access_token)

sp.previous_track()