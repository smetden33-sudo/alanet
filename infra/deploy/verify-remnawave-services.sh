#!/usr/bin/env bash
set -Eeuo pipefail

subscription_token="$(sed -n 's/^REMNAWAVE_API_TOKEN=//p' /opt/remnawave/subscription/.env)"
billing_token="$(sed -n 's/^REMNAWAVE_TOKEN=//p' /opt/alanet/deploy/.env)"

verify_signature() {
  printf '%s' "$1" | docker exec -i remnawave node -e \
    "let t='';process.stdin.on('data',c=>t+=c).on('end',()=>{try{require('jsonwebtoken').verify(t,process.env.APP_SECRET);console.log('valid')}catch(e){console.log(e.name+': '+e.message)}})"
}

printf 'subscription_signature='
verify_signature "${subscription_token}"
printf 'billing_signature='
verify_signature "${billing_token}"

status="$(
  curl --silent --output /tmp/remnawave-metadata.json --write-out '%{http_code}' \
    -H "Authorization: Bearer ${subscription_token}" \
    https://panel.alanet.ru/api/system/metadata
)"

printf 'metadata_status=%s\n' "${status}"
if [[ "${status}" != "200" ]]; then
  sed -E 's/(eyJ[A-Za-z0-9._-]+)/[REDACTED]/g' /tmp/remnawave-metadata.json
  billing_status="$(
    curl --silent --output /tmp/remnawave-billing-metadata.json --write-out '%{http_code}' \
      -H "Authorization: Bearer ${billing_token}" \
      https://panel.alanet.ru/api/system/metadata
  )"
  printf '\nbilling_metadata_status=%s\n' "${billing_status}"
  if [[ "${billing_status}" != "200" ]]; then
    sed -E 's/(eyJ[A-Za-z0-9._-]+)/[REDACTED]/g' /tmp/remnawave-billing-metadata.json
    exit 1
  fi
fi

curl --fail --silent --show-error http://127.0.0.1:8000/health
printf '\nsubscription_container='
docker inspect -f '{{.State.Running}}' remnawave-subscription-page
if [[ -s /root/alanet-test-subscription.url ]]; then
  printf 'subscription_status='
  curl --silent --output /dev/null --write-out '%{http_code}' "$(< /root/alanet-test-subscription.url)"
fi
printf '\n'
