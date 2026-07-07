import { describe, expect, it } from "vitest";
import {
  buildSemTPipelineGraphFromPython,
  isSemTPythonScript,
} from "@/features/semt/semtPythonImport";

const sampleSemTScript = `
import semt_py
from semt_py.reconciliation_manager import ReconciliationManager
from semt_py.extension_manager import ExtensionManager
from semt_py.modification_manager import ModificationManager

base_url = args.base_url or get_input_with_default(
    "Enter base URL or press Enter to keep default", "http://vm.chronos.disco.unimib.it:3003")
username = args.username or get_input_with_default("Enter your username", "")
default_password = ""
dataset_id = args.dataset_id or get_input_with_default(
    "Enter dataset_id or press Enter to keep default", "114")
table_name = args.table_name or get_input_with_default(
    "Enter table_name or press Enter to keep default", "my_table")
filename = args.csv_file or get_input_with_default(
    "Enter path to CSV file or press Enter to keep default", "table.csv")

# =============================================================================
# OPERATION_1: RECONCILIATION [wikidataAlligator]
# Column: City | Timestamp: 2026-06-01T12:27:50.690Z
# =============================================================================
reconciliation_manager.reconcile(
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
reconciliation_manager.reconcile(
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
base_column = "County"
extension_manager.extend_column(
    table=table_data,
    column_name=base_column,
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
manager.modify(
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
base_column = "County"
_dates_col = "Fecha_id"
extension_manager.extend_column(
    table=table_data,
    column_name=base_column,
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
utility.download_json(
    dataset_id=dataset_id,
    table_id=table_id,
    output_file="results.json"
)
`;

describe("SemT Python import", () => {
  it("detects SemT exported scripts", () => {
    expect(isSemTPythonScript(sampleSemTScript)).toBe(true);
    expect(isSemTPythonScript("print('hello')")).toBe(false);
  });

  it("builds an importable graph from SemT Python operations", () => {
    const graph = buildSemTPipelineGraphFromPython(sampleSemTScript);

    expect(graph).not.toBeNull();
    expect(graph?.nodes).toHaveLength(8);
    expect(graph?.edges).toHaveLength(7);
    expect(graph?.nodes?.[0].data.definition_id).toBe("core.input-data");
    expect(graph?.nodes?.[1].data.definition_id).toBe("semt.setup");
    expect(graph?.nodes?.[2].data.implementation).toMatchObject({
      operation: "reconciliation",
      service_id: "wikidataAlligator",
      parameters: {
        column_name: "City",
      },
    });
    expect(graph?.nodes?.[3].data.implementation).toMatchObject({
      operation: "reconciliation",
      service_id: "geocodingGeonames",
      parameters: {
        column_name: "County",
        additionalColumns: ["Country", "City"],
      },
    });
    expect(graph?.nodes?.[4].data.implementation).toMatchObject({
      operation: "extension",
      service_id: "reconciledColumnExt",
      parameters: {
        column_name: "County",
        properties: ["name", "id"],
      },
    });
    expect(graph?.nodes?.[5].data.implementation).toMatchObject({
      operation: "modification",
      service_id: "dateFormatter",
      parameters: {
        column_name: "Fecha_id",
        formatType: "iso",
      },
    });
    expect(graph?.nodes?.[6].data.implementation).toMatchObject({
      operation: "extension",
      service_id: "meteoPropertiesOpenMeteo",
      parameters: {
        column_name: "County",
        dateColumnName: "Fecha_id",
        properties: ["light_hours", "apparent_temperature_max", "apparent_temperature_min"],
      },
    });
    expect(graph?.nodes?.[7].data.implementation).toMatchObject({
      operation: "export",
      service_id: "export_table",
      parameters: {
        output_format: "json",
        output_filename: "results",
      },
    });
  });
});
