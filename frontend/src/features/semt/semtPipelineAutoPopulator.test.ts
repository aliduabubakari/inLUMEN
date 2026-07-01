import { describe, expect, it } from "vitest";
import { parseSemTPipelineScript } from "@/features/semt/semtPipelineParser";
import { populatePipeline } from "@/features/semt/semtPipelineAutoPopulator";
import type { NodeDefinition } from "@/features/nodes/registry/types";
import type { SemTCatalog } from "@/features/semt/types";

const definition = (
  id: NodeDefinition["id"],
  operation: string,
  baseType: NodeDefinition["base_type"] = "action",
): NodeDefinition => ({
  id,
  version: 7,
  base_type: baseType,
  family: "semt",
  operation,
  enabled: true,
  palette: {
    label: `Palette ${operation}`,
    description: `Palette description ${operation}`,
    icon: "box",
    color: "cyan",
    order: 1,
  },
  editor: { kind: "semt" },
  runtime: { generator: "semt" },
  default_implementation: {
    kind: "semt",
    operation,
    service_id: "",
    parameters: {},
    connection_ref: "default-semt",
  },
});

const parameter = (
  name: string,
  label: string,
  type: SemTCatalog["items"][number]["parameters"][number]["type"],
  required = false,
) => ({
  name,
  label,
  type,
  required,
  description: "",
  options: type === "multi-select"
    ? [{ value: "id", label: "ID" }, { value: "url", label: "URL" }]
    : [],
});

const catalogs = {
  setup: {
    family: "setup",
    catalog_version: "1",
    source: "test",
    warnings: [],
    items: [{
      id: "semt_connection",
      label: "SemT Connection + Table Load",
      description: "Load a SemT table",
      supported: true,
      parameters: [
        parameter("api_base_url", "API Base URL", "string", true),
        parameter("dataset_id", "Dataset ID", "string", true),
        parameter("table_name", "Table Name", "string", true),
      ],
    }],
  },
  reconciliators: {
    family: "reconciliation",
    catalog_version: "1",
    source: "test",
    warnings: [],
    items: [{
      id: "wikidataOpenRefine",
      label: "Linking: Wikidata (OpenRefine)",
      description: "Match mentions to Wikidata entities.",
      supported: true,
      parameters: [parameter("column_name", "Target column", "column", true)],
    }, {
      id: "wikidataAlligator",
      label: "Linking: Wikidata (Alligator)",
      description: "Match mentions to Wikidata entities.",
      supported: true,
      parameters: [
        parameter("column_name", "Target column", "column", true),
        parameter("additionalColumns", "Context columns", "column-list"),
        {
          ...parameter("useLLM", "LLM mode", "boolean"),
          default: false,
        },
      ],
    }, {
      id: "geocodingGeonames",
      label: "Geocoding: Geo Coordinates",
      description: "Link locations to GeoNames entries.",
      supported: true,
      parameters: [
        parameter("column_name", "Target column", "column", true),
        parameter("additionalColumns", "Context columns", "column-list"),
      ],
    }],
  },
  modifications: {
    family: "modification",
    catalog_version: "1",
    source: "test",
    warnings: [],
    items: [{
      id: "dateFormatter",
      label: "Date Formatter",
      description: "Parse and reformat dates.",
      supported: true,
      parameters: [
        parameter("column_name", "Target column", "column", true),
        parameter("formatType", "Output format", "select", true),
        parameter("detailLevel", "Detail level", "select"),
        parameter("outputMode", "Output mode", "select"),
      ],
    }],
  },
  extenders: {
    family: "extension",
    catalog_version: "1",
    source: "test",
    warnings: [],
    items: [{
      id: "reconciledColumnExtWikidata",
      label: "Annotation Properties (Wikidata)",
      description: "Add Wikidata label fields.",
      supported: true,
      parameters: [
        parameter("column_name", "Target column", "column", true),
        parameter("properties", "Label properties", "multi-select", true),
      ],
    }, {
      id: "reconciledColumnExt",
      label: "Annotation Properties",
      description: "Add annotation fields.",
      supported: true,
      parameters: [
        parameter("column_name", "Target column", "column", true),
        parameter("properties", "Properties", "property-list", true),
      ],
    }, {
      id: "meteoPropertiesOpenMeteo",
      label: "Meteo Properties (Open-Meteo)",
      description: "Add weather data.",
      supported: true,
      parameters: [
        parameter("column_name", "Target column", "column", true),
        parameter("granularity", "Data granularity", "select", true),
        parameter("dateColumnName", "Date column", "column", true),
        {
          ...parameter("decimalFormat", "Decimal format", "select"),
          default: ".",
        },
        parameter("properties", "Weather parameters", "multi-select", true),
      ],
    }],
  },
  export: {
    family: "export",
    catalog_version: "1",
    source: "test",
    warnings: [],
    items: [{
      id: "export_table",
      label: "Export Table",
      description: "Download the final table.",
      supported: true,
      parameters: [
        parameter("output_format", "Output Format", "select", true),
        parameter("output_filename", "Output Filename", "string"),
      ],
    }],
  },
} satisfies Record<string, SemTCatalog>;

