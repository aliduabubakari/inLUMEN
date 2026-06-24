from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from node_definitions import get_node_definition_registry
from node_definitions.artifacts import configuration_hash
from wikifier.validation import validate_wikifier_implementation

from .base import GeneratedFile, GeneratedRuntimeArtifacts, wikifier_image_reference


GENERATOR_VERSION = "1"
DATA_CONTRACT_VERSION = "1"
TEMPLATE_DIR = Path(__file__).resolve().parent / "templates" / "wikifier"


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


class WikifierGenerator:
    name = "wikifier"
    version = GENERATOR_VERSION

    def __init__(self, template_dir: Path | str = TEMPLATE_DIR):
        self.template_dir = Path(template_dir)
        self.environment = Environment(
            loader=FileSystemLoader(str(self.template_dir)),
            undefined=StrictUndefined,
            autoescape=False,
            keep_trailing_newline=True,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def generate(
        self,
        step: dict[str, Any],
        graph: dict[str, Any] | None = None,
    ) -> GeneratedRuntimeArtifacts:
        del graph
        flow_id = str(step.get("flow_id") or "").strip()
        definition_id = str(step.get("definition_id") or "").strip()
        if not flow_id:
            raise ValueError("Wikifier generation requires flow_id.")

        definition = get_node_definition_registry().get(definition_id)
        if definition is None or definition.runtime.generator != self.name:
            raise ValueError(f"Unsupported Wikifier definition: {definition_id!r}.")

        try:
            definition_version = max(
                int(step.get("definition_version") or definition.version),
                1,
            )
        except (TypeError, ValueError):
            definition_version = definition.version

        implementation = step.get("implementation")
        if not isinstance(implementation, dict):
            implementation = {}
        validation = validate_wikifier_implementation(implementation)
        if validation["status"] != "valid":
            raise ValueError(
                "Wikifier node configuration is not valid: "
                + "; ".join(validation.get("errors") or [])
            )

        generated_configuration_hash = configuration_hash(
            definition_id=definition_id,
            definition_version=definition_version,
            implementation=implementation,
            generator=self.name,
            generator_version=self.version,
            contract_version=DATA_CONTRACT_VERSION,
        )
        image_reference = wikifier_image_reference(flow_id, generated_configuration_hash)
        entrypoint = ("python", "/app/main.py")
        dockerfile_name = f"Dockerfile.{flow_id}"
        build_context_files = [
            "main.py",
            "requirements.txt",
            "node-manifest.json",
        ]
        manifest = {
            "schema_version": 1,
            "flow_id": flow_id,
            "definition_id": definition_id,
            "definition_version": definition_version,
            "generator": self.name,
            "generator_version": self.version,
            "configuration_hash": generated_configuration_hash,
            "image": {
                "reference": image_reference,
                "immutable": True,
            },
            "entrypoint": list(entrypoint),
            "runtime": {
                "base_image": definition.runtime.base_image or "python:3.11-slim",
                "language": "python",
            },
            "data_contract": {
                "id": "inlumen.table",
                "version": DATA_CONTRACT_VERSION,
                "input_encodings": ["csv", "json"],
                "output_encodings": ["json"],
                "input_env": "INLUMEN_INPUT_PATH",
                "output_env": "INLUMEN_OUTPUT_PATH",
            },
            "connection_ref": str(implementation.get("connection_ref") or ""),
            "build": {
                "dockerfile": dockerfile_name,
                "context_files": build_context_files,
                "manifest_filename": "image-build-manifest.json",
            },
        }
        context = {
            "configuration_literal": repr(_canonical_json(implementation)),
            "contract_version": DATA_CONTRACT_VERSION,
            "flow_id_literal": repr(flow_id),
        }
        main_py = self.environment.get_template("main.py.j2").render(**context)
        requirements = self.environment.get_template("requirements.txt.j2").render()
        dockerfile = self.environment.get_template("Dockerfile.j2").render(
            base_image=definition.runtime.base_image or "python:3.11-slim",
            flow_id=flow_id,
        )
        manifest_json = json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n"
        image_build_manifest = {
            "schema_version": 1,
            "flow_id": flow_id,
            "configuration_hash": generated_configuration_hash,
            "dockerfile": dockerfile_name,
            "context_files": build_context_files,
            "image": image_reference,
        }
        image_build_manifest_json = json.dumps(
            image_build_manifest,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n"

        return GeneratedRuntimeArtifacts(
            flow_id=flow_id,
            definition_id=definition_id,
            definition_version=definition_version,
            generator=self.name,
            generator_version=self.version,
            configuration_hash=generated_configuration_hash,
            image_reference=image_reference,
            entrypoint=entrypoint,
            files=(
                GeneratedFile("main.py", main_py, "text/x-python"),
                GeneratedFile("requirements.txt", requirements, "text/plain"),
                GeneratedFile(dockerfile_name, dockerfile, "text/plain"),
                GeneratedFile("node-manifest.json", manifest_json, "application/json"),
                GeneratedFile(
                    "image-build-manifest.json",
                    image_build_manifest_json,
                    "application/json",
                ),
            ),
            manifest=manifest,
        )
