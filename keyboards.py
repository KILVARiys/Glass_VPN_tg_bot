from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def main_menu():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Мой профиль", callback_data="profile")],
        [InlineKeyboardButton(text="🛒 Купить подписку", callback_data="buy")],
        [InlineKeyboardButton(text="🎁 Активировать пробную подписку", callback_data="activate_trial")],
        [InlineKeyboardButton(text="🎁 Ввести промокод", callback_data="promo")],
        [InlineKeyboardButton(text="👥 Реферальная система", callback_data="referral")],
        [InlineKeyboardButton(text="📄 Документация", callback_data="docs")],
        [InlineKeyboardButton(text="ℹ️ Помощь", callback_data="help")],
    ])
    return keyboard


def main_menu_without_trial():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Мой профиль", callback_data="profile")],
        [InlineKeyboardButton(text="🛒 Купить подписку", callback_data="buy")],
        [InlineKeyboardButton(text="🎁 Ввести промокод", callback_data="promo")],
        [InlineKeyboardButton(text="👥 Реферальная система", callback_data="referral")],
        [InlineKeyboardButton(text="📄 Документация", callback_data="docs")],
        [InlineKeyboardButton(text="ℹ️ Помощь", callback_data="help")],
    ])
    return keyboard


def docs_menu():
    """Меню раздела «Документация» — ссылки открываются в браузере."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🔒 Политика конфиденциальности",
            url="https://telegra.ph/Politika-konfidencialnosti-04-01-26"
        )],
        [InlineKeyboardButton(
            text="📋 Пользовательское соглашение",
            url="https://telegra.ph/Polzovatelskoe-soglashenie-04-01-19"
        )],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back")],
    ])
    return keyboard


def profile_keyboard(is_active: bool):
    if is_active:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Продлить подписку (30 дней)", callback_data="extend_subscription")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back")]
        ])
    else:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛒 Купить подписку", callback_data="buy")],
            [InlineKeyboardButton(text="🎁 Активировать пробную подписку", callback_data="activate_trial")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back")]
        ])


def payment_methods():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Карта/СБП (100 ₽)", callback_data="pay_card")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back")]
    ])
    return keyboard


def buy_menu():
    return payment_methods()


def admin_menu():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Список пользователей", callback_data="admin_users")],
        [InlineKeyboardButton(text="📨 Рассылка", callback_data="admin_mailing")],
        [InlineKeyboardButton(text="➕ Создать промокод", callback_data="admin_create_promo")],
        [InlineKeyboardButton(text="🗑 Удалить промокод", callback_data="admin_delete_promo")],
        [InlineKeyboardButton(text="💰 Платежи", callback_data="admin_payments")],
        [InlineKeyboardButton(text="🎫 Тикеты поддержки", callback_data="admin_tickets")],
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
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_payment")]
    ])
    return keyboard


def confirm_back():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_action")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back")]
    ])
    return keyboard
