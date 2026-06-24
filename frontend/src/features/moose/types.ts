import { z } from "zod";
import {
  semtCatalogOptionSchema,
  semtParameterDefinitionSchema,
} from "@/features/semt/types";

export const mooseOperationIdSchema = z.enum([
  "text_ner",
  "table_annotation",
  "table_cpa",
  "privacy_text",
  "privacy_table",
]);

export const mooseSchemaMetadataSchema = z.object({
  value: z.string().min(1),
  label: z.string().min(1),
  supports_text: z.boolean(),
  supports_table: z.boolean(),
  supports_cpa: z.boolean(),
  supports_prefilter: z.boolean(),
  output_format: z.string().min(1),
});

export const moosePrivacyProfileSchema = z.object({
  value: z.string().min(1),
  label: z.string().min(1),
  description: z.string().default(""),
  defaults: z.record(z.unknown()).default({}),
});

export const mooseOperationSchema = z.object({
  id: mooseOperationIdSchema,
  label: z.string().min(1),
  description: z.string().default(""),
  input_contract: z.string().min(1),
  output_contract: z.string().min(1),
  schema_capability: z.enum([
    "supports_text",
    "supports_table",
    "supports_cpa",
  ]).nullable(),
  parameters: z.array(semtParameterDefinitionSchema),
});

export const mooseCatalogSchema = z.object({
  family: z.literal("moose"),
  catalog_version: z.string().min(1),
  source: z.string().min(1),
  warnings: z.array(z.string()).default([]),
  operations: z.array(mooseOperationSchema),
  schemas: z.array(mooseSchemaMetadataSchema),
  privacy_profiles: z.array(moosePrivacyProfileSchema),
  policy_packs: z.array(semtCatalogOptionSchema),
  providers: z.array(semtCatalogOptionSchema),
});

export type MooseOperationId = z.infer<typeof mooseOperationIdSchema>;
export type MooseSchemaMetadata = z.infer<typeof mooseSchemaMetadataSchema>;
export type MooseOperation = z.infer<typeof mooseOperationSchema>;
export type MooseCatalog = z.infer<typeof mooseCatalogSchema>;

export type MooseImplementation = {
  kind: "moose";
  operation: MooseOperationId | "";
  schema: string;
  parameters: Record<string, unknown>;
  llm: {
    provider: string;
    model: string;
  };
  connection_ref: string;
};

export type MooseValidationResult = {
  status: "unconfigured" | "valid" | "invalid";
  errors: string[];
};
