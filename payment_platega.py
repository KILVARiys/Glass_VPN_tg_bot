import logging
import hmac
import hashlib
import json
from uuid import uuid4
from typing import Optional, Dict, Any
from datetime import datetime
from wsgiref import headers

import aiohttp
import requests

from config import PLATEGA_MERCHANT_ID, PLATEGA_SECRET_KEY, WEBHOOK_HOST

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PlategaPaymentClient:
    """
    Клиент для работы с платежной системой Platega.io
    Поддерживает: СБП (Система быстрых платежей)
    """

    def __init__(self):
        self.merchant_id = PLATEGA_MERCHANT_ID
        self.secret_key = PLATEGA_SECRET_KEY
        self.base_url = "https://app.platega.io"
        self.callback_url = f"{WEBHOOK_HOST}/platega_callback"

        # Для синхронных запросов
        self._session = None
        # Для асинхронных запросов
        self._async_session = None

    def _get_session(self) -> requests.Session:
        """Создает или возвращает существующую синхронную сессию"""
        if self._session is None:
            self._session = requests.Session()
            self._session.headers.update({
                "Content-Type": "application/json",
                "Accept": "application/json"
            })
        return self._session

    async def _get_async_session(self) -> aiohttp.ClientSession:
        """Создает или возвращает существующую асинхронную сессию"""
        if self._async_session is None or self._async_session.closed:
            self._async_session = aiohttp.ClientSession()
        return self._async_session

    # def _generate_signature(self, data: Dict[str, Any]) -> str:
    #     """
    #     Генерирует подпись для запроса к Platega.io
    #     Используется алгоритм HMAC-SHA256
    #     """
    #     # Сортируем данные по ключам
    #     sorted_data = dict(sorted(data.items()))
    #     # Преобразуем в JSON строку
    #     json_string = json.dumps(sorted_data, separators=(',', ':'))
    #     # Генерируем подпись
    #     signature = hmac.new(
    #         self.secret_key.encode('utf-8'),
    #         json_string.encode('utf-8'),
    #         hashlib.sha256
    #     ).hexdigest()
    #     return signature

    def _make_request(self, endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Выполняет синхронный запрос к API Platega.io
        """
        url = f"{self.base_url}{endpoint}"

        headers = {
                "Content-Type": "application/json",
                "X-MerchantId": self.merchant_id,
                "X-Secret": self.secret_key,
            }

        session = self._get_session()

        try:
            response = session.post(url, json=data, headers=headers, timeout=30)

            # Логируем тело ответа при ошибке ДО raise_for_status,
            # иначе текст ответа от Platega теряется
            if response.status_code != 200:
                logger.error(
                    f"❌ Platega.io HTTP {response.status_code} | "
                    f"endpoint: {endpoint} | body: {response.text}"
                )

            response.raise_for_status()
            result = response.json()

            if result.get("status") == "error":
                error_message = result.get("message", "Unknown error")
                logger.error(f"❌ Platega.io API error: {error_message}")
                return {"success": False, "error": error_message, "data": None}

            return {"success": True, "data": result.get("data", result)}

        except requests.exceptions.HTTPError as e:
            # response.text уже залогирован выше — пользователю отдаём короткое сообщение,
            # подробности остаются только в логе
            logger.error(f"❌ Platega.io HTTP error: {e}")
            return {
                "success": False,
                "error": "Платёжный сервис вернул ошибку. Попробуйте позже.",
                "data": None,
            }
        except requests.exceptions.RequestException as e:
            # Сюда попадают сетевые ошибки (DNS, таймаут, обрыв соединения и т.п.)
            # Текст исключения может содержать кавычки/скобки/спецсимволы, которые
            # ломают parse_mode="Markdown" при показе пользователю — поэтому в "error"
            # кладём безопасный текст, а сырое исключение оставляем только в логе.
            logger.error(f"❌ Platega.io request error: {e}")
            return {
                "success": False,
                "error": "Не удалось подключиться к платёжному сервису. Попробуйте позже.",
                "data": None,
            }
        except json.JSONDecodeError as e:
            logger.error(f"❌ Platega.io JSON decode error: {e}")
            return {"success": False, "error": "Invalid response format", "data": None}

    async def _make_async_request(self, endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Выполняет асинхронный запрос к API Platega.io
        """
        url = f"{self.base_url}{endpoint}"

        headers = {
            "Content-Type": "application/json",
            "X-MerchantId": self.merchant_id,
            "X-Secret": self.secret_key,
        }

        session = await self._get_async_session()

        try:
            async with session.post(url, json=data, headers=headers, timeout=30) as response:
                # Сначала читаем сырой текст — он нужен и для лога ошибки,
                # и для парсинга JSON ниже
                raw_text = await response.text()

                if response.status != 200:
                    logger.error(
                        f"❌ Platega.io HTTP {response.status} | "
                        f"endpoint: {endpoint} | body: {raw_text}"
                    )
                    return {
                        "success": False,
                        "error": f"HTTP {response.status}: {raw_text}",
                        "data": None,
                    }

                result = json.loads(raw_text)

                if result.get("status") == "error":
                    error_message = result.get("message", "Unknown error")
                    logger.error(f"❌ Platega.io API error: {error_message}")
                    return {"success": False, "error": error_message, "data": None}

                return {"success": True, "data": result.get("data", result)}

        except aiohttp.ClientError as e:
            # Сетевые ошибки (DNS, таймаут, обрыв соединения) — пользователю безопасный текст,
            # подробности только в лог, чтобы не сломать parse_mode="Markdown" спецсимволами.
            logger.error(f"❌ Platega.io async request error: {e}")
            return {
                "success": False,
                "error": "Не удалось подключиться к платёжному сервису. Попробуйте позже.",
                "data": None,
            }
        except json.JSONDecodeError as e:
            logger.error(f"❌ Platega.io JSON decode error: {e}")
            return {"success": False, "error": "Invalid response format", "data": None}

    def create_payment(
        self,
        amount: float,
        description: str,
        order_id: Optional[str] = None,
        return_url: str = "https://t.me",
        failed_url: str = "https://t.me",
        payment_method: int = 2,  # 2 = СБП
    ) -> Dict[str, Any]:
        """
        Создает платеж через Platega.io (синхронная версия)

        Args:
            amount: Сумма в рублях
            description: Описание платежа
            order_id: ID заказа в вашей системе
            return_url: URL для возврата после успешной оплаты
            failed_url: URL для возврата после неудачной оплаты
            payment_method: 2 - СБП, 1 - карта (если поддерживается)

        Returns:
            Dict с результатом: {success, payment_url, transaction_id, order_id}
        """
        transaction_id = order_id or f"order_{int(datetime.now().timestamp())}"

        data = {
            "paymentMethod": payment_method,
            "paymentDetails": {
                "amount": float(amount),
                "currency": "RUB"
            },
            "description": description,
            "return": return_url,
            "failedUrl": failed_url,
            "payload": order_id or transaction_id
        }

        result = self._make_request("/transaction/process", data)

        if not result["success"]:
            return {
                "success": False,
                "error": result.get("error", "Unknown error"),
                "payment_url": None,
                "transaction_id": None,
                "order_id": order_id,
            }

        response_data = result["data"]
        return {
            "success": True,
            "payment_url": response_data.get("redirect"),
            "transaction_id": response_data.get("transactionId"),
            "order_id": order_id or transaction_id,
            "status": response_data.get("status"),
            "data": response_data,
        }

    async def create_payment_async(
        self,
        amount: float,
        description: str,
        order_id: Optional[str] = None,
        return_url: str = "https://t.me",
        failed_url: str = "https://t.me",
        payment_method: int = 2,  # 2 = СБП
    ) -> Dict[str, Any]:
        """
        Создает платеж через Platega.io (асинхронная версия)
        """
        transaction_id = order_id or f"order_{int(datetime.now().timestamp())}"

        data = {
            "paymentMethod": payment_method,
            "paymentDetails": {
                "amount": float(amount),
                "currency": "RUB"
            },
            "description": description,
            "return": return_url,
            "failedUrl": failed_url,
            "payload": order_id or transaction_id
        }

        result = self._make_request("/transaction/process", data)

        if not result["success"]:
            return {
                "success": False,
                "error": result.get("error", "Unknown error"),
                "payment_url": None,
                "transaction_id": None,
                "order_id": order_id,
            }

        response_data = result["data"]
        return {
            "success": True,
            "payment_url": response_data.get("redirect"),
            "transaction_id": response_data.get("transactionId"),
            "order_id": order_id or transaction_id,
            "status": response_data.get("status"),
            "data": response_data,
        }

    def check_payment_status(self, transaction_id: str) -> Dict[str, Any]:
        """
        Проверяет статус платежа (синхронная версия) через GET /transaction/{id}
        согласно официальной документации Platega.
        """
        endpoint = f"/transaction/{transaction_id}"
        url = f"{self.base_url}{endpoint}"
        headers = {
            "X-MerchantId": self.merchant_id,
            "X-Secret": self.secret_key,
        }
        session = self._get_session()

        try:
            response = session.get(url, headers=headers, timeout=30)

            # Логируем тело ответа при ошибке
            if response.status_code != 200:
                logger.error(
                    f"❌ Platega.io HTTP {response.status_code} | "
                    f"endpoint: {endpoint} | body: {response.text}"
                )
            response.raise_for_status()

            result = response.json()
            # Возможные поля ответа: status, transactionId, amount, paymentDetails, ...
            status = result.get("status")
            return {
                "success": True,
                "status": status,
                "is_paid": status == "CONFIRMED",   # Уточните статус успеха в реальных ответах
                "amount": result.get("amount"),
                "transaction_id": result.get("transactionId", transaction_id),
                "data": result,
            }

        except requests.exceptions.HTTPError as e:
            logger.error(f"❌ Platega.io HTTP error: {e}")
            return {
                "success": False,
                "error": "Ошибка при проверке статуса платежа",
                "status": None,
                "is_paid": False,
                "transaction_id": transaction_id,
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Platega.io request error: {e}")
            return {
                "success": False,
                "error": "Не удалось подключиться к платёжному сервису",
                "status": None,
                "is_paid": False,
                "transaction_id": transaction_id,
            }
        except json.JSONDecodeError:
            logger.error("❌ Platega.io JSON decode error")
            return {
                "success": False,
                "error": "Некорректный ответ сервиса",
                "status": None,
                "is_paid": False,
                "transaction_id": transaction_id,
            }

    async def check_payment_status_async(self, transaction_id: str) -> Dict[str, Any]:
        """
        Проверяет статус платежа (асинхронная версия) через GET /transaction/{id}
        согласно официальной документации Platega.
        """
        endpoint = f"/transaction/{transaction_id}"
        url = f"{self.base_url}{endpoint}"
        headers = {
            "X-MerchantId": self.merchant_id,
            "X-Secret": self.secret_key,
        }
        session = await self._get_async_session()

        try:
            async with session.get(url, headers=headers, timeout=30) as response:
                raw_text = await response.text()
                if response.status != 200:
                    logger.error(
                        f"❌ Platega.io HTTP {response.status} | "
                        f"endpoint: {endpoint} | body: {raw_text}"
                    )
                    return {
                        "success": False,
                        "error": f"HTTP {response.status}: {raw_text}",
                        "status": None,
                        "is_paid": False,
                        "transaction_id": transaction_id,
                    }

                result = json.loads(raw_text)
                status = result.get("status")
                return {
                    "success": True,
                    "status": status,
                    "is_paid": status == "CONFIRMED",
                    "amount": result.get("amount"),
                    "transaction_id": result.get("transactionId", transaction_id),
                    "data": result,
                }

        except aiohttp.ClientError as e:
            logger.error(f"❌ Platega.io async request error: {e}")
            return {
                "success": False,
                "error": "Не удалось подключиться к платёжному сервису",
                "status": None,
                "is_paid": False,
                "transaction_id": transaction_id,
            }
        except json.JSONDecodeError:
            logger.error("❌ Platega.io JSON decode error")
            return {
                "success": False,
                "error": "Некорректный ответ сервиса",
                "status": None,
                "is_paid": False,
                "transaction_id": transaction_id,
            }

    def handle_callback(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Обрабатывает callback-уведомление от Platega.io (без подписи)
        """
        # Логируем сырой запрос для отладки
        logger.info(f"📥 Platega callback received: {json.dumps(request_data, indent=2)}")

        # Новый формат колбэка может отличаться. Смотрим, что пришло.
        event_type = request_data.get("event") or request_data.get("status")
        transaction_id = request_data.get("transactionId")
        merchant_order_id = request_data.get("payload")  # наш order_id

        if not transaction_id:
            logger.warning("❌ Callback without transactionId")
            return {"success": False, "error": "Missing transactionId", "response": "bad request"}

        # Определяем статус
        status = request_data.get("status")
        if status == "CONFIRMED":
            event = "payment.succeeded"
        elif status in ("FAILED", "CANCELED"):
            event = "payment.failed"
        else:
            event = f"payment.{status}" if status else "unknown"

        # Защита от дубликатов (простая проверка в памяти, в продакшене – БД)
        if hasattr(self, '_processed_callbacks') and transaction_id in self._processed_callbacks:
            logger.info(f"🔁 Duplicate callback ignored: {transaction_id}")
            return {"success": True, "event": event, "transaction_id": transaction_id,
                    "order_id": merchant_order_id, "response": "OK"}

        # Сохраняем, что обработали
        if not hasattr(self, '_processed_callbacks'):
            self._processed_callbacks = set()
        self._processed_callbacks.add(transaction_id)

        logger.info(f"✅ Callback processed: {event} for tx {transaction_id}, order {merchant_order_id}")
        return {
            "success": True,
            "event": event,
            "transaction_id": transaction_id,
            "order_id": merchant_order_id,
            "status": status,
            "response": "OK",
        }

    def close(self):
        """
        Закрывает синхронное соединение (requests.Session)
        """
        if self._session:
            self._session.close()
            self._session = None
            logger.info("🔒 Platega.io sync session closed")

    async def close_async(self):
        """
        Закрывает асинхронное соединение (aiohttp.ClientSession)
        """
        if self._async_session and not self._async_session.closed:
            await self._async_session.close()
            self._async_session = None
            logger.info("🔒 Platega.io async session closed")

    def __enter__(self):
        """Поддержка контекстного менеджера (синхронного)"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Автоматическое закрытие при выходе из контекста"""
        self.close()

    async def __aenter__(self):
        """Поддержка асинхронного контекстного менеджера"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Автоматическое закрытие при выходе из асинхронного контекста"""
        await self.close_async()