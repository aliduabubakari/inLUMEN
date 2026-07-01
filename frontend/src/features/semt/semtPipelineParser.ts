import type { SemTImplementation } from "@/features/semt/types";

// ── Public types ────────────────────────────────────────────────────────────

export type ParsedSemTOperation = {
  operation: SemTImplementation["operation"];
  service_id: string;
  column?: string;
  parameters: Record<string, unknown>;
  timestamp?: string;
};

export type SemTPipelineSetup = {
  base_url?: string;
  api_url?: string;
  dataset_id?: string;
  table_name?: string;
  csv_file?: string;
};

export type SemTPipeline = {
  setup: SemTPipelineSetup;
  operations: ParsedSemTOperation[];
  parse_warnings: string[];
};

// ── Operation type mapping ──────────────────────────────────────────────────

const OPERATION_MAP: Record<string, SemTImplementation["operation"]> = {
  RECONCILIATION: "reconciliation",
  MODIFICATION: "modification",
  EXTENSION: "extension",
  EXPORT: "export",
  SETUP: "setup",
};

const OPERATION_HEADER_RE = /^#\s*OPERATION_(\d+):\s*(\w+)\s*\[([^\]]+)\]/m;
const COLUMN_LINE_RE = /^#\s*Column:\s*(.+?)\s*\|\s*Timestamp:\s*(.+)/m;
const SECTION_SEPARATOR = /^#\s*=+\s*$/m;

// ── Setup extractors ────────────────────────────────────────────────────────

const extractSetup = (script: string): SemTPipelineSetup => {
  const setup: SemTPipelineSetup = {};

  // base_url
  const baseUrlMatch = script.match(
    /base_url\s*=\s*args\.base_url\s+or\s+get_input_with_default\s*\(\s*[^,]+,\s*"([^"]*)"/
  );
  if (baseUrlMatch) setup.base_url = baseUrlMatch[1];

  // api_url derived from base_url
  const apiUrlMatch = script.match(/api_url\s*=\s*base_url\s*\+\s*"([^"]*)"/);
  if (apiUrlMatch) setup.api_url = apiUrlMatch[1];

  // dataset_id
  const datasetMatch = script.match(
    /dataset_id\s*=\s*args\.dataset_id\s+or\s+get_input_with_default\s*\(\s*[^,]+,\s*"([^"]*)"/
  );
  if (datasetMatch) setup.dataset_id = datasetMatch[1];

  // table_name
  const tableMatch = script.match(
    /table_name\s*=\s*args\.table_name\s+or\s+get_input_with_default\s*\(\s*[^,]+,\s*"([^"]*)"/
  );
  if (tableMatch) setup.table_name = tableMatch[1];

  // csv_file / filename
  const csvMatch = script.match(
    /filename\s*=\s*args\.csv_file\s+or\s+get_input_with_default\s*\(\s*[^,]+,\s*"([^"]*)"/
  );
  if (csvMatch) setup.csv_file = csvMatch[1];

  return setup;
};

// ── JSON-like dict extraction (supports nested, multiline) ──────────────────

/**
 * Extract a JSON-like Python dict from a string starting at `startTag`.
 * Handles nested braces and strings.
 */
const extractPythonDict = (
  text: string,
  startTag: string,
): Record<string, unknown> | null => {
  const startIdx = text.indexOf(startTag);
  if (startIdx === -1) return null;

  let pos = startIdx + startTag.length;
  let depth = 0;
  let inString = false;
  let stringChar = "";
  let escaped = false;
  let started = false;

  for (; pos < text.length; pos++) {
    const ch = text[pos];

    if (escaped) {
      escaped = false;
      continue;
    }

    if (inString) {
      if (ch === "\\") {
        escaped = true;
      } else if (ch === stringChar) {
        inString = false;
      }
      continue;
    }

    if (ch === '"' || ch === "'") {
      inString = true;
      stringChar = ch;
      continue;
    }

    if (ch === "{" || ch === "[") {
      depth++;
      started = true;
      continue;
    }

    if (ch === "}" || ch === "]") {
      depth--;
      if (started && depth === 0) {
        const dictStr = text.slice(startIdx + startTag.length, pos + 1);
        return parsePythonDictToJSON(dictStr);
      }
      continue;
    }
  }

  return null;
};

/**
 * Crude Python dict/list → JSON conversion.
 * Handles: strings, numbers, booleans, null/None, nested dicts, lists.
 */
