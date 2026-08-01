#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.remnawave_registry import compare_registry_to_remnawave, load_node_registry, summarize_drift  # noqa: E402


def read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        values[key] = value.strip().strip('"').strip("'")
    return values


def remnawave_get(base_url: str, token: str, path: str) -> list[dict]:
    request = urllib.request.Request(f"{base_url.rstrip('/')}{path}", headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(request, timeout=20) as response:
        body = json.loads(response.read().decode("utf-8"))
    payload = body.get("response", body)
    if isinstance(payload, list):
        return payload
    key = "nodes" if path.endswith("/nodes") else "hosts"
    return payload.get(key, [])


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare ALANET node registry with Remnawave nodes and hosts.")
    parser.add_argument("--registry", default=str(REPO_ROOT / "infra" / "node-registry.json"))
    parser.add_argument("--env-file", default=str(REPO_ROOT / "deploy" / ".env"))
    parser.add_argument("--base-url", default=os.getenv("REMNAWAVE_BASE_URL"))
    parser.add_argument("--token", default=os.getenv("REMNAWAVE_TOKEN"))
    parser.add_argument("--json", action="store_true", help="Print machine-readable drift report.")
    parser.add_argument("--apply", action="store_true", help="Reserved for future staging-approved safe changes.")
    args = parser.parse_args()

    env_values = read_env_file(Path(args.env_file))
    base_url = args.base_url or env_values.get("REMNAWAVE_BASE_URL") or "https://panel.alanet.ru"
    token = args.token or env_values.get("REMNAWAVE_TOKEN")
    if not token:
        print("REMNAWAVE_TOKEN is required via env or --env-file.", file=sys.stderr)
        return 2

    registry = load_node_registry(args.registry)
    nodes = remnawave_get(base_url, token, "/api/nodes")
    hosts = remnawave_get(base_url, token, "/api/hosts")
    drift = compare_registry_to_remnawave(registry, nodes, hosts)
    active_count = sum(1 for node in registry.get("nodes", []) if node.get("status") == "active")

    if args.apply and drift:
        unsafe = [item for item in drift if not item.safe_to_apply]
        if unsafe:
            print("Apply blocked: drift contains report-only items. Run this in staging after pinning Remnawave write API contract.", file=sys.stderr)
            args.apply = False

    if args.json:
        print(json.dumps({
            "registry_active_nodes": active_count,
            "remnawave_nodes": len(nodes),
            "remnawave_hosts": len(hosts),
            "drift": [item.__dict__ for item in drift],
            "apply": bool(args.apply),
        }, ensure_ascii=False, indent=2))
    else:
        print("\n".join(summarize_drift(drift, registry_count=active_count, nodes_count=len(nodes), hosts_count=len(hosts))))

    if any(item.severity == "critical" for item in drift):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
