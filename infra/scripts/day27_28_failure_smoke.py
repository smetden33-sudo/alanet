#!/usr/bin/env python3
"""ALANET Day 27-28 safe failure smoke runner.

Default mode is safe for local/CI runs:
- runs non-mutating backend unit checks;
- validates that failure-test documentation exists;
- validates that critical rate-limited endpoints remain configured.

Use --live-readonly to add public HTTP GET checks. This still does not mutate
production state and does not stop services, create payments or revoke users.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import urllib.error
import urllib.request


ROOT = pathlib.Path(__file__).resolve().parents[2]


def run_command(args: list[str], *, cwd: pathlib.Path) -> tuple[bool, str]:
    env = None
    if args and pathlib.Path(args[0]).name.startswith("python"):
        env = dict(os.environ)
        current = env.get("PYTHONPATH", "")
        backend_path = str(ROOT / "backend")
        env["PYTHONPATH"] = backend_path if not current else backend_path + os.pathsep + current
    completed = subprocess.run(args, cwd=cwd, text=True, capture_output=True, env=env)
    output = (completed.stdout + completed.stderr).strip()
    return completed.returncode == 0, output


def run_backend_unit_tests() -> tuple[bool, str]:
    tests = [
        "backend.tests.test_payment_metadata",
    ]
    ok, output = run_command([sys.executable, "-m", "unittest", *tests], cwd=ROOT)
    if not ok:
        if "ModuleNotFoundError" in output and "sqlalchemy" in output:
            return True, "SKIP: backend dependencies are not installed in this environment; run after `pip install -r backend/requirements.txt` in CI/WSL/prod."
        return False, output

    expiry_path = ROOT / "backend" / "tests" / "test_expiry.py"
    spec = importlib.util.spec_from_file_location("test_expiry", expiry_path)
    if spec is None or spec.loader is None:
        return False, f"cannot load {expiry_path}"
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(ROOT / "backend"))
    try:
        spec.loader.exec_module(module)
        module.test_extends_active_subscription_from_current_expiry()
        module.test_extends_expired_subscription_from_now()
    finally:
        sys.path = [item for item in sys.path if item != str(ROOT / "backend")]
    return True, output or "backend unit checks passed"


def validate_docs() -> tuple[bool, str]:
    required = [
        ROOT / "docs" / "FAILURE-TEST-MATRIX.md",
        ROOT / "docs" / "ROADMAP-30-DAYS.md",
        ROOT / "docs" / "ROADMAP-30-DAYS-SHORT.md",
    ]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]
    if missing:
        return False, "missing docs: " + ", ".join(missing)
    return True, "failure-test docs present"


def validate_rate_limits() -> tuple[bool, str]:
    main_py = (ROOT / "backend" / "app" / "main.py").read_text(encoding="utf-8")
    required_paths = [
        "/api/v1/checkout",
        "/api/v1/me/checkout",
        "/api/v1/auth/telegram/exchange",
        "/webhooks/yookassa",
        "/webhooks/telegram",
    ]
    missing = [path for path in required_paths if path not in main_py]
    if missing:
        return False, "missing rate-limit paths: " + ", ".join(missing)
    return True, "critical rate-limit paths configured"


def live_get(url: str, expected: int) -> tuple[bool, str]:
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "alanet-day27-28-smoke/1.0"})
        with urllib.request.urlopen(request, timeout=15) as response:
            status = response.status
    except urllib.error.HTTPError as exc:
        status = exc.code
    except Exception as exc:  # noqa: BLE001 - CLI diagnostic
        return False, f"{url}: {type(exc).__name__}: {exc}"
    if status != expected:
        return False, f"{url}: expected {expected}, got {status}"
    return True, f"{url}: {status}"


def run_live_readonly_checks() -> tuple[bool, str]:
    checks = [
        ("https://alanet.ru", 200),
        ("https://account.alanet.ru", 200),
        ("https://api.alanet.ru/health", 200),
        ("https://panel.alanet.ru", 200),
        ("https://sub.alanet.ru", 404),
    ]
    results: list[dict[str, object]] = []
    ok = True
    for url, expected in checks:
        passed, message = live_get(url, expected)
        ok = ok and passed
        results.append({"check": url, "expected": expected, "passed": passed, "message": message})
    return ok, json.dumps(results, ensure_ascii=False, indent=2)


def main() -> int:
    parser = argparse.ArgumentParser(description="ALANET Day 27-28 safe failure smoke runner")
    parser.add_argument("--live-readonly", action="store_true", help="also run public read-only HTTP checks")
    args = parser.parse_args()

    checks: list[tuple[str, tuple[bool, str]]] = [
        ("backend_unit", run_backend_unit_tests()),
        ("docs", validate_docs()),
        ("rate_limits", validate_rate_limits()),
    ]
    if args.live_readonly:
        checks.append(("live_readonly_http", run_live_readonly_checks()))

    failed = False
    for name, (ok, output) in checks:
        status = "OK" if ok else "FAIL"
        print(f"[{status}] {name}")
        if output:
            print(output)
        failed = failed or not ok

    if failed:
        print("ALANET Day 27-28 smoke result: FAIL")
        return 1
    print("ALANET Day 27-28 smoke result: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
