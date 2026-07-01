import type { SemTCatalog, SemTCatalogItem } from "@/features/semt/types";
import type { ParsedSemTOperation } from "@/features/semt/semtPipelineParser";

// ── Common parameter name aliases ──────────────────────────────────────────
// Maps script-side names → likely catalog-side names

const PARAM_ALIASES: Record<string, string[]> = {
  // column field (single column)
  column: ["column", "target_column", "targetColumn", "columnName", "column_name", "selectedColumn", "selected_column", "baseColumn", "base_column", "reconciledColumn", "reconciled_column"],
  // column lists
  selectedColumns: ["selectedColumns", "columns", "column_list", "columnList", "column_name", "target_column", "target_columns", "targetColumns", "targetColumnsList"],
  additionalColumns: ["additionalColumns", "optional_columns", "context_columns", "contextColumns", "columns"],
  // labels/properties for extension
  labels: ["labels", "properties", "property_list", "propertyList", "props", "extract", "extensions"],
  property: ["property", "properties", "property_list", "propertyList"],
  // properties (may be same key as labels, but empty list vs actual values)
  properties: ["properties", "property_list", "propertyList", "additionalColumns", "optional_columns"],
  weatherParams_daily: ["weatherParams_daily", "weatherParamsDaily", "properties"],
  weatherParams_hourly: ["weatherParams_hourly", "weatherParamsHourly", "properties"],
  // format type
  formatType: ["formatType", "format_type", "format", "dateFormat", "date_format"],
  // detail level
  detailLevel: ["detailLevel", "detail_level", "precision", "detail"],
  dateColumnName: ["dateColumnName", "date_column_name", "dateColumn", "date_column"],
  // output mode
  outputMode: ["outputMode", "output_mode", "mode", "writeMode", "write_mode"],
  // setup
  api_url: ["api_url", "api_base_url", "apiBaseUrl", "base_url", "baseUrl"],
  base_url: ["base_url", "api_base_url", "apiBaseUrl", "api_url"],
  // export
  format: ["format", "output_format", "outputFormat"],
  output_file: ["output_file", "output_filename", "outputFilename", "filename", "file_name"],
};

/**
 * Try to find a matching catalog parameter for a given script-side parameter name.
 * Returns the catalog parameter name if found, or null.
 */
const isEmptyValue = (value: unknown): boolean => {
  if (value == null) return true;
  if (typeof value === "string") return value.trim().length === 0;
  if (Array.isArray(value)) return value.length === 0;
  if (typeof value === "object") return Object.keys(value as object).length === 0;
  return false;
};

const findMatchingCatalogParam = (
  scriptParamName: string,
  item: SemTCatalogItem,
): string | null => {
  const catalogNames = new Set(item.parameters.map((p) => p.name));

  // 1. Exact match
  if (catalogNames.has(scriptParamName)) return scriptParamName;

  // 2. Check aliases
  const aliases = PARAM_ALIASES[scriptParamName];
  if (aliases) {
    for (const alias of aliases) {
      if (catalogNames.has(alias)) return alias;
    }
  }

  // 3. Case-insensitive match
  const lower = scriptParamName.toLowerCase();
  for (const name of catalogNames) {
    if (name.toLowerCase() === lower) return name;
  }

  return null;
};

/**
 * Map raw script-extracted parameters to catalog parameter names.
 * Returns a new parameters object with catalog-compatible keys.
 */
export const mapParametersToCatalog = (
  operation: ParsedSemTOperation,
  catalog: SemTCatalog,
): Record<string, unknown> => {
  const item = findCatalogItem(operation.service_id, catalog);
  if (!item) {
    // Service not in catalog — return raw params as-is
    return { ...operation.parameters };
  }

  const mapped: Record<string, unknown> = {};

  // For each raw parameter, try to map to a catalog parameter
  for (const [rawKey, rawValue] of Object.entries(operation.parameters)) {
    const catalogKey = findMatchingCatalogParam(rawKey, item);
    if (catalogKey) {
      const catalogParam = item.parameters.find((p) => p.name === catalogKey);
      if (
        catalogParam?.type === "select" &&
        Array.isArray(rawValue) &&
        rawValue.length === 0
      ) {
        continue;
      }
      const normalizedValue =
        catalogKey === "column_name" && Array.isArray(rawValue)
          ? rawValue[0]
          : catalogParam?.type === "column" && Array.isArray(rawValue)
            ? rawValue[0]
          : catalogKey === "output_filename" && typeof rawValue === "string"
            ? rawValue.replace(/\.(json|csv)$/i, "")
            : rawValue;
      // If already mapped, prefer non-empty values over empty ones
      // (e.g. labels: ["id","url"] should win over properties: [])
      const existing = mapped[catalogKey];
      if (!(catalogKey in mapped)) {
        mapped[catalogKey] = normalizedValue;
      } else if (isEmptyValue(existing) && !isEmptyValue(normalizedValue)) {
        mapped[catalogKey] = normalizedValue;
      }
    }
  }

  // Ensure column parameter is mapped if present
  if (operation.column && !Object.keys(mapped).some((key) => key.toLowerCase().includes("column"))) {
    // Try to find the column-type parameter in the catalog
    const columnParam = item.parameters.find(
      (p) =>
        p.type === "column" ||
        p.type === "column-list" ||
        p.name.toLowerCase().includes("column"),
    );
    if (columnParam) {
      if (columnParam.type === "column-list") {
        mapped[columnParam.name] = [operation.column];
      } else {
        mapped[columnParam.name] = operation.column;
      }
    } else {
      // Fallback: use "column" key
      mapped.column = operation.column;
    }
  }

  return mapped;
};

/**
 * Find the catalog item that matches an operation's service_id.
 * Tries exact match, then case-insensitive, then partial match.
 */
export const findCatalogItem = (
  serviceId: string,
  catalog: SemTCatalog,
): SemTCatalogItem | undefined => {
  const trimmedServiceId = serviceId.trim();
  if (!trimmedServiceId) return undefined;

  // Exact match
  const exact = catalog.items.find((i) => i.id === trimmedServiceId);
  if (exact) return exact;

  // Case-insensitive
  const lower = trimmedServiceId.toLowerCase();
  const ci = catalog.items.find((i) => i.id.toLowerCase() === lower);
  if (ci) return ci;

  // Partial match (serviceId contains catalog id or vice versa)
  const partial = catalog.items.find(
    (i) => {
      const itemId = i.id.toLowerCase();
      return itemId.includes(lower) || lower.includes(itemId);
    },
  );
  return partial;
};