const nodeDefinitions = [
  definition("semt.setup", "setup"),
  definition("semt.reconciliation", "reconciliation"),
  definition("semt.modification", "modification"),
  definition("semt.extension", "extension"),
  definition("semt.export", "export", "output"),
];

describe("SemT pipeline auto-populator", () => {
  it("uses SemT catalogue node definitions and maps script columns to catalogue parameters", () => {
    const script = `
base_url = args.base_url or get_input_with_default("Enter base URL", "http://example.test")
api_url = base_url + "/api"
dataset_id = args.dataset_id or get_input_with_default("Dataset", "0")
table_name = args.table_name or get_input_with_default("Table", "my_table")
filename = args.csv_file or get_input_with_default("CSV", "table.csv")

# =============================================================================
# OPERATION_1: RECONCILIATION [wikidataOpenRefine]
# Column: Place | Timestamp: 2026-06-29T14:53:13.850Z
# =============================================================================
reconciled_table, backend_payload = reconciliation_manager.reconcile(
    table_data,
    "Place",
    "wikidataOpenRefine",
    [],
    dataset_id=dataset_id,
    table_id=table_id
)

# =============================================================================
# OPERATION_2: MODIFICATION [dateFormatter]
# Column: Foundation date | Timestamp: 2026-06-29T14:54:09.854Z
# =============================================================================
modified_column = "Foundation date"
modified_table, payload = manager.modify(
    table=table_data,
    column_name=modified_column,
    modifier_name="dateFormatter",
    props={
        "formatType": "iso",
        "detailLevel": "hourMinutes",
        "outputMode": "update",
        "selectedColumns": [modified_column]
    }
)

# =============================================================================
# OPERATION_3: EXTENSION [reconciledColumnExtWikidata]
# Column: Point of Interest | Timestamp: 2026-06-29T14:59:17.810Z
# =============================================================================
extended_table, extension_payload = extension_manager.extend_column(
    table=table_data,
    column_name="Point of Interest",
    extender_id="reconciledColumnExtWikidata",
    properties=[],
    other_params={
        "labels": ["id", "url"]
    }
)

# =============================================================================
# OPERATION_4: EXPORT (default)
# =============================================================================
json_file = utility.download_json(
    dataset_id=dataset_id,
    table_id=table_id,
    output_file="results.json"
)
`;

    const pipeline = parseSemTPipelineScript(script);
    const { nodes, edges } = populatePipeline(pipeline, 1, catalogs, nodeDefinitions);

    expect(nodes).toHaveLength(4);
    expect(edges).toHaveLength(3);
    expect(nodes.map((node) => node.data.definition_id)).toEqual([
      "semt.reconciliation",
      "semt.modification",
      "semt.extension",
      "semt.export",
    ]);

    expect(nodes[0].data.label).toBe("Linking: Wikidata (OpenRefine)");
    expect(nodes[0].data.definition_version).toBe(7);
    expect(nodes[0].data.implementation).toMatchObject({
      service_id: "wikidataOpenRefine",
      parameters: { column_name: "Place" },
    });
    expect(nodes[0].data.configuration_status).toBe("valid");

    expect(nodes[1].data.implementation).toMatchObject({
      service_id: "dateFormatter",
      parameters: {
        column_name: "Foundation date",
        formatType: "iso",
        detailLevel: "hourMinutes",
        outputMode: "update",
      },
    });

    expect(nodes[2].data.implementation).toMatchObject({
      service_id: "reconciledColumnExtWikidata",
      parameters: {
        column_name: "Point of Interest",
        properties: ["id", "url"],
      },
    });

    expect(nodes[3].data.type).toBe("output");
    expect(nodes[3].data.implementation).toMatchObject({
      service_id: "export_table",
      parameters: {
        output_format: "json",
        output_filename: "results",
      },
    });
  });

  it("maps a non-museum script with context columns and weather extension parameters", () => {
    const script = `
dataset_id = args.dataset_id or get_input_with_default("Dataset", "114")
table_name = args.table_name or get_input_with_default("Table", "my_table")
filename = args.csv_file or get_input_with_default("CSV", "table.csv")

# =============================================================================
# OPERATION_1: RECONCILIATION [wikidataAlligator]
# Column: City | Timestamp: 2026-06-01T12:27:50.690Z
# =============================================================================
reconciled_table, backend_payload = reconciliation_manager.reconcile(
    table_data,
    "City",
    "wikidataAlligator",
    [],
    dataset_id=dataset_id,
    table_id=table_id
)

# =============================================================================
# OPERATION_2: RECONCILIATION [geocodingGeonames]
# Column: County | Timestamp: 2026-06-01T12:28:57.589Z
# =============================================================================
reconciled_table, backend_payload = reconciliation_manager.reconcile(
    table_data,
    "County",
    "geocodingGeonames",
    ["Country", "City"],
    dataset_id=dataset_id,
    table_id=table_id
)

# =============================================================================
# OPERATION_3: EXTENSION [reconciledColumnExt]
# Column: County | Timestamp: 2026-06-29T14:58:42.079Z
# =============================================================================
extended_table, extension_payload = extension_manager.extend_column(
    table=table_data,
    column_name="County",
    extender_id="reconciledColumnExt",
    properties=[],
    other_params={
        "property": ["name", "id"]
    }
)

# =============================================================================
# OPERATION_4: MODIFICATION [dateFormatter]
# Column: Fecha_id | Timestamp: 2026-06-29T14:59:01.372Z
# =============================================================================
modified_column = "Fecha_id"
modified_table, payload = manager.modify(
    table=table_data,
    column_name=modified_column,
    modifier_name="dateFormatter",
    props={
        "formatType": "iso",
        "detailLevel": "hourMinutes",
        "outputMode": "update",
        "selectedColumns": [modified_column]
    }
)

# =============================================================================
# OPERATION_5: EXTENSION [meteoPropertiesOpenMeteo]
# Column: County | Timestamp: 2026-06-29T14:59:22.626Z
# =============================================================================
_dates_col = "Fecha_id"
dates = {row_id: [table_data["rows"][row_id]["cells"][_dates_col]["label"], [], _dates_col] for row_id in table_data["rows"]}
extended_table, extension_payload = extension_manager.extend_column(
    table=table_data,
    column_name="County",
    extender_id="meteoPropertiesOpenMeteo",
    properties=[],
    other_params={
        "dates": dates,
        "granularity": "daily",
        "weatherParams_daily": ["light_hours", "apparent_temperature_max", "apparent_temperature_min"],
        "weatherParams_hourly": [],
        "decimalFormat": []
    }
)

# =============================================================================
# OPERATION_6: EXPORT (default)
# =============================================================================
json_file = utility.download_json(
    dataset_id=dataset_id,
    table_id=table_id,
    output_file="results.json"
)
`;

    const pipeline = parseSemTPipelineScript(script);
    const { nodes } = populatePipeline(pipeline, 1, catalogs, nodeDefinitions);

    expect(nodes).toHaveLength(6);
    expect(nodes.map((node) => node.data.definition_id)).toEqual([
      "semt.reconciliation",
      "semt.reconciliation",
      "semt.extension",
      "semt.modification",
      "semt.extension",
      "semt.export",
    ]);

    expect(nodes[0].data.implementation).toMatchObject({
      service_id: "wikidataAlligator",
      parameters: {
        column_name: "City",
        additionalColumns: [],
        useLLM: false,
      },
    });
    expect(nodes[1].data.implementation).toMatchObject({
      service_id: "geocodingGeonames",
      parameters: {
        column_name: "County",
        additionalColumns: ["Country", "City"],
      },
    });
    expect(nodes[2].data.implementation).toMatchObject({
      service_id: "reconciledColumnExt",
      parameters: {
        column_name: "County",
        properties: ["name", "id"],
      },
    });
    expect(nodes[4].data.implementation).toMatchObject({
      service_id: "meteoPropertiesOpenMeteo",
      parameters: {
        column_name: "County",
        granularity: "daily",
        dateColumnName: "Fecha_id",
        decimalFormat: ".",
        properties: [
          "light_hours",
          "apparent_temperature_max",
          "apparent_temperature_min",
        ],
      },
    });
  });
});
