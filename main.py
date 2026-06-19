import asyncio
import logging
import sys
import os

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession

from config import BOT_TOKEN
from database import init_db
from handlers import router
from payment_platega import PlategaPaymentClient

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


async def main():
    logger.info("=" * 50)
    logger.info("🚀 ЗАПУСК БОТА")
    logger.info("=" * 50)
    
    # 1. Инициализация базы данных
    logger.info("📂 Инициализация базы данных...")
    init_db()
    logger.info("✅ База данных готова")
    
    # 2. Создаем клиент Platega.io
    platega_client = PlategaPaymentClient()
    
    # 3. Создаем сессию (без прокси)
    session = AiohttpSession(timeout=60)
    
    bot = Bot(
        token=BOT_TOKEN,
        session=session,
        default=DefaultBotProperties(parse_mode="HTML")
    )
    
    dp = Dispatcher()
    dp.include_router(router)
    dp["platega_client"] = platega_client
    
    # 4. Устанавливаем команды
    await set_bot_commands(bot)
    logger.info("✅ Команды бота установлены")
    
    # 5. Запускаем бота
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
        import traceback
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
        import traceback
        traceback.print_exc()