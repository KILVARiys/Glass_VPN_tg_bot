import logging
import hmac
import hashlib
import json
from uuid import uuid4
from typing import Optional, Dict, Any
from datetime import datetime

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
        self.base_url = "https://api.platega.io"
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

    def _generate_signature(self, data: Dict[str, Any]) -> str:
        """
        Генерирует подпись для запроса к Platega.io
        Используется алгоритм HMAC-SHA256
        """
        # Сортируем данные по ключам
        sorted_data = dict(sorted(data.items()))
        # Преобразуем в JSON строку
        json_string = json.dumps(sorted_data, separators=(',', ':'))
        # Генерируем подпись
        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            json_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature

    def _make_request(self, endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Выполняет синхронный запрос к API Platega.io
        """
        url = f"{self.base_url}{endpoint}"
        
        # Добавляем идентификатор мерчанта
        data["merchant_id"] = self.merchant_id
        
        # Генерируем подпись
        data["signature"] = self._generate_signature(data)
        
        session = self._get_session()
        
        try:
            response = session.post(url, json=data, timeout=30)
            response.raise_for_status()
            result = response.json()
            
            if result.get("status") == "error":
                error_message = result.get("message", "Unknown error")
                logger.error(f"❌ Platega.io API error: {error_message}")
                return {"success": False, "error": error_message, "data": None}
            
            return {"success": True, "data": result.get("data", result)}
            
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Platega.io request error: {e}")
            return {"success": False, "error": str(e), "data": None}
        except json.JSONDecodeError as e:
            logger.error(f"❌ Platega.io JSON decode error: {e}")
            return {"success": False, "error": "Invalid response format", "data": None}

    async def _make_async_request(self, endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Выполняет асинхронный запрос к API Platega.io
        """
        url = f"{self.base_url}{endpoint}"
        
        # Добавляем идентификатор мерчанта
        data["merchant_id"] = self.merchant_id
        
        # Генерируем подпись
        data["signature"] = self._generate_signature(data)
        
        session = await self._get_async_session()
        
        try:
            async with session.post(url, json=data, timeout=30) as response:
                result = await response.json()
                
                if response.status != 200:
                    logger.error(f"❌ Platega.io HTTP error: {response.status}")
                    return {"success": False, "error": f"HTTP {response.status}", "data": None}
                
                if result.get("status") == "error":
                    error_message = result.get("message", "Unknown error")
                    logger.error(f"❌ Platega.io API error: {error_message}")
                    return {"success": False, "error": error_message, "data": None}
                
                return {"success": True, "data": result.get("data", result)}
                
        except aiohttp.ClientError as e:
            logger.error(f"❌ Platega.io async request error: {e}")
            return {"success": False, "error": str(e), "data": None}
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
            "transaction_id": transaction_id,
            "amount": float(amount),
            "currency": "RUB",
            "description": description,
            "payment_method": payment_method,
            "return_url": return_url,
            "failed_url": failed_url,
            "callback_url": self.callback_url,
            "merchant_order_id": order_id or transaction_id,
        }
        
        result = self._make_request("/v1/create_payment", data)
        
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
            "payment_url": response_data.get("payment_url"),
            "transaction_id": response_data.get("transaction_id"),
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
            "transaction_id": transaction_id,
            "amount": float(amount),
            "currency": "RUB",
            "description": description,
            "payment_method": payment_method,
            "return_url": return_url,
            "failed_url": failed_url,
            "callback_url": self.callback_url,
            "merchant_order_id": order_id or transaction_id,
        }
        
        result = await self._make_async_request("/v1/create_payment", data)
        
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
            "payment_url": response_data.get("payment_url"),
            "transaction_id": response_data.get("transaction_id"),
            "order_id": order_id or transaction_id,
            "status": response_data.get("status"),
            "data": response_data,
        }

    def check_payment_status(self, transaction_id: str) -> Dict[str, Any]:
        """
        Проверяет статус платежа (синхронная версия)
        
        Args:
            transaction_id: ID транзакции в Platega.io
        
        Returns:
            Dict с результатом: {success, status, is_paid}
        """
        data = {
            "transaction_id": transaction_id,
        }
        
        result = self._make_request("/v1/check_payment", data)
        
        if not result["success"]:
            return {
                "success": False,
                "error": result.get("error", "Unknown error"),
                "status": None,
                "is_paid": False,
            }
        
        response_data = result["data"]
        status = response_data.get("status")
        
        return {
            "success": True,
            "status": status,
            "is_paid": status == "CONFIRMED",
            "amount": response_data.get("amount"),
            "transaction_id": response_data.get("transaction_id"),
            "data": response_data,
        }

    async def check_payment_status_async(self, transaction_id: str) -> Dict[str, Any]:
        """
        Проверяет статус платежа (асинхронная версия)
        """
        data = {
            "transaction_id": transaction_id,
        }
        
        result = await self._make_async_request("/v1/check_payment", data)
        
        if not result["success"]:
            return {
                "success": False,
                "error": result.get("error", "Unknown error"),
                "status": None,
                "is_paid": False,
            }
        
        response_data = result["data"]
        status = response_data.get("status")
        
        return {
            "success": True,
            "status": status,
            "is_paid": status == "CONFIRMED",
            "amount": response_data.get("amount"),
            "transaction_id": response_data.get("transaction_id"),
            "data": response_data,
        }

    def verify_callback_signature(self, data: Dict[str, Any], signature: str) -> bool:
        """
        Проверяет подпись callback-уведомления от Platega.io
        
        Args:
            data: Данные callback
            signature: Подпись из заголовка X-Signature
        
        Returns:
            True если подпись верна, иначе False
        """
        # Удаляем подпись из данных для проверки
        data_copy = data.copy()
        data_copy.pop("signature", None)
        
        # Генерируем подпись
        expected_signature = self._generate_signature(data_copy)
        
        return signature == expected_signature

    def handle_callback(self, request_data: Dict[str, Any], signature: str) -> Dict[str, Any]:
        """
        Обрабатывает callback-уведомление от Platega.io
        
        Args:
            request_data: JSON-данные от Platega.io
            signature: Подпись из заголовка X-Signature
        
        Returns:
            Dict с информацией о платеже
        """
        # Проверяем подпись
        if not self.verify_callback_signature(request_data, signature):
            logger.warning("❌ Invalid callback signature")
            return {
                "success": False,
                "error": "Invalid signature",
                "response": "bad sign"
            }
        
        event_type = request_data.get("event")
        payload = request_data.get("payload", {})
        
        logger.info(f"📨 Platega callback: {event_type} for {payload.get('transaction_id')}")
        
        if event_type == "payment_success":
            return {
                "success": True,
                "event": "payment.succeeded",
                "transaction_id": payload.get("transaction_id"),
                "order_id": payload.get("merchant_order_id"),
                "amount": payload.get("amount"),
                "status": payload.get("status"),
                "response": "OK",
            }
        elif event_type == "payment_failed":
            return {
                "success": True,
                "event": "payment.failed",
                "transaction_id": payload.get("transaction_id"),
                "order_id": payload.get("merchant_order_id"),
                "status": payload.get("status"),
                "response": "OK",
            }
        elif event_type == "payment_canceled":
            return {
                "success": True,
                "event": "payment.canceled",
                "transaction_id": payload.get("transaction_id"),
                "order_id": payload.get("merchant_order_id"),
                "response": "OK",
            }
        
        return {
            "success": True,
            "event": f"payment.{event_type}" if event_type else "unknown",
            "transaction_id": payload.get("transaction_id"),
            "order_id": payload.get("merchant_order_id"),
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