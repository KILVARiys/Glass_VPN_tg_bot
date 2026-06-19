from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

def main_menu():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Мой профиль", callback_data="profile")],
        [InlineKeyboardButton(text="🛒 Купить подписку", callback_data="buy")],
        [InlineKeyboardButton(text="🎁 Ввести промокод", callback_data="promo")],
        [InlineKeyboardButton(text="👥 Реферальная система", callback_data="referral")],
        [InlineKeyboardButton(text="ℹ️ Помощь", callback_data="help")]
    ])
    return keyboard

def payment_methods():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Карта/СБП (100 ₽)", callback_data="pay_card")],
        [InlineKeyboardButton(text="⭐ Telegram Stars (100 ⭐)", callback_data="pay_stars")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back")]
    ])
    return keyboard

def buy_menu():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Карта/СБП (100 ₽)", callback_data="pay_card")],
        [InlineKeyboardButton(text="⭐ Telegram Stars (100 ⭐)", callback_data="pay_stars")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back")]
    ])
    return keyboard

def admin_menu():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Список пользователей", callback_data="admin_users")],
        [InlineKeyboardButton(text="📨 Рассылка", callback_data="admin_mailing")],
        [InlineKeyboardButton(text="➕ Создать промокод", callback_data="admin_create_promo")],
        [InlineKeyboardButton(text="🗑 Удалить промокод", callback_data="admin_delete_promo")],
        [InlineKeyboardButton(text="💰 Платежи", callback_data="admin_payments")],
        [InlineKeyboardButton(text="👤 Управление админами", callback_data="admin_admins")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back")]
    ])
    return keyboard

def back_button():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back")]
    ])
    return keyboard

def pay_card_button(url):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Перейти к оплате", url=url)],
        [InlineKeyboardButton(text="✅ Проверить оплату", callback_data="check_payment")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back")]
    ])
    return keyboard

def confirm_back():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_action")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back")]
    ])
    return keyboard