import logging
import asyncio
import time
from datetime import datetime, timedelta
from aiogram import Router, types, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from database import *
from keyboards import *
from utils import XUIClient
from config import SUB_DAYS, PRICE_RUB, TRIAL_DAYS, REFERRAL_BONUS_DAYS
from payment_platega import PlategaPaymentClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = Router()
xui = XUIClient()
platega = PlategaPaymentClient()

pending_payments = {}

class AdminStates(StatesGroup):
    waiting_for_mailing = State()
    waiting_for_mailing_confirm = State()
    waiting_for_promo_code = State()
    waiting_for_promo_bonus = State()
    waiting_for_promo_uses = State()
    waiting_for_promo_delete = State()
    waiting_for_add_admin = State()
    waiting_for_remove_admin = State()

class PromoStates(StatesGroup):
    waiting_for_promo = State()


# ======================== ОСНОВНЫЕ ФУНКЦИИ ============================

async def activate_subscription(telegram_id: int, days: int = SUB_DAYS, payment_method: str = "unknown", bot: Bot = None):
    user = get_user(telegram_id)
    if not user:
        logger.error(f"User {telegram_id} not found")
        return False, "Пользователь не найден"

    success, sub_id, msg = xui.create_client(
        email=user[3],
        days=days,
        total_gb=10,
        limit_ip=1
    )

    if not success:
        return False, f"Ошибка создания клиента: {msg}"

    new_end = update_subscription(telegram_id, days)

    if sub_id:
        sub_link = xui.get_subscription_link(sub_id)
        link_text = f"🔗 *Ссылка для подключения (SUB):*\n`{sub_link}`"
    else:
        link_text = "⚠️ Клиент создан, но ID подписки не получен. Ссылка недоступна."

    try:
        if bot is None:
            from config import BOT_TOKEN
            bot = Bot(token=BOT_TOKEN)
        await bot.send_message(
            telegram_id,
            f"✅ *Подписка активирована!*\n\n"
            f"💳 Способ оплаты: {payment_method}\n"
            f"📅 Подписка активна до: {new_end.strftime('%d.%m.%Y %H:%M')}\n"
            f"📆 Добавлено дней: {days}\n"
            f"📊 Трафик: 10 ГБ\n"
            f"📶 IP-лимит: 1\n\n"
            f"{link_text}",
            parse_mode="Markdown",
            reply_markup=main_menu_without_trial()
        )
    except Exception as e:
        logger.error(f"❌ Ошибка отправки уведомления: {e}")

    return True, new_end


async def activate_trial_subscription(telegram_id: int, bot: Bot = None):
    user = get_user(telegram_id)
    if not user:
        return False, "Пользователь не найден"

    if user[6] == 1:
        logger.info(f"Пользователь {telegram_id} уже использовал пробный период")
        return False, "❌ Вы уже использовали пробный период!"

    end_date = datetime.fromisoformat(user[5]) if user[5] else None
    if end_date and end_date > datetime.now():
        days_left = (end_date - datetime.now()).days
        return False, f"❌ У вас уже активна подписка! Осталось {days_left} дней."

    result, message = await activate_subscription(
        telegram_id,
        TRIAL_DAYS,
        "🎁 Пробный период",
        bot=bot
    )

    if result:
        logger.info(f"Попытка установить флаг пробного периода для {telegram_id}")
        success = set_trial_used(telegram_id)
        if success:
            logger.info(f"✅ Флаг успешно установлен для {telegram_id}")
        else:
            logger.error(f"❌ Не удалось установить флаг для {telegram_id}")
        return True, f"✅ Пробный период на {TRIAL_DAYS} дня активирован!"
    else:
        return False, f"❌ Ошибка активации пробного периода: {message}"


# ======================== ОБРАБОТЧИКИ КОМАНД ============================

