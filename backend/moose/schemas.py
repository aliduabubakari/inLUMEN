"""Typed catalog structures for the Moose integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CatalogOption:
    value: str
    label: str

    def to_dict(self) -> dict[str, str]:
        return {"value": self.value, "label": self.label}


@dataclass(frozen=True)
class ParameterDefinition:
    name: str
    label: str
    type: str
    required: bool = False
    default: Any = None
    description: str = ""
    options: tuple[CatalogOption, ...] = ()
    min_items: int | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "label": self.label,
            "type": self.type,
            "required": self.required,
            "description": self.description,
        }
        if self.default is not None:
            payload["default"] = self.default
        if self.options:
            payload["options"] = [option.to_dict() for option in self.options]
        if self.min_items is not None:
            payload["min_items"] = self.min_items
        return payload


@dataclass(frozen=True)
class MooseSchema:
    value: str
    label: str
    supports_text: bool
    supports_table: bool
    supports_cpa: bool
    supports_prefilter: bool
    output_format: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "label": self.label,
            "supports_text": self.supports_text,
            "supports_table": self.supports_table,
            "supports_cpa": self.supports_cpa,
            "supports_prefilter": self.supports_prefilter,
            "output_format": self.output_format,
        }


@dataclass(frozen=True)
class PrivacyProfile:
    value: str
    label: str
    description: str
    defaults: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "label": self.label,
            "description": self.description,
            "defaults": self.defaults,
        }


@dataclass(frozen=True)
class MooseOperation:
    id: str
    label: str
    description: str
    input_contract: str
    output_contract: str
    schema_capability: str | None
    parameters: tuple[ParameterDefinition, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "input_contract": self.input_contract,
            "output_contract": self.output_contract,
            "schema_capability": self.schema_capability,
            "parameters": [parameter.to_dict() for parameter in self.parameters],
        }


@dataclass(frozen=True)
class MooseCatalog:
    operations: tuple[MooseOperation, ...]
    schemas: tuple[MooseSchema, ...]
    privacy_profiles: tuple[PrivacyProfile, ...]
    policy_packs: tuple[CatalogOption, ...]
    providers: tuple[CatalogOption, ...]
    source: str
    warnings: tuple[str, ...] = field(default_factory=tuple)
    catalog_version: str = "1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": "moose",
            "catalog_version": self.catalog_version,
            "source": self.source,
            "warnings": list(self.warnings),
            "operations": [operation.to_dict() for operation in self.operations],
            "schemas": [schema.to_dict() for schema in self.schemas],
            "privacy_profiles": [
                profile.to_dict() for profile in self.privacy_profiles
            ],
            "policy_packs": [option.to_dict() for option in self.policy_packs],
            "providers": [option.to_dict() for option in self.providers],
        }
