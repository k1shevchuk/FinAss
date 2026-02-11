# Expense Tracker Telegram Bot

Production-grade Telegram-бот для учета личных/семейных расходов:
- ручной ввод трат и fallback-обработка чека по QR;
- Google Sheets как пользовательский ledger;
- SQLite (dev) / PostgreSQL (prod) для метаданных;
- Redis для rate limit, кэша и очереди задач (ARQ worker).

## Архитектура

- `bot` (`aiogram v3`): команды, FSM, inline UX.
- `worker` (`arq`): запись батчей в Google Sheets и аудит.
- `api` (`FastAPI`): webhook endpoint, health, metrics.
- `db` (`SQLAlchemy + Alembic`): семьи, роли, invite, idempotency, audit.
- `google` (`Sheets API + Drive API`): создание/шаринг таблицы и записи.

## Ключевые решения v1

- Только Service Account flow (без OAuth пользователя).
- Роли: `owner`, `editor`.
- Invite-only join: `/join <code>`, TTL 1 час, одноразовый.
- Private chat only.
- Fallback-only для receipt provider (без внешних поставщиков позиций чека).

## Быстрый старт (Windows 11 + Docker Desktop)

1. Скопируйте `.env.example` в `.env` и заполните значения.
2. Подготовьте Google credentials JSON и укажите путь в `GOOGLE_SERVICE_ACCOUNT_JSON_PATH`.
3. Запустите:

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

## Режимы запуска

### DEV (long polling)

- `APP_MODE=polling`
- бот читает апдейты напрямую.

### PROD (webhook)

- `APP_MODE=webhook`
- выставьте `BASE_URL=https://your-domain`
- проксируйте на `bot:8000` через nginx/caddy + TLS.
- webhook endpoint: `POST /telegram/webhook`.

## Команды

- `/start` — онбординг, создание и шаринг таблицы.
- `/help`
- `/add` — пошаговый ручной ввод.
- `/scan` — пришлите фото чека с QR.
- `/report` — week/month/year.
- `/categories` — список/редактирование категорий.
- `/family` — list/invite/remove.
- `/join <код>` — вступить по инвайту.
- `/settings` — currency/timezone/rounding.
- `/cancel`

## Пример UX сообщений

### `/start`

`Привет! Я создам Google-таблицу... Отправьте email Google для шаринга.`

### `/add`

`Как добавить расход? [Позиция] [Одной суммой]`

### `/scan`

`Чек распознан... Провайдер товаров не настроен. [Записать одной суммой] [Внести вручную позиции]`

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
- `QR не найден`: улучшите резкость/контраст фото, уберите блики.
- `Сначала выполните /start`: профиль/семья еще не инициализированы.

