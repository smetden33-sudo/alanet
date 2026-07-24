#!/usr/bin/env bash
set -Eeuo pipefail

token="$(sed -n 's/^REMNAWAVE_TOKEN=//p' /opt/alanet/deploy/.env)"
auth=(-H "Authorization: Bearer ${token}")

nodes_json="$(curl --fail --silent --show-error "${auth[@]}" https://panel.alanet.ru/api/nodes)"
existing_uuid="$(jq -r '(.response | if type == "array" then . else (.nodes // []) end)[]? | select(.name == "ALANET-RU-1") | .uuid' <<<"${nodes_json}" | head -n1)"
if [[ -n "${existing_uuid}" ]]; then
  jq -n --arg uuid "${existing_uuid}" '{status: "exists", uuid: $uuid}'
  exit 0
fi

profiles_json="$(curl --fail --silent --show-error "${auth[@]}" https://panel.alanet.ru/api/config-profiles)"
profile_uuid="$(jq -r '(.response | if type == "array" then . else (.configProfiles // []) end)[] | select(.name == "COMMERCIAL-REALITY") | .uuid' <<<"${profiles_json}")"
inbound_uuid="$(jq -r '(.response | if type == "array" then . else (.configProfiles // []) end)[] | select(.name == "COMMERCIAL-REALITY") | .inbounds[] | select(.tag == "VLESS_TCP_REALITY") | .uuid' <<<"${profiles_json}")"

jq -n \
  --arg profile_uuid "${profile_uuid}" \
  --arg inbound_uuid "${inbound_uuid}" \
  '{
    name: "ALANET-RU-1",
    address: "172.18.0.1",
    port: 2222,
    countryCode: "RU",
    consumptionMultiplier: 1,
    nodeConsumptionMultiplier: 1,
    isTrafficTrackingActive: false,
    configProfile: {
      activeConfigProfileUuid: $profile_uuid,
      activeInbounds: [$inbound_uuid]
    }
  }' > /tmp/alanet-node.json

curl --fail --silent --show-error \
  -X POST \
  "${auth[@]}" \
  -H "Content-Type: application/json" \
  --data-binary @/tmp/alanet-node.json \
  https://panel.alanet.ru/api/nodes |
  jq '{uuid: .response.uuid, name: .response.name, address: .response.address, port: .response.port, isConnected: .response.isConnected}'

rm -f /tmp/alanet-node.json
