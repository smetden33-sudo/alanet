# ALANET production inventory

Inventory checked on 2026-07-27. Credentials, tokens and private keys are intentionally excluded.

## Remnawave nodes

| Name | UUID | Address | Country | Status |
| --- | --- | --- | --- | --- |
| `ALANET-FIN-01` | `19de6a7c-e102-4a62-b153-8817ad26a310` | `172.18.0.1` | FI | connected |
| `ALANET-DE-1` | `5e1f02ec-6ed8-4717-a819-76e60f189a7e` | `132.243.228.206` | DE | connected |
| `ALANET-CZ-1` | `bc3c365e-5ecf-4950-a05e-b7e5d7350f21` | `141.133.172.38` | CZ | connected |

## Internal squads

| Name | UUID | Intended use | Accessible nodes |
| --- | --- | --- | --- |
| `Default-Squad` | `2190759e-13f9-4462-ab98-8c2e2ce15859` | Remnawave default, not used for plans | none |
| `PAID-USERS` | `54e2736b-cf3a-4922-90b3-c1ef3319fc4f` | Paid tariffs | Finland, Germany, Czechia |
| `TRIAL-CZ` | `0b67e804-8f40-4930-bd20-c7a03652bb77` | Trial tariff | Czechia only |

## Plans

| Slug | Name | Duration | Traffic | Devices | Squad |
| --- | --- | ---: | ---: | ---: | --- |
| `trial` | Пробный | 1 day | unlimited | 1 | `TRIAL-CZ` |
| `start` | Старт | 30 days | unlimited | 1 | `PAID-USERS` |
| `calm` | Спокойно | 90 days | unlimited | 1 | `PAID-USERS` |
| `year` | На год | 365 days | unlimited | 1 | `PAID-USERS` |

## Scheduled operations

- `alanet-healthcheck.timer`: every 5 minutes (more frequent than a daily check); validates domains, API, Telegram webhook, all three nodes, one subscription URL, listener 443 and all 10 containers.
- `alanet-backup.timer`: daily at approximately 03:15 UTC with a randomized delay; retains seven days of archives.
- Health-check output and failures are available through `journalctl -u alanet-healthcheck.service`.
