#!/usr/bin/env bash
set -Eeuo pipefail

umask 077

token="$(sed -n 's/^REMNAWAVE_TOKEN=//p' /opt/alanet/deploy/.env | tr -d '\r')"
telegram_token="$(sed -n 's/^TELEGRAM_BOT_TOKEN=//p' /opt/alanet/deploy/.env | tr -d '\r')"
telegram_admin_chat_id="$(sed -n 's/^TELEGRAM_ADMIN_CHAT_ID=//p' /opt/alanet/deploy/.env | tr -d '\r')"
auth=(-H "Authorization: Bearer ${token}")
monitor_state_dir="/var/lib/alanet-monitor"
monitor_state_file="${monitor_state_dir}/health.state"
mkdir -p "${monitor_state_dir}"

send_alert() {
  local message="$1"
  [[ -n "${telegram_token}" && -n "${telegram_admin_chat_id}" ]] || return 0
  curl --silent --show-error --max-time 15 \
    --data-urlencode "chat_id=${telegram_admin_chat_id}" \
    --data-urlencode "text=${message}" \
    "https://api.telegram.org/bot${telegram_token}/sendMessage" >/dev/null || true
}

on_error() {
  local exit_code="$?" line="$1" previous
  trap - ERR
  set +e
  previous="$(cat "${monitor_state_file}" 2>/dev/null || true)"
  if [[ "${previous}" != "failed" ]]; then
    send_alert "ALANET: health-check обнаружил сбой на строке ${line}. Повторные одинаковые оповещения подавлены до восстановления."
  fi
  printf 'failed\n' > "${monitor_state_file}"
  rm -f /tmp/alanet-client-subscription /tmp/alanet-client-subscription.decoded
  exit "${exit_code}"
}
trap 'on_error ${LINENO}' ERR

check_http() {
  local name="$1" url="$2" expected="$3" status
  status="$(curl --silent --output /dev/null --write-out '%{http_code}' "${url}")"
  printf '%s=%s\n' "${name}" "${status}"
  [[ "${status}" == "${expected}" ]]
}

check_http site https://alanet.ru/ 200
check_http account https://account.alanet.ru/ 200
check_http api https://api.alanet.ru/health 200
check_http panel https://panel.alanet.ru/ 200
check_http subscription_root https://sub.alanet.ru/ 404
check_http sensitive_path https://alanet.ru/.env 404

for domain in alanet.ru account.alanet.ru api.alanet.ru panel.alanet.ru sub.alanet.ru; do
  echo | openssl s_client -connect "${domain}:443" -servername "${domain}" 2>/dev/null \
    | openssl x509 -checkend 604800 -noout >/dev/null
done
printf 'tls_certificates=valid_7d\n'

disk_percent="$(df -P / | awk 'NR==2 {gsub(/%/, "", $5); print $5}')"
memory_percent="$(free | awk '/^Mem:/ {printf "%d", ($3/$2)*100}')"
load_1m="$(awk '{print $1}' /proc/loadavg)"
cpu_count="$(nproc)"
printf 'resources=disk_%s%%_memory_%s%%_load_%s_cpus_%s\n' "${disk_percent}" "${memory_percent}" "${load_1m}" "${cpu_count}"
(( disk_percent < 90 ))
(( memory_percent < 95 ))
awk -v load_value="${load_1m}" -v cpus="${cpu_count}" 'BEGIN { exit !(load_value < cpus * 2) }'

webhook_json="$(curl --fail --silent --show-error "https://api.telegram.org/bot${telegram_token}/getWebhookInfo")"
webhook_url="$(jq -r '.result.url // empty' <<<"${webhook_json}")"
[[ "${webhook_url}" == "https://api.alanet.ru/webhooks/telegram" ]]
printf 'telegram_webhook=200\n'

nodes_json="$(curl --fail --silent --show-error "${auth[@]}" https://panel.alanet.ru/api/nodes)"
for node_name in ALANET-FIN-01 ALANET-DE-1 ALANET-CZ-1 ALANET-SE-1 ALANET-PL-1 ALANET-ES-1 ALANET-LV-1; do
  connected="$(jq -r --arg name "${node_name}" '(.response | if type == "array" then . else (.nodes // []) end) | map(select(.name == $name))[0].isConnected // false' <<<"${nodes_json}")"
  printf '%s_connected=%s\n' "${node_name,,}" "${connected}"
  [[ "${connected}" == "true" ]]
done

hosts_json="$(curl --fail --silent --show-error "${auth[@]}" https://panel.alanet.ru/api/hosts)"
jq -e '.response[] | select(.address == "89.125.243.225" and .port == 2053 and (.nodes | index("eeddedb1-1144-4e37-93ec-584ea5f8aacf")))' <<<"${hosts_json}" >/dev/null
printf 'alanet-se-1_host=present\n'
jq -e '.response[] | select(.address == "78.17.154.237" and .port == 2053 and (.nodes | index("329e3229-b142-4d17-9b89-28c39337731e")))' <<<"${hosts_json}" >/dev/null
printf 'alanet-pl-1_host=present\n'
jq -e '.response[] | select(.address == "78.17.180.246" and .port == 2053 and (.nodes | index("75ded50a-09b1-4efc-bc68-57a8f21fdd96")))' <<<"${hosts_json}" >/dev/null
printf 'alanet-es-1_host=present\n'
jq -e '.response[] | select(.address == "213.155.12.131" and .port == 2053 and (.nodes | index("d52aad4e-4e49-4247-9a5f-1312fe40a512")))' <<<"${hosts_json}" >/dev/null
printf 'alanet-lv-1_host=present\n'

subscription_url="$(docker exec alanet-billing-db-1 psql -U billing -d billing -Atq -c "select subscription_url from subscriptions order by starts_at desc limit 1" | tr -d '\r')"
[[ -n "${subscription_url}" ]]
check_http subscription "${subscription_url}" 200
curl --fail --silent --show-error --user-agent 'v2rayN/7.0' "${subscription_url}" > /tmp/alanet-client-subscription

if grep -q '^vless://' /tmp/alanet-client-subscription; then
  cp /tmp/alanet-client-subscription /tmp/alanet-client-subscription.decoded
else
  tr -d '\r\n' < /tmp/alanet-client-subscription | base64 -d > /tmp/alanet-client-subscription.decoded
fi
grep -q '^vless://' /tmp/alanet-client-subscription.decoded
printf 'vless_subscription=valid\n'

ss -ltn | grep -q ':443 '
printf 'xray_listener=443\n'

for container in \
  alanet-web-1 alanet-api-1 alanet-worker-1 alanet-caddy-1 \
  alanet-billing-db-1 alanet-billing-redis-1 \
  remnawave remnawave-db remnawave-redis \
  remnawave-subscription-page remnanode
do
  [[ "$(docker inspect -f '{{.State.Running}}' "${container}")" == "true" ]]
done
printf 'containers=11/11\n'

rm -f /tmp/alanet-client-subscription /tmp/alanet-client-subscription.decoded

previous_state="$(cat "${monitor_state_file}" 2>/dev/null || true)"
printf 'ok\n' > "${monitor_state_file}"
if [[ "${previous_state}" == "failed" ]]; then
  send_alert "ALANET: health-check снова проходит, сервисы восстановлены."
fi
