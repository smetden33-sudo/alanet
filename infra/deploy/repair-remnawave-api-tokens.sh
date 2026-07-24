#!/usr/bin/env bash
set -Eeuo pipefail

umask 077

resign_token() {
  printf '%s' "$1" | docker exec -i remnawave node -e \
    "let t='';process.stdin.on('data',c=>t+=c).on('end',()=>{const j=require('jsonwebtoken');const p=j.decode(t);if(!p?.uuid)process.exit(2);process.stdout.write(j.sign({uuid:p.uuid,username:null,role:'API'},process.env.APP_SECRET,{expiresIn:'3650d'}))})"
}

old_subscription_token="$(sed -n 's/^REMNAWAVE_API_TOKEN=//p' /opt/remnawave/subscription/.env)"
old_billing_token="$(sed -n 's/^REMNAWAVE_TOKEN=//p' /opt/alanet/deploy/.env)"
subscription_token="$(resign_token "${old_subscription_token}")"
billing_token="$(resign_token "${old_billing_token}")"

sed -i "s|^REMNAWAVE_API_TOKEN=.*|REMNAWAVE_API_TOKEN=${subscription_token}|" /opt/remnawave/subscription/.env
sed -i "s|^REMNAWAVE_TOKEN=.*|REMNAWAVE_TOKEN=${billing_token}|" /opt/alanet/deploy/.env
chmod 600 /opt/remnawave/subscription/.env /opt/alanet/deploy/.env

cd /opt/remnawave/subscription
docker compose up -d --no-deps --force-recreate remnawave-subscription-page

cd /opt/alanet/deploy
docker compose up -d --no-deps --force-recreate api
