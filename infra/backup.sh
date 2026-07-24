#!/usr/bin/env sh
set -eu
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
target="/backups/$stamp"
mkdir -p "$target"
pg_dump "$DATABASE_URL" --format=custom --file="$target/billing.dump"
tar -czf "$target/config.tgz" /srv/quiet-network/.env /srv/quiet-network/docker-compose.yml /srv/quiet-network/infra/Caddyfile
find /backups -mindepth 1 -maxdepth 1 -type d -mtime +7 -exec rm -rf -- {} +