@router.message(Command("start"))
async def cmd_start(message: Message):
    telegram_id = message.from_user.id
    user = get_user(telegram_id)

    args = message.text.split()
    referrer_id = None
    if len(args) > 1:
        try:
            referrer_id = int(args[1])
            if referrer_id == telegram_id:
                referrer_id = None
        except:
            pass

    if not user:
        create_user(
            telegram_id,
            message.from_user.username or "",
            message.from_user.first_name,
            referrer_id
        )
        await message.answer(
            f"🎉 Добро пожаловать, {message.from_user.first_name}!\n\n"
            f"📋 Используйте меню ниже для управления подпиской:\n"
            f"• 🎁 Активировать пробную подписку - получите {TRIAL_DAYS} дня бесплатно\n"
            f"• 🛒 Купить - продление на 30 дней\n"
            f"• 🎁 Промокод - активация бонусных дней\n"
            f"• 👥 Рефералы - приглашайте друзей и получайте бонусы",
            reply_markup=main_menu()
        )
    else:
        end_date = datetime.fromisoformat(user[5]) if user[5] else None
        days_left = (end_date - datetime.now()).days if end_date else 0
        status_text = "🟢 Активна" if days_left > 0 else "🔴 Не активна"
        trial_used = "✅ Использован" if user[6] == 1 else "❌ Не использован"
        await message.answer(
            f"👋 С возвращением, {message.from_user.first_name}!\n\n"
            f"📊 Статус подписки: {status_text}\n"
            f"📅 Осталось дней: {days_left if days_left > 0 else 0}\n"
            f"🎁 Пробный период: {trial_used}",
            reply_markup=main_menu_without_trial() if user[6] == 1 else main_menu()
        )


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет прав администратора.")
        return
    await message.answer(
        "🔐 Административная панель\n\nВыберите действие:",
        reply_markup=admin_menu()
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Действие отменено.", reply_markup=main_menu())


# ======================== ОБРАБОТЧИКИ КНОПОК ============================

@router.callback_query(F.data == "profile")
async def profile_callback(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    if not user:
        await callback.answer("Пожалуйста, используйте /start", show_alert=True)
        return

    end_date = datetime.fromisoformat(user[5]) if user[5] else None
    days_left = (end_date - datetime.now()).days if end_date else 0
    is_trial = "✅ Использована" if user[6] == 1 else "❌ Не использована"
    ref_count = get_referral_count(callback.from_user.id)
    is_active = days_left > 0

    if end_date:
        sub_info = f"до {end_date.strftime('%d.%m.%Y %H:%M')} (осталось {max(0, days_left)} дн.)"
    else:
        sub_info = "Не активна"

    text = (
        f"👤 *Мой профиль*\n\n"
        f"🆔 *Telegram ID:* `{user[0]}`\n"
        f"📅 *Подписка:* {sub_info}\n"
        f"👥 *Рефералы:* {ref_count}\n"
        f"🎁 *Пробная подписка:* {is_trial}"
    )
    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=profile_keyboard(is_active)
    )
    await callback.answer()


@router.callback_query(F.data == "activate_trial")
async def activate_trial_callback(callback: CallbackQuery):
    telegram_id = callback.from_user.id
    user = get_user(telegram_id)
    if not user:
        await callback.answer("Пожалуйста, используйте /start", show_alert=True)
        return

    if user[6] == 1:
        sub_id = xui.find_client_sub_id(user[3])
        if sub_id:
            sub_link = xui.get_subscription_link(sub_id)
            await callback.message.edit_text(
                f"ℹ️ *Вы уже использовали пробный период!*\n\n"
                f"Ваша ссылка для подключения:\n`{sub_link}`\n\n"
                f"Вы можете продлить подписку через меню 'Купить подписку'.",
                parse_mode="Markdown",
                reply_markup=main_menu_without_trial()
            )
        else:
            await callback.message.edit_text(
                f"ℹ️ *Вы уже использовали пробный период!*\n\n"
                f"К сожалению, ваша ссылка для подключения не найдена.\n"
                f"Обратитесь к администратору.",
                parse_mode="Markdown",
                reply_markup=main_menu_without_trial()
            )
        await callback.answer()
        return

    end_date = datetime.fromisoformat(user[5]) if user[5] else None
    if end_date and end_date > datetime.now():
        days_left = (end_date - datetime.now()).days
        sub_id = xui.find_client_sub_id(user[3])
        if sub_id:
            sub_link = xui.get_subscription_link(sub_id)
            await callback.message.edit_text(
                f"ℹ️ *У вас уже активна подписка!*\n\n"
                f"Осталось дней: {days_left}\n"
                f"Ваша ссылка для подключения:\n`{sub_link}`\n\n"
                f"Вы можете продлить подписку через меню 'Купить подписку'.",
                parse_mode="Markdown",
                reply_markup=main_menu_without_trial()
            )
        else:
            await callback.message.edit_text(
                f"ℹ️ *У вас уже активна подписка!*\n\n"
                f"Осталось дней: {days_left}\n"
                f"Ссылка для подключения не найдена. Обратитесь к администратору.",
                parse_mode="Markdown",
                reply_markup=main_menu_without_trial()
            )
        await callback.answer()
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, активировать", callback_data="confirm_trial")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="back")]
    ])
    await callback.message.edit_text(
        f"🎁 *Активация пробной подписки*\n\n"
        f"Вы получите бесплатный доступ на *{TRIAL_DAYS} дня*.\n\n"
        f"⚠️ Пробный период можно использовать только один раз!\n\n"
        f"Подтвердите активацию:",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(F.data == "confirm_trial")
async def confirm_trial_callback(callback: CallbackQuery):
    telegram_id = callback.from_user.id
    success, message = await activate_trial_subscription(telegram_id, bot=callback.bot)

    if success:
        await callback.message.edit_text(
            f"✅ *Пробный период активирован!*\n\n"
            f"🎉 Вы получили {TRIAL_DAYS} дня бесплатного доступа.\n\n"
            f"📅 Подписка активна до: {(datetime.now() + timedelta(days=TRIAL_DAYS)).strftime('%d.%m.%Y %H:%M')}",
            parse_mode="Markdown",
            reply_markup=main_menu_without_trial()
        )
    else:
        await callback.message.edit_text(
            f"❌ {message}",
            parse_mode="Markdown",
            reply_markup=main_menu()
        )
    await callback.answer()


@router.callback_query(F.data == "extend_subscription")
async def extend_subscription_callback(callback: CallbackQuery):
    await callback.message.edit_text(
        "💳 *Выберите способ оплаты для продления*\n\n"
        "💰 Цена: 100 ₽\n"
        "📅 Срок: 30 дней\n\n"
        "Оплата через СБП/карту:",
        parse_mode="Markdown",
        reply_markup=payment_methods()
    )
    await callback.answer()


@router.callback_query(F.data == "buy")
async def buy_callback(callback: CallbackQuery):
    await callback.message.edit_text(
        "💳 *Выберите способ оплаты*\n\n"
        "💰 Цена: 100 ₽\n"
        "📅 Срок: 30 дней\n\n"
        "Оплата через СБП/карту:",
        parse_mode="Markdown",
        reply_markup=payment_methods()
    )
    await callback.answer()


@router.callback_query(F.data == "pay_card")
async def pay_card_callback(callback: CallbackQuery):
    telegram_id = callback.from_user.id
    user = get_user(telegram_id)
    if not user:
        await callback.answer("Пожалуйста, используйте /start", show_alert=True)
        return

    order_id = f"order_{telegram_id}_{int(time.time())}"
    result = platega.create_payment(
        amount=PRICE_RUB,
        description=f"Подписка VPN (30 дней) для пользователя {telegram_id}",
        order_id=order_id,
        return_url="https://t.me",
        payment_method=2,
    )

    if result["success"]:
        create_payment(result["transaction_id"], telegram_id, PRICE_RUB, "platega_sbp")
        pending_payments[telegram_id] = result["transaction_id"]
        await callback.message.edit_text(
            f"💳 *Оплата через СБП*\n\n"
            f"💰 Сумма: {PRICE_RUB} ₽\n"
            f"🆔 Заказ: {result['order_id']}\n\n"
            f"⬇️ Нажмите кнопку ниже для перехода на страницу оплаты.\n"
            f"✅ После оплаты нажмите 'Проверить оплату'.\n\n"
            f"⏳ Платеж действителен 15 минут.",
            parse_mode="Markdown",
            reply_markup=pay_card_button(result["payment_url"])
        )
    else:
        error_msg = result.get("error", "Неизвестная ошибка")
        await callback.message.edit_text(
            f"❌ *Ошибка при создании платежа*\n\n{error_msg}",
            parse_mode="Markdown",
            reply_markup=payment_methods()
        )
    await callback.answer()


@router.callback_query(F.data == "check_payment")
async def check_payment_callback(callback: CallbackQuery):
    telegram_id = callback.from_user.id
    if telegram_id not in pending_payments:
        await callback.answer("❌ Нет активных платежей", show_alert=True)
        return

    transaction_id = pending_payments[telegram_id]
    status = platega.check_payment_status(transaction_id)

    if not status["success"]:
        await callback.answer(f"❌ Ошибка проверки: {status.get('error', 'Неизвестная ошибка')}", show_alert=True)
        return

    if status["is_paid"]:
        confirm_payment(transaction_id)
        success, result = await activate_subscription(
            telegram_id,
            SUB_DAYS,
            "СБП (Platega.io)",
            bot=callback.bot
        )
        if success:
            await callback.message.edit_text(
                f"✅ *Оплата подтверждена!*\n\n"
                f"🎉 Подписка успешно продлена!\n"
                f"📅 Действительна до: {result.strftime('%d.%m.%Y %H:%M')}",
                parse_mode="Markdown",
                reply_markup=main_menu_without_trial()
            )
        else:
            await callback.message.edit_text(
                "❌ *Ошибка активации подписки*\n\nПлатеж прошел, но возникла техническая ошибка.",
                parse_mode="Markdown",
                reply_markup=main_menu()
            )
        del pending_payments[telegram_id]
    else:
        status_value = status.get("status", "unknown")
        status_messages = {
            "NEW": "⏳ Платеж создан, ожидается оплата",
            "PENDING": "⏳ Платеж обрабатывается",
            "CONFIRMED": "✅ Платеж оплачен",
            "CANCELED": "❌ Платеж отменен",
            "FAILED": "❌ Платеж не удался",
        }
        message = status_messages.get(status_value, f"❓ Статус: {status_value}")
        if status_value in ["CANCELED", "FAILED"]:
            await callback.message.edit_text(
                f"❌ *Платеж был отменен*\n\nПопробуйте еще раз.",
                parse_mode="Markdown",
                reply_markup=payment_methods()
            )
            del pending_payments[telegram_id]
        else:
            await callback.answer(message, show_alert=True)


# ПРОМОКОДЫ
@router.callback_query(F.data == "promo")
async def promo_callback(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "🎁 *Введите промокод*\n\n"
        "Отправьте код сообщением.\n"
        "Пример: `SUMMER2024`\n\n"
        "Для отмены введите /cancel",
        parse_mode="Markdown",
        reply_markup=back_button()
    )
    await state.set_state(PromoStates.waiting_for_promo)
    await callback.answer()


@router.message(PromoStates.waiting_for_promo)
async def process_promo(message: Message, state: FSMContext):
    code = message.text.strip()
    result, msg = use_promocode(message.from_user.id, code)
    await message.answer(msg, reply_markup=main_menu())
    await state.clear()


# РЕФЕРАЛЫ
@router.callback_query(F.data == "referral")
async def referral_callback(callback: CallbackQuery):
    telegram_id = callback.from_user.id
    bot_username = (await callback.bot.me()).username
    referral_link = f"https://t.me/{bot_username}?start={telegram_id}"
    user = get_user(telegram_id)
    ref_count = get_referral_count(telegram_id)

    text = (
        f"👥 *Реферальная система*\n\n"
        f"🎁 Приглашайте друзей и получайте бонусы!\n\n"
        f"За каждого приглашенного друга вы получите +{REFERRAL_BONUS_DAYS} дней.\n\n"
        f"🔗 Ваша реферальная ссылка:\n`{referral_link}`\n\n"
        f"📊 Приглашено друзей: {ref_count}\n"
        f"⭐ Бонусных дней: {user[6] if user else 0}"
    )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=back_button())
    await callback.answer()


