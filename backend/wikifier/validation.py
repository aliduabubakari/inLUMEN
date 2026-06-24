from __future__ import annotations

from typing import Any


SUPPORTED_OUTPUT_MODES = {"compact_and_raw", "raw_only"}


def validate_wikifier_implementation(implementation: Any) -> dict[str, Any]:
    if not isinstance(implementation, dict):
        return {
            "status": "invalid",
            "errors": ["Wikifier implementation must be an object."],
        }

    errors: list[str] = []
    if implementation.get("kind") not in (None, "", "wikifier"):
        errors.append("Implementation kind must be 'wikifier'.")
    if implementation.get("operation") not in (None, "", "annotation"):
        errors.append("Unsupported Wikifier operation.")

    connection_ref = str(implementation.get("connection_ref") or "").strip()
    if not connection_ref:
        errors.append("Connection profile is required.")

    parameters = implementation.get("parameters")
    if not isinstance(parameters, dict):
        parameters = {}
        errors.append("Parameters must be an object.")

    source_column = str(parameters.get("source_column") or "").strip()
    if not source_column:
        errors.append("Source column is required.")

    language = str(parameters.get("language") or "").strip()
    if not language:
        errors.append("Language is required.")

    threshold = parameters.get("threshold")
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
        errors.append("Threshold must be a number.")
    elif threshold < 0 or threshold > 1:
        errors.append("Threshold must be between 0 and 1.")

    output_mode = str(parameters.get("output_mode") or "").strip()
    if output_mode not in SUPPORTED_OUTPUT_MODES:
        errors.append("Output mode is not supported.")

    if not source_column or not language or not connection_ref:
        status = "unconfigured"
    else:
        status = "invalid" if errors else "valid"
    return {"status": status, "errors": errors}
