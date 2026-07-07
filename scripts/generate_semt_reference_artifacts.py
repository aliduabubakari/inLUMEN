#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "backend"))

from deployment_artifacts import (  # noqa: E402
    build_argo_workflow_yaml,
    build_dockerfile_artifacts,
)


def reference_graph() -> dict:
    return {
        "nodes": [
            {
                "id": "reconcile",
                "data": {
                    "label": "Reconcile City",
                    "type": "action",
                    "definition_id": "semt.reconciliation",
                    "definition_version": 1,
                    "configuration_status": "valid",
                    "implementation": {
                        "kind": "semt",
                        "operation": "reconciliation",
                        "service_id": "wikidataOpenRefine",
                        "parameters": {
                            "column_name": "City",
                            "optional_columns": [],
                            "deduplicate": False,
                        },
                        "connection_ref": "default-semt",
                    },
                },
            },
            {
                "id": "extend",
                "data": {
                    "label": "Extend City",
                    "type": "action",
                    "definition_id": "semt.extension",
                    "definition_version": 1,
                    "configuration_status": "valid",
                    "implementation": {
                        "kind": "semt",
                        "operation": "extension",
                        "service_id": "wikidataPropertySPARQL",
                        "parameters": {
                            "column_name": "City",
                            "properties": ["P17", "P1082"],
                            "other_params": {},
                            "deduplicate": False,
                            "extra_key_columns": [],
                        },
                        "connection_ref": "default-semt",
                    },
                },
            },
        ],
        "edges": [{"source": "reconcile", "target": "extend"}],
    }


def write_runtime(output_dir: Path, runtime: dict) -> None:
    step_dir = output_dir / runtime["flow_id"]
    step_dir.mkdir(parents=True, exist_ok=True)
    for generated_file in runtime["files"]:
        (step_dir / generated_file["filename"]).write_text(
            generated_file["content"],
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate the deterministic SemT reference workflow."
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    output_dir = args.output.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    graph = reference_graph()
    artifacts = build_dockerfile_artifacts(graph)
    for runtime in artifacts["runtime_artifacts"]:
        write_runtime(output_dir, runtime)

    workflow_path = output_dir / "workflow.yaml"
    workflow_path.write_text(
        build_argo_workflow_yaml(graph, artifacts),
        encoding="utf-8",
    )
    (output_dir / "reference-graph.json").write_text(
        json.dumps(graph, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    metadata = {
        item["flow_id"]: {
            "image": item["image"],
            "configuration_hash": item["configuration_hash"],
            "dockerfile": item["dockerfile_filename"],
        }
        for item in artifacts["dockerfiles"]
    }
    (output_dir / "images.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"output": str(output_dir), "images": metadata}, sort_keys=True))


if __name__ == "__main__":
    main()
