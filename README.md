# Parser Monitor

Агрегатор объявлений с площадок Avito, Cian и Youla. Пользователь создает задачи на отслеживание через Telegram-бота или веб-интерфейс, система периодически парсит указанные страницы и отправляет уведомления о новых объявлениях в Telegram, VK или на Email.

## Архитектура

Система состоит из четырех микросервисов, фронтенда и общей очереди сообщений:

| Сервис | Технологии | Назначение |
|---|---|---|
| **ApiCoreService** | FastAPI, SQLAlchemy 2.0, asyncpg | REST API, авторизация (JWT), управление задачами, каналами уведомлений, хранение истории объявлений |
| **BotService** | aiogram 3.0, aiohttp | Telegram-бот (регистрация, создание задач, одноразовые токены для входа в веб), опционально VK-бот |
| **ParserService** | aiohttp, BeautifulSoup4 | Планировщик задач, парсинг площадок, дедупликация, публикация событий |
| **NotificationService** | aiohttp, aiosmtplib | Рассылка уведомлений по Telegram, Email, VK |
| **webClient** | React 19, TypeScript, Vite 6 | SPA для управления задачами и просмотра объявлений |
| **RabbitMQ** | — | Асинхронный обмен событиями между сервисами (topic exchange) |

Каждый сервис имеет собственную базу данных PostgreSQL.

## Локальный запуск

### Предварительные требования

