#!/usr/bin/env bash
set -Eeuo pipefail

umask 077

token="$(sed -n 's/^REMNAWAVE_TOKEN=//p' /opt/alanet/deploy/.env)"
subscription_url="$(< /root/alanet-test-subscription.url)"
auth=(-H "Authorization: Bearer ${token}")

check_http() {
  local name="$1"
  local url="$2"
  local expected="$3"
  local status
  status="$(curl --silent --output /dev/null --write-out '%{http_code}' "${url}")"
  printf '%s=%s\n' "${name}" "${status}"
  [[ "${status}" == "${expected}" ]]
}

check_http site https://alanet.ru/ 200
check_http account https://account.alanet.ru/ 200
check_http api https://api.alanet.ru/health 200
check_http panel https://panel.alanet.ru/ 200
check_http subscription "${subscription_url}" 200
check_http sensitive_path https://alanet.ru/.env 404

nodes_json="$(curl --fail --silent --show-error "${auth[@]}" https://panel.alanet.ru/api/nodes)"
node_connected="$(jq -r '(.response | if type == "array" then . else (.nodes // []) end)[] | select(.name == "ALANET-RU-1") | .isConnected' <<<"${nodes_json}")"
printf 'node_connected=%s\n' "${node_connected}"
[[ "${node_connected}" == "true" ]]

curl --fail --silent --show-error \
  --user-agent 'v2rayN/7.0' \
  "${subscription_url}" > /tmp/alanet-client-subscription

if grep -q '^vless://' /tmp/alanet-client-subscription; then
  cp /tmp/alanet-client-subscription /tmp/alanet-client-subscription.decoded
else
  tr -d '\r\n' < /tmp/alanet-client-subscription |
    base64 -d > /tmp/alanet-client-subscription.decoded
fi

grep -q 'vless://' /tmp/alanet-client-subscription.decoded
grep -q '@78.17.54.252:443' /tmp/alanet-client-subscription.decoded
grep -q 'security=reality' /tmp/alanet-client-subscription.decoded
grep -q 'sni=alanet.ru' /tmp/alanet-client-subscription.decoded
grep -q 'fp=firefox' /tmp/alanet-client-subscription.decoded
grep -q 'flow=xtls-rprx-vision' /tmp/alanet-client-subscription.decoded
grep -q 'sid=6ba85179e30d4fc2' /tmp/alanet-client-subscription.decoded
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
