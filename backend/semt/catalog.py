from __future__ import annotations

from dataclasses import replace
from threading import Lock
from typing import Any

from .client import SemTClient, SemTClientError
from .schemas import (
    CatalogItem,
    CatalogOption,
    OperationCatalog,
    ParameterDefinition,
    get_path,
    validate_parameter_value,
)


def _parameter(
    name: str,
    label: str,
    parameter_type: str,
    *,
    required: bool = False,
    description: str = "",
    default: Any = None,
    placeholder: str | None = None,
    min_items: int | None = None,
    max_items: int | None = None,
    options: tuple[tuple[str, str], ...] = (),
) -> ParameterDefinition:
    return ParameterDefinition(
        name=name,
        label=label,
        type=parameter_type,
        required=required,
        description=description,
        default=default,
        placeholder=placeholder,
        min_items=min_items,
        max_items=max_items,
        options=tuple(CatalogOption(value=value, label=label) for value, label in options),
    )


COLUMN_NAME = _parameter(
    "column_name",
    "Target column",
    "column",
    required=True,
    description="Name of the input table column to process.",
)
MODIFICATION_ITEMS = (
    CatalogItem(
        id="dataCleaning",
        label="Data Cleaning",
        description="Clean text data: trim whitespace, change case, remove special characters, or normalise accents.",
        supported=True,
        parameters=(
            COLUMN_NAME,
            _parameter(
                "operationType",
                "Transform operation",
                "select",
                required=True,
                options=(
                    ("trim", "Remove unnecessary whitespace"),
                    ("removeSpecial", "Remove special characters"),
                    ("normalizeAccents", "Normalise accents and diacritics"),
                    ("toLowercase", "Convert to lowercase"),
                    ("toUppercase", "Convert to uppercase"),
                    ("toTitlecase", "Convert to titlecase"),
                ),
            ),
        ),
    ),
    CatalogItem(
        id="dateFormatter",
        label="Date Formatter",
        description="Parse and reformat date values into standardised or custom date patterns.",
        supported=True,
        parameters=(
            COLUMN_NAME,
            _parameter(
                "formatType",
                "Output format",
                "select",
                required=True,
                options=(
                    ("iso", "ISO 8601 (yyyy-MM-dd'T'HH:mm:ssXXX)"),
                    ("european", "European (dd/MM/yyyy)"),
                    ("us", "US (MM/dd/yyyy)"),
                    ("custom", "Custom pattern"),
                ),
            ),
            _parameter(
                "customPattern",
                "Custom date pattern",
                "string",
                placeholder="yyyy-MM-dd HH:mm:ss.SSS",
                description="Custom pattern using date-fns tokens. Only used when format is 'Custom'.",
            ),
            _parameter(
                "detailLevel",
                "Detail level",
                "select",
                options=(
                    ("year", "Year only"),
                    ("monthYear", "Month-Year only"),
                    ("dateOnly", "Date only"),
                    ("hourMinutes", "Hour and minutes"),
                    ("hourSeconds", "Hour with seconds"),
                    ("hourMilliseconds", "Hour with milliseconds"),
                    ("timezone", "With timezone offset"),
                ),
                description="Level of detail to include. Only used with standard formats.",
            ),
            _parameter(
                "outputMode",
                "Output mode",
                "select",
                default="update",
                options=(("update", "Update current column"), ("create", "Create new column")),
            ),
        ),
    ),
    CatalogItem(
        id="coordinateTruncation",
        label="Coordinate Truncation",
        description="Reduce geographic precision of lat,lon values by truncating decimal places.",
        supported=True,
        parameters=(
            COLUMN_NAME,
            _parameter(
                "decimalPlaces",
                "Decimal places",
                "number",
                required=True,
                default=3,
                description="Number of decimal digits to keep (0–10). Coordinates are truncated, not rounded.",
            ),
            _parameter(
                "outputMode",
                "Output mode",
                "select",
                default="update",
                options=(("update", "Update current column"), ("create", "Create new column")),
            ),
            _parameter(
                "newColumnName",
                "New column name",
                "string",
                description="Name for the new column (only when output mode is 'Create').",
            ),
        ),
    ),
    CatalogItem(
        id="regexpModifier",
        label="Regex Modifier",
        description="Apply regular expressions: match, replace, extract, count, or test patterns.",
        supported=True,
        parameters=(
            COLUMN_NAME,
            _parameter(
                "operationType",
                "Operation type",
                "select",
                required=True,
                options=(
                    ("replace", "Match and replace"),
                    ("extractAll", "Extract all matches"),
                    ("extractFirst", "Extract first match"),
                    ("extractNth", "Extract nth match"),
                    ("extractUpToN", "Extract up to N matches"),
                    ("test", "Test pattern (true/false)"),
                    ("count", "Count matches"),
                ),
            ),
            _parameter(
                "pattern",
                "Regex pattern",
                "string",
                required=True,
                placeholder="\\d+\\.\\d{1,2}",
                description="JavaScript regular expression pattern.",
            ),
            _parameter(
                "flags",
                "Regex flags",
                "string",
                default="g",
                placeholder="gi",
                description="Pattern flags: g (global), i (case-insensitive), m (multiline), etc.",
            ),
            _parameter(
                "replacement",
                "Replacement string",
                "string",
                placeholder="$1",
                description="Replacement text. Use $1, $2 for capture groups. Only for 'replace' operation.",
            ),
            _parameter(
                "matchIndex",
                "Match index",
                "number",
                default=0,
                description="0-based index of match to extract. Only for 'extractNth'.",
            ),
            _parameter(
                "matchCount",
                "Match count",
                "number",
                default=3,
                description="Max number of matches to extract. Only for 'extractUpToN'.",
            ),
            _parameter(
                "outputMode",
                "Output mode",
                "select",
                default="update",
                options=(("update", "Update current column"), ("create", "Create new column")),
            ),
            _parameter(
                "newColumnName",
                "New column name",
                "string",
                description="Name for the new column (only when output mode is 'Create').",
            ),
        ),
    ),
    CatalogItem(
        id="textColumnsTransformer",
        label="Text ↔ Columns",
        description="Join multiple columns into one, or split one column into many using a separator.",
        supported=True,
        parameters=(
            COLUMN_NAME,
            _parameter(
                "operationType",
                "Operation type",
                "select",
                required=True,
                options=(
                    ("joinOp", "Join multiple columns into one"),
                    ("splitOp", "Split one column into many"),
                ),
            ),
            _parameter(
                "columnToJoin",
                "Additional columns to join",
                "column-list",
                description="Other columns to include in the join operation.",
            ),
            _parameter(
                "separator",
                "Separator",
                "string",
                required=True,
                placeholder=",",
                description="Separator character(s) for joining or splitting.",
            ),
            _parameter(
                "splitMode",
                "Split mode",
                "select",
                options=(
                    ("separatorAll", "Split at every occurrence"),
                    ("separatorSingle", "Split at a single occurrence"),
                ),
                description="How to split the column. Only for 'split' operation.",
            ),
            _parameter(
                "splitDirection",
                "Split direction",
                "select",
                options=(("left", "From left (first occurrence)"), ("right", "From right (last occurrence)")),
                description="Direction for single-occurrence split.",
            ),
            _parameter(
                "renameMode",
                "Column naming",
                "select",
                options=(("auto", "Use default names"), ("custom", "Custom names")),
            ),
            _parameter(
                "renameNewColumnSplit",
                "New column names (split)",
                "string",
                placeholder="col1, col2, col3",
                description="Comma-separated names for split columns.",
            ),
            _parameter(
                "renameJoinedColumn",
                "New column name (join)",
                "string",
                placeholder="full_name",
                description="Name for the joined result column.",
            ),
        ),
    ),
    CatalogItem(
        id="textRows",
        label="Text → Rows",
        description="Split cell values into multiple rows using a separator.",
        supported=True,
        parameters=(
            COLUMN_NAME,
            _parameter(
                "separator",
                "Separator",
                "string",
                required=True,
                placeholder=";",
                description="Separator to split cell values into new rows.",
            ),
        ),
    ),
    CatalogItem(
        id="pseudoanonymization",
        label="Pseudoanonymization",
        description="Encrypt (anonymise) or decrypt (de-anonymise) column values.",
        supported=True,
        parameters=(
            COLUMN_NAME,
            _parameter(
                "decrypt",
                "De-anonymise",
                "boolean",
                default=False,
                description="Enable to decrypt vault keys back to original values. Default is to encrypt.",
            ),
            _parameter(
                "outputMode",
                "Output mode",
                "select",
                default="create",
                options=(("update", "Update current column"), ("create", "Create new column")),
            ),
            _parameter(
                "newColumnName",
                "New column name",
                "string",
                description="Name for the new column (only when output mode is 'Create').",
            ),
        ),
    ),
    CatalogItem(
        id="llmModifier",
        label="LLM Modifier",
        description="Use an LLM to intelligently clean, rewrite, join, or split column values via a custom prompt.",
        supported=True,
        parameters=(
            COLUMN_NAME,
            _parameter(
                "operationType",
                "Operation type",
                "select",
                required=True,
                options=(
                    ("joinOp", "Join multiple columns into one"),
                    ("splitOp", "Split one column into many"),
                    ("inPlace", "Edit the column directly"),
                ),
            ),
            _parameter(
                "columnToJoin",
                "Additional columns to join",
                "column-list",
                description="Other columns for the join operation.",
            ),
            _parameter(
                "renameMode",
                "Column naming",
                "select",
                options=(("auto", "Use default names"), ("custom", "Custom names")),
            ),
            _parameter(
                "renameNewColumnSplit",
                "New column names (split)",
                "string",
                placeholder="col1, col2",
                description="Comma-separated names for split columns.",
            ),
            _parameter(
                "renameJoinedColumn",
                "New column name (join)",
                "string",
                placeholder="result",
                description="Name for the joined result column.",
            ),
            _parameter(
                "prompt",
                "Modification prompt",
                "string",
                required=True,
                placeholder="Standardise dates to ISO format (YYYY-MM-DD)...",
                description="Instructions describing how the LLM should modify the cell values.",
            ),
        ),
    ),
)


