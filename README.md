# Expense Tracker Telegram Bot

Production-grade Telegram-бот для учета личных/семейных расходов:
- ручной ввод трат и fallback-обработка чека по QR;
- учет балансов (основной и накопительный счет);
- SQL (SQLite dev / PostgreSQL prod) как primary-хранилище операций;
- Google Sheets как пользовательская витрина/выгрузка и dashboard;
- Redis для rate limit, кэша и очереди задач (ARQ worker).

## Архитектура

- `bot` (`aiogram v3`): кнопочный UX (reply + inline), FSM, fallback-команды.
- `worker` (`arq`): запись батчей в Google Sheets и аудит.
- `api` (`FastAPI`): webhook endpoint, health, metrics.
- `db` (`SQLAlchemy + Alembic`): семьи, роли, invite, idempotency, audit, expense/ledger history.
- `google` (`Sheets API + Drive API`): подключение таблицы, синхронизация projection и dashboard.
  - Пользователь видит только 2 вкладки: `Сводка` и `Покупки`.
  - Технические вкладки (`raw_expenses`, `settings`, `ledger`, `categories`, `users`, `audit`) скрыты.

## Ключевые решения v1

- Только Service Account flow (без OAuth пользователя).
- Только подключение существующей таблицы (без функции "создать таблицу").
- Роли: `owner`, `editor`.
- Invite-only join: `/join <code>`, TTL 1 час, одноразовый.
- Private chat only.
- Для чеков: авто-позиции через optional provider + безопасный fallback, если провайдер недоступен.
- Изменение балансов (`пополнить`/`перевести в накопления`) разрешено только `owner`.

## Быстрый старт (Windows 11 + Docker Desktop)

1. Скопируйте `.env.example` в `.env` и заполните значения.
2. Подготовьте Google credentials JSON и укажите путь в `GOOGLE_SERVICE_ACCOUNT_JSON_PATH`.
3. В вашей Google Таблице добавьте Editor-доступ для:
   - `hydra-950@finassbobot.iam.gserviceaccount.com`
4. Запустите:

```bash
docker compose up --build
```

Бот (`bot`) и воркер (`worker`) поднимутся вместе с Redis.

## Google Cloud setup

1. Создайте Google Cloud Project.
2. Включите APIs:
   - Google Sheets API
   - Google Drive API
3. Создайте Service Account.
4. Скачайте JSON credentials.
5. Передайте путь через env:
   - `GOOGLE_SERVICE_ACCOUNT_JSON_PATH`
   - либо `GOOGLE_APPLICATION_CREDENTIALS`

## Telegram setup

1. Создайте бота через BotFather.
2. Укажите `TELEGRAM_BOT_TOKEN` в `.env`.

## Receipt provider: где взять API token

Для автоподтягивания товарных позиций из QR (не только суммы) нужен внешний провайдер.

1. Зарегистрируйтесь на `https://proverkacheka.com`.
2. В личном кабинете получите API token.
3. Добавьте в `.env`:
   - `RECEIPT_ITEMS_PROVIDER=proverkacheka`
   - `RECEIPT_PROVIDER_API_TOKEN=<ваш_токен>`
4. Перезапустите контейнеры: `docker compose up -d --build bot worker`.

Если токена нет или сервис временно недоступен, бот автоматически переключится на fallback-сценарий.

## Режимы запуска

### DEV (long polling)

- `APP_MODE=polling`
- бот читает апдейты напрямую.

### PROD (webhook)

- `APP_MODE=webhook`
- выставьте `BASE_URL=https://your-domain`
- проксируйте на `bot:8000` через nginx/caddy + TLS.
- webhook endpoint: `POST /telegram/webhook`.

## Навигация

- Основной сценарий полностью на кнопках (RU): после нажатия `Start` в Telegram дальше можно работать без ввода `/команд`.
- Команды оставлены как технический fallback: `/start`, `/help`, `/add`, `/scan`, `/report`, `/accounts`, `/categories`, `/family`, `/join <код>`, `/settings`, `/cancel`.

