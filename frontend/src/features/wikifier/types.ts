export type WikifierOutputMode = "compact_and_raw" | "raw_only";

export type WikifierImplementation = {
  kind: "wikifier";
  operation: "annotation";
  parameters: {
    source_column: string;
    language: string;
    threshold: number;
    output_mode: WikifierOutputMode;
  };
  connection_ref: string;
};

export type WikifierValidationResult = {
  status: "unconfigured" | "valid" | "invalid";
  errors: string[];
};

export type WikifierGeneratedFile = {
  filename: string;
  content: string;
  content_type: string;
};

export type WikifierGeneratedArtifact = {
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

export type WikifierGenerationResponse = {
  flow_id: string;
  files: WikifierGeneratedFile[];
  generated_artifact: WikifierGeneratedArtifact;
};
