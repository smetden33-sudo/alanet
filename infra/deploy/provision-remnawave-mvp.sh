#!/usr/bin/env bash
set -Eeuo pipefail

umask 077

token="$(sed -n 's/^REMNAWAVE_TOKEN=//p' /opt/alanet/deploy/.env)"
auth=(-H "Authorization: Bearer ${token}")
json_auth=("${auth[@]}" -H "Content-Type: application/json")

profiles_json="$(curl --fail --silent --show-error "${auth[@]}" https://panel.alanet.ru/api/config-profiles)"
profile_uuid="$(jq -r '(.response | if type == "array" then . else (.configProfiles // []) end)[] | select(.name == "COMMERCIAL-REALITY") | .uuid' <<<"${profiles_json}")"
inbound_uuid="$(jq -r '(.response | if type == "array" then . else (.configProfiles // []) end)[] | select(.name == "COMMERCIAL-REALITY") | .inbounds[] | select(.tag == "VLESS_TCP_REALITY") | .uuid' <<<"${profiles_json}")"

nodes_json="$(curl --fail --silent --show-error "${auth[@]}" https://panel.alanet.ru/api/nodes)"
node_uuid="$(jq -r '(.response | if type == "array" then . else (.nodes // []) end)[] | select(.name == "ALANET-RU-1") | .uuid' <<<"${nodes_json}")"

hosts_json="$(curl --fail --silent --show-error "${auth[@]}" https://panel.alanet.ru/api/hosts)"
host_uuid="$(jq -r '(.response | if type == "array" then . else (.hosts // []) end)[]? | select(.remark == "ALANET-RU-1") | .uuid' <<<"${hosts_json}" | head -n1)"
if [[ -z "${host_uuid}" ]]; then
  jq -n \
    --arg profile_uuid "${profile_uuid}" \
    --arg inbound_uuid "${inbound_uuid}" \
    --arg node_uuid "${node_uuid}" \
    '{
      inbound: {
        configProfileUuid: $profile_uuid,
        configProfileInboundUuid: $inbound_uuid
      },
      remark: "ALANET-RU-1",
      address: "78.17.54.252",
      port: 8443,
      sni: "www.microsoft.com",
      fingerprint: "chrome",
      isDisabled: false,
      isHidden: false,
      serverDescription: "ALANET Russia",
      nodes: [$node_uuid]
    }' > /tmp/alanet-host.json
  host_response="$(curl --fail --silent --show-error -X POST "${json_auth[@]}" --data-binary @/tmp/alanet-host.json https://panel.alanet.ru/api/hosts)"
  host_uuid="$(jq -r '.response.uuid' <<<"${host_response}")"
fi

squads_json="$(curl --fail --silent --show-error "${auth[@]}" https://panel.alanet.ru/api/internal-squads)"
squad_uuid="$(jq -r '(.response | if type == "array" then . else (.internalSquads // .squads // []) end)[]? | select(.name == "PAID-USERS") | .uuid' <<<"${squads_json}" | head -n1)"
if [[ -z "${squad_uuid}" ]]; then
  jq -n --arg inbound_uuid "${inbound_uuid}" \
    '{name: "PAID-USERS", inbounds: [$inbound_uuid]}' > /tmp/alanet-squad.json
  squad_response="$(curl --fail --silent --show-error -X POST "${json_auth[@]}" --data-binary @/tmp/alanet-squad.json https://panel.alanet.ru/api/internal-squads)"
  squad_uuid="$(jq -r '.response.uuid' <<<"${squad_response}")"
fi

set +e
user_response="$(curl --silent --show-error "${auth[@]}" https://panel.alanet.ru/api/users/by-username/alanet_smoke)"
user_uuid="$(jq -r '.response.uuid // empty' <<<"${user_response}" 2>/dev/null)"
set -e
if [[ -z "${user_uuid}" ]]; then
  expire_at="$(date -u -d '+30 days' '+%Y-%m-%dT%H:%M:%S.000Z')"
  jq -n \
    --arg expire_at "${expire_at}" \
    --arg squad_uuid "${squad_uuid}" \
    '{
      username: "alanet_smoke",
      status: "ACTIVE",
      expireAt: $expire_at,
      trafficLimitBytes: 10737418240,
      trafficLimitStrategy: "MONTH",
      hwidDeviceLimit: 3,
      description: "Production smoke-test account",
      tag: "SMOKE_TEST",
      activeInternalSquads: [$squad_uuid]
    }' > /tmp/alanet-user.json
  user_response="$(curl --fail --silent --show-error -X POST "${json_auth[@]}" --data-binary @/tmp/alanet-user.json https://panel.alanet.ru/api/users)"
  user_uuid="$(jq -r '.response.uuid' <<<"${user_response}")"
fi

subscription_url="$(jq -r '.response.subscriptionUrl // .response.subscriptionUrlRaw // empty' <<<"${user_response}")"
if [[ -z "${subscription_url}" ]]; then
  user_response="$(curl --fail --silent --show-error "${auth[@]}" https://panel.alanet.ru/api/users/by-username/alanet_smoke)"
  subscription_url="$(jq -r '.response.subscriptionUrl // .response.subscriptionUrlRaw // empty' <<<"${user_response}")"
fi

printf '%s\n' "${subscription_url}" > /root/alanet-test-subscription.url
chmod 600 /root/alanet-test-subscription.url

sed -i "s|^REMNAWAVE_SQUAD_ID=.*|REMNAWAVE_SQUAD_ID=${squad_uuid}|" /opt/alanet/deploy/.env
chmod 600 /opt/alanet/deploy/.env
cd /opt/alanet/deploy
docker compose up -d --no-deps --force-recreate api >/dev/null

subscription_status="$(curl --silent --output /dev/null --write-out '%{http_code}' "${subscription_url}")"
jq -n \
  --arg host_uuid "${host_uuid}" \
  --arg squad_uuid "${squad_uuid}" \
  --arg user_uuid "${user_uuid}" \
  --arg subscription_status "${subscription_status}" \
  '{
    host: $host_uuid,
    squad: $squad_uuid,
    testUser: $user_uuid,
    subscriptionStatus: $subscription_status
  }'

rm -f /tmp/alanet-host.json /tmp/alanet-squad.json /tmp/alanet-user.json
