from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


PARAMETER_TYPES = {
    "string",
    "boolean",
    "number",
    "select",
    "multi-select",
    "column",
    "column-list",
    "property",
    "property-list",
    "key-value-map",
    "ordered-column-list",
    "secret-reference",
}


@dataclass(frozen=True)
class CatalogOption:
    value: str
    label: str


@dataclass(frozen=True)
class ParameterDefinition:
    name: str
    label: str
    type: str
    required: bool = False
    description: str = ""
    default: Any = None
    placeholder: str | None = None
    min_items: int | None = None
    max_items: int | None = None
    options: tuple[CatalogOption, ...] = ()

    def __post_init__(self):
        if self.type not in PARAMETER_TYPES:
            raise ValueError(f"Unsupported SemT parameter type: {self.type}")
        if self.min_items is not None and self.min_items < 0:
            raise ValueError("min_items cannot be negative")
        if (
            self.max_items is not None
            and self.min_items is not None
            and self.max_items < self.min_items
        ):
            raise ValueError("max_items cannot be smaller than min_items")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["options"] = [asdict(option) for option in self.options]
        return {
            key: value
            for key, value in data.items()
            if value is not None and value != ()
        }


@dataclass(frozen=True)
class CatalogItem:
    id: str
    label: str
    description: str
    supported: bool
    parameters: tuple[ParameterDefinition, ...]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "supported": self.supported,
            "parameters": [parameter.to_dict() for parameter in self.parameters],
        }
        if self.metadata:
            data["metadata"] = dict(self.metadata)
        return data


@dataclass(frozen=True)
class OperationCatalog:
    family: str
    catalog_version: str
    items: tuple[CatalogItem, ...]
    source: str = "local"
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        data = {
            "family": self.family,
            "catalog_version": self.catalog_version,
            "source": self.source,
            "items": [item.to_dict() for item in self.items],
        }
        if self.warnings:
            data["warnings"] = list(self.warnings)
        return data


def get_path(value: Any, path: str) -> Any:
    current = value
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict)):
        return len(value) > 0
    return True


def validate_parameter_value(
    parameter: ParameterDefinition,
    value: Any,
) -> list[str]:
    errors: list[str] = []
    if parameter.required and not _has_value(value):
        return [f"{parameter.label} is required."]
    if not _has_value(value):
        return errors

    if parameter.type == "boolean":
        if not isinstance(value, bool):
            errors.append(f"{parameter.label} must be true or false.")
    elif parameter.type == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            errors.append(f"{parameter.label} must be a number.")
    elif parameter.type in {
        "column-list",
        "property-list",
        "multi-select",
        "ordered-column-list",
    }:
        if not isinstance(value, list) or not all(
            isinstance(item, str) and item.strip() for item in value
        ):
            errors.append(f"{parameter.label} must be a list of values.")
        else:
            if parameter.min_items is not None and len(value) < parameter.min_items:
                errors.append(
                    f"{parameter.label} requires at least {parameter.min_items} value(s)."
                )
            if parameter.max_items is not None and len(value) > parameter.max_items:
                errors.append(
                    f"{parameter.label} allows at most {parameter.max_items} value(s)."
                )
    elif parameter.type == "key-value-map":
        if not isinstance(value, dict) or not all(
            isinstance(key, str) and key.strip() for key in value
        ):
            errors.append(f"{parameter.label} must be a key-value map.")
    elif parameter.type == "select":
        allowed = {option.value for option in parameter.options}
        if allowed and value not in allowed:
            errors.append(f"{parameter.label} has an unsupported value.")
    elif not isinstance(value, str):
        errors.append(f"{parameter.label} must be text.")

    return errors
