import os
import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_alert(message: str) -> None:
    """
    Gửi tin nhắn cảnh báo qua Telegram.
    Sử dụng \\ để escape các ký tự đặc biệt nếu parse_mode là MarkdownV2
    """
    if not TOKEN or not CHAT_ID or TOKEN == "your_bot_token_here" or CHAT_ID == "your_chat_id_here":
        print(f"\n🔔 [TELEGRAM MOCK ALERT]\n{message}\n")
        return
    
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"  # Sử dụng Markdown cơ bản để dễ tương thích hơn
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        print("Tín hiệu đã được gửi qua Telegram thành công!")
    except Exception as e:
        print(f"Lỗi khi gửi cảnh báo Telegram: {e}")