RECONCILIATION_ITEMS = (
    CatalogItem(
        id="geocodingGeonames",
        label="Geocoding: Geo Coordinates",
        description="Link location mentions to GeoNames entries with latitude, longitude, labels, and descriptions.",
        supported=True,
        parameters=(
            COLUMN_NAME,
            _parameter(
                "additionalColumns",
                "Context columns",
                "column-list",
                description="Optional columns that provide context to improve reconciliation accuracy.",
            ),
        ),
    ),
    CatalogItem(
        id="geocodingHere",
        label="Geocoding: HERE",
        description="Link location mentions to HERE entries with street-level precision.",
        supported=True,
        parameters=(
            COLUMN_NAME,
            _parameter(
                "additionalColumns",
                "Context columns",
                "column-list",
                description="Optional columns that provide context to improve reconciliation accuracy.",
            ),
        ),
    ),
    CatalogItem(
        id="geonames",
        label="Linking: GeoNames",
        description="Link locations to GeoNames entries without explicit coordinates.",
        supported=True,
        parameters=(
            COLUMN_NAME,
            _parameter(
                "additionalColumns",
                "Context columns",
                "column-list",
                description="Optional columns that provide context to improve reconciliation accuracy.",
            ),
        ),
    ),
    CatalogItem(
        id="wikidataAlligator",
        label="Linking: Wikidata (Alligator)",
        description="Match mentions to Wikidata entities using the Alligator service. More precise than OpenRefine.",
        supported=True,
        parameters=(
            COLUMN_NAME,
            _parameter(
                "additionalColumns",
                "Context columns",
                "column-list",
                description="Optional columns that provide context to improve reconciliation accuracy.",
            ),
            _parameter(
                "useLLM",
                "LLM mode",
                "boolean",
                default=False,
                description="Use LLM-based ranking instead of the default ML model.",
            ),
        ),
    ),
    CatalogItem(
        id="wikidataOpenRefine",
        label="Linking: Wikidata (OpenRefine)",
        description="Match mentions to Wikidata entities using the OpenRefine reconciliation service.",
        supported=True,
        parameters=(COLUMN_NAME,),
    ),
    CatalogItem(
        id="inTableLinker",
        label="Linking: In-Table",
        description="Link values to corresponding values in another column of the same table.",
        supported=True,
        parameters=(
            COLUMN_NAME,
            _parameter(
                "prefix",
                "URI prefix",
                "string",
                required=True,
                default="wd",
                placeholder="wd",
                description="URI prefix for matched values (e.g. wd, geo).",
            ),
            _parameter(
                "columnToReconcile",
                "Reference column",
                "column",
                required=True,
                description="The reference column containing target values for matching.",
            ),
        ),
    ),
    CatalogItem(
        id="llmReconciler",
        label="Custom LLM Reconciler",
        description="Use an LLM to match text values to entities with custom instructions.",
        supported=True,
        parameters=(
            COLUMN_NAME,
            _parameter(
                "prefix",
                "Entity prefix",
                "string",
                default="wd",
                description="Prefix for entity IDs (e.g. 'wd' for Wikidata, 'geo' for Geonames).",
            ),
            _parameter(
                "uri",
                "Base URI",
                "string",
                default="https://www.wikidata.org/wiki/",
                description="Base URI for entities.",
            ),
            _parameter(
                "prompt",
                "Reconciliation prompt",
                "string",
                required=True,
                placeholder="Match this location to a Wikidata entity...",
                description="Instructions describing how the LLM should match cell values to entities.",
            ),
        ),
    ),
    CatalogItem(
        id="llmReconcilerWikidata",
        label="Custom Wikidata LLM Reconciler",
        description="Use an LLM to match text values to Wikidata entities without specifying a prompt.",
        supported=True,
        parameters=(
            COLUMN_NAME,
            _parameter(
                "additionalColumns",
                "Context columns",
                "column-list",
                description="Optional columns that provide context to support reconciliation.",
            ),
        ),
    ),
)


