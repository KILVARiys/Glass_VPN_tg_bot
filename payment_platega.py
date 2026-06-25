import logging
import uuid
from typing import Optional, Dict, Any

import aiohttp
import requests

from config import PLATEGA_MERCHANT_ID, PLATEGA_SECRET_KEY, WEBHOOK_HOST, WEBHOOK_PATH

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Методы оплаты Platega.io (см. "Список доступных методов оплат") ---
PAYMENT_METHOD_SBP = 2            # СБП / QR (НСПК)
PAYMENT_METHOD_CARD_RU = 10       # Карты МИР
PAYMENT_METHOD_INTERNATIONAL = 12  # Международный эквайринг

# --- Статусы транзакции (PaymentStatus) ---
STATUS_PENDING = "PENDING"
STATUS_CONFIRMED = "CONFIRMED"
STATUS_EXPIRED = "EXPIRED"
STATUS_CANCELED = "CANCELED"
STATUS_FAILED = "FAILED"

FAILED_STATUSES = {STATUS_CANCELED, STATUS_FAILED, STATUS_EXPIRED}


class PlategaPaymentClient:
    """
    Клиент для работы с платёжной системой Platega.io.

    Базовый URL API: https://app.platega.io
    Авторизация: заголовки X-MerchantId и X-Secret в каждом запросе.
    """

    BASE_URL = "https://app.platega.io"

    def __init__(self):
        self.merchant_id = PLATEGA_MERCHANT_ID
        self.secret_key = PLATEGA_SECRET_KEY
        # Полный адрес, на который Platega.io будет слать уведомления об оплате.
        # Должен указываться в Личном кабинете -> Настройки -> Callback URLs
        self.callback_url = f"{WEBHOOK_HOST.rstrip('/')}{WEBHOOK_PATH}"

        self._session: Optional[requests.Session] = None
        self._async_session: Optional[aiohttp.ClientSession] = None

    # ---------------------------------------------------------------- #
    # Служебное
    # ---------------------------------------------------------------- #

    def _headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-MerchantId": self.merchant_id,
            "X-Secret": self.secret_key,
        }

    def _get_session(self) -> requests.Session:
        if self._session is None:
            self._session = requests.Session()
            self._session.headers.update(self._headers())
        return self._session

    async def _get_async_session(self) -> aiohttp.ClientSession:
        if self._async_session is None or self._async_session.closed:
            self._async_session = aiohttp.ClientSession(headers=self._headers())
        return self._async_session

    @staticmethod
    def _safe_json(response) -> Dict[str, Any]:
        try:
            return response.json()
        except Exception:
            return {}

    # ---------------------------------------------------------------- #
    # Создание платежа — POST app.platega.io/transaction/process
    # ---------------------------------------------------------------- #

    def _build_create_payload(
        self,
        amount: float,
        description: str,
        transaction_id: str,
        return_url: str,
        failed_url: str,
        payment_method: int,
        payload: Optional[str],
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "paymentMethod": payment_method,
            # Передаём свой UUID транзакции — это позволяет нам однозначно
            # сопоставить заказ в нашей БД с транзакцией Platega.
            "id": transaction_id,
            "paymentDetails": {
                "amount": float(amount),
                "currency": "RUB",
            },
            "description": description,
            "return": return_url,
            "failedUrl": failed_url,
        }
        if payload:
            # Произвольное поле для хранения своей информации (например, telegram_id)
            body["payload"] = str(payload)
        return body

    def create_payment(
        self,
        amount: float,
        description: str,
        order_id: Optional[str] = None,
        return_url: str = "https://t.me",
        failed_url: str = "https://t.me",
        payment_method: int = PAYMENT_METHOD_SBP,
        payload: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Создаёт платёж через Platega.io (синхронная версия).

        Returns:
            {success, payment_url, transaction_id, order_id, status, expires_in, data}
        """
        # ID транзакции обязан быть в формате UUID
        transaction_id = order_id if order_id else str(uuid.uuid4())
        body = self._build_create_payload(
            amount, description, transaction_id, return_url, failed_url, payment_method, payload
        )

        url = f"{self.BASE_URL}/transaction/process"
        session = self._get_session()

        try:
            response = session.post(url, json=body, timeout=30)
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Platega.io request error: {e}")
            return {"success": False, "error": str(e), "payment_url": None,
                    "transaction_id": None, "order_id": order_id}

        data = self._safe_json(response)

        if response.status_code >= 400:
            error_message = data.get("message", f"HTTP {response.status_code}")
            logger.error(f"❌ Platega.io API error: {error_message}")
            return {"success": False, "error": error_message, "payment_url": None,
                    "transaction_id": None, "order_id": order_id}

        # На случай, если сервер вернёт свой собственный transactionId,
        # отличный от переданного нами id — ориентируемся на ответ сервера.
        returned_id = data.get("transactionId", transaction_id)
        if returned_id != transaction_id:
            logger.warning(
                f"⚠️ Platega.io вернул transactionId ({returned_id}), "
                f"отличный от переданного id ({transaction_id}). Используем ответ сервера."
            )

        return {
            "success": True,
            "payment_url": data.get("redirect"),
            "transaction_id": returned_id,
            "order_id": order_id or returned_id,
            "status": data.get("status"),
            "expires_in": data.get("expiresIn"),
            "data": data,
        }

    async def create_payment_async(
        self,
        amount: float,
        description: str,
        order_id: Optional[str] = None,
        return_url: str = "https://t.me",
        failed_url: str = "https://t.me",
        payment_method: int = PAYMENT_METHOD_SBP,
        payload: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Создаёт платёж через Platega.io (асинхронная версия)."""
        transaction_id = order_id if order_id else str(uuid.uuid4())
        body = self._build_create_payload(
            amount, description, transaction_id, return_url, failed_url, payment_method, payload
        )

        url = f"{self.BASE_URL}/transaction/process"
        session = await self._get_async_session()

        try:
            async with session.post(url, json=body, timeout=30) as response:
                try:
                    data = await response.json()
                except Exception:
                    data = {}

                if response.status >= 400:
                    error_message = data.get("message", f"HTTP {response.status}")
                    logger.error(f"❌ Platega.io API error: {error_message}")
                    return {"success": False, "error": error_message, "payment_url": None,
                            "transaction_id": None, "order_id": order_id}

                returned_id = data.get("transactionId", transaction_id)
                return {
                    "success": True,
                    "payment_url": data.get("redirect"),
                    "transaction_id": returned_id,
                    "order_id": order_id or returned_id,
                    "status": data.get("status"),
                    "expires_in": data.get("expiresIn"),
                    "data": data,
                }
        except aiohttp.ClientError as e:
            logger.error(f"❌ Platega.io async request error: {e}")
            return {"success": False, "error": str(e), "payment_url": None,
                    "transaction_id": None, "order_id": order_id}

    # ---------------------------------------------------------------- #
    # Проверка статуса — GET app.platega.io/transaction/{id}
    # ---------------------------------------------------------------- #

    def check_payment_status(self, transaction_id: str) -> Dict[str, Any]:
        """Проверяет статус платежа (синхронная версия)."""
        url = f"{self.BASE_URL}/transaction/{transaction_id}"
        session = self._get_session()

        try:
            response = session.get(url, timeout=30)
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Platega.io request error: {e}")
            return {"success": False, "error": str(e), "status": None, "is_paid": False}

        data = self._safe_json(response)

        if response.status_code >= 400:
            error_message = data.get("message", f"HTTP {response.status_code}")
            logger.error(f"❌ Platega.io API error: {error_message}")
            return {"success": False, "error": error_message, "status": None, "is_paid": False}

        status = data.get("status")
        payment_details = data.get("paymentDetails") or {}

        return {
            "success": True,
            "status": status,
            "is_paid": status == STATUS_CONFIRMED,
            "is_failed": status in FAILED_STATUSES,
            "amount": payment_details.get("amount"),
            "transaction_id": data.get("id", transaction_id),
            "payload": data.get("payload"),
            "data": data,
        }

    async def check_payment_status_async(self, transaction_id: str) -> Dict[str, Any]:
        """Проверяет статус платежа (асинхронная версия)."""
        url = f"{self.BASE_URL}/transaction/{transaction_id}"
        session = await self._get_async_session()

        try:
            async with session.get(url, timeout=30) as response:
                try:
                    data = await response.json()
                except Exception:
                    data = {}

                if response.status >= 400:
                    error_message = data.get("message", f"HTTP {response.status}")
                    logger.error(f"❌ Platega.io API error: {error_message}")
                    return {"success": False, "error": error_message, "status": None, "is_paid": False}

                status = data.get("status")
                payment_details = data.get("paymentDetails") or {}

                return {
                    "success": True,
                    "status": status,
                    "is_paid": status == STATUS_CONFIRMED,
                    "is_failed": status in FAILED_STATUSES,
                    "amount": payment_details.get("amount"),
                    "transaction_id": data.get("id", transaction_id),
                    "payload": data.get("payload"),
                    "data": data,
                }
        except aiohttp.ClientError as e:
            logger.error(f"❌ Platega.io async request error: {e}")
            return {"success": False, "error": str(e), "status": None, "is_paid": False}

    # ---------------------------------------------------------------- #
    # Callback от Platega.io (входящие уведомления об оплате)
    # ---------------------------------------------------------------- #

    def verify_callback_headers(self, merchant_id_header: str, secret_header: str) -> bool:
        """
        Platega.io присылает callback с заголовками X-MerchantId и X-Secret —
        нужно сверить их с нашими собственными значениями (НЕ HMAC-подпись!).
        """
        return (
            merchant_id_header == self.merchant_id
            and secret_header == self.secret_key
            and bool(self.merchant_id)
            and bool(self.secret_key)
        )

    def handle_callback(
        self,
        body: Dict[str, Any],
        merchant_id_header: str,
        secret_header: str,
    ) -> Dict[str, Any]:
        """
        Обрабатывает callback-уведомление от Platega.io.

        Тело запроса (CallbackPayload):
            {"id": "...", "amount": 0.0, "currency": "RUB",
            "status": "CONFIRMED", "paymentMethod": 2}
        """
        if not self.verify_callback_headers(merchant_id_header, secret_header):
            logger.warning("❌ Platega callback: неверные X-MerchantId/X-Secret")
            return {"success": False, "error": "invalid credentials"}

        transaction_id = body.get("id")
        status = body.get("status")

        logger.info(f"📨 Platega callback: transaction={transaction_id} status={status}")

        return {
            "success": True,
            "transaction_id": transaction_id,
            "status": status,
            "is_paid": status == STATUS_CONFIRMED,
            "is_failed": status in FAILED_STATUSES,
            "amount": body.get("amount"),
            "currency": body.get("currency"),
            "payment_method": body.get("paymentMethod"),
        }

    # ---------------------------------------------------------------- #
    # Закрытие соединений
    # ---------------------------------------------------------------- #

    def close(self):
        if self._session:
            self._session.close()
            self._session = None
            logger.info("🔒 Platega.io sync session closed")

    async def close_async(self):
        if self._async_session and not self._async_session.closed:
            await self._async_session.close()
            self._async_session = None
            logger.info("🔒 Platega.io async session closed")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close_async()