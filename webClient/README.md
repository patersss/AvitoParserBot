# WebClient

Минимальный React + TypeScript клиент для ApiCoreService.

## Логика входа

На сайте нет публичной регистрации. Пользователь сначала открывает Telegram-бота и получает одноразовую ссылку вида:

```text
http://localhost:3000/login?token=<one-time-token>
```

WebClient читает `token` из query string, вызывает `POST /auth/telegram-token`, сохраняет JWT и открывает кабинет. Если у пользователя ещё нет `login_email`, интерфейс сразу отправляет его в раздел аккаунта, где нужно подтвердить email и задать первый пароль. После этого можно входить через `POST /auth/login` по email и паролю.

## Локальный запуск

```bash
cd webClient
npm install
npm run dev
```

По умолчанию клиент ожидает ApiCoreService на `http://localhost:8000`. Для другого адреса создайте `.env.local`:

```env
VITE_API_BASE_URL=http://localhost:8000
```

После запуска сайт будет доступен на `http://localhost:3000`.

## Docker Compose

Из корня проекта:

```bash
docker compose up -d --build api_core_service web_client
```

Если BotService должен выдавать ссылки именно на сайт, в корневом `.env` оставьте:

```env
SITE_LOGIN_URL=http://localhost:3000/login?token={token}
VITE_API_BASE_URL=http://localhost:8000
```

Для пересборки только фронтенда:

```bash
docker compose up -d --build --force-recreate web_client
```