# ПОМОЩЬ
@router.callback_query(F.data == "help")
async def help_callback(callback: CallbackQuery):
    text = (
        "ℹ️ Помощь и поддержка\n\n"
        "📌 Как пользоваться ботом:\n"
        "1️⃣ Используйте /start для начала\n"
        "2️⃣ Активируйте пробный период через кнопку в меню\n"
        "3️⃣ Купите или продлите подписку через меню\n\n"
        "💳 Способы оплаты:\n"
        "• СБП через Platega.io\n\n"
        "🎁 Промокоды:\n"
        "Вводите промокоды в соответствующем разделе\n\n"
        "👥 Рефералы:\n"
        "Приглашайте друзей и получайте бонусные дни\n\n"
        "❓ Вопросы и поддержка:\n"
        "@support_bot"
    )
    await callback.message.edit_text(text, reply_markup=back_button())
    await callback.answer()


@router.callback_query(F.data == "back")
async def back_callback(callback: CallbackQuery):
    await callback.message.edit_text(
        "📋 *Главное меню*\n\nВыберите действие:",
        reply_markup=main_menu()
    )
    await callback.answer()


# ======================== АДМИН-ПАНЕЛЬ ============================

@router.callback_query(F.data == "admin_users")
async def admin_users(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен")
        return
    users = get_all_users()
    text = "📋 *Список пользователей:*\n\n"
    if not users:
        text += "Пользователей пока нет"
    else:
        for user in users[:20]:
            end_date = datetime.fromisoformat(user[3]) if user[3] else None
            days_left = (end_date - datetime.now()).days if end_date else 0
            status = "🟢" if days_left > 0 else "🔴"
            text += f"{status} {user[1]} (@{user[2]}) - {days_left} дн.\n"
        if len(users) > 20:
            text += f"\n... и еще {len(users) - 20} пользователей"
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=admin_menu())
    await callback.answer()