## Пример UX сообщений

### Старт

`Привет! ... Выберите действие: [Подключить таблицу] [Подключиться по коду]`

### `/add`

`Как добавить расход? [Позиция] [Одной суммой]`

### `/scan`

`Чек распознан. Позиции получены автоматически... [Да] [Нет]`
`Если авторазбор не сработал: [Записать одной суммой] [Внести вручную позиции]`

### `/family invite`

`Инвайт создан. Код: <...>. Выполните /join <код>.`

### `/report`

`Итого: ... По категориям: ...`

## Переменные окружения

Обязательные:
- `TELEGRAM_BOT_TOKEN`
- `GOOGLE_SERVICE_ACCOUNT_JSON_PATH` (или `GOOGLE_APPLICATION_CREDENTIALS`)
- `DB_DSN`
- `REDIS_URL`

Рекомендуемые:
- `APP_MODE`
- `BASE_URL` (для webhook)
- `WEBHOOK_SECRET_TOKEN`
- `LOG_LEVEL`
- `DEFAULT_CURRENCY`
- `DEFAULT_TIMEZONE`
  - по умолчанию: `Europe/Berlin`
- `RECEIPT_ITEMS_PROVIDER` (`none`/`proverkacheka`)
- `RECEIPT_PROVIDER_API_TOKEN` (если включен `proverkacheka`)
- `RECEIPT_PROVIDER_BASE_URL` (default: `https://proverkacheka.com`)
- `RECEIPT_PROVIDER_TIMEOUT_SECONDS`

Полный список: `.env.example`.

## Разработка

```bash
uv pip install -e ".[dev]"
pytest
ruff check .
mypy app tests
```

или через `make`:

```bash
make test
make lint
make typecheck
```

## Миграции

```bash
alembic upgrade head
```

В Docker Compose миграции запускаются автоматически в `bot` контейнере (`MIGRATE_ON_START=1`).

## Security notes

- Секреты не хранятся в репозитории.
- Логи не содержат полный QR payload и маскируют email.
- Invite хранится только в hash-виде.
- Идемпотентность чеков: `processed_receipts` (`owner_telegram_id + receipt_hash`).
- `/metrics` предполагает внутренний доступ (ограничивайте reverse proxy/VPC).

## Health & metrics

- `GET /health/live`
- `GET /health/ready`
- `GET /metrics`

## Troubleshooting

- `403 webhook`: проверьте `WEBHOOK_SECRET_TOKEN`.
- `Google 403`: проверьте API enablement, SA credentials и права Drive.
- `Google 403` при подключении: таблица должна быть расшарена на `hydra-950@finassbobot.iam.gserviceaccount.com` с ролью Editor.
- `QR не найден`: улучшите резкость/контраст фото, уберите блики.
- `Позиции чека не получены`: настройте `RECEIPT_ITEMS_PROVIDER=proverkacheka` и `RECEIPT_PROVIDER_API_TOKEN`, либо используйте fallback сценарий.
- `Сначала подключите таблицу`: профиль/семья еще не инициализированы.
- Если часть покупок не появилась в Google Sheets (из-за временных сетевых сбоев worker), выполните досинхронизацию из SQL:

```bash
docker compose run --rm bot python -m app.scripts.reconcile_expenses
```

## Deploy on Ubuntu VM

Production deployment artifacts added:
- `docker-compose.prod.yml`
- `.env.prod.example`
- `deploy/nginx/finass.conf.example`
- `deploy/systemd/finass-compose.service`
- `docs/DEPLOY_UBUNTU_VM.md`

Quick start:

```bash
cp .env.prod.example .env.prod
mkdir -p secrets
# put google_service_account.json into ./secrets

docker compose -f docker-compose.prod.yml up -d --build
```

Full runbook: `docs/DEPLOY_UBUNTU_VM.md`