SETUP_ITEMS = (
    CatalogItem(
        id="semt_connection",
        label="SemT Connection + Table Load",
        description="Authenticate with the SemT API, initialise managers, and load a CSV table.",
        supported=True,
        parameters=(
            _parameter(
                "api_base_url",
                "API Base URL",
                "string",
                required=True,
                placeholder="https://your-semt-instance.example.com",
                description="Base URL of the SemT API server.",
            ),
            _parameter(
                "username",
                "Username",
                "string",
                required=True,
                description="SemT API username for basic authentication.",
            ),
            _parameter(
                "password",
                "Password",
                "secret-reference",
                required=True,
                description="SemT API password.",
            ),
            _parameter(
                "token",
                "Bearer Token",
                "secret-reference",
                description="Optional bearer token for API authentication.",
            ),
            _parameter(
                "dataset_id",
                "Dataset ID",
                "string",
                required=True,
                default="114",
                description="SemT dataset identifier where the table will be stored.",
            ),
            _parameter(
                "table_name",
                "Table Name",
                "string",
                required=True,
                default="my_table",
                description="Name for the table in the SemT dataset.",
            ),
        ),
    ),
)

EXPORT_ITEMS = (
    CatalogItem(
        id="export_table",
        label="Export Table",
        description="Fetch the final enriched table from the SemT backend and download it as a JSON or CSV file.",
        supported=True,
        parameters=(
            _parameter(
                "output_format",
                "Output Format",
                "select",
                required=True,
                default="json",
                options=(("json", "JSON (W3C format)"), ("csv", "CSV")),
                description="Format for the downloaded file.",
            ),
            _parameter(
                "output_filename",
                "Output Filename",
                "string",
                default="exported_data",
                description="Base filename for the exported file (extension added automatically).",
            ),
        ),
    ),
)

