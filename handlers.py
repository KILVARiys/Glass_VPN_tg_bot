import logging
import asyncio
import time
from datetime import datetime, timedelta
from aiogram import Router, types, F, Bot
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery

from database import *
from keyboards import *
from utils import XUIClient
from payment_platega import PlategaPaymentClient
from config import STAR_PRICE, SUB_DAYS, PRICE_RUB, TRIAL_DAYS, REFERRAL_BONUS_DAYS

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = Router()
xui = XUIClient()
platega = PlategaPaymentClient()

# Хранилище для временных данных
pending_payments = {}
user_data = {}

# Состояния для FSM
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


# --- Функция активации подписки ---
async def activate_subscription(telegram_id: int, days: int = SUB_DAYS, payment_method: str = "unknown"):
    """
    Активирует подписку пользователю
    """
    user = get_user(telegram_id)
    if not user:
        logger.error(f"User {telegram_id} not found")
        return False, "Пользователь не найден"
    
    # Обновляем дату подписки
    new_end = update_subscription(telegram_id, days)
    
    # Создаем/обновляем клиента в 3x-ui
    success, message = xui.add_client(user[3], days)
    
    if not success:
        logger.error(f"Failed to add client to 3x-ui: {message}")
    
    # Отправляем уведомление пользователю
    bot = Bot.get_current()
    try:
        await bot.send_message(
            telegram_id,
            f"✅ *Подписка активирована!*\n\n"
            f"💳 Способ оплаты: {payment_method}\n"
            f"📅 Подписка активна до: {new_end.strftime('%d.%m.%Y %H:%M')}\n"
            f"📆 Добавлено дней: {days}\n\n"
            f"🔗 Ссылка для подключения будет отправлена в ближайшее время.\n"
            f"При возникновении проблем обратитесь к @support",
            parse_mode="Markdown",
            reply_markup=main_menu()
        )
    except Exception as e:
        logger.error(f"Failed to send notification to {telegram_id}: {e}")
    
    return True, new_end


# --- Команда /start ---
@router.message(Command("start"))
async def cmd_start(message: Message):
    telegram_id = message.from_user.id
    user = get_user(telegram_id)
    
    # Обработка реферальной ссылки
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
        
        # Создаем клиента в 3x-ui с пробным периодом
        xui.add_client(f"user_{telegram_id}@vpn.local", TRIAL_DAYS)
        
        await message.answer(
            f"🎉 *Добро пожаловать, {message.from_user.first_name}!*\n\n"
            f"✅ Вам активирован пробный период на *{TRIAL_DAYS} дня*.\n\n"
            f"📋 Используйте меню ниже для управления подпиской:\n"
            f"• 📊 Профиль - просмотр статуса подписки\n"
            f"• 🛒 Купить - продление на 30 дней\n"
            f"• 🎁 Промокод - активация бонусных дней\n"
            f"• 👥 Рефералы - приглашайте друзей и получайте бонусы",
            parse_mode="Markdown",
            reply_markup=main_menu()
        )
    else:
        # Проверяем статус подписки
        end_date = datetime.fromisoformat(user[4]) if user[4] else None
        days_left = (end_date - datetime.now()).days if end_date else 0
        
        status_text = "🟢 *Активна*" if days_left > 0 else "🔴 *Истекла*"
        
        await message.answer(
            f"👋 *С возвращением, {message.from_user.first_name}!*\n\n"
            f"📊 Статус подписки: {status_text}\n"
            f"📅 Осталось дней: {days_left if days_left > 0 else 0}",
            parse_mode="Markdown",
            reply_markup=main_menu()
        )


# --- Команда /admin ---
@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет прав администратора.")
        return
    
    await message.answer(
        "🔐 *Административная панель*\n\n"
        "Выберите действие:",
        parse_mode="Markdown",
        reply_markup=admin_menu()
    )


# --- Команда /cancel ---
@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "❌ Действие отменено.",
        reply_markup=main_menu()
    )


# --- Обработчики callback'ов ---

