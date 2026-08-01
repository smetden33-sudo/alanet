#!/usr/bin/env bash
set -Eeuo pipefail

umask 077

backup_root="${ALANET_BACKUP_DIR:-/var/backups/alanet}"
status_dir="${ALANET_MONITOR_DIR:-/var/lib/alanet-monitor}"
stamp="$(date -u '+%Y%m%dT%H%M%SZ')"
work_dir="$(mktemp -d "${backup_root}/.work-${stamp}-XXXXXX")"
archive="${backup_root}/alanet-${stamp}.tar.gz"
encrypted_archive="${archive}.enc"
status_file="${status_dir}/backup.status.json"

mkdir -p "${backup_root}" "${status_dir}"

cleanup() {
  rm -rf -- "${work_dir}"
}
trap cleanup EXIT

json_status() {
  local status="$1" message="$2" archive_path="${3:-}" external_path="${4:-}"
  python3 - "$status" "$message" "$archive_path" "$external_path" > "${status_file}" <<'PY'
import json
import os
import sys
from datetime import datetime, timezone

status, message, archive_path, external_path = sys.argv[1:5]
payload = {
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "status": status,
    "message": message,
    "archive": archive_path or None,
    "archive_size_bytes": os.path.getsize(archive_path) if archive_path and os.path.exists(archive_path) else None,
    "external_archive": external_path or None,
}
print(json.dumps(payload, ensure_ascii=False))
PY
  chmod 644 "${status_file}"
}

fail() {
  local message="$1"
  json_status "failed" "${message}" "${archive}" ""
  echo "backup_failed=${message}"
  exit 1
}

docker exec remnawave-db sh -lc 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' \
  | gzip -9 > "${work_dir}/remnawave.sql.gz" || fail "remnawave pg_dump failed"
docker exec alanet-billing-db-1 sh -lc 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' \
  | gzip -9 > "${work_dir}/billing.sql.gz" || fail "billing pg_dump failed"

tar -czf "${work_dir}/configuration.tar.gz" \
  /opt/remnawave/.env \
  /opt/remnawave/docker-compose.yml \
  /opt/remnawave/subscription/.env \
  /opt/remnawave/subscription/docker-compose.yml \
  /opt/remnanode/docker-compose.yml \
  /opt/alanet/deploy/.env \
  /opt/alanet/deploy/compose.yml \
  /opt/alanet/deploy/Caddyfile \
  /opt/alanet/infra/node-registry.json \
  /opt/beszel/compose.yml \
  /opt/beszel/agent-compose.yml || fail "configuration archive failed"

tar -C "${work_dir}" -czf "${archive}" \
  remnawave.sql.gz billing.sql.gz configuration.tar.gz || fail "final archive failed"
chmod 600 "${archive}"

external_result="not_configured"
external_target=""

if [[ -n "${ALANET_BACKUP_ENCRYPTION_PASSPHRASE:-}" ]]; then
  openssl enc -aes-256-cbc -pbkdf2 -salt \
    -in "${archive}" \
    -out "${encrypted_archive}" \
    -pass env:ALANET_BACKUP_ENCRYPTION_PASSPHRASE || fail "backup encryption failed"
  chmod 600 "${encrypted_archive}"

  if [[ -n "${ALANET_BACKUP_EXTERNAL_DIR:-}" ]]; then
    mkdir -p "${ALANET_BACKUP_EXTERNAL_DIR}"
    external_target="${ALANET_BACKUP_EXTERNAL_DIR}/$(basename "${encrypted_archive}")"
    cp -f "${encrypted_archive}" "${external_target}" || fail "external copy failed"
    chmod 600 "${external_target}" || true
    external_result="copied"
  elif [[ -n "${ALANET_BACKUP_RCLONE_DEST:-}" && "$(command -v rclone || true)" ]]; then
    external_target="${ALANET_BACKUP_RCLONE_DEST%/}/$(basename "${encrypted_archive}")"
    rclone copyto "${encrypted_archive}" "${external_target}" || fail "rclone upload failed"
    external_result="uploaded"
  elif [[ -n "${ALANET_BACKUP_S3_URI:-}" && "$(command -v aws || true)" ]]; then
    external_target="${ALANET_BACKUP_S3_URI%/}/$(basename "${encrypted_archive}")"
    aws s3 cp "${encrypted_archive}" "${external_target}" || fail "s3 upload failed"
    external_result="uploaded"
  else
    external_result="encrypted_only_no_external_target"
  fi
else
  external_result="skipped_no_encryption_passphrase"
fi

find "${backup_root}" -maxdepth 1 -type f -name 'alanet-*.tar.gz' -mtime +"${ALANET_LOCAL_RETENTION_DAYS:-7}" -delete
find "${backup_root}" -maxdepth 1 -type f -name 'alanet-*.tar.gz.enc' -mtime +"${ALANET_LOCAL_RETENTION_DAYS:-7}" -delete

if [[ -n "${ALANET_BACKUP_EXTERNAL_DIR:-}" ]]; then
  find "${ALANET_BACKUP_EXTERNAL_DIR}" -maxdepth 1 -type f -name 'alanet-*.tar.gz.enc' -mtime +"${ALANET_EXTERNAL_RETENTION_DAYS:-90}" -delete || true
fi

json_status "ok" "local backup created; external=${external_result}" "${archive}" "${external_target}"
printf 'Created %s external=%s\n' "${archive}" "${external_result}"