const parsePythonDictToJSON = (raw: string): Record<string, unknown> => {
  // Replace Python literals with JSON equivalents
  let json = raw
    .replace(/None/g, "null")
    .replace(/True/g, "true")
    .replace(/False/g, "false");

  // Quote unquoted keys:  word:  →  "word":
  json = json.replace(/([{,]\s*)([a-zA-Z_]\w*)\s*:/g, '$1"$2":');

  // Quote bare Python identifiers inside arrays (e.g. [modified_column] → ["modified_column"])
  json = json.replace(/\[([^\]]*)\]/g, (_match: string, inner: string) => {
    const fixed = inner.replace(
      /(^|,\s*)([a-zA-Z_]\w*)(\s*,|\s*$)/g,
      '$1"$2"$3',
    );
    return `[${fixed}]`;
  });

  // Try JSON.parse, with fallback
  try {
    return JSON.parse(json);
  } catch {
    // If direct parse fails, try to salvage
    const cleaned = json
      .replace(/,\s*}/g, "}")
      .replace(/,\s*]/g, "]")
      // Quote bare identifiers used as dict values
      .replace(/:\s*([a-zA-Z_]\w*)(\s*[,}\]])/g, ':"$1"$2');
    try {
      return JSON.parse(cleaned);
    } catch {
      return {};
    }
  }
};

// ── Operation block parsers ─────────────────────────────────────────────────

const extractReconciliationParams = (
  blockText: string,
  column: string | undefined,
): Record<string, unknown> => {
  const params: Record<string, unknown> = {};
  if (column) params.column = column;

  // Try to extract context columns list (the 4th arg to reconcile)
  const propsMatch = blockText.match(
    /reconciliation_manager\.reconcile\s*\([^)]*?,\s*"[^"]*",\s*"[^"]*",\s*(\[[^\]]*\])/s
  );
  if (propsMatch) {
    try {
      const propsStr = propsMatch[1]
        .replace(/None/g, "null")
        .replace(/True/g, "true")
        .replace(/False/g, "false");
      params.additionalColumns = JSON.parse(propsStr);
    } catch {
      // ignore
    }
  }

  return params;
};

const extractModificationParams = (
  blockText: string,
  column: string | undefined,
): Record<string, unknown> => {
  const params: Record<string, unknown> = {};

  if (column) {
    params.selectedColumns = [column];
  }

  // Extract props dict
  const props = extractPythonDict(blockText, "props=");
  if (props) {
    Object.assign(params, props);
    // Fix up variable references in selectedColumns
    if (column && Array.isArray(params.selectedColumns)) {
      params.selectedColumns = (params.selectedColumns as string[]).map(
        (c: string) =>
          /^[a-z_]\w*$/.test(c) && c !== column ? column : c,
      );
    }
  }

  // Also try modifier_name
  const modifierMatch = blockText.match(
    /modifier_name\s*=\s*"([^"]*)"/
  );
  if (modifierMatch && !params.modifier_name) {
    params.modifier_name = modifierMatch[1];
  }

  // column_name
  const colMatch = blockText.match(/column_name\s*=\s*"([^"]*)"/);
  if (colMatch && !params.column) {
    params.column = colMatch[1];
  }

  return params;
};

const extractExtensionParams = (
  blockText: string,
  column: string | undefined,
): Record<string, unknown> => {
  const params: Record<string, unknown> = {};

  if (column) params.column = column;

  // Extract properties list
  const propsMatch = blockText.match(/properties\s*=\s*(\[[^\]]*\])/s);
  if (propsMatch) {
    try {
      const cleaned = propsMatch[1]
        .replace(/None/g, "null")
        .replace(/True/g, "true")
        .replace(/False/g, "false");
      params.properties = JSON.parse(cleaned);
    } catch {
      // ignore
    }
  }

  // Extract other_params dict
  const otherParams = extractPythonDict(blockText, "other_params=");
  if (otherParams) {
    Object.assign(params, otherParams);
  }

  const dateColumnMatch = blockText.match(/(?:date|dates|_dates)_col(?:umn)?\s*=\s*"([^"]+)"/i);
  if (dateColumnMatch && !params.dateColumnName) {
    params.dateColumnName = dateColumnMatch[1];
  }

  return params;
};