# Профиль пользователя
@router.callback_query(F.data == "profile")
async def profile_callback(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    if not user:
        await callback.answer("Пожалуйста, используйте /start", show_alert=True)
        return
    
    end_date = datetime.fromisoformat(user[4]) if user[4] else None
    days_left = (end_date - datetime.now()).days if end_date else 0
    is_trial = "Да" if user[5] == 0 else "Нет"
    ref_count = get_referral_count(callback.from_user.id)
    
    text = (
        f"👤 *Ваш профиль*\n\n"
        f"🆔 ID: {user[0]}\n"
        f"👤 Имя: {user[2]}\n"
        f"📧 Email: {user[3]}\n"
        f"📅 Подписка до: {end_date.strftime('%d.%m.%Y %H:%M') if end_date else 'Не активна'}\n"
        f"⏳ Осталось дней: {max(0, days_left)}\n"
        f"🎁 Пробный период: {is_trial}\n"
        f"👥 Рефералов: {ref_count}\n"
        f"⭐ Бонусных дней: {user[6]}"
    )
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=back_button())
    await callback.answer()


# Покупка подписки
@router.callback_query(F.data == "buy")
async def buy_callback(callback: CallbackQuery):
    await callback.message.edit_text(
        "💳 *Выберите способ оплаты*\n\n"
        "💰 Цена: 100 ₽ / 100 ⭐\n"
        "📅 Срок: 30 дней\n\n"
        "Выберите удобный способ оплаты:",
        parse_mode="Markdown",
        reply_markup=payment_methods()
    )
    await callback.answer()


# --- ОПЛАТА КАРТОЙ/СБП ЧЕРЕЗ PLATEGA.IO ---
@router.callback_query(F.data == "pay_card")
async def pay_card_callback(callback: CallbackQuery):
    telegram_id = callback.from_user.id
    
    user = get_user(telegram_id)
    if not user:
        await callback.answer("Пожалуйста, используйте /start", show_alert=True)
        return
    
    # Генерируем уникальный номер заказа
    order_id = f"order_{telegram_id}_{int(time.time())}"
    
    # Создаем платеж через Platega.io
    result = platega.create_payment(
        amount=PRICE_RUB,
        description=f"Подписка VPN (30 дней) для пользователя {telegram_id}",
        order_id=order_id,
        return_url="https://t.me",
        payment_method=2,  # 2 = СБП
    )
    
    if result["success"]:
        # Сохраняем платеж в БД
        create_payment(result["transaction_id"], telegram_id, PRICE_RUB, "platega_sbp")
        
        # Сохраняем для проверки
        pending_payments[telegram_id] = result["transaction_id"]
        
        await callback.message.edit_text(
            f"💳 *Оплата через СБП (Platega.io)*\n\n"
            f"💰 Сумма: {PRICE_RUB} ₽\n"
            f"🆔 Заказ: {result['order_id']}\n\n"
            f"⬇️ Нажмите кнопку ниже для перехода на страницу оплаты.\n"
            f"✅ После оплаты нажмите 'Проверить оплату'.\n\n"
            f"🔹 Вы будете перенаправлены в приложение вашего банка для оплаты через СБП.\n\n"
            f"⏳ Платеж действителен 15 минут.",
            parse_mode="Markdown",
            reply_markup=pay_card_button(result["payment_url"])
        )
    else:
        error_msg = result.get("error", "Неизвестная ошибка")
        await callback.message.edit_text(
            f"❌ *Ошибка при создании платежа*\n\n"
            f"Причина: {error_msg}\n\n"
            f"Попробуйте позже или выберите другой способ оплаты.",
            parse_mode="Markdown",
            reply_markup=payment_methods()
        )
    
    await callback.answer()


# --- ПРОВЕРКА ОПЛАТЫ ---
@router.callback_query(F.data == "check_payment")
async def check_payment_callback(callback: CallbackQuery):
    telegram_id = callback.from_user.id
    
    if telegram_id not in pending_payments:
        await callback.answer("❌ Нет активных платежей", show_alert=True)
        return
    
    transaction_id = pending_payments[telegram_id]
    
    # Проверяем статус платежа в Platega.io
    status = platega.check_payment_status(transaction_id)
    
    if not status["success"]:
        await callback.answer(
            f"❌ Ошибка проверки: {status.get('error', 'Неизвестная ошибка')}",
            show_alert=True
        )
        return
    
    if status["is_paid"]:
        # Подтверждаем платеж в БД
        confirm_payment(transaction_id)
        
        # Активируем подписку
        success, result = await activate_subscription(
            telegram_id, 
            SUB_DAYS, 
            "СБП (Platega.io)"
        )
        
        if success:
            await callback.message.edit_text(
                f"✅ *Оплата подтверждена!*\n\n"
                f"🎉 Подписка успешно активирована!\n"
                f"📅 Действительна до: {result.strftime('%d.%m.%Y %H:%M')}",
                parse_mode="Markdown",
                reply_markup=main_menu()
            )
        else:
            await callback.message.edit_text(
                "❌ *Ошибка активации подписки*\n\n"
                "Платеж прошел, но возникла техническая ошибка.\n"
                "Пожалуйста, обратитесь к администратору.",
                parse_mode="Markdown",
                reply_markup=main_menu()
            )
        
        # Удаляем из временного хранилища
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
                f"❌ *Платеж был отменен*\n\n"
                f"Попробуйте еще раз или выберите другой способ оплаты.",
                parse_mode="Markdown",
                reply_markup=payment_methods()
            )
            del pending_payments[telegram_id]
        else:
            await callback.answer(message, show_alert=True)


