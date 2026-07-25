#!/usr/bin/env bash
set -Eeuo pipefail

umask 077

token="$(sed -n 's/^REMNAWAVE_TOKEN=//p' /opt/alanet/deploy/.env)"
private_key="$(sed -n 's/^PrivateKey: //p' /root/reality.keys)"

jq -n \
  --arg uuid "00000000-0000-0000-0000-000000000000" \
  --arg name "COMMERCIAL-REALITY" \
  --arg private_key "${private_key}" \
  '{
    uuid: $uuid,
    name: $name,
    config: {
      log: {loglevel: "warning"},
      inbounds: [
        {
          tag: "VLESS_TCP_REALITY",
          port: 443,
          listen: "0.0.0.0",
          protocol: "vless",
          settings: {
            clients: [],
            flow: "xtls-rprx-vision",
            decryption: "none"
          },
          sniffing: {
            enabled: true,
            destOverride: ["http", "tls", "quic"],
            routeOnly: true
          },
          streamSettings: {
            network: "raw",
            security: "reality",
            realitySettings: {
              target: "127.0.0.1:9443",
              shortIds: ["6ba85179e30d4fc2"],
              privateKey: $private_key,
              serverNames: ["alanet.ru"]
            }
          }
        }
      ],
      outbounds: [
        {protocol: "freedom", tag: "DIRECT"},
        {protocol: "blackhole", tag: "BLOCK"}
      ],
      routing: {
        domainStrategy: "IPIfNonMatch",
        rules: [
          {type: "field", ip: ["geoip:private"], outboundTag: "BLOCK"},
          {type: "field", domain: ["geosite:private"], outboundTag: "BLOCK"},
          {type: "field", protocol: ["bittorrent"], outboundTag: "BLOCK"}
        ]
      }
    }
  }' > /root/remnawave-vless-profile.json

curl --fail --silent --show-error \
  -X PATCH \
  -H "Authorization: Bearer ${token}" \
  -H "Content-Type: application/json" \
  --data-binary @/root/remnawave-vless-profile.json \
  https://panel.alanet.ru/api/config-profiles |
  jq '{name: .response.name, inbounds: [.response.inbounds[] | {tag, type, network, security, port}]}'

rm -f /root/reality.keys /root/remnawave-vless-profile.json