const extractExportParams = (
  blockText: string,
): Record<string, unknown> => {
  const params: Record<string, unknown> = {};

  // Check what kind of export
  if (blockText.includes("download_json")) {
    params.format = "json";
    const fileMatch = blockText.match(/output_file\s*=\s*"([^"]*)"/);
    if (fileMatch) params.output_file = fileMatch[1];
  } else if (blockText.includes("download_csv")) {
    params.format = "csv";
  } else {
    params.format = "default";
  }

  return params;
};

// ── Main parser ─────────────────────────────────────────────────────────────

/**
 * Parse a SemT pipeline Python script into structured data.
 * Extracts setup configuration and operation blocks.
 */
export const parseSemTPipelineScript = (
  script: string,
): SemTPipeline => {
  const warnings: string[] = [];
  const setup = extractSetup(script);
  const operations: ParsedSemTOperation[] = [];

  // Split the script by section separators to find operation blocks
  // Strategy: find all OPERATION_N headers, then extract the try block after each

  // Find all operation headers with their positions
  const opHeaderRe =
    /#\s*=+\s*\n#\s*OPERATION_(\d+):\s*(\w+)\s*(?:\[([^\]]+)\]|\(([^)]+)\))?\s*\n(?:#\s*Column:\s*(.+?)\s*\|\s*Timestamp:\s*(.+?)\s*\n)?#\s*=+\s*\n/gi;

  const matches: Array<{
    index: number;
    endIndex: number;
    number: string;
    type: string;
    service: string;
    column?: string;
    timestamp?: string;
  }> = [];

  let match: RegExpExecArray | null;
  const headerRe = new RegExp(opHeaderRe.source, opHeaderRe.flags);
  while ((match = headerRe.exec(script)) !== null) {
    matches.push({
      index: match.index,
      endIndex: match.index + match[0].length,
      number: match[1],
      type: match[2].toUpperCase(),
      service: match[3] || match[4] || "",
      column: match[5] ? match[5].trim() : undefined,
      timestamp: match[6] ? match[6].trim() : undefined,
    });
  }

  // For each match, extract the try block that follows
  for (let i = 0; i < matches.length; i++) {
    const current = matches[i];
    const nextIndex =
      i + 1 < matches.length ? matches[i + 1].index : script.length;
    const blockText = script.slice(current.endIndex, nextIndex);

    const opType = OPERATION_MAP[current.type];
    if (!opType) {
      warnings.push(
        `Unknown operation type "${current.type}" at OPERATION_${current.number}. Skipping.`,
      );
      continue;
    }

    let parameters: Record<string, unknown> = {};

    switch (opType) {
      case "reconciliation":
        parameters = extractReconciliationParams(blockText, current.column);
        break;
      case "modification":
        parameters = extractModificationParams(blockText, current.column);
        break;
      case "extension":
        parameters = extractExtensionParams(blockText, current.column);
        break;
      case "export":
        parameters = extractExportParams(blockText);
        break;
    }

    operations.push({
      operation: opType,
      service_id:
        current.service && current.service !== "default"
          ? current.service
          : opType === "export"
            ? "export_table"
            : current.service,
      column: current.column,
      parameters,
      timestamp: current.timestamp,
    });
  }

  // If no operations were found via headers, try the summary section
  if (operations.length === 0) {
    const summaryRe =
      /#\s*-\s*(\w+)\s+on\s+'([^']+)'\s+\[([^\]]+)\]\s+@\s+(\S+)/g;
    while ((match = summaryRe.exec(script)) !== null) {
      const opType = OPERATION_MAP[match[1].toUpperCase()];
      if (!opType) {
        warnings.push(
          `Unknown operation type "${match[1]}" in summary. Skipping.`,
        );
        continue;
      }
      operations.push({
        operation: opType,
        service_id: match[3],
        column: match[2],
        parameters: { column: match[2] },
        timestamp: match[4],
      });
    }

    if (operations.length === 0) {
      warnings.push(
        "No SemT operations detected in the script. Ensure the script contains OPERATION headers or a summary section.",
      );
    } else {
      warnings.push(
        "Operations extracted from summary only. Parameters may be incomplete — full try-block parsing was not available.",
      );
    }
  }

  return {
    setup,
    operations,
    parse_warnings: warnings,
  };
};

/**
 * Group operations into a recommended node order.
 * Reconciliations/modifications/extensions in order, export last.
 */
export const getOperationOrder = (
  operations: ParsedSemTOperation[],
): ParsedSemTOperation[] => {
  const exportOps = operations.filter((op) => op.operation === "export");
  const nonExportOps = operations.filter((op) => op.operation !== "export");
  return [...nonExportOps, ...exportOps];
};