# --- ОПЛАТА STARS ---
@router.callback_query(F.data == "pay_stars")
async def pay_stars_callback(callback: CallbackQuery):
    await callback.message.answer_invoice(
        title="🌐 Подписка VPN (30 дней)",
        description=f"Доступ к VPN-сервису на 30 дней\n\n"
                    f"✅ Мгновенная активация\n"
                    f"🔒 Безлимитный трафик\n"
                    f"⚡ Высокая скорость\n\n"
                    f"💰 Стоимость: 100 ⭐",
        payload="subscription_30days_stars",
        currency="XTR",
        prices=[{"label": "Подписка на месяц", "amount": STAR_PRICE}],
        provider_token="",
        reply_markup=back_button()
    )
    await callback.answer()


@router.pre_checkout_query()
async def pre_checkout_query(pre_checkout: types.PreCheckoutQuery):
    await pre_checkout.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment(message: Message):
    telegram_id = message.from_user.id
    
    payment_id = f"stars_{telegram_id}_{int(datetime.now().timestamp())}"
    create_payment(payment_id, telegram_id, STAR_PRICE, "stars")
    confirm_payment(payment_id)
    
    success, result = await activate_subscription(
        telegram_id,
        SUB_DAYS,
        "⭐ Telegram Stars"
    )
    
    if success:
        await message.answer(
            f"✅ *Оплата Stars прошла успешно!*\n\n"
            f"🎉 Подписка активирована!\n"
            f"📅 Действительна до: {result.strftime('%d.%m.%Y %H:%M')}",
            parse_mode="Markdown",
            reply_markup=main_menu()
        )
    else:
        await message.answer(
            "❌ *Ошибка активации подписки*\n\n"
            "Платеж прошел, но возникла техническая ошибка.\n"
            "Пожалуйста, обратитесь к администратору.",
            parse_mode="Markdown",
            reply_markup=main_menu()
        )


# --- ПРОМОКОДЫ ---
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


# --- РЕФЕРАЛЬНАЯ СИСТЕМА ---
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
        f"За каждого приглашенного друга, который активирует подписку,\n"
        f"вы получите +{REFERRAL_BONUS_DAYS} дней к подписке.\n\n"
        f"🔗 Ваша реферальная ссылка:\n"
        f"`{referral_link}`\n\n"
        f"📊 Приглашено друзей: {ref_count}\n"
        f"⭐ Бонусных дней: {user[6] if user else 0}\n\n"
        f"💡 Поделитесь ссылкой с друзьями!"
    )
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=back_button())
    await callback.answer()


# --- ПОМОЩЬ ---
@router.callback_query(F.data == "help")
async def help_callback(callback: CallbackQuery):
    text = (
        f"ℹ️ *Помощь и поддержка*\n\n"
        f"📌 *Как пользоваться ботом:*\n"
        f"1️⃣ Используйте /start для начала\n"
        f"2️⃣ Получите пробный период на 3 дня\n"
        f"3️⃣ Купите подписку через меню\n\n"
        f"💳 *Способы оплаты:*\n"
        f"• СБП через Platega.io\n"
        f"• Telegram Stars\n\n"
        f"🎁 *Промокоды:*\n"
        f"Вводите промокоды в соответствующем разделе\n\n"
        f"👥 *Рефералы:*\n"
        f"Приглашайте друзей и получайте бонусные дни\n\n"
        f"❓ *Вопросы и поддержка:*\n"
        f"@support_bot"
    )
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=back_button())
    await callback.answer()


