import type {
  SemTCatalogItem,
  SemTImplementation,
  SemTParameterDefinition,
  SemTValidationResult,
} from "@/features/semt/types";

const operationForDefinition = (
  definitionId: string,
): SemTImplementation["operation"] => {
  if (definitionId === "semt.setup") return "setup";
  if (definitionId === "semt.reconciliation") return "reconciliation";
  if (definitionId === "semt.extension") return "extension";
  if (definitionId === "semt.export") return "export";
  return "modification";
};

export const normalizeSemTImplementation = (
  definitionId: string,
  value: unknown,
): SemTImplementation => {
  const implementation =
    value && typeof value === "object" && !Array.isArray(value)
      ? value as Record<string, unknown>
      : {};
  const parameters =
    implementation.parameters &&
    typeof implementation.parameters === "object" &&
    !Array.isArray(implementation.parameters)
      ? structuredClone(implementation.parameters as Record<string, unknown>)
      : {};
  const operation = operationForDefinition(definitionId);
  if (operation !== "modification") {
    delete parameters.deduplicate;
  }

  return {
    kind: "semt",
    operation,
    service_id:
      typeof implementation.service_id === "string"
        ? implementation.service_id
        : "",
    parameters,
    connection_ref:
      typeof implementation.connection_ref === "string" &&
      implementation.connection_ref.trim()
        ? implementation.connection_ref
        : "default-semt",
  };
};

export const getParameterValue = (
  parameters: Record<string, unknown>,
  path: string,
): unknown => {
  let current: unknown = parameters;
  for (const part of path.split(".")) {
    if (!current || typeof current !== "object" || Array.isArray(current)) {
      return undefined;
    }
    current = (current as Record<string, unknown>)[part];
  }
  return current;
};

export const setParameterValue = (
  parameters: Record<string, unknown>,
  path: string,
  value: unknown,
): Record<string, unknown> => {
  const result = structuredClone(parameters);
  const parts = path.split(".");
  let current = result;
  parts.forEach((part, index) => {
    if (index === parts.length - 1) {
      current[part] = value;
      return;
    }
    const existing = current[part];
    if (!existing || typeof existing !== "object" || Array.isArray(existing)) {
      current[part] = {};
    }
    current = current[part] as Record<string, unknown>;
  });
  return result;
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
    const errors: string[] = [];
    if (parameter.min_items != null && value.length < parameter.min_items) {
      errors.push(
        `${parameter.label} requires at least ${parameter.min_items} value(s).`,
      );
    }
    if (parameter.max_items != null && value.length > parameter.max_items) {
      errors.push(
        `${parameter.label} allows at most ${parameter.max_items} value(s).`,
      );
    }
    return errors;
  }
  if (parameter.type === "key-value-map") {
    return value &&
      typeof value === "object" &&
      !Array.isArray(value) &&
      Object.keys(value).every((key) => key.trim())
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

export const validateSemTImplementation = (
  implementation: SemTImplementation,
  item: SemTCatalogItem | undefined,
): SemTValidationResult => {
  if (!implementation.service_id) {
    return {
      status: "unconfigured",
      errors: ["Select an operation or service."],
    };
  }
  if (!item || !item.supported) {
    return {
      status: "invalid",
      errors: ["The selected service is not supported by this installation."],
    };
  }

  const errors: string[] = [];
  item.parameters.forEach((parameter) => {
    errors.push(
      ...validateParameter(
        parameter,
        getParameterValue(implementation.parameters, parameter.name),
      ),
    );
  });
  return {
    status: errors.length > 0 ? "invalid" : "valid",
    errors,
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
  ) {
    return [];
  }
  if (parameter.type === "key-value-map") return {};
  if (parameter.type === "number") return 0;
  return "";
};

export const parametersForCatalogItem = (
  item: SemTCatalogItem,
): Record<string, unknown> =>
  item.parameters.reduce<Record<string, unknown>>(
    (parameters, parameter) =>
      setParameterValue(
        parameters,
        parameter.name,
        defaultForParameter(parameter),
      ),
    {},
  );
