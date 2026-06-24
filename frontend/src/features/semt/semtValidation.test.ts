import { describe, expect, it } from "vitest";
import {
  normalizeSemTImplementation,
  parametersForCatalogItem,
  validateSemTImplementation,
} from "@/features/semt/semtValidation";
import type { SemTCatalogItem } from "@/features/semt/types";

const hereItem: SemTCatalogItem = {
  id: "geocodingHere",
  label: "HERE Geocoding",
  description: "",
  supported: true,
  parameters: [
    {
      name: "column_name",
      label: "Target column",
      type: "column",
      required: true,
      description: "",
      options: [],
    },
    {
      name: "optional_columns",
      label: "Context columns",
      type: "column-list",
      required: true,
      description: "",
      min_items: 2,
      max_items: 2,
      options: [],
    },
  ],
};

describe("SemT validation", () => {
  it("builds nested and typed defaults from a catalog item", () => {
    const item: SemTCatalogItem = {
      id: "meteoPropertiesOpenMeteo",
      label: "Open-Meteo",
      description: "",
      supported: true,
      parameters: [
        {
          name: "properties",
          label: "Properties",
          type: "property-list",
          required: true,
          description: "",
          options: [],
        },
        {
          name: "other_params.decimal_format",
          label: "Decimal format",
          type: "select",
          required: true,
          description: "",
          default: ".",
          options: [
            { value: ".", label: "Dot" },
            { value: "comma", label: "Comma" },
          ],
        },
      ],
    };

    expect(parametersForCatalogItem(item)).toEqual({
      properties: [],
      other_params: { decimal_format: "." },
    });
  });

  it("marks an unselected operation as unconfigured", () => {
    const implementation = normalizeSemTImplementation(
      "semt.reconciliation",
      {},
    );

    expect(validateSemTImplementation(implementation, undefined).status)
      .toBe("unconfigured");
  });

  it("enforces service-specific context column counts", () => {
    const implementation = normalizeSemTImplementation(
      "semt.reconciliation",
      {
        service_id: "geocodingHere",
        connection_ref: "default-semt",
        parameters: {
          column_name: "City",
          optional_columns: ["Country"],
        },
      },
    );

    const result = validateSemTImplementation(implementation, hereItem);

    expect(result.status).toBe("invalid");
    expect(result.errors).toContain(
      "Context columns requires at least 2 value(s).",
    );
  });

  it("accepts a complete supported service configuration", () => {
    const implementation = normalizeSemTImplementation(
      "semt.reconciliation",
      {
        service_id: "geocodingHere",
        connection_ref: "default-semt",
        parameters: {
          column_name: "City",
          optional_columns: ["County", "Country"],
        },
      },
    );

    expect(validateSemTImplementation(implementation, hereItem)).toEqual({
      status: "valid",
      errors: [],
    });
  });

  it("uses the internal default connection reference without requiring a UI field", () => {
    const implementation = normalizeSemTImplementation(
      "semt.reconciliation",
      {
        service_id: "geocodingHere",
        parameters: {
          column_name: "City",
          optional_columns: ["County", "Country"],
        },
      },
    );

    expect(implementation.connection_ref).toBe("default-semt");
    expect(validateSemTImplementation(implementation, hereItem)).toEqual({
      status: "valid",
      errors: [],
    });
  });

  it("removes legacy deduplication settings from remote SemT nodes", () => {
    const implementation = normalizeSemTImplementation(
      "semt.reconciliation",
      {
        service_id: "geocodingHere",
        parameters: {
          column_name: "City",
          optional_columns: ["County", "Country"],
          deduplicate: false,
        },
      },
    );

    expect(implementation.parameters).not.toHaveProperty("deduplicate");
  });
});