# --- КНОПКА НАЗАД ---
@router.callback_query(F.data == "back")
async def back_callback(callback: CallbackQuery):
    await callback.message.edit_text(
        "📋 *Главное меню*\n\n"
        "Выберите действие:",
        parse_mode="Markdown",
        reply_markup=main_menu()
    )
    await callback.answer()


# ================================================================================
# АДМИНИСТРАТИВНАЯ ПАНЕЛЬ
# ================================================================================

# Список пользователей
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


# Рассылка
@router.callback_query(F.data == "admin_mailing")
async def admin_mailing(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен")
        return
    
    await callback.message.edit_text(
        "📨 *Рассылка*\n\n"
        "Отправьте сообщение для рассылки.\n"
        "Поддерживается Markdown.\n\n"
        "Для отмены введите /cancel",
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
    
    await state.update_data(mailing_text=message.text, mailing_id=message.message_id)
    
    await message.answer(
        "📨 *Подтверждение рассылки*\n\n"
        "Отправить это сообщение всем пользователям?\n\n"
        f"Текст сообщения:\n{message.text[:200]}...",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Отправить", callback_data="confirm_mailing")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_mailing")]
        ])
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
    
    await callback.message.edit_text(
        f"📨 *Рассылка запущена*\n\n"
        f"Всего пользователей: {len(users)}\n"
        f"Статус: в процессе...",
        parse_mode="Markdown",
        reply_markup=admin_menu()
    )
    await callback.answer()
    
    # Рассылаем
    for user in users:
        try:
            await callback.bot.send_message(
                user[0],
                text,
                parse_mode="Markdown",
                disable_web_page_preview=True
            )
            success += 1
            await asyncio.sleep(0.05)  # Защита от флуда
        except Exception as e:
            logger.error(f"Failed to send to {user[0]}: {e}")
            fail += 1
    
    await callback.message.edit_text(
        f"✅ *Рассылка завершена!*\n\n"
        f"📨 Успешно: {success}\n"
        f"❌ Ошибок: {fail}\n"
        f"👥 Всего: {len(users)}",
        parse_mode="Markdown",
        reply_markup=admin_menu()
    )
    
    await state.clear()


@router.callback_query(F.data == "cancel_mailing")
async def cancel_mailing(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "❌ Рассылка отменена.",
        reply_markup=admin_menu()
    )
    await callback.answer()


