import type { Node, Edge } from "reactflow";
import type {
  ParsedSemTOperation,
  SemTPipeline,
} from "@/features/semt/semtPipelineParser";
import type { SemTCatalog, SemTImplementation } from "@/features/semt/types";
import type { NodeDefinition } from "@/features/nodes/registry/types";
import {
  findCatalogItem,
  mapParametersToCatalog,
} from "@/features/semt/semtParameterMapper";
import {
  parametersForCatalogItem,
  validateSemTImplementation,
} from "@/features/semt/semtValidation";

// ── Layout constants ────────────────────────────────────────────────────────

const NODE_WIDTH = 220;
const NODE_HEIGHT = 120;
const HORIZONTAL_SPACING = 80;
const VERTICAL_SPACING = 60;

const START_X = 250;
const START_Y = 100;

// ── Definition ID mapping ───────────────────────────────────────────────────

const OPERATION_DEFINITION_MAP: Record<
  SemTImplementation["operation"],
  string
> = {
  setup: "semt.setup",
  reconciliation: "semt.reconciliation",
  modification: "semt.modification",
  extension: "semt.extension",
  export: "semt.export",
};

// ── Node label generators ───────────────────────────────────────────────────

const nodeLabelForOperation = (op: ParsedSemTOperation): string => {
  const columnSuffix = op.column ? `: ${op.column}` : "";
  switch (op.operation) {
    case "reconciliation":
      return `Reconcile${columnSuffix}`;
    case "modification":
      return `Modify${columnSuffix}`;
    case "extension":
      return `Extend${columnSuffix}`;
    case "export":
      return "Export";
    case "setup":
      return "SemT Setup";
    default:
      return op.service_id;
  }
};

const nodeDescriptionForOperation = (op: ParsedSemTOperation): string => {
  const actionMap: Record<string, string> = {
    reconciliation: "Reconciles",
    modification: "Modifies",
    extension: "Extends",
    export: "Exports",
    setup: "Initialises",
  };
  const action = actionMap[op.operation] ?? "Processes";
  const column = op.column ? ` column '${op.column}'` : "";
  return `${action}${column} using ${op.service_id}`;
};

// ── Main populator ──────────────────────────────────────────────────────────

export type PopulatedPipeline = {
  nodes: Node[];
  edges: Edge[];
  nodeIdCounter: number;
};

/**
 * Catalogs mapped by operation type for parameter name resolution.
 */
export type SemTCatalogMap = Partial<Record<string, SemTCatalog>>;

const CATALOG_FOR_OPERATION: Record<string, string> = {
  reconciliation: "reconciliators",
  modification: "modifications",
  extension: "extenders",
  export: "export",
  setup: "setup",
};

const cloneImplementation = (value: Record<string, unknown>) =>
  JSON.parse(JSON.stringify(value ?? {})) as Record<string, unknown>;

const createNodeDataFromDefinition = (definition: NodeDefinition) => ({
  label: definition.palette.label,
  description: definition.palette.description,
  type: definition.base_type,
  definition_id: definition.id,
  definition_version: definition.version,
  implementation: cloneImplementation(definition.default_implementation),
  ...(definition.editor.kind !== "default"
    ? { configuration_status: "unconfigured" as const }
    : {}),
});

/**
 * Create ReactFlow nodes and edges from a parsed SemT pipeline.
 * When catalogs are provided, parameter names are mapped to match the catalog.
 * Nodes are positioned in a vertical chain.
 * Returns nodes, edges, and the next available numeric node ID.
 */
export const populatePipeline = (
  pipeline: SemTPipeline,
  startNodeId: number = 1,
  catalogs?: SemTCatalogMap,
  nodeDefinitions: NodeDefinition[] = [],
): PopulatedPipeline => {
  const nodes: Node[] = [];
  const edges: Edge[] = [];
  let nodeId = startNodeId;

  const operations = pipeline.operations;
  const definitionsById = new Map(
    nodeDefinitions.map((definition) => [definition.id, definition]),
  );

  if (operations.length === 0) {
    return { nodes, edges, nodeIdCounter: nodeId };
  }

  // Create nodes
  operations.forEach((op, index) => {
    const id = String(nodeId++);
    const definitionId = OPERATION_DEFINITION_MAP[op.operation];
    const definition = definitionsById.get(definitionId);

    // Map parameters to catalog if catalog is available
    let parameters = op.parameters;
    let serviceId = op.service_id;
    let catalogItem;
    if (catalogs) {
      const catalogName = CATALOG_FOR_OPERATION[op.operation];
      const catalog = catalogName ? catalogs[catalogName] : undefined;
      if (catalog) {
        catalogItem = findCatalogItem(op.service_id, catalog);
        serviceId = catalogItem?.id ?? serviceId;
        parameters = mapParametersToCatalog(op, catalog);
      }
    }

    const definitionData = definition
      ? createNodeDataFromDefinition(definition)
      : null;
    const defaultImplementation =
      definitionData?.implementation &&
      typeof definitionData.implementation === "object" &&
      !Array.isArray(definitionData.implementation)
        ? definitionData.implementation
        : {};
    const defaultParameters =
      defaultImplementation.parameters &&
      typeof defaultImplementation.parameters === "object" &&
      !Array.isArray(defaultImplementation.parameters)
        ? defaultImplementation.parameters as Record<string, unknown>
        : {};
    const catalogDefaultParameters = catalogItem
      ? parametersForCatalogItem(catalogItem)
      : {};

    const implementation: SemTImplementation = {
      ...defaultImplementation,
      kind: "semt",
      operation: op.operation,
      service_id: serviceId,
      parameters: {
        ...defaultParameters,
        ...catalogDefaultParameters,
        ...parameters,
      },
      connection_ref: "default-semt",
    };
    const validation = catalogItem
      ? validateSemTImplementation(implementation, catalogItem)
      : undefined;

    const x = START_X;
    const y = START_Y + index * (NODE_HEIGHT + VERTICAL_SPACING);

    nodes.push({
      id,
      type: "custom",
      position: { x, y },
      data: {
        ...(definitionData ?? {}),
        label: catalogItem?.label ?? nodeLabelForOperation(op),
        description: catalogItem?.description || nodeDescriptionForOperation(op),
        type: definitionData?.type ?? "action",
        definition_id: definitionId,
        definition_version: definition?.version ?? 1,
        implementation: implementation as unknown as Record<string, unknown>,
        configuration_status: validation?.status ?? "unconfigured" as const,
      },
    });
  });

  // Create edges (chain them sequentially)
  for (let i = 0; i < nodes.length - 1; i++) {
    const source = nodes[i].id;
    const target = nodes[i + 1].id;
    edges.push({
      id: `e-${source}-${target}`,
      source,
      target,
    });
  }

  return { nodes, edges, nodeIdCounter: nodeId };
};

/**
 * Build a pipeline from raw operation data (alternative entry point
 * for when parsing is done elsewhere or data comes from backend).
 */
export const populateFromRawOperations = (
  operations: ParsedSemTOperation[],
  startNodeId: number = 1,
): PopulatedPipeline => {
  return populatePipeline(
    { setup: {}, operations, parse_warnings: [] },
    startNodeId,
  );
};