EXTENSION_ITEMS = (
    CatalogItem(
        id="reconciledColumnExt",
        label="Annotation Properties",
        description="Extend a reconciled column with annotation properties (IDs, labels, URIs).",
        supported=True,
        parameters=(
            COLUMN_NAME,
            _parameter(
                "properties",
                "Properties",
                "property-list",
                required=True,
                min_items=1,
                placeholder="id, name, description",
            ),
        ),
    ),
    CatalogItem(
        id="reconciledColumnExtWikidata",
        label="Annotation Properties (Wikidata)",
        description="Add Wikidata label fields (ID, name, description, URL) for a reconciled column.",
        supported=True,
        parameters=(
            COLUMN_NAME,
            _parameter(
                "properties",
                "Label properties",
                "multi-select",
                required=True,
                min_items=1,
                options=(
                    ("id", "ID"),
                    ("name", "Name"),
                    ("description", "Description"),
                    ("url", "URL"),
                ),
            ),
        ),
    ),
    CatalogItem(
        id="wikidataPropertySPARQL",
        label="Wikidata Properties",
        description="Fetch Wikidata property values for entities in a reconciled column.",
        supported=True,
        parameters=(
            COLUMN_NAME,
            _parameter(
                "properties",
                "Wikidata property IDs",
                "property-list",
                required=True,
                min_items=1,
                placeholder="P31, P17",
            ),
        ),
    ),
    CatalogItem(
        id="wikidataSPARQL",
        label="SPARQL (Wikidata)",
        description="Run a custom SPARQL query against Wikidata for each entity.",
        supported=True,
        parameters=(
            COLUMN_NAME,
            _parameter(
                "whereClause",
                "WHERE clause",
                "string",
                required=True,
                placeholder="?item wdt:P31 wd:Q515 ...",
                description="SPARQL WHERE clause body. Use VALUES { ... } for the entity variable.",
            ),
            _parameter(
                "orderBy",
                "ORDER BY",
                "string",
                description="Optional ORDER BY clause.",
            ),
            _parameter(
                "limit",
                "LIMIT",
                "string",
                description="Optional result limit.",
            ),
        ),
    ),
    CatalogItem(
        id="geoPropertiesWikidata",
        label="Geo Properties (Wikidata)",
        description="Retrieve geographic properties from Wikidata for entities in a column.",
        supported=True,
        parameters=(
            COLUMN_NAME,
            _parameter(
                "properties",
                "Properties",
                "property-list",
                required=True,
                min_items=1,
                placeholder="P625, P17",
            ),
        ),
    ),
    CatalogItem(
        id="geoRouteHere",
        label="Geo Route (HERE)",
        description="Calculate routes between locations using the HERE API.",
        supported=True,
        parameters=(
            COLUMN_NAME,
            _parameter(
                "destinationColumn",
                "Destination column",
                "column",
                required=True,
                description="Column containing destination coordinates or POI names.",
            ),
            _parameter(
                "isPOI",
                "Destination is POI",
                "boolean",
                default=False,
                description="Whether the destination column contains Points of Interest names.",
            ),
            _parameter(
                "properties",
                "Route properties",
                "multi-select",
                required=True,
                min_items=1,
                options=(
                    ("distance", "Distance"),
                    ("duration", "Duration"),
                    ("polyline", "Polyline"),
                ),
            ),
        ),
    ),
    CatalogItem(
        id="geoRouteOSRM",
        label="Geo Route (OSRM)",
        description="Calculate routes using the Open Source Routing Machine.",
        supported=True,
        parameters=(
            COLUMN_NAME,
            _parameter(
                "travelMode",
                "Travel mode",
                "select",
                required=True,
                options=(
                    ("driving", "Driving"),
                    ("walking", "Walking"),
                    ("cycling", "Cycling"),
                ),
            ),
            _parameter(
                "properties",
                "Route properties",
                "multi-select",
                required=True,
                min_items=1,
                options=(
                    ("distance", "Distance"),
                    ("duration", "Duration"),
                    ("polyline", "Polyline"),
                ),
            ),
        ),
    ),
    CatalogItem(
        id="meteoPropertiesOpenMeteo",
        label="Meteo Properties (Open-Meteo)",
        description="Add weather data using location and date columns.",
        supported=True,
        parameters=(
            COLUMN_NAME,
            _parameter(
                "granularity",
                "Data granularity",
                "select",
                required=True,
                default="daily",
                options=(("daily", "Daily"), ("hourly", "Hourly")),
            ),
            _parameter(
                "dateColumnName",
                "Date column",
                "column",
                required=True,
            ),
            _parameter(
                "decimalFormat",
                "Decimal format",
                "select",
                default=".",
                options=((".", "Dot"), ("comma", "Comma")),
            ),
            _parameter(
                "properties",
                "Weather parameters",
                "multi-select",
                required=True,
                min_items=1,
                options=(
                    ("light_hours", "Light Hours"),
                    ("apparent_temperature_max", "Apparent Max Temperature"),
                    ("apparent_temperature_min", "Apparent Min Temperature"),
                    ("temperature_2m_max", "Max Temperature"),
                    ("temperature_2m_min", "Min Temperature"),
                    ("precipitation_sum", "Precipitation"),
                    ("wind_speed_10m_max", "Wind Speed"),
                    ("weather_code", "Weather Code"),
                ),
            ),
        ),
    ),
    CatalogItem(
        id="llmClassifier",
        label="COFOG (LLM Classifier)",
        description="Use an LLM to classify organisation descriptions with optional country context.",
        supported=True,
        parameters=(
            COLUMN_NAME,
            _parameter(
                "descriptionColumn",
                "Description column",
                "column",
                description="Column containing organisation description text.",
            ),
            _parameter(
                "countryColumn",
                "Country column",
                "column",
                description="Column containing country name for context.",
            ),
        ),
    ),
    CatalogItem(
        id="llmExtender",
        label="Custom LLM Extender",
        description="Use an LLM to extend a column with custom-generated data via a prompt.",
        supported=True,
        parameters=(
            COLUMN_NAME,
            _parameter(
                "prompt",
                "Extension prompt",
                "string",
                required=True,
                placeholder="For each entity, return a JSON object with ...",
                description="Instructions describing what data the LLM should generate for each cell.",
            ),
            _parameter(
                "properties",
                "Output fields",
                "property-list",
                description="List of field names the LLM should return (comma-separated).",
            ),
        ),
    ),
    CatalogItem(
        id="chMatching",
        label="CH Matching",
        description="Private company matching service for Swiss business registry.",
        supported=True,
        parameters=(
            COLUMN_NAME,
            _parameter(
                "properties",
                "Properties",
                "property-list",
                description="Properties to fetch for matched companies.",
            ),
        ),
    ),
)


