from flask import Flask, request, jsonify
import logging
import threading
import asyncio
from datetime import datetime

from database import confirm_payment, get_user, update_subscription
from payment_platega import PlategaPaymentClient
from config import WEBHOOK_PATH, SUB_DAYS

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация клиента Platega.io
platega = PlategaPaymentClient()

# Хранилище для обработки в фоне
pending_activations = {}


def activate_subscription_sync(telegram_id: int, transaction_id: str):
    """
    Синхронная версия активации подписки для webhook
    """
    try:
        user = get_user(telegram_id)
        if not user:
            logger.error(f"User {telegram_id} not found")
            return False
        
        # Обновляем подписку
        from datetime import timedelta
        new_end = update_subscription(telegram_id, SUB_DAYS)
        
        logger.info(f"✅ Subscription activated for user {telegram_id} until {new_end}")
        return True
    except Exception as e:
        logger.error(f"❌ Activation error: {e}")
        return False


@app.route('/platega_callback', methods=['POST'])
def platega_callback():
    """
    Принимает callback-уведомления от Platega.io
    """
    try:
        # Получаем данные
        data = request.get_json()
        signature = request.headers.get('X-Signature', '')
        
        logger.info(f"📨 Platega callback received: {data}")
        
        # Обрабатываем уведомление
        result = platega.handle_callback(data, signature)
        
        if result.get("success"):
            event = result.get("event")
            transaction_id = result.get("transaction_id")
            order_id = result.get("order_id")
            
            logger.info(f"✅ Callback processed: {event} for {transaction_id}")
            
            if event == "payment.succeeded":
                # Извлекаем telegram_id из order_id
                if order_id and order_id.startswith("order_"):
                    parts = order_id.split("_")
                    if len(parts) >= 3:
                        telegram_id = int(parts[1])
                        
                        # Подтверждаем платеж в БД
                        confirm_payment(transaction_id)
                        logger.info(f"✅ Payment {transaction_id} confirmed in database")
                        
                        # Активируем подписку
                        if activate_subscription_sync(telegram_id, transaction_id):
                            logger.info(f"✅ Subscription activated for user {telegram_id}")
                            return "OK", 200
                        else:
                            logger.error(f"❌ Failed to activate subscription for {telegram_id}")
                            return "error", 500
            
            return result.get("response", "OK"), 200
        
        # Если подпись неверная
        logger.warning(f"❌ Invalid callback signature: {data}")
        return "bad sign", 403
        
    except Exception as e:
        logger.error(f"❌ Platega callback error: {e}")
        return "error", 500


@app.route('/platega_success', methods=['GET'])
def platega_success():
    """
    Страница успешной оплаты (перенаправление клиента)
    """
    transaction_id = request.args.get("transaction_id", "неизвестен")
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Оплата успешна</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
                background: #f0f4f8;
                margin: 0;
            }}
            .container {{
                background: white;
                padding: 40px;
                border-radius: 16px;
                box-shadow: 0 4px 20px rgba(0,0,0,0.1);
                text-align: center;
                max-width: 500px;
            }}
            .success {{
                color: #22c55e;
                font-size: 64px;
                margin-bottom: 20px;
            }}
            h1 {{
                color: #1e293b;
                margin-bottom: 10px;
            }}
            p {{
                color: #475569;
                margin: 10px 0;
            }}
            .button {{
                display: inline-block;
                margin-top: 20px;
                padding: 12px 30px;
                background: #3b82f6;
                color: white;
                text-decoration: none;
                border-radius: 8px;
                font-weight: bold;
            }}
            .button:hover {{
                background: #2563eb;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="success">✅</div>
            <h1>Оплата прошла успешно!</h1>
            <p>Транзакция #{transaction_id} оплачена.</p>
            <p>Можете вернуться в Telegram-бот для активации подписки.</p>
            <a href="https://t.me" class="button">📱 Вернуться в Telegram</a>
        </div>
    </body>
    </html>
    """


@app.route('/platega_fail', methods=['GET'])
def platega_fail():
    """
    Страница ошибки оплаты
    """
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Оплата не прошла</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
                background: #f0f4f8;
                margin: 0;
            }}
            .container {{
                background: white;
                padding: 40px;
                border-radius: 16px;
                box-shadow: 0 4px 20px rgba(0,0,0,0.1);
                text-align: center;
                max-width: 500px;
            }}
            .error {{
                color: #ef4444;
                font-size: 64px;
                margin-bottom: 20px;
            }}
            h1 {{
                color: #1e293b;
                margin-bottom: 10px;
            }}
            p {{
                color: #475569;
                margin: 10px 0;
            }}
            .button {{
                display: inline-block;
                margin-top: 20px;
                padding: 12px 30px;
                background: #3b82f6;
                color: white;
                text-decoration: none;
                border-radius: 8px;
                font-weight: bold;
            }}
            .button:hover {{
                background: #2563eb;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="error">❌</div>
            <h1>Оплата не прошла</h1>
            <p>Попробуйте еще раз или выберите другой способ оплаты.</p>
            <a href="https://t.me" class="button">📱 Вернуться в Telegram</a>
        </div>
    </body>
    </html>
    """


@app.route('/health', methods=['GET'])
def health():
    """Проверка работоспособности сервера"""
    return jsonify({
        "status": "ok",
        "service": "Platega.io Webhook Server",
        "timestamp": datetime.now().isoformat(),
        "endpoints": {
            "/platega_callback": "POST - Platega.io Callback URL",
            "/platega_success": "GET - Success page",
            "/platega_fail": "GET - Fail page",
            "/health": "GET - Health check"
        }
    }), 200


@app.route('/', methods=['GET'])
def index():
    return jsonify({
        "service": "Platega.io Webhook Server",
        "status": "running",
        "endpoints": {
            "/platega_callback": "POST - Platega.io Callback URL",
            "/platega_success": "GET - Success page",
            "/platega_fail": "GET - Fail page",
            "/health": "GET - Health check"
        }
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)