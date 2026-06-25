import asyncio
import logging
import sys
import threading
import traceback

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession

from config import BOT_TOKEN, WEBHOOK_PORT
from database import init_db
from handlers import router
from payment_platega import PlategaPaymentClient
from webhook_server import app as flask_app

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


async def set_bot_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="🔰 Запустить бота"),
        BotCommand(command="admin", description="🔐 Админ-панель"),
        BotCommand(command="cancel", description="❌ Отменить действие"),
    ]
    await bot.set_my_commands(commands)


def start_webhook_server():
    """
    Запускает Flask-сервер, принимающий callback от Platega.io,
    в отдельном (фоновом) потоке, чтобы он работал параллельно
    с aiogram-поллингом в основном asyncio-цикле.

    Для продакшена рекомендуется поставить перед этим Nginx/Caddy
    с настоящим (не self-signed) SSL-сертификатом и проксировать
    запросы на 127.0.0.1:{WEBHOOK_PORT} — Platega.io требует HTTPS
    с валидным сертификатом и не принимает приватные/localhost-адреса
    напрямую как callback URL.
    """
    try:
        flask_app.run(host="0.0.0.0", port=WEBHOOK_PORT, debug=False, use_reloader=False)
    except Exception as e:
        logger.error(f"❌ Webhook-сервер Platega.io упал: {e}")
        traceback.print_exc()


async def main():
    logger.info("=" * 50)
    logger.info("🚀 ЗАПУСК БОТА")
    logger.info("=" * 50)

    logger.info("📂 Инициализация базы данных...")
    init_db()
    logger.info("✅ База данных готова")

    platega_client = PlategaPaymentClient()

    # Поднимаем webhook-сервер Platega.io в фоновом потоке
    webhook_thread = threading.Thread(target=start_webhook_server, daemon=True)
    webhook_thread.start()
    logger.info(f"🌐 Webhook-сервер Platega.io запущен на порту {WEBHOOK_PORT}")

    session = AiohttpSession(timeout=60)
    bot = Bot(
        token=BOT_TOKEN,
        session=session,
        default=DefaultBotProperties(parse_mode="HTML")
    )

    dp = Dispatcher()
    dp.include_router(router)
    dp["platega_client"] = platega_client

    await set_bot_commands(bot)
    logger.info("✅ Команды бота установлены")

    logger.info("=" * 50)
    logger.info("🤖 БОТ ЗАПУЩЕН И ГОТОВ К РАБОТЕ!")
    logger.info("=" * 50)

    try:
        await dp.start_polling(
            bot,
            allowed_updates=["message", "callback_query", "pre_checkout_query"]
        )
    except KeyboardInterrupt:
        logger.info("👋 Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        traceback.print_exc()
    finally:
        await platega_client.close_async()
        await bot.session.close()
        logger.info("🔒 Все соединения закрыты")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Программа завершена")
    except Exception as e:
        logger.error(f"❌ Фатальная ошибка: {e}")
        traceback.print_exc()