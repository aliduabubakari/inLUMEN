"""Stable Moose operation catalog with dynamic service metadata."""

from __future__ import annotations

from typing import Any, Callable

from .client import MooseClientError, MooseMetadataClient
from .schemas import (
    CatalogOption,
    MooseCatalog,
    MooseOperation,
    MooseSchema,
    ParameterDefinition,
    PrivacyProfile,
)

LOCAL_SCHEMAS = (
    MooseSchema("coarse", "Coarse", True, True, False, False, "dense"),
    MooseSchema("cpa", "CPA Relationships", False, False, True, False, "sparse"),
    MooseSchema("dpv", "DPV (Full)", True, True, False, True, "sparse"),
    MooseSchema(
        "dpv_pd",
        "DPV Personal Data + AI (Fast)",
        True,
        True,
        False,
        True,
        "sparse",
    ),
    MooseSchema("fine", "Fine", True, True, False, False, "sparse"),
    MooseSchema(
        "schemaorg_cpa_v1",
        "schema.org CPA (curated_v1)",
        False,
        False,
        True,
        True,
        "sparse",
    ),
    MooseSchema(
        "schemaorg_cta_v1",
        "schema.org CTA (curated_v1)",
        False,
        True,
        False,
        True,
        "sparse",
    ),
    MooseSchema("sti", "STI Column Types", False, True, False, False, "sparse"),
)

LOCAL_PROFILES = (
    PrivacyProfile(
        "balanced",
        "Balanced",
        "Balanced privacy discovery with rules and model-assisted classification.",
        {
            "policy_pack": "gdpr_basic",
            "analysis_mode": "hybrid",
            "text_schema": "dpv_pd",
            "table_schema": "dpv_pd",
            "scan_schema": "dpv_pd",
            "include_extraction": True,
        },
    ),
    PrivacyProfile(
        "deep",
        "Deep",
        "Broader DPV analysis for higher-recall privacy discovery.",
        {
            "policy_pack": "gdpr_basic",
            "analysis_mode": "hybrid",
            "text_schema": "dpv",
            "table_schema": "dpv",
            "scan_schema": "dpv",
            "include_extraction": True,
        },
    ),
    PrivacyProfile(
        "fast",
        "Fast",
        "Rule-led privacy analysis for low-latency previews.",
        {
            "policy_pack": "gdpr_basic",
            "analysis_mode": "rules",
            "text_schema": "dpv_pd",
            "table_schema": "dpv_pd",
            "scan_schema": "dpv_pd",
            "include_extraction": True,
        },
    ),
)

LOCAL_POLICY_PACKS = (CatalogOption("gdpr_basic", "GDPR Basic"),)

PROVIDERS = (
    CatalogOption("openrouter", "OpenRouter"),
    CatalogOption("ollama", "Ollama"),
    CatalogOption("deepinfra", "DeepInfra"),
    CatalogOption("deepseek", "DeepSeek"),
)

_default_client: MooseMetadataClient | None = None


def get_moose_metadata_client() -> MooseMetadataClient:
    global _default_client
    if _default_client is None:
        _default_client = MooseMetadataClient()
    return _default_client


def _options(values: tuple[Any, ...]) -> tuple[CatalogOption, ...]:
    return tuple(CatalogOption(value.value, value.label) for value in values)


def _parameter(
    name: str,
    label: str,
    type_: str,
    *,
    required: bool = False,
    default: Any = None,
    description: str = "",
    options: tuple[CatalogOption, ...] = (),
    min_items: int | None = None,
) -> ParameterDefinition:
    return ParameterDefinition(
        name=name,
        label=label,
        type=type_,
        required=required,
        default=default,
        description=description,
        options=options,
        min_items=min_items,
    )


