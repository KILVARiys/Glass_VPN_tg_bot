import sqlite3
from datetime import datetime, timedelta
import random
import string

from config import TRIAL_DAYS, REFERRAL_BONUS_DAYS

DB_PATH = "bot.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # Таблица пользователей
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            xui_email TEXT UNIQUE,
            xui_id INTEGER,
            subscription_end TIMESTAMP,
            is_trial_used BOOLEAN DEFAULT 0,
            referrer_id INTEGER,
            balance_days INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица промокодов
    cur.execute('''
        CREATE TABLE IF NOT EXISTS promocodes (
            code TEXT PRIMARY KEY,
            bonus_days INTEGER,
            max_uses INTEGER,
            used_count INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT 1
        )
    ''')
    
    # Таблица использованных промокодов
    cur.execute('''
        CREATE TABLE IF NOT EXISTS used_promocodes (
            telegram_id INTEGER,
            code TEXT,
            PRIMARY KEY (telegram_id, code)
        )
    ''')
    
    # Таблица платежей
    cur.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            payment_id TEXT PRIMARY KEY,
            telegram_id INTEGER,
            amount INTEGER,
            payment_type TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            confirmed_at TIMESTAMP
        )
    ''')
    
    # Таблица рефералов
    cur.execute('''
        CREATE TABLE IF NOT EXISTS referrals (
            referrer_id INTEGER,
            referred_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (referrer_id, referred_id)
        )
    ''')
    
    # Таблица админов
    cur.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            telegram_id INTEGER PRIMARY KEY
        )
    ''')
    
    # Добавляем админа из конфига
    from config import ADMIN_ID
    cur.execute("INSERT OR IGNORE INTO admins (telegram_id) VALUES (?)", (ADMIN_ID,))
    
    conn.commit()
    conn.close()

