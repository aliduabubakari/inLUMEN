import { z } from "zod";

export const semtParameterTypeSchema = z.enum([
  "string",
  "boolean",
  "number",
  "select",
  "multi-select",
  "column",
  "column-list",
  "property",
  "property-list",
  "key-value-map",
  "ordered-column-list",
  "secret-reference",
]);

export const semtCatalogOptionSchema = z.object({
  value: z.string(),
  label: z.string(),
});

export const semtParameterDefinitionSchema = z.object({
  name: z.string().min(1),
  label: z.string().min(1),
  type: semtParameterTypeSchema,
  required: z.boolean().default(false),
  description: z.string().default(""),
  default: z.unknown().optional(),
  placeholder: z.string().optional(),
  min_items: z.number().int().nonnegative().optional(),
  max_items: z.number().int().nonnegative().optional(),
  options: z.array(semtCatalogOptionSchema).default([]),
});

export const semtCatalogItemSchema = z.object({
  id: z.string().min(1),
  label: z.string().min(1),
  description: z.string().default(""),
  supported: z.boolean(),
  parameters: z.array(semtParameterDefinitionSchema),
  metadata: z.record(z.unknown()).optional(),
});

export const semtCatalogSchema = z.object({
  family: z.enum(["setup", "modification", "reconciliation", "extension", "export"]),
  catalog_version: z.string().min(1),
  source: z.string().min(1),
  warnings: z.array(z.string()).default([]),
  items: z.array(semtCatalogItemSchema),
});

export type SemTParameterType = z.infer<typeof semtParameterTypeSchema>;
export type SemTParameterDefinition = z.infer<typeof semtParameterDefinitionSchema>;
export type SemTCatalogItem = z.infer<typeof semtCatalogItemSchema>;
export type SemTCatalog = z.infer<typeof semtCatalogSchema>;

export type SemTImplementation = {
  kind: "semt";
  operation: "setup" | "modification" | "reconciliation" | "extension" | "export";
  service_id: string;
  parameters: Record<string, unknown>;
  connection_ref: string;
};

export type SemTValidationResult = {
  status: "unconfigured" | "valid" | "invalid";
  errors: string[];
};

export type SemTGeneratedArtifact = {
  status: "current" | "stale";
  generator: string;
  generator_version: string;
  configuration_hash: string;
  entrypoint: string[];
  files: Array<{
    filename: string;
    bucket?: string;
    content_type?: string;
  }>;
  data_contract: Record<string, unknown>;
  [key: string]: unknown;
};
