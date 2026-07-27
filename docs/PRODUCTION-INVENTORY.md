# ALANET production inventory

Inventory checked on 2026-07-27. Credentials, tokens and private keys are intentionally excluded.

## Remnawave nodes

| Name | UUID | Address | Country | Status |
| --- | --- | --- | --- | --- |
| `ALANET-FIN-01` | `19de6a7c-e102-4a62-b153-8817ad26a310` | `172.18.0.1` | FI | connected |
| `ALANET-DE-1` | `5e1f02ec-6ed8-4717-a819-76e60f189a7e` | `132.243.228.206` | DE | connected |
| `ALANET-CZ-1` | `bc3c365e-5ecf-4950-a05e-b7e5d7350f21` | `141.133.172.38` | CZ | connected |
| `ALANET-SE-1` | `eeddedb1-1144-4e37-93ec-584ea5f8aacf` | `89.125.243.225` | SE | connected |
| `ALANET-PL-1` | `329e3229-b142-4d17-9b89-28c39337731e` | `78.17.154.237` | PL | connected |
| `ALANET-ES-1` | `75ded50a-09b1-4efc-bc68-57a8f21fdd96` | `78.17.180.246` | ES | connected |
| `ALANET-LV-1` | `d52aad4e-4e49-4247-9a5f-1312fe40a512` | `213.155.12.131` | LV | connected |

## Internal squads

| Name | UUID | Intended use | Accessible nodes |
| --- | --- | --- | --- |
| `Default-Squad` | `2190759e-13f9-4462-ab98-8c2e2ce15859` | Remnawave default, not used for plans | none |
| `PAID-USERS` | `54e2736b-cf3a-4922-90b3-c1ef3319fc4f` | Paid tariffs | Finland, Germany, Czechia, Sweden, Poland, Spain, Latvia |
| `TRIAL-CZ` | `0b67e804-8f40-4930-bd20-c7a03652bb77` | Trial tariff | Czechia only |

## Remnawave hosts

| Host | UUID | Address | Inbound | Node |
| --- | --- | --- | --- | --- |
| `🇫🇮 Финляндия` | `3d4e5059-d5bb-45ad-80ef-5c84d265ec9f` | `78.17.54.252:8443` | `VLESS_TCP_REALITY_FIN_1` | `ALANET-FIN-01` |
| `🇸🇪 Швеция` | `82623a5c-ee0f-4116-b9ff-a4b182f7c26e` | `89.125.243.225:2053` | `VLESS_TCP_REALITY_SE_1` | `ALANET-SE-1` |
| `Poland` | `ef704276-c89b-446c-84ca-e5a9a4a30aca` | `78.17.154.237:2053` | `VLESS_TCP_REALITY_PL_1` | `ALANET-PL-1` |
| `Spain` | `357bcce5-31b3-43cb-8228-3913ba26f22b` | `78.17.180.246:2053` | `VLESS_TCP_REALITY_ES_1` | `ALANET-ES-1` |
| `Latvia` | `32f75a50-ff6a-4c46-b43d-3f43098e158d` | `213.155.12.131:2053` | `VLESS_TCP_REALITY_LV_1` | `ALANET-LV-1` |

## Plans

| Slug | Name | Duration | Traffic | Devices | Squad |
| --- | --- | ---: | ---: | ---: | --- |
| `trial` | Пробный | 1 day | unlimited | 1 | `TRIAL-CZ` |
| `start` | Старт | 30 days | unlimited | 1 | `PAID-USERS` |
| `calm` | Спокойно | 90 days | unlimited | 1 | `PAID-USERS` |
| `year` | На год | 365 days | unlimited | 1 | `PAID-USERS` |

## Scheduled operations

- `alanet-healthcheck.timer`: every 5 minutes (more frequent than a daily check); validates domains, API, Telegram webhook, all seven nodes, one subscription URL, listener 443 and all 10 containers on the primary VPS.
- `alanet-backup.timer`: daily at approximately 03:15 UTC with a randomized delay; retains seven days of archives.
- Health-check output and failures are available through `journalctl -u alanet-healthcheck.service`.
