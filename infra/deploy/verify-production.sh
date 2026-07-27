#!/usr/bin/env bash
set -Eeuo pipefail

umask 077

token="$(sed -n 's/^REMNAWAVE_TOKEN=//p' /opt/alanet/deploy/.env | tr -d '\r')"
telegram_token="$(sed -n 's/^TELEGRAM_BOT_TOKEN=//p' /opt/alanet/deploy/.env | tr -d '\r')"
auth=(-H "Authorization: Bearer ${token}")

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

webhook_json="$(curl --fail --silent --show-error "https://api.telegram.org/bot${telegram_token}/getWebhookInfo")"
webhook_url="$(jq -r '.result.url // empty' <<<"${webhook_json}")"
[[ "${webhook_url}" == "https://api.alanet.ru/webhooks/telegram" ]]
printf 'telegram_webhook=200\n'

nodes_json="$(curl --fail --silent --show-error "${auth[@]}" https://panel.alanet.ru/api/nodes)"
for node_name in ALANET-FIN-01 ALANET-DE-1 ALANET-CZ-1 ALANET-SE-1; do
  connected="$(jq -r --arg name "${node_name}" '(.response | if type == "array" then . else (.nodes // []) end) | map(select(.name == $name))[0].isConnected // false' <<<"${nodes_json}")"
  printf '%s_connected=%s\n' "${node_name,,}" "${connected}"
  [[ "${connected}" == "true" ]]
done

hosts_json="$(curl --fail --silent --show-error "${auth[@]}" https://panel.alanet.ru/api/hosts)"
jq -e '.response[] | select(.address == "89.125.243.225" and .port == 2053 and (.nodes | index("eeddedb1-1144-4e37-93ec-584ea5f8aacf")))' <<<"${hosts_json}" >/dev/null
printf 'alanet-se-1_host=present\n'

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
  alanet-web-1 alanet-api-1 alanet-caddy-1 \
  alanet-billing-db-1 alanet-billing-redis-1 \
  remnawave remnawave-db remnawave-redis \
  remnawave-subscription-page remnanode
do
  [[ "$(docker inspect -f '{{.State.Running}}' "${container}")" == "true" ]]
done
printf 'containers=10/10\n'

rm -f /tmp/alanet-client-subscription /tmp/alanet-client-subscription.decoded
