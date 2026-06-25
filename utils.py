import email
import requests
import json
import uuid
import logging
import base64
from datetime import datetime, timedelta
from config import XUI_URL, XUI_API_TOKEN, XUI_USERNAME, XUI_PASSWORD, XUI_SUB_URL

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class XUIClient:
    def __init__(self):
        self.base_url = XUI_URL.rstrip('/')
        self.sub_url = XUI_SUB_URL.rstrip('/') if XUI_SUB_URL else None
        self.session = requests.Session()
        self.session.verify = False
        self.logged_in = False

        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0',
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        })

        self.login()

    def login(self):
        if XUI_API_TOKEN:
            self.session.headers.update({'Authorization': f'Bearer {XUI_API_TOKEN}'})
            try:
                resp = self.session.get(f"{self.base_url}/panel/api/inbounds/list", timeout=10)
                if resp.status_code == 200:
                    self.logged_in = True
                    logger.info("✅ Авторизация по токену")
                    return True
            except Exception as e:
                logger.error(f"Ошибка токена: {e}")

        if XUI_USERNAME and XUI_PASSWORD:
            try:
                resp = self.session.post(
                    f"{self.base_url}/login",
                    json={"username": XUI_USERNAME, "password": XUI_PASSWORD},
                    timeout=10
                )
                if resp.status_code == 200:
                    self.logged_in = True
                    logger.info("✅ Авторизация по логину/паролю")
                    return True
            except Exception as e:
                logger.error(f"Ошибка логина: {e}")

        logger.error("❌ Не удалось авторизоваться")
        return False

    def get_all_inbound_ids(self):
        if not self.logged_in:
            self.login()
        try:
            resp = self.session.get(f"{self.base_url}/panel/api/inbounds/list", timeout=10)
            if resp.status_code != 200:
                return []
            data = resp.json()
            inbounds = data.get('obj', []) or data.get('data', [])
            ids = [inb['id'] for inb in inbounds if inb.get('enable', True)]
            logger.info(f"📋 Найдено инбаундов: {len(ids)} -> {ids}")
            return ids
        except Exception as e:
            logger.error(f"Ошибка получения инбаундов: {e}")
            return []

    def create_client(self, email: str, days: int = 3, total_gb: int = 10, limit_ip: int = 1):
        if not self.logged_in:
            self.login()

        inbound_ids = self.get_all_inbound_ids()
        if not inbound_ids:
            return False, None, "Нет активных инбаундов"

        expiry_time = int((datetime.now() + timedelta(days=days)).timestamp() * 1000)
        total_bytes = total_gb * 1024 * 1024 * 1024

        payload = {
            "client": {
                "email": email,
                "totalGB": total_bytes,
                "expiryTime": expiry_time,
                "tGId": 0,
                "limitIp": limit_ip,
                "enable": True,
                "flow": "xtls-rprx-vision"
            },
            "inboundIds": inbound_ids
        }

        logger.info(f"📤 Создание клиента {email}: {payload}")
        try:
            resp = self.session.post(
                f"{self.base_url}/panel/api/clients/add",
                json=payload,
                timeout=10
            )
            logger.info(f"📥 Ответ API: статус {resp.status_code}, тело: {resp.text}")
            if resp.status_code == 200:
                data = resp.json()
                if data.get('success'):
                    sub_id = self.find_client_sub_id(email)
                    if sub_id:
                        logger.info(f"✅ Найден subId: {sub_id}")
                        return True, sub_id, "Клиент создан"
                    else:
                        logger.warning("⚠️ Клиент создан, но subId не найден")
                        return True, None, "Клиент создан, subId не найден"
                else:
                    return False, None, f"Ошибка: {data.get('msg', 'Unknown error')}"
            else:
                return False, None, f"Ошибка API: {resp.status_code}"
        except Exception as e:
            logger.error(f"❌ Исключение: {e}")
            return False, None, str(e)

    def find_client_sub_id(self, email):
        """Ищет subId (UUID) клиента по email"""
        if not self.logged_in:
            self.login()
        try:
            resp = self.session.get(f"{self.base_url}/panel/api/inbounds/list", timeout=10)
            if resp.status_code != 200:
                return None
            data = resp.json()
            inbounds = data.get('obj', []) or data.get('data', [])
            for inbound in inbounds:
                settings = inbound.get('settings', {})
                if isinstance(settings, str):
                    settings = json.loads(settings)
                clients = settings.get('clients', [])
                for client in clients:
                    if client.get('email') == email:
                        # Приоритет subId, если есть, иначе id
                        return client.get('subId') or client.get('id')
            return None
        except Exception as e:
            logger.error(f"Ошибка поиска subId: {e}")
            return None

    def update_client(self, client_id: int, email: str, total_gb: int = 0, expiry_time: int = 0, limit_ip: int = 3, enable: bool = True) -> bool:
        url = f"{self.base_url}/panel/api/inbounds/update/{client_id}"
        payload = {
            "id": client_id,
            "settings": json.dumps({
                "clients": [{
                    "email": email,
                    "totalGB": total_gb,
                    "expiryTime": expiry_time,
                    "limitIp": limit_ip,
                    "enable": enable,
                    "flow": "xtls-rprx-vision",  # или тот же, что был при создании
                }]
            })
        }
        try:
            response = self.session.post(url, json=payload, headers=self.headers)
            if response.status_code == 200 and response.json().get("success"):
                logger.info(f"✅ Клиент {email} обновлён")
                return True
            else:
                logger.error(f"❌ Ошибка обновления клиента: {response.text}")
                return False
        except Exception as e:
            logger.error(f"❌ Ошибка обновления клиента: {e}")
            return False

    def get_subscription_link(self, sub_id: str):
        if not sub_id:
            return None
        if self.sub_url:
            base = self.sub_url.rstrip('/')
            return f"{base}/{sub_id}"
        else:
            logger.warning("⚠️ XUI_SUB_URL не задан, используется стандартный /sub/")
            return f"{self.base_url}/sub/{sub_id}"

    # ===== Остальные методы (если нужны) можно добавить сюда =====
    def get_all_clients(self):
        if not self.logged_in:
            self.login()
        try:
            resp = self.session.get(f"{self.base_url}/panel/api/inbounds/list", timeout=10)
            if resp.status_code != 200:
                return []
            data = resp.json()
            inbounds = data.get('obj', []) or data.get('data', [])
            clients = []
            for inbound in inbounds:
                settings = inbound.get('settings', {})
                if isinstance(settings, str):
                    settings = json.loads(settings)
                for client in settings.get('clients', []):
                    clients.append({
                        'email': client.get('email'),
                        'enable': client.get('enable'),
                        'expiryTime': client.get('expiryTime'),
                        'id': client.get('id'),
                        'inbound_id': inbound.get('id')
                    })
            return clients
        except:
            return []