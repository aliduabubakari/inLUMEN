"""Validation for persisted Moose node implementations."""

from __future__ import annotations

from typing import Any

from .schemas import MooseCatalog, MooseOperation, ParameterDefinition

SECRET_KEYS = {
    "api_key",
    "llm_api_key",
    "x_api_key",
    "authorization",
    "token",
    "openrouter_api_key",
    "deepinfra_api_key",
    "deepseek_api_key",
    "ollama_token",
    "mongo_url",
    "mongodb_url",
}


def _find_secret_path(value: Any, path: str = "implementation") -> str | None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower().replace("-", "_")
            if (
                normalized in SECRET_KEYS
                or normalized.endswith("_api_key")
                or normalized.endswith("_token")
                or normalized in {"password", "secret", "client_secret"}
            ):
                return f"{path}.{key}"
            found = _find_secret_path(child, f"{path}.{key}")
            if found:
                return found
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found = _find_secret_path(child, f"{path}[{index}]")
            if found:
                return found
    return None


def _missing(value: Any) -> bool:
    return value is None or value == "" or value == []


def _validate_parameter(
    definition: ParameterDefinition,
    value: Any,
) -> str | None:
    if _missing(value):
        return f"{definition.label} is required" if definition.required else None
    if definition.type in {"string", "column", "select"} and not isinstance(value, str):
        return f"{definition.label} must be text"
    if definition.type == "boolean" and not isinstance(value, bool):
        return f"{definition.label} must be true or false"
    if definition.type == "number" and (
        isinstance(value, bool) or not isinstance(value, (int, float))
    ):
        return f"{definition.label} must be a number"
    if definition.type in {"column-list", "multi-select"}:
        if not isinstance(value, list) or not all(
            isinstance(item, str) and item for item in value
        ):
            return f"{definition.label} must be a list of column names"
        if definition.min_items and len(value) < definition.min_items:
            return (
                f"{definition.label} requires at least "
                f"{definition.min_items} item(s)"
            )
    if definition.type == "key-value-map" and not isinstance(value, dict):
        return f"{definition.label} must be a key-value map"
    if definition.options and isinstance(value, str):
        allowed = {option.value for option in definition.options}
        if value not in allowed:
            return f"{definition.label} has an unsupported value"
    return None


def _operation_by_id(catalog: MooseCatalog, operation_id: str) -> MooseOperation | None:
    return next(
        (operation for operation in catalog.operations if operation.id == operation_id),
        None,
    )


def validate_moose_implementation(
    implementation: Any,
    catalog: MooseCatalog,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings = list(catalog.warnings)
    if not isinstance(implementation, dict):
        return {
            "status": "invalid",
            "errors": ["Moose implementation must be an object"],
            "warnings": warnings,
        }

    secret_path = _find_secret_path(implementation)
    if secret_path:
        errors.append(
            f"Secrets cannot be stored in node configuration ({secret_path}); "
            "use a server-side connection reference"
        )

    if implementation.get("kind") not in (None, "", "moose"):
        errors.append("Implementation kind must be 'moose'")

    operation_id = str(implementation.get("operation") or "")
    if not operation_id:
        return {
            "status": "unconfigured" if not errors else "invalid",
            "errors": errors,
            "warnings": warnings,
        }
    operation = _operation_by_id(catalog, operation_id)
    if operation is None:
        errors.append(f"Unsupported Moose operation: {operation_id}")
        return {"status": "invalid", "errors": errors, "warnings": warnings}

    if not implementation.get("connection_ref"):
        errors.append("A server-side Moose connection reference is required")

    llm = implementation.get("llm")
    if not isinstance(llm, dict):
        errors.append("LLM provider and model configuration is required")
    else:
        provider = llm.get("provider")
        model = llm.get("model")
        if provider not in {option.value for option in catalog.providers}:
            errors.append("Select a supported LLM provider")
        if not isinstance(model, str) or not model.strip():
            errors.append("An LLM model is required")

    schema_id = implementation.get("schema")
    if operation.schema_capability:
        if not isinstance(schema_id, str) or not schema_id:
            errors.append("Select a compatible Moose schema")
        else:
            schema = next(
                (item for item in catalog.schemas if item.value == schema_id), None
            )
            if schema is None:
                errors.append(f"Unknown Moose schema: {schema_id}")
            elif not bool(getattr(schema, operation.schema_capability)):
                errors.append(
                    f"Schema {schema.label} does not support {operation.label}"
                )

    parameters = implementation.get("parameters") or {}
    if not isinstance(parameters, dict):
        errors.append("Operation parameters must be an object")
        parameters = {}
    for definition in operation.parameters:
        parameter_error = _validate_parameter(
            definition, parameters.get(definition.name)
        )
        if parameter_error:
            errors.append(parameter_error)

    sample_size = parameters.get("sample_size")
    if sample_size is not None:
        if (
            isinstance(sample_size, bool)
            or not isinstance(sample_size, (int, float))
            or int(sample_size) != sample_size
            or not 1 <= int(sample_size) <= 1000
        ):
            errors.append("Sample Size must be an integer between 1 and 1000")

    if operation_id == "table_cpa":
        subject = parameters.get("subject_column")
        targets = parameters.get("target_columns")
        if isinstance(subject, str) and isinstance(targets, list) and subject in targets:
            errors.append("Subject Column cannot also be a Target Column")

    return {
        "status": "invalid" if errors else "valid",
        "errors": errors,
        "warnings": warnings,
    }
