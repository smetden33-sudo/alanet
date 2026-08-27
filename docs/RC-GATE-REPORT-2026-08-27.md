# ALANET — RC Gate Report

Дата: 2026-08-27

## GitHub Actions

| Workflow | SHA | Status | Conclusion | Link |
|---|---|---|---|---|
| Release readiness checks | `bd63b3f723222a581d1031c9470f7ad3cc18d25a` | completed | success | https://github.com/smetden33-sudo/alanet/actions/runs/33111146723 |

Job:

| Job | Status | Conclusion | Started | Completed |
|---|---|---|---|---|
| readiness | completed | success | 2026-08-27 19:59:55 UTC | 2026-08-27 20:00:11 UTC |

Production deploy workflow did not run for this docs/readiness-only SHA, which is expected.

## RC gate

Telegram admin checks to run:

```text
/incident
/backup
/disk
/ports
/finance
```

Expected gate result:

| Check | Expected | Status |
|---|---|---|
| `/incident` | `ok` or controlled warning | Pending admin run |
| `/backup` | fresh backup + restore-test visible | Pending admin run |
| `/disk` | prod disk below critical threshold | Pending admin run |
| `/ports` | production host-ports reachable | Pending admin run |
| `/finance` | no payment/subscription drift | Pending admin run |

## Notes

Direct SSH RC gate from the local workstation was not available with the local keys checked in this session. Use Telegram admin commands first; if deeper host inspection is required, use the configured production deploy key/port from the operations environment.

