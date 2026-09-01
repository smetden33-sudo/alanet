# ALANET production inventory

Inventory checked on 2026-07-30. Credentials, tokens and private keys are intentionally excluded.

The source of truth for nodes is `infra/node-registry.json`. Render it with:

```bash
python infra/scripts/render-node-registry.py --format markdown
```

## Node registry

| node_name | country | ip | remnawave_node_uuid | host_uuid | public_port | control_port | squad | provider | status |
| --- | --- | --- | --- | --- | ---: | ---: | --- | --- | --- |
| ALANET-FIN-01 | FI | 78.17.54.252 | 19de6a7c-e102-4a62-b153-8817ad26a310 | 3d4e5059-d5bb-45ad-80ef-5c84d265ec9f | 8443 | 2222 | PAID-USERS | existing-vps | active |
| ALANET-DE-1 | DE | 132.243.228.206 | 5e1f02ec-6ed8-4717-a819-76e60f189a7e | 9dcf4fd6-bbb8-4f16-afde-5a5d3c177f36 | 2053 | 22 | PAID-USERS | existing-shared-vps | active |
| ALANET-CZ-1 | CZ | 141.133.172.38 | bc3c365e-5ecf-4950-a05e-b7e5d7350f21 | aa7e0f91-018f-4cda-b867-eaa6b9a0b88b | 2053 | 22 | PAID-USERS,TRIAL-CZ | existing-shared-vps | active |
| ALANET-SE-1 | SE | 89.125.243.225 | eeddedb1-1144-4e37-93ec-584ea5f8aacf | 82623a5c-ee0f-4116-b9ff-a4b182f7c26e | 2053 | 22 | PAID-USERS | existing-shared-vps | active |
| ALANET-PL-1 | PL | 78.17.154.237 | 329e3229-b142-4d17-9b89-28c39337731e | ef704276-c89b-446c-84ca-e5a9a4a30aca | 2053 | 34852 | PAID-USERS | existing-shared-vps | active |
| ALANET-ES-1 | ES | 78.17.180.246 | 75ded50a-09b1-4efc-bc68-57a8f21fdd96 | 357bcce5-31b3-43cb-8228-3913ba26f22b | 2053 | 22 | PAID-USERS | existing-shared-vps | active |
| ALANET-LV-1 | LV | 194.1.134.145 | d52aad4e-4e49-4247-9a5f-1312fe40a512 | 32f75a50-ff6a-4c46-b43d-3f43098e158d | 2053 | 34852 | PAID-USERS | existing-shared-vps | active |

## Internal squads

| Name | UUID | Intended use | Accessible nodes |
| --- | --- | --- | --- |
| `Default-Squad` | `2190759e-13f9-4462-ab98-8c2e2ce15859` | Remnawave default, not used for plans | none |
| `PAID-USERS` | `54e2736b-cf3a-4922-90b3-c1ef3319fc4f` | Paid tariffs | Finland, Germany, Czechia, Sweden, Poland, Spain, Latvia |
| `TRIAL-CZ` | `0b67e804-8f40-4930-bd20-c7a03652bb77` | Trial tariff | Czechia only |

## Plans

| Slug | Name | Duration | Traffic | Devices | Squad |
| --- | --- | ---: | ---: | ---: | --- |
| `trial` | Пробный | 1 day | unlimited | 1 | `TRIAL-CZ` |
| `start` | Старт | 30 days | unlimited | 1 | `PAID-USERS` |
| `calm` | Спокойно | 90 days | unlimited | 1 | `PAID-USERS` |
| `year` | На год | 365 days | unlimited | 1 | `PAID-USERS` |

## Scheduled operations

- `alanet-healthcheck.timer`: every 5 minutes; validates domains, API, Telegram webhook, expected registry nodes, live Remnawave hosts, one subscription URL, listeners, resources and required containers.
- `alanet-worker-1`: retries failed provisioning every minute, reconciles payments and subscription lifecycle every five minutes, and sends the daily audit report at 06:00 UTC.
- `alanet-backup.timer`: daily at approximately 03:15 UTC with a randomized delay; retains seven days of archives.
- Docker JSON logs rotate daily at 20 MB, retain seven compressed generations. Health-check output and failures are available through `journalctl -u alanet-healthcheck.service`.
