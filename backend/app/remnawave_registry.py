from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DriftItem:
    severity: str
    kind: str
    name: str
    message: str
    safe_to_apply: bool = False


def load_node_registry(path: str | Path = "/opt/alanet/infra/node-registry.json") -> dict[str, Any]:
    registry_path = Path(path)
    return json.loads(registry_path.read_text(encoding="utf-8"))


def _node_id(node: dict[str, Any]) -> str:
    return str(node.get("uuid") or node.get("id") or "")


def _host_id(host: dict[str, Any]) -> str:
    return str(host.get("uuid") or host.get("id") or "")


def _host_node_ids(host: dict[str, Any]) -> set[str]:
    raw_nodes = host.get("nodes") or []
    if not isinstance(raw_nodes, list):
        return set()
    result: set[str] = set()
    for item in raw_nodes:
        if isinstance(item, str):
            result.add(item)
        elif isinstance(item, dict):
            value = item.get("uuid") or item.get("id")
            if value is not None:
                result.add(str(value))
    return result


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _display_name_key(value: Any) -> str:
    return "".join(_normalize_text(value).split()).casefold()


def _normalize_port(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _registry_nodes(registry: dict[str, Any], *, include_inactive: bool = True) -> list[dict[str, Any]]:
    nodes = registry.get("nodes") or []
    if include_inactive:
        return list(nodes)
    return [node for node in nodes if node.get("status") == "active"]


def compare_registry_to_remnawave(
    registry: dict[str, Any],
    remnawave_nodes: list[dict[str, Any]],
    remnawave_hosts: list[dict[str, Any]],
) -> list[DriftItem]:
    """Compare ALANET node registry with Remnawave nodes and hosts.

    The function is intentionally read-only. Mutating Remnawave hosts/nodes is
    operationally risky until the exact API contract is pinned and covered by
    staging tests.
    """

    drift: list[DriftItem] = []
    active_registry_nodes = _registry_nodes(registry, include_inactive=False)
    all_registry_nodes = _registry_nodes(registry)

    remote_nodes_by_uuid = {_node_id(node): node for node in remnawave_nodes if _node_id(node)}
    remote_nodes_by_name = {_normalize_text(node.get("name")): node for node in remnawave_nodes if node.get("name")}
    remote_hosts_by_uuid = {_host_id(host): host for host in remnawave_hosts if _host_id(host)}

    expected_node_uuids = {str(node.get("remnawave_node_uuid")) for node in active_registry_nodes if node.get("remnawave_node_uuid")}
    expected_node_names = {_normalize_text(node.get("node_name")) for node in active_registry_nodes if node.get("node_name")}
    expected_host_uuids = {str(node.get("host_uuid")) for node in active_registry_nodes if node.get("host_uuid")}

    for entry in active_registry_nodes:
        node_name = _normalize_text(entry.get("node_name"))
        node_uuid = _normalize_text(entry.get("remnawave_node_uuid"))
        host_uuid = _normalize_text(entry.get("host_uuid"))
        expected_country = _normalize_text(entry.get("country")).upper()
        expected_ip = _normalize_text(entry.get("ip"))
        expected_port = _normalize_port(entry.get("public_port"))
        expected_host_name = _normalize_text(entry.get("host_name"))

        remote_node = remote_nodes_by_uuid.get(node_uuid) or remote_nodes_by_name.get(node_name)
        if not remote_node:
            drift.append(DriftItem("critical", "missing_node", node_name, f"Registry node {node_name} ({node_uuid}) is missing in Remnawave."))
        else:
            actual_uuid = _node_id(remote_node)
            actual_name = _normalize_text(remote_node.get("name"))
            actual_country = _normalize_text(remote_node.get("countryCode")).upper()
            if node_uuid and actual_uuid and actual_uuid != node_uuid:
                drift.append(DriftItem("critical", "node_uuid_mismatch", node_name, f"{node_name}: registry UUID {node_uuid}, Remnawave UUID {actual_uuid}."))
            if actual_name and node_name and actual_name != node_name:
                drift.append(DriftItem("warning", "node_name_mismatch", node_name, f"{node_name}: Remnawave name is {actual_name}."))
            if expected_country and actual_country and actual_country != expected_country:
                drift.append(DriftItem("warning", "node_country_mismatch", node_name, f"{node_name}: registry country {expected_country}, Remnawave country {actual_country}."))
            if remote_node.get("isConnected") is False:
                drift.append(DriftItem("warning", "node_disconnected", node_name, f"{node_name}: node is disconnected in Remnawave."))

        remote_host = remote_hosts_by_uuid.get(host_uuid)
        if not remote_host:
            drift.append(DriftItem("critical", "missing_host", node_name, f"Registry host {expected_host_name or host_uuid} ({host_uuid}) is missing in Remnawave."))
            continue

        actual_ip = _normalize_text(remote_host.get("address"))
        actual_port = _normalize_port(remote_host.get("port"))
        actual_name = _normalize_text(remote_host.get("remark") or remote_host.get("name"))
        if remote_host.get("isDisabled") is True:
            drift.append(DriftItem("critical", "host_disabled", node_name, f"{node_name}: host {actual_name or host_uuid} is disabled in Remnawave."))
        if expected_ip and actual_ip and actual_ip != expected_ip:
            drift.append(DriftItem("critical", "host_ip_mismatch", node_name, f"{node_name}: registry host IP {expected_ip}, Remnawave IP {actual_ip}."))
        if expected_port is not None and actual_port is not None and actual_port != expected_port:
            drift.append(DriftItem("critical", "host_port_mismatch", node_name, f"{node_name}: registry port {expected_port}, Remnawave port {actual_port}."))
        if expected_host_name and actual_name and _display_name_key(actual_name) != _display_name_key(expected_host_name):
            drift.append(DriftItem("warning", "host_name_mismatch", node_name, f"{node_name}: registry host name {expected_host_name}, Remnawave host name {actual_name}."))
        if node_uuid and node_uuid not in _host_node_ids(remote_host):
            drift.append(DriftItem("critical", "host_node_binding_mismatch", node_name, f"{node_name}: host {actual_name or host_uuid} is not bound to registry node UUID {node_uuid}."))

    inactive_uuids = {
        str(node.get("remnawave_node_uuid"))
        for node in all_registry_nodes
        if node.get("status") != "active" and node.get("remnawave_node_uuid")
    }
    for remote_node in remnawave_nodes:
        remote_uuid = _node_id(remote_node)
        remote_name = _normalize_text(remote_node.get("name"))
        if remote_uuid in inactive_uuids:
            drift.append(DriftItem("warning", "inactive_node_present", remote_name, f"{remote_name}: registry status is not active, but node still exists in Remnawave."))
        elif remote_uuid and remote_uuid not in expected_node_uuids and remote_name not in expected_node_names:
            drift.append(DriftItem("warning", "extra_node", remote_name or remote_uuid, f"Remnawave has node not present as active in registry: {remote_name or remote_uuid}."))

    for remote_host in remnawave_hosts:
        remote_uuid = _host_id(remote_host)
        remote_name = _normalize_text(remote_host.get("remark") or remote_host.get("name") or remote_host.get("address"))
        if remote_uuid and remote_uuid not in expected_host_uuids and remote_host.get("isDisabled") is not True:
            drift.append(DriftItem("warning", "extra_host", remote_name or remote_uuid, f"Remnawave has enabled host not present as active in registry: {remote_name or remote_uuid}."))

    return drift


def summarize_drift(drift: list[DriftItem], *, registry_count: int, nodes_count: int, hosts_count: int) -> list[str]:
    critical = sum(1 for item in drift if item.severity == "critical")
    warnings = sum(1 for item in drift if item.severity == "warning")
    safe = sum(1 for item in drift if item.safe_to_apply)
    lines = [
        "Remnawave registry sync",
        f"Registry active nodes: {registry_count}",
        f"Remnawave nodes: {nodes_count}",
        f"Remnawave hosts: {hosts_count}",
        f"Drift: critical {critical}, warnings {warnings}, safe auto-fixes {safe}",
    ]
    if not drift:
        lines.append("Status: ok — registry and Remnawave match.")
        return lines
    lines.append("Status: report-only — Remnawave changes are blocked until API contract is pinned in staging.")
    for item in drift[:40]:
        icon = "⛔" if item.severity == "critical" else "⚠️"
        lines.append(f"{icon} {item.kind}: {item.message}")
    if len(drift) > 40:
        lines.append(f"...and {len(drift) - 40} more drift items.")
    return lines
