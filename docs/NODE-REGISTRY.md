# ALANET node registry

Единый источник правды по нодам: `infra/node-registry.json`.

Он содержит поля:

- `node_name`
- `country`
- `ip`
- `remnawave_node_uuid`
- `host_uuid`
- `public_port`
- `control_port`
- `squad`
- `provider`
- `status`

Использование:

- health-check читает активные `node_name` из registry и сверяет их с Remnawave `/api/nodes`;
- host-порты всё равно проверяются live из Remnawave `/api/hosts`;
- Remnawave sync сверяет registry с `/api/nodes` и `/api/hosts`, показывает drift и не выполняет опасные изменения без staging-проверки API-контракта;
- документация может генерировать таблицу командой `python infra/scripts/render-node-registry.py --format markdown`;
- Ansible inventory можно получить командой `python infra/scripts/render-node-registry.py --format ansible`;
- Terraform/Beszel/Remnawave sync используют этот файл как входной inventory.

Текущая таблица:

| node_name | country | ip | remnawave_node_uuid | host_uuid | public_port | control_port | squad | provider | status |
| --- | --- | --- | --- | --- | ---: | ---: | --- | --- | --- |
| ALANET-FIN-01 | FI | 78.17.54.252 | 19de6a7c-e102-4a62-b153-8817ad26a310 | 3d4e5059-d5bb-45ad-80ef-5c84d265ec9f | 8443 | 2222 | PAID-USERS | existing-vps | active |
| ALANET-DE-1 | DE | 132.243.228.206 | 5e1f02ec-6ed8-4717-a819-76e60f189a7e | 9dcf4fd6-bbb8-4f16-afde-5a5d3c177f36 | 2053 | 22 | PAID-USERS | existing-shared-vps | active |
| ALANET-CZ-1 | CZ | 141.133.172.38 | bc3c365e-5ecf-4950-a05e-b7e5d7350f21 | aa7e0f91-018f-4cda-b867-eaa6b9a0b88b | 2053 | 22 | PAID-USERS,TRIAL-CZ | existing-shared-vps | active |
| ALANET-SE-1 | SE | 89.125.243.225 | eeddedb1-1144-4e37-93ec-584ea5f8aacf | 82623a5c-ee0f-4116-b9ff-a4b182f7c26e | 2053 | 22 | PAID-USERS | existing-shared-vps | active |
| ALANET-PL-1 | PL | 78.17.154.237 | 329e3229-b142-4d17-9b89-28c39337731e | ef704276-c89b-446c-84ca-e5a9a4a30aca | 2053 | 34852 | PAID-USERS | existing-shared-vps | active |
| ALANET-ES-1 | ES | 78.17.180.246 | 75ded50a-09b1-4efc-bc68-57a8f21fdd96 | 357bcce5-31b3-43cb-8228-3913ba26f22b | 2053 | 22 | PAID-USERS | existing-shared-vps | active |
| ALANET-LV-1 | LV | 194.1.134.145 | d52aad4e-4e49-4247-9a5f-1312fe40a512 | 32f75a50-ff6a-4c46-b43d-3f43098e158d | 2053 | 34852 | PAID-USERS | existing-shared-vps | active |
| ALANET-RU-1 | RU | 80.78.245.199 | c795489f-a92d-4acd-ba13-6bc6143c37ad | 1fee4813-0980-4368-aab4-c14eef752acd | 2053 | 22 | PAID-USERS | existing-shared-vps | active |
| ALANET-RU-2 | RU | 195.19.20.123 | b0054f6f-ddd1-4dfd-9df0-734c8691873e | 90996263-99de-472b-a576-b2898461774f | 2053 | 22 | PAID-USERS | existing-shared-vps | active |