# Создание промокода
@router.callback_query(F.data == "admin_create_promo")
async def admin_create_promo(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен")
        return
    
    await callback.message.edit_text(
        "➕ *Создание промокода*\n\n"
        "Введите название промокода (латиница, цифры):\n"
        "Пример: `SUMMER2024`\n\n"
        "Для отмены введите /cancel",
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
    await message.answer(
        "📅 Введите количество бонусных дней (число):\n"
        "Пример: `7`",
        parse_mode="Markdown"
    )
    await state.set_state(AdminStates.waiting_for_promo_bonus)


@router.message(AdminStates.waiting_for_promo_bonus)
async def process_promo_bonus(message: Message, state: FSMContext):
    try:
        days = int(message.text)
        if days <= 0:
            await message.answer("❌ Введите число больше 0:")
            return
        
        await state.update_data(promo_bonus=days)
        await message.answer(
            "🔢 Введите максимальное количество использований (число):\n"
            "Пример: `100`",
            parse_mode="Markdown"
        )
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
        
        # Создаем промокод
        create_promocode(code, bonus, uses)
        
        await message.answer(
            f"✅ *Промокод создан!*\n\n"
            f"🎫 Код: `{code}`\n"
            f"📅 Бонусных дней: {bonus}\n"
            f"🔢 Максимум использований: {uses}\n\n"
            f"Промокод активен!",
            parse_mode="Markdown",
            reply_markup=admin_menu()
        )
        await state.clear()
    except ValueError:
        await message.answer("❌ Введите число! Попробуйте снова:")


# Удаление промокода
@router.callback_query(F.data == "admin_delete_promo")
async def admin_delete_promo(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен")
        return
    
    promos = get_all_promocodes()
    
    if not promos:
        await callback.message.edit_text(
            "📭 *Нет активных промокодов*",
            parse_mode="Markdown",
            reply_markup=admin_menu()
        )
        await callback.answer()
        return
    
    text = "🗑 *Удаление промокода*\n\n"
    text += "Выберите код для удаления:\n\n"
    
    for promo in promos:
        text += f"`{promo[0]}` - {promo[1]} дн. ({promo[3]}/{promo[2]})\n"
    
    text += "\nВведите код для удаления:"
    
    await callback.message.edit_text(text, parse_mode="Markdown")
    await state.set_state(AdminStates.waiting_for_promo_delete)
    await callback.answer()


@router.message(AdminStates.waiting_for_promo_delete)
async def process_promo_delete(message: Message, state: FSMContext):
    code = message.text.strip().upper()
    
    # Проверяем, существует ли промокод
    promo = get_promocode(code)
    if not promo:
        await message.answer("❌ Промокод не найден. Попробуйте снова:")
        return
    
    delete_promocode(code)
    await message.answer(
        f"✅ Промокод `{code}` удален.",
        parse_mode="Markdown",
        reply_markup=admin_menu()
    )
    await state.clear()


# Платежи
@router.callback_query(F.data == "admin_payments")
async def admin_payments(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен")
        return
    
    payments = get_all_payments()
    
    if not payments:
        await callback.message.edit_text(
            "📭 *Нет платежей*",
            parse_mode="Markdown",
            reply_markup=admin_menu()
        )
        await callback.answer()
        return
    
    text = "💰 *Последние платежи:*\n\n"
    
    for payment in payments[:10]:
        status_emoji = {
            'pending': '⏳',
            'confirmed': '✅',
            'canceled': '❌'
        }.get(payment[4], '❓')
        
        text += (
            f"{status_emoji} #{payment[0][:8]} | "
            f"Пользователь: {payment[1]} | "
            f"{payment[2]} руб. | "
            f"{payment[3]} | "
            f"{payment[4]}\n"
        )
    
    if len(payments) > 10:
        text += f"\n... и еще {len(payments) - 10} платежей"
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=admin_menu())
    await callback.answer()


# Управление админами
@router.callback_query(F.data == "admin_admins")
async def admin_admins(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен")
        return
    
    admins = get_all_admins()
    text = "👤 *Управление администраторами*\n\n"
    text += "Текущие админы:\n"
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
    
    await callback.message.edit_text(
        "➕ *Добавление администратора*\n\n"
        "Введите Telegram ID пользователя, которого хотите сделать админом:",
        parse_mode="Markdown"
    )
    await state.set_state(AdminStates.waiting_for_add_admin)
    await callback.answer()


@router.message(AdminStates.waiting_for_add_admin)
async def process_add_admin(message: Message, state: FSMContext):
    try:
        admin_id = int(message.text.strip())
        add_admin(admin_id)
        await message.answer(
            f"✅ Пользователь `{admin_id}` теперь администратор.",
            parse_mode="Markdown",
            reply_markup=admin_menu()
        )
        await state.clear()
    except ValueError:
        await message.answer("❌ Введите корректный Telegram ID (число):")


@router.callback_query(F.data == "admin_remove_admin")
async def admin_remove_admin(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен")
        return
    
    await callback.message.edit_text(
        "➖ *Удаление администратора*\n\n"
        "Введите Telegram ID администратора, которого хотите удалить:",
        parse_mode="Markdown"
    )
    await state.set_state(AdminStates.waiting_for_remove_admin)
    await callback.answer()


@router.message(AdminStates.waiting_for_remove_admin)
async def process_remove_admin(message: Message, state: FSMContext):
    try:
        admin_id = int(message.text.strip())
        
        # Нельзя удалить самого себя
        if admin_id == message.from_user.id:
            await message.answer("❌ Вы не можете удалить самого себя!")
            return
        
        remove_admin(admin_id)
        await message.answer(
            f"✅ Администратор `{admin_id}` удален.",
            parse_mode="Markdown",
            reply_markup=admin_menu()
        )
        await state.clear()
    except ValueError:
        await message.answer("❌ Введите корректный Telegram ID (число):")


@router.callback_query(F.data == "back_admin")
async def back_admin(callback: CallbackQuery):
    await callback.message.edit_text(
        "🔐 *Административная панель*\n\n"
        "Выберите действие:",
        parse_mode="Markdown",
        reply_markup=admin_menu()
    )
    await callback.answer()