import {
  getParameterValue,
  setParameterValue,
} from "@/features/semt/semtValidation";
import type { SemTParameterDefinition } from "@/features/semt/types";
import {
  mooseOperationIdSchema,
  type MooseCatalog,
  type MooseImplementation,
  type MooseOperation,
  type MooseSchemaMetadata,
  type MooseValidationResult,
} from "@/features/moose/types";

const asObject = (value: unknown): Record<string, unknown> =>
  value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};

export const normalizeMooseImplementation = (
  value: unknown,
): MooseImplementation => {
  const implementation = asObject(value);
  const llm = asObject(implementation.llm);
  const operation = mooseOperationIdSchema.safeParse(implementation.operation);

  return {
    kind: "moose",
    operation: operation.success ? operation.data : "",
    schema:
      typeof implementation.schema === "string" ? implementation.schema : "",
    parameters: asObject(implementation.parameters),
    llm: {
      provider:
        typeof llm.provider === "string" && llm.provider
          ? llm.provider
          : "openrouter",
      model: typeof llm.model === "string" ? llm.model : "",
    },
    connection_ref:
      typeof implementation.connection_ref === "string" &&
      implementation.connection_ref.trim()
        ? implementation.connection_ref
        : "default-moose",
  };
};

const defaultForParameter = (parameter: SemTParameterDefinition): unknown => {
  if (parameter.default !== undefined) return structuredClone(parameter.default);
  if (parameter.type === "boolean") return false;
  if (
    parameter.type === "column-list" ||
    parameter.type === "property-list" ||
    parameter.type === "multi-select" ||
    parameter.type === "ordered-column-list"
  ) return [];
  if (parameter.type === "key-value-map") return {};
  if (parameter.type === "number") return 0;
  return "";
};

export const parametersForMooseOperation = (
  operation: MooseOperation,
): Record<string, unknown> =>
  operation.parameters.reduce<Record<string, unknown>>(
    (parameters, parameter) =>
      setParameterValue(
        parameters,
        parameter.name,
        defaultForParameter(parameter),
      ),
    {},
  );

export const schemasForMooseOperation = (
  operation: MooseOperation | undefined,
  schemas: MooseSchemaMetadata[],
) => {
  if (!operation?.schema_capability) return [];
  return schemas.filter((schema) => schema[operation.schema_capability!] === true);
};

const hasValue = (value: unknown) => {
  if (value == null) return false;
  if (typeof value === "string") return value.trim().length > 0;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === "object") return Object.keys(value).length > 0;
  return true;
};

const validateParameter = (
  parameter: SemTParameterDefinition,
  value: unknown,
): string[] => {
  if (parameter.required && !hasValue(value)) {
    return [`${parameter.label} is required.`];
  }
  if (!hasValue(value)) return [];
  if (parameter.type === "boolean") {
    return typeof value === "boolean"
      ? []
      : [`${parameter.label} must be true or false.`];
  }
  if (parameter.type === "number") {
    return typeof value === "number" && Number.isFinite(value)
      ? []
      : [`${parameter.label} must be a number.`];
  }
  if (
    parameter.type === "column-list" ||
    parameter.type === "property-list" ||
    parameter.type === "multi-select" ||
    parameter.type === "ordered-column-list"
  ) {
    if (
      !Array.isArray(value) ||
      !value.every((item) => typeof item === "string" && item.trim())
    ) {
      return [`${parameter.label} must be a list of values.`];
    }
    if (parameter.min_items != null && value.length < parameter.min_items) {
      return [
        `${parameter.label} requires at least ${parameter.min_items} value(s).`,
      ];
    }
    return [];
  }
  if (parameter.type === "key-value-map") {
    return value && typeof value === "object" && !Array.isArray(value)
      ? []
      : [`${parameter.label} must be a key-value map.`];
  }
  if (parameter.type === "select") {
    const allowed = new Set(parameter.options.map((option) => option.value));
    return allowed.size === 0 || allowed.has(String(value))
      ? []
      : [`${parameter.label} has an unsupported value.`];
  }
  return typeof value === "string"
    ? []
    : [`${parameter.label} must be text.`];
};

export const validateMooseImplementation = (
  implementation: MooseImplementation,
  catalog: MooseCatalog | null,
): MooseValidationResult => {
  if (!implementation.operation) {
    return {
      status: "unconfigured",
      errors: ["Select a Moose operation."],
    };
  }
  const operation = catalog?.operations.find(
    (candidate) => candidate.id === implementation.operation,
  );
  if (!operation) {
    return {
      status: "invalid",
      errors: ["The selected Moose operation is not available."],
    };
  }

  const errors: string[] = [];
  if (!implementation.connection_ref.trim()) {
    errors.push("Connection profile is required.");
  }
  if (!catalog.providers.some(
    (provider) => provider.value === implementation.llm.provider,
  )) {
    errors.push("Select a supported LLM provider.");
  }
  if (!implementation.llm.model.trim()) {
    errors.push("LLM model is required.");
  }

  if (operation.schema_capability) {
    const schema = catalog.schemas.find(
      (candidate) => candidate.value === implementation.schema,
    );
    if (!schema) {
      errors.push("Select a compatible Moose schema.");
    } else if (!schema[operation.schema_capability]) {
      errors.push(`${schema.label} does not support ${operation.label}.`);
    }
  }

  operation.parameters.forEach((parameter) => {
    errors.push(
      ...validateParameter(
        parameter,
        getParameterValue(implementation.parameters, parameter.name),
      ),
    );
  });

  const sampleSize = implementation.parameters.sample_size;
  if (
    sampleSize !== undefined &&
    (
      typeof sampleSize !== "number" ||
      !Number.isInteger(sampleSize) ||
      sampleSize < 1 ||
      sampleSize > 1000
    )
  ) {
    errors.push("Sample Size must be an integer between 1 and 1000.");
  }
  if (
    operation.id === "table_cpa" &&
    typeof implementation.parameters.subject_column === "string" &&
    Array.isArray(implementation.parameters.target_columns) &&
    implementation.parameters.target_columns.includes(
      implementation.parameters.subject_column,
    )
  ) {
    errors.push("Subject Column cannot also be a Target Column.");
  }

  return {
    status: errors.length > 0 ? "invalid" : "valid",
    errors,
  };
};
