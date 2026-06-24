import { describe, expect, it } from "vitest";
import type { SemTParameterDefinition } from "@/features/semt/types";
import type {
  MooseCatalog,
  MooseOperation,
} from "@/features/moose/types";
import {
  normalizeMooseImplementation,
  parametersForMooseOperation,
  schemasForMooseOperation,
  validateMooseImplementation,
} from "@/features/moose/mooseValidation";

const parameter = (
  name: string,
  label: string,
  type: SemTParameterDefinition["type"],
  options: Partial<SemTParameterDefinition> = {},
): SemTParameterDefinition => ({
  name,
  label,
  type,
  required: false,
  description: "",
  options: [],
  ...options,
});

const operations: MooseOperation[] = [
  {
    id: "text_ner",
    label: "Text NER",
    description: "",
    input_contract: "inlumen.text@1",
    output_contract: "inlumen.text@1",
    schema_capability: "supports_text",
    parameters: [],
  },
  {
    id: "table_annotation",
    label: "Table Annotation",
    description: "",
    input_contract: "inlumen.table@1",
    output_contract: "inlumen.table@1",
    schema_capability: "supports_table",
    parameters: [
      parameter("sample_size", "Sample Size", "number", { default: 50 }),
    ],
  },
  {
    id: "table_cpa",
    label: "Table CPA",
    description: "",
    input_contract: "inlumen.table@1",
    output_contract: "inlumen.table@1",
    schema_capability: "supports_cpa",
    parameters: [
      parameter("subject_column", "Subject Column", "column", {
        required: true,
      }),
      parameter("target_columns", "Target Columns", "column-list", {
        required: true,
        min_items: 1,
      }),
    ],
  },
  {
    id: "privacy_text",
    label: "Privacy Text",
    description: "",
    input_contract: "inlumen.text@1",
    output_contract: "inlumen.text@1",
    schema_capability: null,
    parameters: [
      parameter("profile", "Profile", "select", {
        required: true,
        default: "balanced",
        options: [{ value: "balanced", label: "Balanced" }],
      }),
    ],
  },
  {
    id: "privacy_table",
    label: "Privacy Table",
    description: "",
    input_contract: "inlumen.table@1",
    output_contract: "inlumen.table@1",
    schema_capability: null,
    parameters: [
      parameter("sample_size", "Sample Size", "number", { default: 50 }),
      parameter("profile", "Profile", "select", {
        required: true,
        default: "balanced",
        options: [{ value: "balanced", label: "Balanced" }],
      }),
    ],
  },
];

const catalog: MooseCatalog = {
  family: "moose",
  catalog_version: "1",
  source: "test",
  warnings: [],
  operations,
  schemas: [
    {
      value: "dpv_pd",
      label: "DPV PD",
      supports_text: true,
      supports_table: true,
      supports_cpa: false,
      supports_prefilter: true,
      output_format: "sparse",
    },
    {
      value: "cpa",
      label: "CPA",
      supports_text: false,
      supports_table: false,
      supports_cpa: true,
      supports_prefilter: false,
      output_format: "sparse",
    },
  ],
  privacy_profiles: [],
  policy_packs: [{ value: "gdpr_basic", label: "GDPR Basic" }],
  providers: [{ value: "openrouter", label: "OpenRouter" }],
};

const configured = (
  operation: MooseOperation["id"],
  schema = "",
  parameters: Record<string, unknown> = {},
) => ({
  kind: "moose" as const,
  operation,
  schema,
  parameters,
  llm: { provider: "openrouter", model: "test/model" },
  connection_ref: "default-moose",
});

describe("Moose configuration", () => {
  it("normalizes an empty node to one unconfigured Moose implementation", () => {
    expect(normalizeMooseImplementation(undefined)).toEqual({
      kind: "moose",
      operation: "",
      schema: "",
      parameters: {},
      llm: { provider: "openrouter", model: "" },
      connection_ref: "default-moose",
    });
  });

  it("creates only the selected operation defaults", () => {
    const privacy = operations.find(
      (operation) => operation.id === "privacy_table",
    )!;

    expect(parametersForMooseOperation(privacy)).toEqual({
      sample_size: 50,
      profile: "balanced",
    });
  });

  it("filters schemas using operation capabilities", () => {
    const text = operations.find((operation) => operation.id === "text_ner");
    const cpa = operations.find((operation) => operation.id === "table_cpa");

    expect(schemasForMooseOperation(text, catalog.schemas).map((item) => item.value))
      .toEqual(["dpv_pd"]);
    expect(schemasForMooseOperation(cpa, catalog.schemas).map((item) => item.value))
      .toEqual(["cpa"]);
  });

  it("validates all five operation shapes", () => {
    const cases = [
      configured("text_ner", "dpv_pd"),
      configured("table_annotation", "dpv_pd", { sample_size: 50 }),
      configured("table_cpa", "cpa", {
        subject_column: "Person",
        target_columns: ["Country"],
      }),
      configured("privacy_text", "", { profile: "balanced" }),
      configured("privacy_table", "", {
        sample_size: 50,
        profile: "balanced",
      }),
    ];

    cases.forEach((implementation) => {
      expect(validateMooseImplementation(implementation, catalog)).toEqual({
        status: "valid",
        errors: [],
      });
    });
  });

  it("rejects incompatible schemas and invalid CPA columns", () => {
    const result = validateMooseImplementation(
      configured("table_cpa", "dpv_pd", {
        subject_column: "Person",
        target_columns: ["Person"],
      }),
      catalog,
    );

    expect(result.status).toBe("invalid");
    expect(result.errors).toContain(
      "DPV PD does not support Table CPA.",
    );
    expect(result.errors).toContain(
      "Subject Column cannot also be a Target Column.",
    );
  });
});
