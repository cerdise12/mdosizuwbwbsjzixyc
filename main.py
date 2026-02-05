import requests
import time
import threading

TOKEN = "8590009113:AAGgxOtZ8M6QhgT1J_2QPOMco2Vlmv_MeSg"
URL = f"https://api.telegram.org/bot{TOKEN}"

# Словарь для отслеживания активных спам-потоков {chat_id: threading.Event}
active_spam = {}

SPAM_TEXT = "сосиски жареные от @FallClientOfficial " * 15

def spam_user(chat_id, stop_event):
    """Функция для спама одному пользователю"""
    while not stop_event.is_set():
        try:
            requests.post(
                f"{URL}/sendMessage",
                json={"chat_id": chat_id, "text": SPAM_TEXT},
                timeout=1
            )
        except:
            pass
        time.sleep(0.1)  # Минимальная задержка

def get_updates(offset):
    """Получение обновлений от Telegram"""
    try:
        resp = requests.get(
            f"{URL}/getUpdates",
            params={"offset": offset, "timeout": 10},
            timeout=15
        )
        if resp.status_code == 200:
            return resp.json()
    except:
        pass
    return {"ok": True, "result": []}

def main():
    print("[*] Бот запущен. Жду /start...")
    offset = 0
    
    while True:
        updates = get_updates(offset)
        
        if updates.get("ok"):
            for update in updates.get("result", []):
                offset = update["update_id"] + 1
                
                if "message" in update and "text" in update["message"]:
                    chat_id = update["message"]["chat"]["id"]
                    text = update["message"]["text"]
                    
                    if text.lower() == "/start":
                        # Если спам уже идет, пропускаем
                        if chat_id in active_spam:
                            continue
                        
                        # Создаем событие для остановки потока
                        stop_event = threading.Event()
                        active_spam[chat_id] = stop_event
                        
                        # Запускаем поток спама
                        thread = threading.Thread(
                            target=spam_user,
                            args=(chat_id, stop_event),
                            daemon=True
                        )
                        thread.start()
                        
                        print(f"[+] Начат спам для {chat_id}")
                        
                    elif text.lower() == "/stop":
                        # Останавливаем спам для этого пользователя
                        if chat_id in active_spam:
                            active_spam[chat_id].set()
                            del active_spam[chat_id]
                            print(f"[!] Остановлен спам для {chat_id}")
        
        time.sleep(0.1)

if __name__ == "__main__":
    main()