@router.callback_query(F.data == "admin_mailing")
async def admin_mailing(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен")
        return
    await callback.message.edit_text(
        "📨 *Рассылка*\n\nОтправьте сообщение для рассылки.\nДля отмены введите /cancel",
        parse_mode="Markdown"
    )
    await state.set_state(AdminStates.waiting_for_mailing)
    await callback.answer()


@router.message(AdminStates.waiting_for_mailing)
async def process_mailing(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещен")
        await state.clear()
        return
    await state.update_data(mailing_text=message.text)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Отправить", callback_data="confirm_mailing")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_mailing")]
    ])
    await message.answer(
        f"📨 *Подтверждение рассылки*\n\nОтправить это сообщение всем пользователям?\n\n{message.text[:200]}...",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    await state.set_state(AdminStates.waiting_for_mailing_confirm)


@router.callback_query(F.data == "confirm_mailing")
async def confirm_mailing(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен")
        return
    data = await state.get_data()
    text = data.get('mailing_text')
    if not text:
        await callback.answer("❌ Ошибка: сообщение не найдено")
        await state.clear()
        return
    users = get_all_users()
    success = 0
    fail = 0
    await callback.message.edit_text(f"📨 *Рассылка запущена*\n\nВсего пользователей: {len(users)}", parse_mode="Markdown")
    await callback.answer()
    for user in users:
        try:
            await callback.bot.send_message(user[0], text, parse_mode="Markdown", disable_web_page_preview=True)
            success += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            logger.error(f"Failed to send to {user[0]}: {e}")
            fail += 1
    await callback.message.edit_text(
        f"✅ *Рассылка завершена!*\n\n📨 Успешно: {success}\n❌ Ошибок: {fail}\n👥 Всего: {len(users)}",
        parse_mode="Markdown",
        reply_markup=admin_menu()
    )
    await state.clear()


@router.callback_query(F.data == "cancel_mailing")
async def cancel_mailing(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Рассылка отменена.", reply_markup=admin_menu())
    await callback.answer()


@router.callback_query(F.data == "admin_create_promo")
async def admin_create_promo(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен")
        return
    await callback.message.edit_text(
        "➕ *Создание промокода*\n\nВведите название промокода (латиница, цифры):\nПример: SUMMER2024\n\nДля отмены введите /cancel",
        parse_mode="Markdown"
    )
    await state.set_state(AdminStates.waiting_for_promo_code)
    await callback.answer()


@router.message(AdminStates.waiting_for_promo_code)
async def process_promo_code(message: Message, state: FSMContext):
    code = message.text.strip().upper()
    if not code.isalnum():
        await message.answer("❌ Код должен содержать только буквы и цифры. Попробуйте снова:")
        return
    await state.update_data(promo_code=code)
    await message.answer("📅 Введите количество бонусных дней (число):\nПример: 7")
    await state.set_state(AdminStates.waiting_for_promo_bonus)


@router.message(AdminStates.waiting_for_promo_bonus)
async def process_promo_bonus(message: Message, state: FSMContext):
    try:
        days = int(message.text)
        if days <= 0:
            await message.answer("❌ Введите число больше 0:")
            return
        await state.update_data(promo_bonus=days)
        await message.answer("🔢 Введите максимальное количество использований (число):\nПример: 100")
        await state.set_state(AdminStates.waiting_for_promo_uses)
    except ValueError:
        await message.answer("❌ Введите число! Попробуйте снова:")


@router.message(AdminStates.waiting_for_promo_uses)
async def process_promo_uses(message: Message, state: FSMContext):
    try:
        uses = int(message.text)
        if uses <= 0:
            await message.answer("❌ Введите число больше 0:")
            return
        data = await state.get_data()
        code = data.get('promo_code')
        bonus = data.get('promo_bonus')
        create_promocode(code, bonus, uses)
        await message.answer(
            f"✅ *Промокод создан!*\n\n🎫 Код: `{code}`\n📅 Бонусных дней: {bonus}\n🔢 Максимум использований: {uses}\n\nПромокод активен!",
            parse_mode="Markdown",
            reply_markup=admin_menu()
        )
        await state.clear()
    except ValueError:
        await message.answer("❌ Введите число! Попробуйте снова:")


@router.callback_query(F.data == "admin_delete_promo")
async def admin_delete_promo(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен")
        return
    promos = get_all_promocodes()
    if not promos:
        await callback.message.edit_text("📭 *Нет активных промокодов*", parse_mode="Markdown", reply_markup=admin_menu())
        await callback.answer()
        return
    text = "🗑 *Удаление промокода*\n\nВыберите код для удаления:\n\n"
    for promo in promos:
        text += f"`{promo[0]}` - {promo[1]} дн. ({promo[3]}/{promo[2]})\n"
    text += "\nВведите код для удаления:"
    await callback.message.edit_text(text, parse_mode="Markdown")
    await state.set_state(AdminStates.waiting_for_promo_delete)
    await callback.answer()


@router.message(AdminStates.waiting_for_promo_delete)
async def process_promo_delete(message: Message, state: FSMContext):
    code = message.text.strip().upper()
    promo = get_promocode(code)
    if not promo:
        await message.answer("❌ Промокод не найден. Попробуйте снова:")
        return
    delete_promocode(code)
    await message.answer(f"✅ Промокод `{code}` удален.", parse_mode="Markdown", reply_markup=admin_menu())
    await state.clear()


@router.callback_query(F.data == "admin_payments")
async def admin_payments(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен")
        return
    payments = get_all_payments()
    if not payments:
        await callback.message.edit_text("📭 *Нет платежей*", parse_mode="Markdown", reply_markup=admin_menu())
        await callback.answer()
        return
    text = "💰 *Последние платежи:*\n\n"
    for payment in payments[:10]:
        status_emoji = {'pending': '⏳', 'confirmed': '✅', 'canceled': '❌'}.get(payment[4], '❓')
        text += f"{status_emoji} #{payment[0][:8]} | Пользователь: {payment[1]} | {payment[2]} руб. | {payment[3]} | {payment[4]}\n"
    if len(payments) > 10:
        text += f"\n... и еще {len(payments) - 10} платежей"
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=admin_menu())
    await callback.answer()


@router.callback_query(F.data == "admin_admins")
async def admin_admins(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен")
        return
    admins = get_all_admins()
    text = "👤 *Управление администраторами*\n\nТекущие админы:\n"
    for admin_id in admins:
        text += f"• `{admin_id}`\n"
    text += "\nВыберите действие:"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить админа", callback_data="admin_add_admin")],
        [InlineKeyboardButton(text="➖ Удалить админа", callback_data="admin_remove_admin")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_admin")]
    ])
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "admin_add_admin")
async def admin_add_admin(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен")
        return
    await callback.message.edit_text("➕ *Добавление администратора*\n\nВведите Telegram ID пользователя, которого хотите сделать админом:", parse_mode="Markdown")
    await state.set_state(AdminStates.waiting_for_add_admin)
    await callback.answer()


@router.message(AdminStates.waiting_for_add_admin)
async def process_add_admin(message: Message, state: FSMContext):
    try:
        admin_id = int(message.text.strip())
        add_admin(admin_id)
        await message.answer(f"✅ Пользователь `{admin_id}` теперь администратор.", parse_mode="Markdown", reply_markup=admin_menu())
        await state.clear()
    except ValueError:
        await message.answer("❌ Введите корректный Telegram ID (число):")


@router.callback_query(F.data == "admin_remove_admin")
async def admin_remove_admin(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен")
        return
    await callback.message.edit_text("➖ *Удаление администратора*\n\nВведите Telegram ID администратора, которого хотите удалить:", parse_mode="Markdown")
    await state.set_state(AdminStates.waiting_for_remove_admin)
    await callback.answer()


@router.message(AdminStates.waiting_for_remove_admin)
async def process_remove_admin(message: Message, state: FSMContext):
    try:
        admin_id = int(message.text.strip())
        if admin_id == message.from_user.id:
            await message.answer("❌ Вы не можете удалить самого себя!")
            return
        remove_admin(admin_id)
        await message.answer(f"✅ Администратор `{admin_id}` удален.", parse_mode="Markdown", reply_markup=admin_menu())
        await state.clear()
    except ValueError:
        await message.answer("❌ Введите корректный Telegram ID (число):")


@router.callback_query(F.data == "back_admin")
async def back_admin(callback: CallbackQuery):
    await callback.message.edit_text(
        "🔐 *Административная панель*\n\nВыберите действие:",
        parse_mode="Markdown",
        reply_markup=admin_menu()
    )
    await callback.answer()