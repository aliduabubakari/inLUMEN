import type {
  WikifierImplementation,
  WikifierOutputMode,
  WikifierValidationResult,
} from "@/features/wikifier/types";

const OUTPUT_MODES = new Set<WikifierOutputMode>([
  "compact_and_raw",
  "raw_only",
]);

const asRecord = (value: unknown): Record<string, unknown> =>
  value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};

const normalizeThreshold = (value: unknown) =>
  typeof value === "number" && Number.isFinite(value) ? value : 0.8;

const normalizeOutputMode = (value: unknown): WikifierOutputMode =>
  typeof value === "string" && OUTPUT_MODES.has(value as WikifierOutputMode)
    ? value as WikifierOutputMode
    : "compact_and_raw";

export const normalizeWikifierImplementation = (
  value: unknown,
): WikifierImplementation => {
  const implementation = asRecord(value);
  const parameters = asRecord(implementation.parameters);
  return {
    kind: "wikifier",
    operation: "annotation",
    parameters: {
      source_column:
        typeof parameters.source_column === "string"
          ? parameters.source_column
          : "",
      language:
        typeof parameters.language === "string" && parameters.language.trim()
          ? parameters.language
          : "en",
      threshold: normalizeThreshold(parameters.threshold),
      output_mode: normalizeOutputMode(parameters.output_mode),
    },
    connection_ref:
      typeof implementation.connection_ref === "string" &&
      implementation.connection_ref.trim()
        ? implementation.connection_ref
        : "default-wikifier",
  };
};

export const validateWikifierImplementation = (
  implementation: WikifierImplementation,
): WikifierValidationResult => {
  const errors: string[] = [];
  const sourceColumn = implementation.parameters.source_column.trim();
  const language = implementation.parameters.language.trim();
  const connectionRef = implementation.connection_ref.trim();

  if (!sourceColumn) errors.push("Source column is required.");
  if (!language) errors.push("Language is required.");
  if (!connectionRef) errors.push("Connection profile is required.");
  if (
    !Number.isFinite(implementation.parameters.threshold) ||
    implementation.parameters.threshold < 0 ||
    implementation.parameters.threshold > 1
  ) {
    errors.push("Threshold must be between 0 and 1.");
  }
  if (!OUTPUT_MODES.has(implementation.parameters.output_mode)) {
    errors.push("Output mode is not supported.");
  }

  if (!sourceColumn || !language || !connectionRef) {
    return { status: "unconfigured", errors };
  }
  return { status: errors.length > 0 ? "invalid" : "valid", errors };
};
