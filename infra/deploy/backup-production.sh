#!/usr/bin/env bash
set -Eeuo pipefail

umask 077

backup_root="/var/backups/alanet"
stamp="$(date -u '+%Y%m%dT%H%M%SZ')"
work_dir="$(mktemp -d "${backup_root}/.work-${stamp}-XXXXXX")"
archive="${backup_root}/alanet-${stamp}.tar.gz"

cleanup() {
  rm -rf -- "${work_dir}"
}
trap cleanup EXIT

docker exec remnawave-db sh -lc 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' \
  | gzip -9 > "${work_dir}/remnawave.sql.gz"
docker exec alanet-billing-db-1 sh -lc 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' \
  | gzip -9 > "${work_dir}/billing.sql.gz"

tar -czf "${work_dir}/configuration.tar.gz" \
  /opt/remnawave/.env \
  /opt/remnawave/docker-compose.yml \
  /opt/remnawave/subscription/.env \
  /opt/remnawave/subscription/docker-compose.yml \
  /opt/remnanode/docker-compose.yml \
  /opt/alanet/deploy/.env \
  /opt/alanet/deploy/compose.yml \
  /opt/alanet/deploy/Caddyfile

tar -C "${work_dir}" -czf "${archive}" \
  remnawave.sql.gz billing.sql.gz configuration.tar.gz
chmod 600 "${archive}"

find "${backup_root}" -maxdepth 1 -type f -name 'alanet-*.tar.gz' -mtime +7 -delete
printf 'Created %s\n' "${archive}"
