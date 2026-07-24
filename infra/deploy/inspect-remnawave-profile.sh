#!/usr/bin/env bash
set -Eeuo pipefail

token="$(sed -n 's/^REMNAWAVE_TOKEN=//p' /opt/alanet/deploy/.env)"
curl --fail --silent --show-error \
  -H "Authorization: Bearer ${token}" \
  https://panel.alanet.ru/api/config-profiles |
  jq '{response: (.response.configProfiles // .response // .)}'