# --- Работа с пользователями ---
def get_user(telegram_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
    user = cur.fetchone()
    conn.close()
    return user

def get_user_by_email(email):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE xui_email = ?", (email,))
    user = cur.fetchone()
    conn.close()
    return user

def create_user(telegram_id, username, first_name, referrer_id=None):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    xui_email = f"user_{telegram_id}_{random.randint(1000,9999)}@vpn.local"
    trial_end = datetime.now() + timedelta(days=TRIAL_DAYS)
    
    cur.execute('''
        INSERT INTO users (telegram_id, username, first_name, xui_email, subscription_end, is_trial_used, referrer_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (telegram_id, username, first_name, xui_email, trial_end.isoformat(), 0, referrer_id))
    
    conn.commit()
    conn.close()
    
    if referrer_id:
        add_referral(referrer_id, telegram_id)
        add_referral_bonus(referrer_id)
    
    return True

def update_subscription(telegram_id, days_to_add):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    cur.execute("SELECT subscription_end FROM users WHERE telegram_id = ?", (telegram_id,))
    result = cur.fetchone()
    
    if result and result[0]:
        try:
            current_end = datetime.fromisoformat(result[0])
            new_end = current_end + timedelta(days=days_to_add)
        except:
            new_end = datetime.now() + timedelta(days=days_to_add)
    else:
        new_end = datetime.now() + timedelta(days=days_to_add)
    
    cur.execute("UPDATE users SET subscription_end = ? WHERE telegram_id = ?", 
                (new_end.isoformat(), telegram_id))
    conn.commit()
    conn.close()
    return new_end

def set_trial_used(telegram_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE users SET is_trial_used = 1 WHERE telegram_id = ?", (telegram_id,))
    conn.commit()
    conn.close()

def add_referral(referrer_id, referred_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('''
        INSERT OR IGNORE INTO referrals (referrer_id, referred_id)
        VALUES (?, ?)
    ''', (referrer_id, referred_id))
    conn.commit()
    conn.close()

def add_referral_bonus(telegram_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE users SET balance_days = balance_days + ? WHERE telegram_id = ?", 
                (REFERRAL_BONUS_DAYS, telegram_id))
    conn.commit()
    conn.close()

def get_referral_count(telegram_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (telegram_id,))
    count = cur.fetchone()[0]
    conn.close()
    return count

def get_all_users():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT telegram_id, first_name, username, subscription_end FROM users ORDER BY created_at DESC")
    users = cur.fetchall()
    conn.close()
    return users

def get_active_users():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT telegram_id FROM users WHERE subscription_end > datetime('now')")
    users = cur.fetchall()
    conn.close()
    return users

def get_expired_users():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT telegram_id, xui_email FROM users WHERE subscription_end < datetime('now') AND subscription_end IS NOT NULL")
    users = cur.fetchall()
    conn.close()
    return users

# --- Работа с платежами ---
def create_payment(payment_id, telegram_id, amount, payment_type):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO payments (payment_id, telegram_id, amount, payment_type, status)
        VALUES (?, ?, ?, ?, 'pending')
    ''', (payment_id, telegram_id, amount, payment_type))
    conn.commit()
    conn.close()

def confirm_payment(payment_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('''
        UPDATE payments 
        SET status = 'confirmed', confirmed_at = CURRENT_TIMESTAMP 
        WHERE payment_id = ?
    ''', (payment_id,))
    conn.commit()
    conn.close()
    
    cur.execute("SELECT telegram_id FROM payments WHERE payment_id = ?", (payment_id,))
    result = cur.fetchone()
    conn.close()
    return result[0] if result else None

def get_payment(payment_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT * FROM payments WHERE payment_id = ?", (payment_id,))
    payment = cur.fetchone()
    conn.close()
    return payment

def get_pending_payments():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT * FROM payments WHERE status = 'pending' AND created_at < datetime('now', '-15 minutes')")
    payments = cur.fetchall()
    conn.close()
    return payments

def get_all_payments():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT * FROM payments ORDER BY created_at DESC LIMIT 50")
    payments = cur.fetchall()
    conn.close()
    return payments

# --- Работа с промокодами ---
def create_promocode(code, bonus_days, max_uses):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO promocodes (code, bonus_days, max_uses)
        VALUES (?, ?, ?)
    ''', (code.upper(), bonus_days, max_uses))
    conn.commit()
    conn.close()

def get_promocode(code):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT * FROM promocodes WHERE code = ? AND is_active = 1", (code.upper(),))
    promo = cur.fetchone()
    conn.close()
    return promo

def use_promocode(telegram_id, code):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    code = code.upper()
    
    # Проверяем, не использовал ли уже
    cur.execute("SELECT * FROM used_promocodes WHERE telegram_id = ? AND code = ?", (telegram_id, code))
    if cur.fetchone():
        conn.close()
        return False, "Вы уже использовали этот промокод"
    
    promo = get_promocode(code)
    if not promo:
        conn.close()
        return False, "Промокод не найден или неактивен"
    
    if promo[3] >= promo[2]:
        conn.close()
        return False, "Промокод уже использован максимальное число раз"
    
    # Начисляем дни
    bonus_days = promo[1]
    update_subscription(telegram_id, bonus_days)
    
    # Увеличиваем счетчик
    cur.execute("UPDATE promocodes SET used_count = used_count + 1 WHERE code = ?", (code,))
    cur.execute("INSERT INTO used_promocodes (telegram_id, code) VALUES (?, ?)", (telegram_id, code))
    
    conn.commit()
    conn.close()
    return True, f"✅ Промокод активирован! Вам добавлено {bonus_days} дней."

def delete_promocode(code):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM promocodes WHERE code = ?", (code.upper(),))
    conn.commit()
    conn.close()

def get_all_promocodes():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT * FROM promocodes ORDER BY code")
    promos = cur.fetchall()
    conn.close()
    return promos

# --- Проверка админа ---
def is_admin(telegram_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT * FROM admins WHERE telegram_id = ?", (telegram_id,))
    admin = cur.fetchone()
    conn.close()
    return admin is not None

def add_admin(telegram_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO admins (telegram_id) VALUES (?)", (telegram_id,))
    conn.commit()
    conn.close()

def remove_admin(telegram_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM admins WHERE telegram_id = ?", (telegram_id,))
    conn.commit()
    conn.close()

def get_all_admins():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT telegram_id FROM admins")
    admins = cur.fetchall()
    conn.close()
    return [admin[0] for admin in admins]