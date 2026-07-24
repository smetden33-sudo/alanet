#!/usr/bin/env bash
set -euo pipefail

cd /opt/remnawave
curl -fsSLo docker-compose.yml https://raw.githubusercontent.com/remnawave/backend/refs/heads/main/docker-compose-prod.yml
curl -fsSLo .env https://raw.githubusercontent.com/remnawave/backend/refs/heads/main/.env.sample

set_env() {
  local key="$1" value="$2"
  if grep -qE "^#?${key}=" .env; then
    sed -i -E "s|^#?${key}=.*|${key}=${value}|" .env
  else
    printf '%s=%s\n' "$key" "$value" >> .env
  fi
}

postgres_password="$(openssl rand -hex 24)"
set_env PANEL_DOMAIN panel.alanet.ru
set_env FRONT_END_DOMAIN https://panel.alanet.ru
set_env SUB_PUBLIC_DOMAIN sub.alanet.ru
set_env POSTGRES_USER postgres
set_env POSTGRES_PASSWORD "$postgres_password"
set_env POSTGRES_DB postgres
set_env DATABASE_URL "\"postgresql://postgres:${postgres_password}@remnawave-db:5432/postgres\""
set_env JWT_AUTH_SECRET "$(openssl rand -hex 64)"
set_env JWT_API_TOKENS_SECRET "$(openssl rand -hex 64)"
set_env APP_SECRET "$(openssl rand -hex 64)"
set_env METRICS_USER metrics
set_env METRICS_PASS "$(openssl rand -hex 48)"
set_env WEBHOOK_SECRET_HEADER "$(openssl rand -hex 32)"
set_env WEBHOOK_ENABLED false
set_env IS_DOCS_ENABLED false
set_env IS_TELEGRAM_NOTIFICATIONS_ENABLED false
set_env API_INSTANCES 1

chmod 600 .env

cat >compose.override.yml <<'EOF'
services:
  remnawave:
    mem_limit: 600m
  remnawave-db:
    mem_limit: 320m
    shm_size: 128mb
  remnawave-redis:
    mem_limit: 96m
EOF

docker compose pull
docker compose up -d
docker compose ps
