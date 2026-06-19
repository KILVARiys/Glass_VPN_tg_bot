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

# --- Subscription settings ---
TRIAL_DAYS = 3
SUB_DAYS = 30
PRICE_RUB = 100
STAR_PRICE = 100

# --- Platega.io ---
PLATEGA_MERCHANT_ID = os.getenv("PLATEGA_MERCHANT_ID", "ваш_merchant_id")
PLATEGA_SECRET_KEY = os.getenv("PLATEGA_SECRET_KEY", "ваш_secret_key")

# --- Referral system ---
REFERRAL_BONUS_DAYS = 3

# --- Webhook settings ---
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "https://ваш-домен")

# --- Admin ID ---
ADMIN_ID = int(os.getenv("ADMIN_ID", 7337563103))