#!/usr/bin/env bash
set -Eeuo pipefail

umask 077

subscription_token="$(< /root/alanet-secrets/sub.token)"
billing_token="$(< /root/alanet-secrets/billing.token)"

cat > /opt/remnawave/subscription/.env <<EOF
APP_PORT=3010
REMNAWAVE_PANEL_URL=http://remnawave:3000
REMNAWAVE_API_TOKEN=${subscription_token}
TRUST_PROXY=1
EOF

sed -i "s|^REMNAWAVE_TOKEN=.*|REMNAWAVE_TOKEN=${billing_token}|" /opt/alanet/deploy/.env
chmod 600 /opt/remnawave/subscription/.env /opt/alanet/deploy/.env

cd /opt/remnawave/subscription
docker compose pull
docker compose up -d

cd /opt/alanet/deploy
docker compose up -d --no-deps --force-recreate api
docker compose up -d --no-deps caddy
docker compose exec -T caddy caddy validate --config /etc/caddy/Caddyfile
docker compose up -d --no-deps --force-recreate caddy

rm -f /root/alanet-secrets/sub.token /root/alanet-secrets/billing.token

curl --fail --silent --show-error http://127.0.0.1:8000/health >/dev/null
[[ "$(docker inspect -f '{{.State.Running}}' remnawave-subscription-page)" == "true" ]]
docker compose ps
