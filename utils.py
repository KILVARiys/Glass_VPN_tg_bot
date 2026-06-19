import requests
import json
import uuid
import logging
from datetime import datetime, timedelta
from config import XUI_URL, XUI_API_TOKEN, XUI_USERNAME, XUI_PASSWORD

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class XUIClient:
    """
    Клиент для работы с 3x-UI через официальное API
    Поддерживает авторизацию через API Token и логин/пароль
    """

    def __init__(self):
        self.base_url = XUI_URL.rstrip('/')
        self.session = requests.Session()
        self.session.verify = False
        self.logged_in = False
        
        # Отключаем предупреждения SSL
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        # Заголовки для API запросов
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Content-Type': 'application/json'
        })
        
        self.login()

    def _get_api_endpoint(self, endpoint):
        """
        Формирует правильный URL для API эндпоинта с учетом кастомного пути
        Пробует разные варианты расположения API
        """
        # Список возможных префиксов для API
        api_prefixes = [
            '',  # прямой путь (уже включен в base_url)
            '/panel',
            '/xui',
            '/api',
            '/xui/API',
            '/panel/api',
        ]
        
        urls = []
        for prefix in api_prefixes:
            url = f"{self.base_url}{prefix}{endpoint}"
            urls.append(url)
        
        # Убираем дубли
        urls = list(dict.fromkeys(urls))
        return urls

    def login(self):
        """
        Авторизация в 3x-UI.
        Сначала пробует API Token, затем логин/пароль.
        """
        # 1. Пробуем API Token
        if XUI_API_TOKEN:
            logger.info("🔑 Использование API Token для авторизации")
            self.session.headers.update({
                'Authorization': f'Bearer {XUI_API_TOKEN}'
            })
            
            # Проверяем токен через разные эндпоинты
            test_endpoints = [
                '/inbound/list',
                '/xui/API/inbound/list',
                '/panel/api/inbounds/list',
                '/api/inbounds/list'
            ]
            
            for test_endpoint in test_endpoints:
                try:
                    urls = self._get_api_endpoint(test_endpoint)
                    for url in urls:
                        try:
                            response = self.session.get(url, timeout=10)
                            if response.status_code == 200:
                                self.logged_in = True
                                logger.info(f"✅ Авторизация через API Token успешна (эндпоинт: {url})")
                                return True
                            elif response.status_code == 401:
                                logger.warning("⚠️ API Token недействителен")
                                break
                        except:
                            continue
                except:
                    continue

        # 2. Пробуем логин/пароль
        if XUI_USERNAME and XUI_PASSWORD:
            logger.info("🔑 Использование логина/пароля для авторизации")
            return self._login_with_password()

        logger.error("❌ Нет доступных способов авторизации")
        return False

    def _login_with_password(self):
        """
        Авторизация через логин и пароль с разными эндпоинтами
        """
        login_data = {
            "username": XUI_USERNAME,
            "password": XUI_PASSWORD
        }
        
        # Пробуем разные эндпоинты для логина
        login_endpoints = [
            '/login',
            '/panel/login',
            '/xui/login',
            '/api/login',
            '/auth/login',
            '/xui/API/login',
            '/panel/api/login'
        ]
        
        for endpoint in login_endpoints:
            try:
                urls = self._get_api_endpoint(endpoint)
                for url in urls:
                    try:
                        logger.info(f"🔄 Попытка входа: {url}")
                        
                        # Пробуем JSON
                        response = self.session.post(url, json=login_data, timeout=10)
                        if response.status_code == 200:
                            try:
                                data = response.json()
                                if data.get('success') or data.get('status') == 'success':
                                    self.logged_in = True
                                    logger.info(f"✅ Успешная авторизация через {url}")
                                    return True
                            except:
                                pass
                            
                            # Проверяем cookies
                            cookies = self.session.cookies.get_dict()
                            if 'session' in cookies or 'token' in cookies or 'auth' in cookies:
                                self.logged_in = True
                                logger.info(f"✅ Успешная авторизация (cookies) через {url}")
                                return True
                        
                        # Пробуем form-data
                        response = self.session.post(url, data=login_data, timeout=10)
                        if response.status_code == 200:
                            cookies = self.session.cookies.get_dict()
                            if 'session' in cookies or 'token' in cookies or 'auth' in cookies:
                                self.logged_in = True
                                logger.info(f"✅ Успешная авторизация (form-data) через {url}")
                                return True
                                
                    except Exception as e:
                        logger.warning(f"Ошибка при входе через {url}: {e}")
                        continue
            except:
                continue

        logger.error("❌ Ошибка авторизации через логин/пароль")
        return False

    def _api_request(self, method, endpoint, data=None):
        """
        Универсальный метод для запросов к API 3x-UI
        """
        if not self.logged_in:
            if not self.login():
                return None

        # Получаем список возможных URL для эндпоинта
        urls = self._get_api_endpoint(endpoint)
        
        for url in urls:
            try:
                if method.upper() == 'GET':
                    response = self.session.get(url, timeout=15)
                elif method.upper() == 'POST':
                    response = self.session.post(url, json=data, timeout=15)
                elif method.upper() == 'PUT':
                    response = self.session.put(url, json=data, timeout=15)
                elif method.upper() == 'DELETE':
                    response = self.session.delete(url, timeout=15)
                else:
                    continue

                if response.status_code == 200:
                    try:
                        return response.json()
                    except:
                        return {"success": True, "data": response.text}
                elif response.status_code == 401:
                    # Сессия истекла — перелогиниваемся
                    logger.warning("⚠️ Сессия истекла, перелогиниваемся...")
                    self.logged_in = False
                    if self.login():
                        return self._api_request(method, endpoint, data)
                    return None
                else:
                    # Пробуем следующий URL
                    continue

            except Exception as e:
                logger.warning(f"Ошибка запроса к {url}: {e}")
                continue

        logger.error(f"❌ API ошибка: все эндпоинты не отвечают для {endpoint}")
        return None

    def get_inbounds(self):
        """Получает список всех inbound'ов"""
        endpoints = [
            '/inbound/list',
            '/xui/API/inbound/list',
            '/panel/api/inbounds/list',
            '/api/inbounds/list'
        ]
        
        for endpoint in endpoints:
            result = self._api_request('GET', endpoint)
            if result:
                inbounds = result.get('obj', []) or result.get('data', []) or []
                if inbounds:
                    return inbounds
        
        return []

    def add_client(self, email, days=30):
        """Создает клиента в первом доступном inbound"""
        try:
            inbounds = self.get_inbounds()
            if not inbounds:
                return False, "Нет доступных inbound"

            inbound = inbounds[0]
            inbound_id = inbound.get('id')

            client_uuid = str(uuid.uuid4())
            expiry_time = int((datetime.now() + timedelta(days=days)).timestamp() * 1000)

            settings = inbound.get('settings', {})
            if isinstance(settings, str):
                settings = json.loads(settings)

            clients = settings.get('clients', [])

            new_client = {
                "id": client_uuid,
                "email": email,
                "limitIp": 0,
                "totalGB": 0,
                "expiryTime": expiry_time,
                "enable": True
            }
            clients.append(new_client)

            settings['clients'] = clients

            update_data = {
                "id": inbound_id,
                "settings": json.dumps(settings)
            }

            # Пробуем разные эндпоинты для обновления
            update_endpoints = [
                f'/inbound/update/{inbound_id}',
                f'/xui/API/inbound/update/{inbound_id}',
                f'/panel/api/inbounds/update/{inbound_id}',
                f'/api/inbounds/update/{inbound_id}'
            ]

            for endpoint in update_endpoints:
                result = self._api_request('POST', endpoint, update_data)
                if result:
                    logger.info(f"✅ Клиент {email} добавлен в панель на {days} дней")
                    return True, f"Клиент создан. UUID: {client_uuid}"

            return False, "Не удалось создать клиента"

        except Exception as e:
            logger.error(f"❌ Ошибка при добавлении клиента: {e}")
            return False, str(e)

    def remove_client(self, email):
        """Удаляет клиента по email"""
        try:
            inbounds = self.get_inbounds()
            if not inbounds:
                return False

            for inbound in inbounds:
                settings = inbound.get('settings', {})
                if isinstance(settings, str):
                    settings = json.loads(settings)

                clients = settings.get('clients', [])
                for client in clients:
                    if client.get('email') == email:
                        delete_data = {"id": client.get('id')}
                        
                        delete_endpoints = [
                            '/inbound/delClient',
                            '/xui/API/inbound/delClient',
                            '/panel/api/inbounds/delClient',
                            '/api/inbounds/delClient'
                        ]
                        
                        for endpoint in delete_endpoints:
                            result = self._api_request('POST', endpoint, delete_data)
                            if result:
                                logger.info(f"✅ Клиент {email} удален из панели")
                                return True
                        
                        return False

            logger.warning(f"⚠️ Клиент {email} не найден в панели")
            return False

        except Exception as e:
            logger.error(f"❌ Ошибка при удалении клиента: {e}")
            return False

    def get_all_clients(self):
        """Получает всех клиентов из панели"""
        try:
            inbounds = self.get_inbounds()
            clients = []

            for inbound in inbounds:
                settings = inbound.get('settings', {})
                if isinstance(settings, str):
                    settings = json.loads(settings)

                inbound_clients = settings.get('clients', [])
                for client in inbound_clients:
                    clients.append({
                        'email': client.get('email'),
                        'enable': client.get('enable'),
                        'expiryTime': client.get('expiryTime'),
                        'id': client.get('id'),
                        'inbound_id': inbound.get('id')
                    })

            return clients

        except Exception as e:
            logger.error(f"❌ Ошибка при получении клиентов: {e}")
            return []

    def get_client(self, email):
        """Получает информацию о клиенте по email"""
        clients = self.get_all_clients()
        for client in clients:
            if client.get('email') == email:
                return client
        return None

    def get_client_traffic(self, email):
        """Получает информацию о трафике клиента"""
        return self.get_client(email)

    def get_server_status(self):
        """Получает статус сервера"""
        endpoints = [
            '/server/status',
            '/xui/API/server/status',
            '/panel/api/server/status'
        ]
        
        for endpoint in endpoints:
            result = self._api_request('GET', endpoint)
            if result:
                return result
        return None

    def restart_xray(self):
        """Перезапускает Xray"""
        endpoints = [
            '/server/restartXray',
            '/xui/API/server/restartXray',
            '/panel/api/server/restartXray'
        ]
        
        for endpoint in endpoints:
            result = self._api_request('POST', endpoint)
            if result:
                return result
        return None