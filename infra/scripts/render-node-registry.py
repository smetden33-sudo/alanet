#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


def load_registry(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["nodes"]


def render_markdown(nodes: list[dict]) -> str:
    lines = [
        "| node_name | country | ip | remnawave_node_uuid | host_uuid | public_port | control_port | squad | provider | status |",
        "| --- | --- | --- | --- | --- | ---: | ---: | --- | --- | --- |",
    ]
    for node in nodes:
        lines.append(
            "| {node_name} | {country} | {ip} | {remnawave_node_uuid} | {host_uuid} | {public_port} | {control_port} | {squad} | {provider} | {status} |".format(**node)
        )
    return "\n".join(lines)


def render_ansible(nodes: list[dict]) -> str:
    lines = ["[vpn_nodes]"]
    for node in nodes:
        if node["status"] != "active":
            continue
        row = {**node, "shared_vps": str(node["shared_vps"]).lower()}
        lines.append(
            "{node_name} ansible_host={ip} ansible_port={control_port} country={country} public_port={public_port} remnawave_node_uuid={remnawave_node_uuid} host_uuid={host_uuid} shared_vps={shared_vps}".format(
                **row
            )
        )
    lines.extend(["", "[vpn_nodes:vars]", "ansible_user=root"])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Render ALANET node registry for docs and automation.")
    parser.add_argument("--registry", default="infra/node-registry.json")
    parser.add_argument("--format", choices=["markdown", "ansible"], default="markdown")
    args = parser.parse_args()
    nodes = load_registry(Path(args.registry))
    if args.format == "markdown":
        print(render_markdown(nodes))
    else:
        print(render_ansible(nodes))


if __name__ == "__main__":
    main()
