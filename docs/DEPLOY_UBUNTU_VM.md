# Deploy на Ubuntu VM (production)

Этот runbook рассчитан на перенос проекта с локального Windows на Ubuntu VM.

## 1) Подготовка VM

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y ca-certificates curl gnupg lsb-release git
```

## 2) Установка Docker + Compose plugin

```bash
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo $VERSION_CODENAME) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker $USER
newgrp docker
```

## 3) Клонирование проекта

```bash
sudo mkdir -p /opt/finass
sudo chown -R $USER:$USER /opt/finass
cd /opt/finass
git clone <YOUR_REPO_URL> .
```

## 4) Secrets и env

```bash
mkdir -p /opt/finass/secrets
cp .env.prod.example .env.prod
```

- Отредактируйте `.env.prod`:
  - `TELEGRAM_BOT_TOKEN`
  - `WEBHOOK_SECRET_TOKEN`
  - `BASE_URL=https://<your-domain>`
  - `DB_DSN` (обычно PostgreSQL внутри compose)
  - `POSTGRES_PASSWORD`
  - `GOOGLE_SERVICE_ACCOUNT_JSON_PATH=/run/secrets/google_service_account.json`

- Скопируйте JSON service account:

```bash
cp /path/to/google-sa.json /opt/finass/secrets/google_service_account.json
chmod 600 /opt/finass/secrets/google_service_account.json
```

Важно: таблица пользователя должна быть расшарена на
`hydra-950@finassbobot.iam.gserviceaccount.com` с ролью `Editor`.

## 5) Запуск production compose

```bash
cd /opt/finass
docker compose -f docker-compose.prod.yml up -d --build
```

Проверка:

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f bot worker
curl -fsS http://127.0.0.1:8000/health/ready
```

## 6) Nginx + TLS (Webhook)

1. Установить nginx и certbot:

```bash
sudo apt install -y nginx certbot python3-certbot-nginx
```

2. Скопировать шаблон:

```bash
sudo cp deploy/nginx/finass.conf.example /etc/nginx/sites-available/finass.conf
sudo ln -s /etc/nginx/sites-available/finass.conf /etc/nginx/sites-enabled/finass.conf
sudo nginx -t
sudo systemctl reload nginx
```

3. Выпустить сертификат:

```bash
sudo certbot --nginx -d <your-domain>
```

4. Проверить webhook endpoint снаружи:
- `https://<your-domain>/health/ready`

## 7) Автозапуск после reboot (опционально)

```bash
sudo cp deploy/systemd/finass-compose.service /etc/systemd/system/finass-compose.service
sudo systemctl daemon-reload
sudo systemctl enable finass-compose
sudo systemctl start finass-compose
```

## 8) Перенос текущих данных с Windows

### Вариант A (быстро, без миграции на Postgres):
- Скопируйте `data/app.db` с Windows в `/opt/finass/data/app.db`.
- В `.env.prod` поставьте:
  - `DB_DSN=sqlite+aiosqlite:///./data/app.db`

### Вариант B (рекомендуется для прод):
- Используйте PostgreSQL в `docker-compose.prod.yml`.
- Если нужны старые данные из SQLite, сначала запуститесь по варианту A, проверьте целостность, затем планируйте отдельную миграцию в Postgres.

## 9) Восстановление пропущенных строк в Google Sheets

Если из-за временных сетевых ошибок worker часть покупок не попала в таблицу:

```bash
docker compose -f docker-compose.prod.yml run --rm bot python -m app.scripts.reconcile_expenses
```

## 10) Обновление на VM

```bash
cd /opt/finass
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

## 11) Мини-чеклист перед go-live

- `APP_MODE=webhook`
- `BASE_URL` публичный и с TLS
- `WEBHOOK_SECRET_TOKEN` установлен
- таблица расшарена на service account
- `worker` в статусе `Up`
- `/health/ready` отвечает `{"status":"ready"}`
