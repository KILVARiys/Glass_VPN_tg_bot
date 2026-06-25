from flask import Flask, request, jsonify
import logging
from datetime import datetime

from database import confirm_payment, get_payment, update_subscription
from payment_platega import PlategaPaymentClient
from config import WEBHOOK_PATH, WEBHOOK_PORT, SUB_DAYS

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация клиента Platega.io (используется только для проверки
# заголовков callback'а — verify_callback_headers/handle_callback)
platega = PlategaPaymentClient()


def activate_subscription_sync(telegram_id: int, days: int = SUB_DAYS) -> bool:
    """
    Синхронная активация/продление подписки после подтверждения оплаты.
    Здесь обновляется только срок подписки в БД. Если вам нужно также
    выдавать/обновлять клиента в 3x-UI (как это делает activate_subscription
    в handlers.py), либо вызывайте бот через очередь задач, либо продлевайте
    существующего xui-клиента отдельным вызовом XUIClient здесь же.
    """
    try:
        new_end = update_subscription(telegram_id, days)
        logger.info(f"✅ Подписка для {telegram_id} продлена до {new_end}")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка активации подписки для {telegram_id}: {e}")
        return False


@app.route(WEBHOOK_PATH, methods=['POST'])
def platega_callback():
    """
    Принимает callback-уведомления от Platega.io.

    Platega шлёт POST с заголовками X-MerchantId / X-Secret и телом:
        {"id": "...", "amount": 0.0, "currency": "RUB",
        "status": "CONFIRMED", "paymentMethod": 2}

    Если не ответить 200 за 60 секунд — Platega повторит запрос
    до 3 раз с интервалом 5 минут.
    """
    try:
        body = request.get_json(silent=True) or {}
        merchant_id_header = request.headers.get('X-MerchantId', '')
        secret_header = request.headers.get('X-Secret', '')

        logger.info(f"📨 Platega callback получен: {body}")

        result = platega.handle_callback(body, merchant_id_header, secret_header)

        if not result.get("success"):
            logger.warning(f"❌ Callback отклонён: {result.get('error')}")
            return "unauthorized", 401

        transaction_id = result["transaction_id"]
        status = result["status"]

        payment = get_payment(transaction_id)
        if not payment:
            # Платёж не найден в нашей БД — отвечаем 200, чтобы Platega
            # не повторяла запрос бесконечно, но логируем для расследования.
            logger.warning(f"⚠️ Платёж {transaction_id} не найден в локальной БД")
            return "OK", 200

        # Структура строки payments: (payment_id, telegram_id, amount,
        # payment_type, status, created_at, confirmed_at)
        telegram_id = payment[1]
        current_status = payment[4]

        if result.get("is_paid") and current_status != "confirmed":
            confirm_payment(transaction_id)
            if activate_subscription_sync(telegram_id, SUB_DAYS):
                logger.info(f"✅ Платёж {transaction_id} подтверждён, подписка продлена для {telegram_id}")
            else:
                logger.error(f"❌ Платёж {transaction_id} подтверждён, но подписку продлить не удалось")
        elif result.get("is_failed"):
            logger.info(f"❌ Платёж {transaction_id} не прошёл, статус: {status}")

        return "OK", 200

    except Exception as e:
        logger.error(f"❌ Ошибка обработки Platega callback: {e}")
        return "error", 500


@app.route('/platega_success', methods=['GET'])
def platega_success():
    """Страница успешной оплаты (редирект клиента после оплаты)."""
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
h1 {{ color: #1e293b; margin-bottom: 10px; }}
p {{ color: #475569; margin: 10px 0; }}
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
.button:hover {{ background: #2563eb; }}
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
    """Страница ошибки оплаты."""
    return """
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>Оплата не прошла</title>
<style>
body {
    font-family: Arial, sans-serif;
    display: flex;
    justify-content: center;
    align-items: center;
    height: 100vh;
    background: #f0f4f8;
    margin: 0;
}
.container {
    background: white;
    padding: 40px;
    border-radius: 16px;
    box-shadow: 0 4px 20px rgba(0,0,0,0.1);
    text-align: center;
    max-width: 500px;
}
.error { color: #ef4444; font-size: 64px; margin-bottom: 20px; }
h1 { color: #1e293b; margin-bottom: 10px; }
p { color: #475569; margin: 10px 0; }
.button {
    display: inline-block;
    margin-top: 20px;
    padding: 12px 30px;
    background: #3b82f6;
    color: white;
    text-decoration: none;
    border-radius: 8px;
    font-weight: bold;
}
.button:hover { background: #2563eb; }
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
    """Проверка работоспособности сервера."""
    return jsonify({
        "status": "ok",
        "service": "Platega.io Webhook Server",
        "timestamp": datetime.now().isoformat(),
        "endpoints": {
            WEBHOOK_PATH: "POST - Platega.io Callback URL",
            "/platega_success": "GET - Success page",
            "/platega_fail": "GET - Fail page",
            "/health": "GET - Health check",
        },
    }), 200


@app.route('/', methods=['GET'])
def index():
    return jsonify({
        "service": "Platega.io Webhook Server",
        "status": "running",
        "endpoints": {
            WEBHOOK_PATH: "POST - Platega.io Callback URL",
            "/platega_success": "GET - Success page",
            "/platega_fail": "GET - Fail page",
            "/health": "GET - Health check",
        },
    })


if __name__ == "__main__":
    # Запуск как отдельный процесс, например:
    #   python webhook_server.py
    # либо через gunicorn/uwsgi за Nginx с HTTPS:
    #   gunicorn -w 2 -b 0.0.0.0:5000 webhook_server:app
    app.run(host="0.0.0.0", port=WEBHOOK_PORT, debug=False, threaded=True)