def build_operations(
    schemas: tuple[MooseSchema, ...],
    profiles: tuple[PrivacyProfile, ...],
    policy_packs: tuple[CatalogOption, ...],
) -> tuple[MooseOperation, ...]:
    profile_options = _options(profiles)
    text_schema_options = tuple(
        CatalogOption(schema.value, schema.label)
        for schema in schemas
        if schema.supports_text
    )
    table_schema_options = tuple(
        CatalogOption(schema.value, schema.label)
        for schema in schemas
        if schema.supports_table
    )
    common_table = (
        _parameter("table_id", "Table ID", "string"),
        _parameter("sample_size", "Sample Size", "number", default=50),
        _parameter(
            "sample_strategy",
            "Sample Strategy",
            "select",
            default="head",
            options=(CatalogOption("head", "First rows"),),
        ),
    )
    privacy_common = (
        _parameter("context", "Context", "key-value-map"),
        _parameter(
            "profile",
            "Privacy Profile",
            "select",
            required=True,
            default="balanced",
            options=profile_options,
        ),
        _parameter(
            "policy_pack",
            "Policy Pack",
            "select",
            default="gdpr_basic",
            options=policy_packs,
        ),
        _parameter(
            "analysis_mode",
            "Analysis Mode",
            "select",
            default="hybrid",
            options=(
                CatalogOption("rules", "Rules"),
                CatalogOption("hybrid", "Hybrid"),
            ),
        ),
        _parameter(
            "include_extraction",
            "Include Extraction",
            "boolean",
            default=True,
        ),
    )
    return (
        MooseOperation(
            "text_ner",
            "Text Entity Recognition",
            "Recognize ontology-backed entities in incoming text.",
            "inlumen.text@1",
            "inlumen.text@1",
            "supports_text",
        ),
        MooseOperation(
            "table_annotation",
            "Table Annotation",
            "Classify table columns against the selected Moose schema.",
            "inlumen.table@1",
            "inlumen.table@1",
            "supports_table",
            common_table,
        ),
        MooseOperation(
            "table_cpa",
            "Column Property Annotation",
            "Infer relationships between a subject column and target columns.",
            "inlumen.table@1",
            "inlumen.table@1",
            "supports_cpa",
            common_table
            + (
                _parameter(
                    "subject_column",
                    "Subject Column",
                    "column",
                    required=True,
                ),
                _parameter("subject_class", "Subject Class", "string"),
                _parameter(
                    "target_columns",
                    "Target Columns",
                    "column-list",
                    required=True,
                    min_items=1,
                ),
                _parameter(
                    "use_sti_signature_cache",
                    "Use STI Signature Cache",
                    "boolean",
                    default=True,
                ),
                _parameter("debug", "Debug", "boolean", default=False),
                _parameter(
                    "debug_preview_limit",
                    "Debug Preview Limit",
                    "number",
                    default=20,
                ),
            ),
        ),
        MooseOperation(
            "privacy_text",
            "Privacy Analysis: Text",
            "Analyze text for privacy concepts and policy signals.",
            "inlumen.text@1",
            "inlumen.text@1",
            None,
            privacy_common
            + (
                _parameter(
                    "text_schema",
                    "Text Schema",
                    "select",
                    default="dpv_pd",
                    options=text_schema_options,
                ),
            ),
        ),
        MooseOperation(
            "privacy_table",
            "Privacy Analysis: Table",
            "Analyze table columns and sampled values for privacy concepts.",
            "inlumen.table@1",
            "inlumen.table@1",
            None,
            common_table
            + privacy_common
            + (
                _parameter("scan_columns", "Scan Columns", "column-list"),
                _parameter(
                    "table_schema",
                    "Table Schema",
                    "select",
                    default="dpv_pd",
                    options=table_schema_options,
                ),
                _parameter(
                    "scan_schema",
                    "Scan Schema",
                    "select",
                    default="dpv_pd",
                    options=text_schema_options,
                ),
            ),
        ),
    )


def _parse_schemas(payload: Any) -> tuple[MooseSchema, ...]:
    rows = payload.get("schemas", payload) if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError("Moose schema catalog must be a list")
    return tuple(
        MooseSchema(
            value=str(row.get("name") or row.get("id") or row.get("value") or ""),
            label=str(
                row.get("label")
                or row.get("name")
                or row.get("id")
                or row.get("value")
                or ""
            ),
            supports_text=bool(row.get("supports_text")),
            supports_table=bool(row.get("supports_table")),
            supports_cpa=bool(row.get("supports_cpa")),
            supports_prefilter=bool(
                row.get("prefilter_types", row.get("supports_prefilter"))
            ),
            output_format=str(
                row.get("score_mode") or row.get("output_format") or "sparse"
            ),
        )
        for row in rows
        if isinstance(row, dict)
        and (row.get("name") or row.get("id") or row.get("value"))
    )


