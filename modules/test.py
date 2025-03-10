import time
from plyer import notification

def reminder(message, delay_minutes):
    """Отправляет уведомление через заданное количество минут."""
    time.sleep(10)  # Преобразуем минуты в секунды
    notification.notify(
        title='Напоминание!',
        message=message,
        app_name='Напоминалка'
    )

if __name__ == '__main__':
    reminder("Пора выйти в магазин!", 10)  # Напомнить через 10 минут
    print("Напоминание установлено на 10 минут...")