FAMILY_ITEMS = {
    "setup": SETUP_ITEMS,
    "modifications": MODIFICATION_ITEMS,
    "reconciliators": RECONCILIATION_ITEMS,
    "extenders": EXTENSION_ITEMS,
    "export": EXPORT_ITEMS,
}

CATALOG_FAMILIES = {
    "setup": "setup",
    "modifications": "modification",
    "reconciliators": "reconciliation",
    "extenders": "extension",
    "export": "export",
}


class SemTCatalogService:
    def __init__(self, client: SemTClient | None = None):
        self.client = client or SemTClient()

    def get_catalog(
        self,
        catalog_name: str,
        *,
        force_refresh: bool = False,
    ) -> OperationCatalog:
        if catalog_name not in FAMILY_ITEMS:
            raise KeyError(f"Unknown SemT catalog: {catalog_name}")

        family = CATALOG_FAMILIES[catalog_name]
        local_items = FAMILY_ITEMS[catalog_name]
        if catalog_name in {"modifications", "setup", "export"}:
            return OperationCatalog(
                family=family,
                catalog_version="1",
                items=local_items,
                source="local",
            )

        if not self.client.configured:
            return OperationCatalog(
                family=family,
                catalog_version="1",
                items=local_items,
                source="local-adapters",
            )

        try:
            remote_services = self.client.list_services(
                catalog_name,
                force_refresh=force_refresh,
            )
        except SemTClientError as exc:
            return OperationCatalog(
                family=family,
                catalog_version="1",
                items=local_items,
                source="local-fallback",
                warnings=(str(exc),),
            )

        remote_by_id = {
            str(service.get("id") or "").strip(): service
            for service in remote_services
        }
        items = tuple(
            replace(
                item,
                label=str(remote_by_id[item.id].get("name") or item.label).strip(),
                metadata={
                    "relative_url": remote_by_id[item.id].get("relativeUrl", ""),
                },
            )
            for item in local_items
            if item.id in remote_by_id
        )
        return OperationCatalog(
            family=family,
            catalog_version="1",
            items=items,
            source="remote-intersection",
        )

    def validate_implementation(
        self,
        definition_id: str,
        implementation: Any,
    ) -> dict[str, Any]:
        catalog_name = {
            "semt.setup": "setup",
            "semt.modification": "modifications",
            "semt.reconciliation": "reconciliators",
            "semt.extension": "extenders",
            "semt.export": "export",
        }.get(definition_id)
        if not catalog_name:
            return {
                "status": "invalid",
                "errors": [f"Unsupported SemT definition: {definition_id}"],
            }
        if not isinstance(implementation, dict):
            return {
                "status": "invalid",
                "errors": ["Implementation must be an object."],
            }

        errors: list[str] = []
        service_id = str(implementation.get("service_id") or "").strip()
        if not service_id:
            errors.append("Operation or service is required.")
            return {"status": "unconfigured", "errors": errors}

        catalog = self.get_catalog(catalog_name)
        selected = next(
            (item for item in catalog.items if item.id == service_id and item.supported),
            None,
        )
        if selected is None:
            errors.append(f"Service {service_id!r} is not supported by this installation.")
            return {"status": "invalid", "errors": errors}

        parameters = implementation.get("parameters")
        if not isinstance(parameters, dict):
            parameters = {}
            errors.append("Parameters must be an object.")
        for parameter in selected.parameters:
            errors.extend(
                validate_parameter_value(
                    parameter,
                    get_path(parameters, parameter.name),
                )
            )

        return {
            "status": "invalid" if errors else "valid",
            "errors": errors,
        }


_catalog_service: SemTCatalogService | None = None
_catalog_service_lock = Lock()


def get_semt_catalog_service() -> SemTCatalogService:
    global _catalog_service
    with _catalog_service_lock:
        if _catalog_service is None:
            _catalog_service = SemTCatalogService()
        return _catalog_service
