"""Copy current FastAPI OpenAPI into the V1 proposal without publishing planned routes."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]
ACTUAL = ROOT / "contracts" / "openapi.json"
PROPOSAL = Path(__file__).with_name("openapi.yaml")
PLANNED = Path(__file__).with_name("planned.yaml")
METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}


def build() -> dict:
    raw = ACTUAL.read_bytes()
    actual = json.loads(raw)
    planned = yaml.safe_load(PLANNED.read_text(encoding="utf-8")) if PLANNED.exists() else {}
    paths = copy.deepcopy(actual["paths"])
    for path in paths.values():
        for method, operation in path.items():
            if method in METHODS:
                operation["x-serviceos-status"] = "implemented"

    for name, path in planned.get("paths", {}).items():
        for method, operation in path.items():
            if method not in METHODS:
                raise ValueError(f"Unsupported planned path entry: {method} {name}")
            if operation.get("x-serviceos-status") != "planned":
                raise ValueError(f"Planned operation must have planned status: {method.upper()} {name}")
            if method in paths.get(name, {}):
                raise ValueError(f"Planned operation now exists in actual OpenAPI: {method.upper()} {name}")
            paths.setdefault(name, {})[method] = operation

    components = copy.deepcopy(actual["components"])
    for name, schema in planned.get("components", {}).get("schemas", {}).items():
        if not name.startswith("Proposed"):
            raise ValueError(f"Planned schema must use Proposed prefix: {name}")
        if name in components["schemas"]:
            raise ValueError(f"Planned schema now exists in actual OpenAPI: {name}")
        components["schemas"][name] = schema

    document = {
        "openapi": actual["openapi"],
        "info": {
            **actual["info"],
            "description": "V1 interface proposal. Planned operations are design only and are not callable.",
        },
        "x-serviceos-proposal-status": "draft",
        "x-serviceos-implemented-sha256": hashlib.sha256(raw).hexdigest(),
        "x-serviceos-planned-source": "contracts/proposed/v1/planned.yaml",
        "paths": paths,
        "components": components,
    }
    operation_ids = set()
    for name, path in document["paths"].items():
        for method, operation in path.items():
            if method not in METHODS:
                continue
            operation_id = operation["operationId"]
            if operation_id in operation_ids:
                raise ValueError(f"Duplicate operationId: {operation_id}")
            operation_ids.add(operation_id)
            if operation.get("x-serviceos-status") not in {"implemented", "planned"}:
                raise ValueError(f"Missing status: {method.upper()} {name}")

    def check_refs(node):
        if isinstance(node, dict):
            if "$ref" in node:
                ref = node["$ref"]
                prefix = "#/components/schemas/"
                if ref.startswith(prefix) and ref[len(prefix):] not in components["schemas"]:
                    raise ValueError(f"Unresolved schema reference: {ref}")
            for value in node.values():
                check_refs(value)
        elif isinstance(node, list):
            for value in node:
                check_refs(value)

    check_refs(document)
    return document


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Fail if the proposal differs from its source files")
    args = parser.parse_args()
    document = yaml.safe_dump(build(), allow_unicode=True, sort_keys=False, width=110)
    if args.check:
        if not PROPOSAL.exists() or PROPOSAL.read_text(encoding="utf-8") != document:
            raise SystemExit("Proposal drift detected; run sync_implemented.py and review the diff.")
        print("V1 proposal matches actual OpenAPI and planned additions.")
    else:
        PROPOSAL.write_text(document, encoding="utf-8")
        print(f"Wrote {PROPOSAL}")


if __name__ == "__main__":
    main()
