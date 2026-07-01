from __future__ import annotations

from collections import defaultdict
from typing import Any, Sequence

from node_definitions.artifacts import configuration_hash

from .catalog import get_semt_catalog_service


SEMT_DEFINITION_IDS = {
    "semt.setup",
    "semt.modification",
    "semt.reconciliation",
    "semt.extension",
    "semt.export",
}
SEMT_INPUT_DEFINITION_ID = "core.input-data"
SEMT_NON_TABLE_DEFINITION_IDS = {"semt.setup"}
SEMT_OUTPUT_DEFINITION_IDS = {"semt.export"}
GENERATOR_VERSION = "3"
CONTRACT_VERSION = "1"


class SemTGraphValidationError(ValueError):
    def __init__(self, errors: Sequence[str]):
        self.errors = list(errors)
        super().__init__("; ".join(self.errors))


def is_semt_step(step: dict[str, Any]) -> bool:
    return str(step.get("definition_id") or "").startswith("semt.")


def _semt_settings_parameters(graph: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(graph, dict):
        return {}
    settings = graph.get("settings")
    if not isinstance(settings, dict):
        return {}
    semt = settings.get("semt")
    if not isinstance(semt, dict):
        return {}
    parameters: dict[str, Any] = {}
    api_base_url = str(
        semt.get("api_base_url") or semt.get("base_url") or semt.get("api_url") or ""
    ).strip().rstrip("/")
    if api_base_url.endswith("/api"):
        api_base_url = api_base_url[:-4].rstrip("/")
    if api_base_url:
        parameters["api_base_url"] = api_base_url
    for key in ("username", "password", "token"):
        value = semt.get(key)
        if value not in (None, ""):
            parameters[key] = value
    return parameters


def _semt_table_load_parameters(steps: Sequence[dict[str, Any]]) -> dict[str, Any]:
    for step in steps:
        if str(step.get("definition_id") or "") != SEMT_INPUT_DEFINITION_ID:
            continue
        implementation = step.get("implementation")
        if not isinstance(implementation, dict):
            continue
        if str(implementation.get("kind") or "") != "semt-input":
            continue
        parameters = implementation.get("parameters")
        if not isinstance(parameters, dict) or parameters.get("semt_table_load") is not True:
            continue
        result: dict[str, Any] = {"semt_table_load": True}
        for key in ("dataset_id", "table_name", "csv_file"):
            value = parameters.get(key)
            if value not in (None, ""):
                result[key] = value
        return result
    return {}


def _implementation_with_graph_context(
    implementation: dict[str, Any],
    steps: Sequence[dict[str, Any]],
    graph: dict[str, Any] | None,
) -> dict[str, Any]:
    global_parameters = _semt_settings_parameters(graph)
    table_load_parameters = _semt_table_load_parameters(steps)
    if not global_parameters and not table_load_parameters:
        return implementation
    current_parameters = implementation.get("parameters")
    if not isinstance(current_parameters, dict):
        current_parameters = {}
    return {
        **implementation,
        "parameters": {
            **global_parameters,
            **table_load_parameters,
            **current_parameters,
        },
    }


def _is_semt_input_step(step: dict[str, Any]) -> bool:
    return str(step.get("definition_id") or "") == SEMT_INPUT_DEFINITION_ID


def _is_semt_table_step(step: dict[str, Any]) -> bool:
    """SemT steps that participate in the table processing chain."""
    definition_id = str(step.get("definition_id") or "")
    return definition_id in SEMT_DEFINITION_IDS and definition_id not in SEMT_NON_TABLE_DEFINITION_IDS


def _implementation_parameters(step: dict[str, Any]) -> dict[str, Any]:
    implementation = step.get("implementation")
    if not isinstance(implementation, dict):
        return {}
    parameters = implementation.get("parameters")
    return parameters if isinstance(parameters, dict) else {}


def _upstream_reconciliations_for_column(
    flow_id: str,
    column_name: Any,
    incoming: dict[str, list[str]],
    steps_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    """Return upstream reconciliations for the requested target column.

    Extension operations can depend on reconciliation metadata produced earlier in
    the table chain, even when another SemT table operation sits between the
    reconciliation and extension. Keep the check column-aware so unrelated
    upstream reconciliations do not accidentally satisfy the contract.
    """
    target_column = str(column_name or "")
    if not target_column:
        return []

    matches: list[str] = []
    stack = list(incoming.get(flow_id) or [])
    visited: set[str] = set()
    while stack:
        parent_id = stack.pop()
        if parent_id in visited:
            continue
        visited.add(parent_id)
        parent = steps_by_id.get(parent_id)
        if not parent:
            continue
        parent_definition_id = str(parent.get("definition_id") or "")
        parent_column = str(_implementation_parameters(parent).get("column_name") or "")
        if (
            parent_definition_id == "semt.reconciliation"
            and parent_column == target_column
        ):
            matches.append(parent_id)
        stack.extend(incoming.get(parent_id) or [])
    return matches


def get_semt_ingress_artifact(
    steps: Sequence[dict[str, Any]],
    edges: Sequence[dict[str, Any]],
) -> dict[str, str] | None:
    semt_ids = {
        str(step.get("flow_id") or "")
        for step in steps
        if is_semt_step(step)
    }
    ingress_steps = [
        step
        for step in steps
        if _is_semt_input_step(step)
        and any(
            str(edge.get("source") or "") == str(step.get("flow_id") or "")
            and str(edge.get("target") or "") in semt_ids
            for edge in edges
        )
    ]
    if len(ingress_steps) != 1:
        return None

    files = ingress_steps[0].get("files") or []
    if len(files) != 1 or not isinstance(files[0], dict):
        return None
    file_ref = files[0]
    bucket = str(file_ref.get("snapshot_bucket") or file_ref.get("bucket") or "")
    key = str(file_ref.get("snapshot_object") or file_ref.get("filename") or "")
    if not bucket or not key:
        return None
    return {"bucket": bucket, "key": key}


def validate_semt_pipeline(
    steps: Sequence[dict[str, Any]],
    edges: Sequence[dict[str, Any]],
    dockerfiles_by_step: dict[str, dict[str, Any]],
    graph: dict[str, Any] | None = None,
) -> None:
    semt_steps = [step for step in steps if is_semt_step(step)]
    if not semt_steps:
        return

    errors: list[str] = []
    table_semt_steps = [step for step in semt_steps if _is_semt_table_step(step)]
    input_steps = [
        step
        for step in steps
        if _is_semt_input_step(step)
    ]
    allowed_non_table_ids = {SEMT_INPUT_DEFINITION_ID} | SEMT_NON_TABLE_DEFINITION_IDS
    unsupported_steps = [
        step
        for step in steps
        if not is_semt_step(step)
        and str(step.get("definition_id") or "") not in allowed_non_table_ids
    ]
    if unsupported_steps:
        errors.append(
            "Mixed SemT and non-SemT runtime nodes are not supported by the current table contract."
        )
    if len(input_steps) > 1:
        errors.append("A SemT workflow supports exactly one Input Data node.")

    steps_by_id = {str(step["flow_id"]): step for step in table_semt_steps}
    incoming: dict[str, list[str]] = defaultdict(list)
    outgoing: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if source in steps_by_id and target in steps_by_id:
            outgoing[source].append(target)
            incoming[target].append(source)

    # Only require edges when multiple table-processing nodes exist.
    # A single table node chained from a non-table setup node is fine.
    if len(table_semt_steps) > 1 and not any(incoming.values()):
        errors.append("SemT nodes must be connected by explicit graph edges.")

    roots = []
    leaves = []
    for flow_id in steps_by_id:
        if len(incoming[flow_id]) > 1:
            errors.append(
                f"SemT step {flow_id!r} has multiple table inputs; fan-in is deferred."
            )
        if len(outgoing[flow_id]) > 1:
            errors.append(
                f"SemT step {flow_id!r} has multiple table outputs; fan-out is deferred."
            )
        if not incoming[flow_id]:
            roots.append(flow_id)
        if not outgoing[flow_id]:
            leaves.append(flow_id)

    if table_semt_steps:
        if len(roots) != 1:
            errors.append("A SemT workflow must have exactly one CSV ingress node.")
        if len(leaves) != 1:
            errors.append("A SemT workflow must have exactly one JSON egress node.")

    if input_steps:
        input_step = input_steps[0]
        input_id = str(input_step.get("flow_id") or "")
        input_parents = [
            str(edge.get("source") or "")
            for edge in edges
            if str(edge.get("target") or "") == input_id
        ]
        input_targets = [
            str(edge.get("target") or "")
            for edge in edges
            if str(edge.get("source") or "") == input_id
        ]
        if input_parents:
            errors.append("The SemT Input Data node cannot have an upstream node.")

        # The input may connect to a non-table SemT node (setup) which
        # then chains to the root of the table-processing steps.
        def _reaches_root(target_id: str, visited: set | None = None) -> bool:
            if target_id in roots:
                return True
            if visited is None:
                visited = set()
            if target_id in visited:
                return False
            visited.add(target_id)
            # Follow outgoing edges through non-table nodes
            for edge in edges:
                src = str(edge.get("source") or "")
                tgt = str(edge.get("target") or "")
                if src == target_id and tgt not in visited:
                    if _reaches_root(tgt, visited):
                        return True
            return False

        if len(input_targets) != 1 or not _reaches_root(input_targets[0]):
            errors.append(
                "The SemT Input Data node must connect to the first SemT "
                "node (directly or through a SemT Setup node)."
            )

        files = input_step.get("files") or []
        if len(files) != 1:
            errors.append(
                "The SemT Input Data node must contain exactly one uploaded CSV file "
                "so Argo can mount it as /data/input.csv."
            )
        elif not isinstance(files[0], dict):
            errors.append("The SemT Input Data file metadata is invalid.")
        else:
            filename = str(
                files[0].get("snapshot_object")
                or files[0].get("filename")
                or ""
            )
            bucket = str(
                files[0].get("snapshot_bucket")
                or files[0].get("bucket")
                or ""
            )
            if not filename.lower().endswith(".csv"):
                errors.append("The SemT Input Data file must use CSV encoding.")
            if not bucket:
                errors.append("The SemT Input Data file is missing its MinIO bucket.")

    catalog = get_semt_catalog_service()
    for flow_id, step in steps_by_id.items():
        definition_id = str(step.get("definition_id") or "")
        implementation = step.get("implementation")
        implementation = implementation if isinstance(implementation, dict) else {}
        implementation = _implementation_with_graph_context(
            implementation,
            steps,
            graph,
        )

        if definition_id not in SEMT_DEFINITION_IDS:
            errors.append(
                f"SemT step {flow_id!r} uses unsupported definition {definition_id!r}."
            )
            continue

        validation = catalog.validate_implementation(definition_id, implementation)
        if validation.get("status") != "valid":
            detail = "; ".join(validation.get("errors") or ["invalid configuration"])
            errors.append(f"SemT step {flow_id!r} is not configured: {detail}")

        configuration_status = str(step.get("configuration_status") or "").lower()
        if configuration_status and configuration_status != "valid":
            errors.append(
                f"SemT step {flow_id!r} has configuration status "
                f"{configuration_status!r}; regenerate it before deployment."
            )

        generated_artifact = step.get("generated_artifact")
        if isinstance(generated_artifact, dict):
            artifact_status = str(generated_artifact.get("status") or "").lower()
            if artifact_status == "stale":
                errors.append(
                    f"SemT step {flow_id!r} has stale generated runtime artifacts."
                )

        try:
            definition_version = max(int(step.get("definition_version") or 1), 1)
        except (TypeError, ValueError):
            definition_version = 1
        expected_hash = configuration_hash(
            definition_id=definition_id,
            definition_version=definition_version,
            implementation=implementation,
            generator="semt",
            generator_version=GENERATOR_VERSION,
            contract_version=CONTRACT_VERSION,
        )
        dockerfile = dockerfiles_by_step.get(flow_id) or {}
        actual_hash = str(dockerfile.get("configuration_hash") or "")
        image = str(dockerfile.get("image") or "")
        if not dockerfile:
            errors.append(f"SemT step {flow_id!r} is missing generated runtime metadata.")
        elif actual_hash != expected_hash:
            errors.append(
                f"SemT step {flow_id!r} runtime is stale or does not match its configuration."
            )
        if not image:
            errors.append(f"SemT step {flow_id!r} is missing an image reference.")
        elif image.endswith(":latest"):
            errors.append(
                f"SemT step {flow_id!r} uses a floating latest image tag."
            )
        elif not image.endswith(expected_hash.removeprefix("sha256:")[:12]):
            errors.append(
                f"SemT step {flow_id!r} image tag does not match its configuration hash."
            )

        if definition_id == "semt.extension":
            extension_parameters = implementation.get("parameters") or {}
            parents = incoming[flow_id]
            if len(parents) != 1:
                errors.append(
                    f"SemT extension {flow_id!r} must have exactly one table input."
                )
                continue
            upstream_reconciliations = _upstream_reconciliations_for_column(
                flow_id,
                extension_parameters.get("column_name"),
                incoming,
                steps_by_id,
            )
            if not upstream_reconciliations:
                errors.append(
                    f"SemT extension {flow_id!r} must target a column reconciled earlier in the pipeline."
                )

    if errors:
        raise SemTGraphValidationError(errors)
