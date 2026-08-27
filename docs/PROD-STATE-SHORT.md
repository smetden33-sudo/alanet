# ALANET PROD STATE — short

1. Prod healthy.
2. Web/API/Worker/Caddy/Remnawave/RemnaNode/Beszel are up.
3. Remnawave nodes: 13/13 connected.
4. Drift registry ↔ Remnawave: 0 critical, 0 warnings.
5. Current deploy SHA: `08f4a7771de8f048f9f367e64c1f06ea603e0af2`.
6. CI builds and deploys automatically from GitHub Actions.
7. Prod backup uploads to S3 Timeweb.
8. Node backups upload to S3 Timeweb and restore-test is enabled.
9. Beszel + ALANET health-check are active and green.
10. Main risks: shared VPS caution, older SSH ports on some nodes, staging on the same host.
