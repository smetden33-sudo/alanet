#!/usr/bin/env bash
set -Eeuo pipefail

: "${REMNAWAVE_TOKEN:?REMNAWAVE_TOKEN is required}"
: "${NODE_NAME:?NODE_NAME is required}"
: "${NODE_ADDRESS:?NODE_ADDRESS is required}"

REMNAWAVE_BASE_URL="${REMNAWAVE_BASE_URL:-https://panel.alanet.ru}"
NODE_PORT="${NODE_PORT:-2222}"
NODE_COUNTRY="${NODE_COUNTRY:-XX}"
CONFIG_PROFILE_NAME="${CONFIG_PROFILE_NAME:-COMMERCIAL-REALITY}"
INBOUND_TAG="${INBOUND_TAG:-VLESS_TCP_REALITY}"

auth=(-H "Authorization: Bearer ${REMNAWAVE_TOKEN}")

nodes_json="$(curl --fail --silent --show-error "${auth[@]}" "${REMNAWAVE_BASE_URL}/api/nodes")"
existing_uuid="$(
  jq -r --arg name "${NODE_NAME}" \
    '(.response | if type == "array" then . else (.nodes // []) end)[]? | select(.name == $name) | .uuid' \
    <<<"${nodes_json}" | head -n1
)"

if [[ -n "${existing_uuid}" ]]; then
  jq -n --arg status "exists" --arg uuid "${existing_uuid}" --arg name "${NODE_NAME}" \
    '{status: $status, uuid: $uuid, name: $name}'
  exit 0
fi

profiles_json="$(curl --fail --silent --show-error "${auth[@]}" "${REMNAWAVE_BASE_URL}/api/config-profiles")"
profile_uuid="$(
  jq -r --arg name "${CONFIG_PROFILE_NAME}" \
    '(.response | if type == "array" then . else (.configProfiles // []) end)[] | select(.name == $name) | .uuid' \
    <<<"${profiles_json}" | head -n1
)"
inbound_uuid="$(
  jq -r --arg name "${CONFIG_PROFILE_NAME}" --arg tag "${INBOUND_TAG}" \
    '(.response | if type == "array" then . else (.configProfiles // []) end)[] | select(.name == $name) | .inbounds[] | select(.tag == $tag) | .uuid' \
    <<<"${profiles_json}" | head -n1
)"

if [[ -z "${profile_uuid}" || -z "${inbound_uuid}" ]]; then
  echo "Config profile or inbound not found: ${CONFIG_PROFILE_NAME}/${INBOUND_TAG}" >&2
  exit 1
fi

payload="$(mktemp)"
jq -n \
  --arg name "${NODE_NAME}" \
  --arg address "${NODE_ADDRESS}" \
  --argjson port "${NODE_PORT}" \
  --arg country "${NODE_COUNTRY}" \
  --arg profile_uuid "${profile_uuid}" \
  --arg inbound_uuid "${inbound_uuid}" \
  '{
    name: $name,
    address: $address,
    port: $port,
    countryCode: $country,
    consumptionMultiplier: 1,
    nodeConsumptionMultiplier: 1,
    isTrafficTrackingActive: false,
    configProfile: {
      activeConfigProfileUuid: $profile_uuid,
      activeInbounds: [$inbound_uuid]
    }
  }' > "${payload}"

curl --fail --silent --show-error \
  -X POST \
  "${auth[@]}" \
  -H "Content-Type: application/json" \
  --data-binary @"${payload}" \
  "${REMNAWAVE_BASE_URL}/api/nodes" |
  jq '{status: "created", uuid: .response.uuid, name: .response.name, address: .response.address, port: .response.port, isConnected: .response.isConnected}'

rm -f "${payload}"