- Docker и Docker Compose
- Telegram-бот (создать через [@BotFather](https://t.me/BotFather) и получить токен)

### 1. Создайте файл `.env`

В корне проекта (рядом с `docker-compose.yml`) создайте файл `.env`:

```env
# ======================================
# Обязательные переменные
# ======================================

# Токен Telegram-бота (получить у @BotFather)
TELEGRAM_TOKEN=123456:ABC-DEF...

# Секрет для подписи JWT-токенов (любая случайная строка)
JWT_SECRET=my-super-secret-key

# Токен для межсервисной авторизации (BotService -> ApiCoreService)
SERVICE_API_TOKEN=my-service-token

# ======================================
# Cookies для площадок (парсинг)
# ======================================
# Без cookies парсеры могут получать блокировки или пустые ответы.
# Cookies можно передать двумя способами:
#
# Способ 1 — строка из заголовка Cookie браузера:
#   AVITO_COOKIE_HEADER=name1=value1; name2=value2
#
# Способ 2 — JSON (объект или массив из DevTools):
#   AVITO_COOKIES_JSON={"name1": "value1", "name2": "value2"}
#   или
#   AVITO_COOKIES_JSON=[{"name": "n1", "value": "v1"}, ...]
#
# Как получить: откройте площадку в браузере, DevTools -> Network ->
# любой запрос к домену -> заголовок Cookie. Скопируйте значение целиком.

# Avito
AVITO_COOKIE_HEADER=
# AVITO_COOKIES_JSON=

# Cian
# CIAN_COOKIE_HEADER=
# CIAN_COOKIES_JSON=

# Youla
# YOULA_COOKIE_HEADER=
# YOULA_COOKIES_JSON=

# ======================================
# VK-бот (опционально)
# ======================================
# Если указаны оба параметра, BotService запустит VK-бота параллельно с Telegram.

# Токен сообщества VK (Управление -> Работа с API -> Ключи доступа)
# VK_GROUP_TOKEN=
# ID сообщества VK (числовой)
# VK_GROUP_ID=

# ======================================
# Email-уведомления (опционально)
# ======================================
# Без SMTP-настроек email-канал уведомлений работать не будет.

# SMTP_HOST=smtp.mail.ru
# SMTP_PORT=465
# SMTP_USERNAME=avitoparser.noreply@mail.ru
# SMTP_PASSWORD=
# SMTP_USE_SSL=true
# EMAIL_FROM=avitoparser.noreply@mail.ru
# EMAIL_FROM_NAME=Parser Monitor

# ======================================
# Фронтенд
# ======================================
# URL API для веб-клиента (по умолчанию http://localhost:8000)
# VITE_API_BASE_URL=http://localhost:8000

# URL страницы логина, подставляется в ссылку из Telegram-бота
# SITE_LOGIN_URL=http://localhost:3000/login?token={token}
```

### 2. Запустите проект

```bash
docker compose up --build
```

После запуска будут доступны:

| Сервис | Адрес |
|---|---|
| Веб-интерфейс | http://localhost:3000 |
| API | http://localhost:8000 |
| API документация (Swagger) | http://localhost:8000/docs |
| RabbitMQ Management | http://localhost:15672 (guest / guest) |

### 3. Начало работы

1. Напишите `/start` вашему Telegram-боту — это создаст аккаунт
2. Создайте задачу на парсинг через бота (команда `/add`) или веб-интерфейс
3. Планировщик подхватит задачу и начнет парсинг по расписанию

## Справочник переменных окружения

### ApiCoreService

| Переменная | По умолчанию | Описание |
|---|---|---|
| `DB_USER` | `postgres` | Пользователь PostgreSQL |
| `DB_PASSWORD` | `postgres` | Пароль PostgreSQL |
| `DB_HOST` | `api_core_service_db` | Хост БД |
| `DB_PORT` | `5432` | Порт БД |
| `DB_NAME` | `api_core_db` | Имя базы данных |
| `JWT_SECRET` | `change-me-in-production` | Секрет для подписи JWT |
| `JWT_ALGORITHM` | `HS256` | Алгоритм JWT |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `10080` (7 дней) | Время жизни access-токена |
| `SERVICE_API_TOKEN` | `dev-service-token` | Токен для межсервисных запросов |
| `RABBITMQ_URL` | `amqp://guest:guest@localhost:5672/` | URL подключения к RabbitMQ |
| `EXPOSE_DEV_EMAIL_CODE` | `false` | Возвращать код верификации email в ответе API (только для разработки) |

### BotService

| Переменная | По умолчанию | Описание |
|---|---|---|
| `TELEGRAM_TOKEN` | — | Токен Telegram-бота (обязательно) |
| `API_CORE_BASE_URL` | `http://localhost:8000` | Адрес ApiCoreService |
| `SERVICE_API_TOKEN` | `dev-service-token` | Токен для запросов к API |
| `SITE_LOGIN_URL` | `http://localhost:3000/login?token={token}` | Шаблон ссылки для входа в веб-интерфейс |
| `MIN_TASK_INTERVAL_MINUTES` | `1` | Минимальный интервал парсинга (минуты) |
| `MAX_TASK_DAYS` | `365` | Максимальный срок действия задачи (дни) |
| `VK_GROUP_TOKEN` | — | Токен сообщества VK (опционально) |
| `VK_GROUP_ID` | — | ID сообщества VK (опционально) |

### ParserService

| Переменная | По умолчанию | Описание |
|---|---|---|
| `RABBITMQ_URL` | `amqp://guest:guest@localhost:5672/` | URL подключения к RabbitMQ |
| `SCHEDULER_TICK_SECONDS` | `30` | Интервал проверки задач планировщиком (секунды) |
| `SCHEDULER_BATCH_SIZE` | `20` | Количество задач за один цикл планировщика |
| `FIRST_RUN_NOTIFY_LIMIT` | `5` | Лимит объявлений при первом запуске задачи |
| `AVITO_COOKIE_HEADER` | — | Cookies для Avito (строка из заголовка Cookie) |
| `AVITO_COOKIES_JSON` | — | Cookies для Avito (JSON-формат) |
| `AVITO_USER_AGENT` | Chrome 124 | User-Agent для запросов к Avito |
| `CIAN_COOKIE_HEADER` | — | Cookies для Cian |
| `CIAN_COOKIES_JSON` | — | Cookies для Cian (JSON-формат) |
| `CIAN_USER_AGENT` | Chrome 124 | User-Agent для запросов к Cian |
| `YOULA_COOKIE_HEADER` | — | Cookies для Youla |
| `YOULA_COOKIES_JSON` | — | Cookies для Youla (JSON-формат) |
| `YOULA_USER_AGENT` | Chrome 124 | User-Agent для запросов к Youla |
| `PARSER_DEBUG_HTML` | `false` | Сохранять HTML-ответы площадок для отладки |
| `PARSER_DEBUG_DIR` | `debug_html` | Директория для сохранения отладочных HTML |

### NotificationService

| Переменная | По умолчанию | Описание |
|---|---|---|
| `TELEGRAM_TOKEN` | — | Токен Telegram-бота (тот же, что и у BotService) |
| `TELEGRAM_PARSE_MODE` | — | Режим разметки сообщений Telegram (`HTML` или не задан) |
| `VK_GROUP_TOKEN` | — | Токен сообщества VK |
| `VK_API_VERSION` | `5.199` | Версия VK API |
| `SMTP_HOST` | — | SMTP-сервер для отправки email |
| `SMTP_PORT` | `587` | Порт SMTP |
| `SMTP_USERNAME` | — | Логин SMTP |
| `SMTP_PASSWORD` | — | Пароль SMTP |
| `SMTP_USE_SSL` | `false` | Использовать SSL (порт 465) |
| `SMTP_STARTTLS` | `true` | Использовать STARTTLS (порт 587) |
| `EMAIL_FROM` | `no-reply@example.com` | Адрес отправителя |
| `EMAIL_FROM_NAME` | `Parser Monitor` | Имя отправителя |

### webClient

| Переменная | По умолчанию | Описание |
|---|---|---|
| `VITE_API_BASE_URL` | `http://localhost:8000` | URL API (подставляется при сборке) |
| `VK_GROUP_ID` | — | ID группы VK (для ссылки в интерфейсе) |