def _parse_profiles(payload: Any) -> tuple[PrivacyProfile, ...]:
    rows = payload.get("profiles", payload) if isinstance(payload, dict) else payload
    if isinstance(rows, dict):
        rows = [
            dict(value, id=key) if isinstance(value, dict) else {"id": key}
            for key, value in rows.items()
        ]
    if not isinstance(rows, list):
        raise ValueError("Moose privacy profile catalog must be a list")
    return tuple(
        PrivacyProfile(
            value=str(row.get("id") or row.get("value") or ""),
            label=str(row.get("label") or row.get("name") or row.get("id") or ""),
            description=str(row.get("description") or ""),
            defaults=dict(row.get("defaults") or row.get("config") or {}),
        )
        for row in rows
        if isinstance(row, dict) and (row.get("id") or row.get("value"))
    )


def _parse_policy_packs(payload: Any) -> tuple[CatalogOption, ...]:
    rows = payload.get("policy_packs", payload) if isinstance(payload, dict) else payload
    if isinstance(rows, dict):
        rows = list(rows)
    if not isinstance(rows, list):
        raise ValueError("Moose policy pack catalog must be a list")
    options: list[CatalogOption] = []
    for row in rows:
        if isinstance(row, str):
            options.append(CatalogOption(row, row.replace("_", " ").title()))
        elif isinstance(row, dict) and (row.get("id") or row.get("value")):
            value = str(row.get("id") or row.get("value"))
            options.append(
                CatalogOption(value, str(row.get("label") or row.get("name") or value))
            )
    return tuple(options)


def _dynamic_metadata(
    client: MooseMetadataClient,
    path: str,
    parser: Callable[[Any], tuple[Any, ...]],
    fallback: tuple[Any, ...],
    label: str,
    force_refresh: bool,
) -> tuple[tuple[Any, ...], str, str | None]:
    try:
        parsed = parser(client.get_json(path, force=force_refresh))
        if not parsed:
            raise ValueError(f"Moose returned an empty {label} catalog")
        return parsed, "moose-api", None
    except (MooseClientError, TypeError, ValueError) as exc:
        if isinstance(exc, MooseClientError) and exc.stale_value is not None:
            try:
                parsed = parser(exc.stale_value)
                if parsed:
                    return parsed, "stale-cache", f"Using stale Moose {label}: {exc}"
            except (TypeError, ValueError):
                pass
        return fallback, "local-baseline", f"Using local Moose {label}: {exc}"


def get_moose_catalog(
    client: MooseMetadataClient | None = None,
    *,
    force_refresh: bool = False,
) -> MooseCatalog:
    client = client or get_moose_metadata_client()
    if not client.configured:
        return MooseCatalog(
            operations=build_operations(
                LOCAL_SCHEMAS, LOCAL_PROFILES, LOCAL_POLICY_PACKS
            ),
            schemas=LOCAL_SCHEMAS,
            privacy_profiles=LOCAL_PROFILES,
            policy_packs=LOCAL_POLICY_PACKS,
            providers=PROVIDERS,
            source="local-baseline",
            warnings=(
                "Moose metadata service is not configured; using the pinned local catalog.",
            ),
        )

    schemas, schema_source, schema_warning = _dynamic_metadata(
        client,
        "/schemas",
        _parse_schemas,
        LOCAL_SCHEMAS,
        "schemas",
        force_refresh,
    )
    profiles, profile_source, profile_warning = _dynamic_metadata(
        client,
        "/privacy/profiles",
        _parse_profiles,
        LOCAL_PROFILES,
        "privacy profiles",
        force_refresh,
    )
    policy_packs, pack_source, pack_warning = _dynamic_metadata(
        client,
        "/policy-packs",
        _parse_policy_packs,
        LOCAL_POLICY_PACKS,
        "policy packs",
        force_refresh,
    )
    sources = {schema_source, profile_source, pack_source}
    source = "moose-api" if sources == {"moose-api"} else "+".join(sorted(sources))
    warnings = tuple(
        warning
        for warning in (schema_warning, profile_warning, pack_warning)
        if warning
    )
    return MooseCatalog(
        operations=build_operations(schemas, profiles, policy_packs),
        schemas=schemas,
        privacy_profiles=profiles,
        policy_packs=policy_packs,
        providers=PROVIDERS,
        source=source,
        warnings=warnings,
    )
