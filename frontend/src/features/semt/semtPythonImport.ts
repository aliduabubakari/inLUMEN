import type { Edge, Node } from "reactflow";
import type { PipelineVersionGraph } from "@/features/flow/flowPersistence";

type SemTImportedOperation =
  | "reconciliation"
  | "extension"
  | "modification"
  | "export";

type ParsedOperation = {
  index: number;
  operation: SemTImportedOperation;
  serviceId: string;
  columnName: string;
  parameters: Record<string, unknown>;
};

type NodeData = Record<string, unknown>;

const nodePosition = (index: number) => ({
  x: 120 + index * 260,
  y: index === 0 ? 140 : 220,
});

const node = (
  id: string,
  index: number,
  data: NodeData,
): Node<NodeData> => ({
  id,
  type: "custom",
  position: nodePosition(index),
  data,
});

const edge = (source: string, target: string): Edge => ({
  id: `reactflow__edge-${source}-${target}`,
  source,
  target,
});

const quotedStrings = (value: string): string[] => {
  const strings: string[] = [];
  const matcher = /(["'])((?:\\.|(?!\1).)*)\1/g;
  let match: RegExpExecArray | null;
  while ((match = matcher.exec(value)) !== null) {
    strings.push(match[2].replace(/\\(["'\\])/g, "$1"));
  }
  return strings;
};

const extractAssignedDefault = (source: string, variableName: string) => {
  const assignmentIndex = source.search(new RegExp(`\\b${variableName}\\s*=`));
  if (assignmentIndex < 0) return "";
  const assignmentText = source.slice(assignmentIndex, assignmentIndex + 500);
  const defaultCallIndex = assignmentText.indexOf("get_input_with_default(");
  if (defaultCallIndex < 0) return "";
  const values = quotedStrings(assignmentText.slice(defaultCallIndex));
  return values[values.length - 1] ?? "";
};

const extractAssignedString = (source: string, variableName: string) => {
  const match = source.match(new RegExp(`\\b${variableName}\\s*=\\s*(["'])(.*?)\\1`));
  return match?.[2] ?? "";
};

const extractBlockAssignedString = (block: string, variableName: string) =>
  extractAssignedString(block, variableName);

const parseStringArray = (value: string): string[] =>
  quotedStrings(value).filter((item) => item.trim().length > 0);

const parseObjectLike = (value: string): Record<string, unknown> => {
  const result: Record<string, unknown> = {};
  const matcher = /(["'])([^"']+)\1\s*:\s*(\[[\s\S]*?\]|(["'])(.*?)\4|-?\d+(?:\.\d+)?|True|False|None)/g;
  let match: RegExpExecArray | null;
  while ((match = matcher.exec(value)) !== null) {
    const key = match[2];
    const rawValue = match[3].trim();
    if (rawValue.startsWith("[") && rawValue.endsWith("]")) {
      result[key] = parseStringArray(rawValue);
    } else if (rawValue === "True") {
      result[key] = true;
    } else if (rawValue === "False") {
      result[key] = false;
    } else if (rawValue === "None") {
      result[key] = "";
    } else if (match[5] != null) {
      result[key] = match[5];
    } else {
      const parsedNumber = Number(rawValue);
      result[key] = Number.isFinite(parsedNumber) ? parsedNumber : rawValue;
    }
  }
  return result;
};

const extractBalancedAfter = (
  source: string,
  marker: string,
  openChar: "{" | "(" | "[",
  closeChar: "}" | ")" | "]",
) => {
  const markerIndex = source.indexOf(marker);
  if (markerIndex < 0) return "";
  const start = source.indexOf(openChar, markerIndex + marker.length);
  if (start < 0) return "";

  let depth = 0;
  let quote: string | null = null;
  let escaping = false;
  for (let index = start; index < source.length; index += 1) {
    const char = source[index];
    if (quote) {
      if (escaping) {
        escaping = false;
      } else if (char === "\\") {
        escaping = true;
      } else if (char === quote) {
        quote = null;
      }
      continue;
    }
    if (char === "'" || char === '"') {
      quote = char;
      continue;
    }
    if (char === openChar) depth += 1;
    if (char === closeChar) depth -= 1;
    if (depth === 0) return source.slice(start, index + 1);
  }
  return "";
};

const extractCall = (block: string, marker: string) =>
  extractBalancedAfter(block, marker, "(", ")");

const extractKeywordString = (source: string, keyword: string) => {
  const match = source.match(new RegExp(`${keyword}\\s*=\\s*(["'])(.*?)\\1`));
  return match?.[2] ?? "";
};

const extractKeywordArray = (source: string, keyword: string) => {
  const match = source.match(new RegExp(`${keyword}\\s*=\\s*(\\[[\\s\\S]*?\\])`));
  return match ? parseStringArray(match[1]) : [];
};

const extractOtherParams = (source: string) => {
  const markerIndex = source.indexOf("other_params");
  if (markerIndex < 0) return {};
  return parseObjectLike(extractBalancedAfter(source.slice(markerIndex), "=", "{", "}"));
};

const parseReconciliation = (
  index: number,
  block: string,
  headerServiceId: string,
  headerColumnName: string,
): ParsedOperation => {
  const call = extractCall(block, "reconciliation_manager.reconcile");
  const values = quotedStrings(call);
  const columnName = headerColumnName || values[0] || "";
  const serviceId = headerServiceId || values[1] || "";
  const optionalColumns = extractKeywordArray(call, "optional_columns");
  const positionalColumns = values.slice(2);

  return {
    index,
    operation: "reconciliation",
    serviceId,
    columnName,
    parameters: {
      column_name: columnName,
      additionalColumns: optionalColumns.length > 0 ? optionalColumns : positionalColumns,
      optional_columns: optionalColumns.length > 0 ? optionalColumns : positionalColumns,
    },
  };
};

const parseExtension = (
  index: number,
  block: string,
  headerServiceId: string,
  headerColumnName: string,
): ParsedOperation => {
  const call = extractCall(block, "extension_manager.extend_column");
  const otherParams = extractOtherParams(call);
  const granularity = String(otherParams.granularity || "daily");
  const weatherParamsKey = granularity === "hourly"
    ? "weatherParams_hourly"
    : "weatherParams_daily";
  const properties = [
    ...extractKeywordArray(call, "properties"),
    ...(
      Array.isArray(otherParams.property)
        ? otherParams.property as string[]
        : []
    ),
    ...(
      Array.isArray(otherParams.properties)
        ? otherParams.properties as string[]
        : []
    ),
    ...(
      Array.isArray(otherParams[weatherParamsKey])
        ? otherParams[weatherParamsKey] as string[]
        : []
    ),
  ].filter((item, itemIndex, items) => item && items.indexOf(item) === itemIndex);

  const dateColumnName =
    extractBlockAssignedString(block, "_dates_col") ||
    String(otherParams.dateColumnName || "");
  const columnName =
    headerColumnName ||
    extractBlockAssignedString(block, "base_column") ||
    extractKeywordString(call, "column_name");
  const serviceId =
    headerServiceId ||
    extractKeywordString(call, "extender_id");

  return {
    index,
    operation: "extension",
    serviceId,
    columnName,
    parameters: {
      column_name: columnName,
      properties,
      ...(granularity ? { granularity } : {}),
      ...(dateColumnName ? { dateColumnName } : {}),
      ...(otherParams.decimalFormat ? { decimalFormat: otherParams.decimalFormat } : {}),
      other_params: otherParams,
    },
  };
};

const parseModification = (
  index: number,
  block: string,
  headerServiceId: string,
  headerColumnName: string,
): ParsedOperation => {
  const call = extractCall(block, "manager.modify");
  const props = parseObjectLike(extractBalancedAfter(call, "props", "{", "}"));
  const columnName =
    headerColumnName ||
    extractBlockAssignedString(block, "modified_column") ||
    extractKeywordString(call, "column_name");
  const serviceId =
    headerServiceId ||
    extractKeywordString(call, "modifier_name");

  return {
    index,
    operation: "modification",
    serviceId,
    columnName,
    parameters: {
      column_name: columnName,
      ...props,
    },
  };
};

const parseExport = (index: number, block: string): ParsedOperation => {
  const isCsv = block.includes("download_csv");
  const outputFile = extractKeywordString(block, "output_file");
  const outputFormat = isCsv ? "csv" : "json";
  const outputFilename = outputFile
    ? outputFile.replace(/\.(json|csv)$/i, "")
    : "exported_data";

  return {
    index,
    operation: "export",
    serviceId: "export_table",
    columnName: "",
    parameters: {
      output_format: outputFormat,
      output_filename: outputFilename,
    },
  };
};

const parseOperations = (source: string): ParsedOperation[] => {
  const headerRegex = /^# OPERATION_(\d+):\s*([A-Z]+)(?:\s*\[([^\]]+)\])?.*$/gm;
  const headers = Array.from(source.matchAll(headerRegex));
  return headers.flatMap((header, headerIndex) => {
    const blockStart = header.index ?? 0;
    const blockEnd = headers[headerIndex + 1]?.index ?? source.length;
    const block = source.slice(blockStart, blockEnd);
    const index = Number(header[1]);
    const operationLabel = header[2].toLowerCase();
    const serviceId = (header[3] || "").trim();
    const columnName = block.match(/^# Column:\s*([^|]+?)(?:\s*\||$)/m)?.[1]?.trim() || "";

    if (operationLabel === "reconciliation") {
      return [parseReconciliation(index, block, serviceId, columnName)];
    }
    if (operationLabel === "extension") {
      return [parseExtension(index, block, serviceId, columnName)];
    }
    if (operationLabel === "modification") {
      return [parseModification(index, block, serviceId, columnName)];
    }
    if (operationLabel === "export") {
      return [parseExport(index, block)];
    }
    return [];
  });
};

const semtDefinitionForOperation = (operation: SemTImportedOperation) => {
  if (operation === "reconciliation") return "semt.reconciliation";
  if (operation === "extension") return "semt.extension";
  if (operation === "export") return "semt.export";
  return "semt.modification";
};

const labelForOperation = (operation: ParsedOperation) => {
  if (operation.operation === "reconciliation") {
    return `Reconcile ${operation.columnName || "Column"}`;
  }
  if (operation.operation === "extension") {
    return `Extend ${operation.columnName || "Column"}`;
  }
  if (operation.operation === "modification") {
    return `Modify ${operation.columnName || "Column"}`;
  }
  return "SemT Export";
};

const descriptionForOperation = (operation: ParsedOperation) => {
  if (operation.operation === "export") {
    return `Export the final SemT table as ${operation.parameters.output_format || "json"}.`;
  }
  return `${operation.operation} using ${operation.serviceId || "a SemT service"}.`;
};

export const isSemTPythonScript = (source: string) =>
  /import\s+semt_py/.test(source) && /# OPERATION_\d+:/m.test(source);

export const buildSemTPipelineGraphFromPython = (
  source: string,
): PipelineVersionGraph | null => {
  if (!isSemTPythonScript(source)) return null;

  const operations = parseOperations(source);
  if (operations.length === 0) return null;

  const csvFile = extractAssignedDefault(source, "filename") || "table.csv";
  const baseUrl = extractAssignedDefault(source, "base_url");
  const username = extractAssignedDefault(source, "username");
  const password = extractAssignedString(source, "default_password");
  const datasetId = extractAssignedDefault(source, "dataset_id") || "114";
  const tableName = extractAssignedDefault(source, "table_name") || "my_table";

  const nodes: Node<NodeData>[] = [
    node("1", 0, {
      label: "Input Data",
      description: `CSV input referenced by imported SemT script: ${csvFile}`,
      type: "input",
      definition_id: "core.input-data",
      definition_version: 1,
      content: csvFile,
      files: [
        {
          filename: csvFile,
          bucket: "files-step-id-1",
        },
      ],
      has_files: "yes",
    }),
    node("2", 1, {
      label: "SemT Setup",
      description: "Authenticate with SemT and load the input CSV table.",
      type: "action",
      definition_id: "semt.setup",
      definition_version: 1,
      implementation: {
        kind: "semt",
        operation: "setup",
        service_id: "semt_connection",
        parameters: {
          api_base_url: baseUrl,
          username,
          password,
          token: "",
          dataset_id: datasetId,
          table_name: tableName,
        },
        connection_ref: "default-semt",
      },
      configuration_status: username && password ? "valid" : "unconfigured",
    }),
  ];

  operations.forEach((operation, operationIndex) => {
    const definitionId = semtDefinitionForOperation(operation.operation);
    nodes.push(
      node(String(operationIndex + 3), operationIndex + 2, {
        label: labelForOperation(operation),
        description: descriptionForOperation(operation),
        type: operation.operation === "export" ? "output" : "action",
        definition_id: definitionId,
        definition_version: 1,
        implementation: {
          kind: "semt",
          operation: operation.operation,
          service_id: operation.serviceId,
          parameters: operation.parameters,
          connection_ref: "default-semt",
        },
        configuration_status: "valid",
      }),
    );
  });

  const edges = nodes.slice(0, -1).map((currentNode, index) =>
    edge(currentNode.id, nodes[index + 1].id),
  );

  return {
    updated_at: new Date().toISOString(),
    nodes,
    edges,
    viewport: { x: 0, y: 0, zoom: 1 },
    pipeline: {
      active_version_uid: "main",
      active_version_name: "Main",
      description: `Imported SemT pipeline with ${operations.length} operation(s).`,
    },
  };
};
