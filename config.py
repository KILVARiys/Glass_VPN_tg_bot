import os
from dotenv import load_dotenv

load_dotenv()

# --- Telegram Bot ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "ВАШ_ТОКЕН_БОТА")

# --- 3x-UI Panel (API Token) ---
XUI_URL = os.getenv("XUI_URL", "https://ваш-домен:порт/путь")
XUI_API_TOKEN = os.getenv("XUI_API_TOKEN", "")  # API Token
XUI_USERNAME = os.getenv("XUI_USERNAME", "admin")  # Логин (если нет токена)
XUI_PASSWORD = os.getenv("XUI_PASSWORD", "ваш_пароль")  # Пароль (если нет токена)
XUI_SUB_URL = os.getenv("XUI_SUB_URL", "")  # URL подписки x-ui

# --- Subscription settings ---
TRIAL_DAYS = 3
SUB_DAYS = 30
PRICE_RUB = 1

# --- Platega.io ---
# MerchantId и API-ключ выдаются менеджером при подключении или доступны
# в Личном кабинете -> "Настройки". Передаются в заголовках X-MerchantId / X-Secret.
PLATEGA_MERCHANT_ID = os.getenv("PLATEGA_MERCHANT_ID", "ваш_merchant_id")
PLATEGA_SECRET_KEY = os.getenv("PLATEGA_SECRET_KEY", "ваш_secret_key")

# --- Referral system ---
REFERRAL_BONUS_DAYS = 3

# --- Webhook settings ---
# WEBHOOK_HOST — публичный домен с действующим (не self-signed) SSL-сертификатом,
# на котором крутится webhook_server.py. Platega.io шлёт сюда callback об оплате.
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "https://ваш-домен")
# Путь, по которому Flask-сервер принимает callback. Этот же путь нужно
# зарегистрировать в ЛК Platega.io -> Настройки -> Callback URLs
# (полный адрес = WEBHOOK_HOST + WEBHOOK_PATH).
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/platega_callback")
# Порт, на котором слушает Flask (webhook_server.py). Если сервер стоит за
# Nginx/Caddy с TLS-терминацией — это внутренний порт за прокси.
WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", 5000))

# --- Admin ID ---
ADMIN_ID = int(os.getenv("ADMIN_ID", 7337563103))
