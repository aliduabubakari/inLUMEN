import { useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  RefreshCw,
  ScanSearch,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { DynamicParameterForm } from "@/components/properties/fields/DynamicParameterForm";
import { fetchMooseCatalog } from "@/features/moose/mooseCatalogService";
import {
  normalizeMooseImplementation,
  parametersForMooseOperation,
  schemasForMooseOperation,
  validateMooseImplementation,
} from "@/features/moose/mooseValidation";
import type {
  MooseCatalog,
  MooseImplementation,
  MooseValidationResult,
} from "@/features/moose/types";

type MooseNodeEditorProps = {
  implementation: Record<string, unknown> | undefined;
  onChange: (
    implementation: MooseImplementation,
    validation: MooseValidationResult,
  ) => void;
};

export function MooseNodeEditor({
  implementation: implementationValue,
  onChange,
}: MooseNodeEditorProps) {
  const implementation = useMemo(
    () => normalizeMooseImplementation(implementationValue),
    [implementationValue],
  );
  const [catalog, setCatalog] = useState<MooseCatalog | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");

  const loadCatalog = async (force = false) => {
    setIsLoading(true);
    setError("");
    try {
      setCatalog(await fetchMooseCatalog(force));
    } catch (loadError) {
      setError(
        loadError instanceof Error
          ? loadError.message
          : "Failed to load the Moose catalog.",
      );
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void loadCatalog();
  }, []);

  const selectedOperation = catalog?.operations.find(
    (operation) => operation.id === implementation.operation,
  );
  const compatibleSchemas = schemasForMooseOperation(
    selectedOperation,
    catalog?.schemas ?? [],
  );
  const validation = validateMooseImplementation(implementation, catalog);

  const emitChange = (nextImplementation: MooseImplementation) => {
    onChange(
      nextImplementation,
      validateMooseImplementation(nextImplementation, catalog),
    );
  };

  return (
    <div className="space-y-4 rounded-lg border border-amber-500/20 bg-amber-500/5 p-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="flex items-center gap-2 text-sm font-medium">
            <ScanSearch className="h-4 w-4 text-amber-400" />
            Moose configuration
          </h3>
          <p className="text-xs text-muted-foreground">
            One canvas node, with one selected analysis operation.
          </p>
        </div>
        <Badge
          variant="outline"
          className={
            validation.status === "valid"
              ? "border-emerald-500/40 text-emerald-400"
              : validation.status === "invalid"
                ? "border-red-500/40 text-red-400"
                : "border-amber-500/40 text-amber-400"
          }
        >
          {validation.status === "valid" ? (
            <CheckCircle2 className="mr-1 h-3 w-3" />
          ) : (
            <AlertCircle className="mr-1 h-3 w-3" />
          )}
          {validation.status}
        </Badge>
      </div>

      {isLoading ? (
        <p className="text-xs text-muted-foreground">Loading Moose metadata...</p>
      ) : error ? (
        <div className="space-y-2">
          <p className="text-xs text-red-400">{error}</p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => { void loadCatalog(true); }}
          >
            <RefreshCw className="mr-2 h-3.5 w-3.5" />
            Retry
          </Button>
        </div>
      ) : (
        <>
          <div className="space-y-2">
            <Label htmlFor="moose-operation">Operation</Label>
            <select
              id="moose-operation"
              className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
              value={implementation.operation}
              onChange={(event) => {
                const nextOperation = catalog?.operations.find(
                  (operation) => operation.id === event.target.value,
                );
                emitChange({
                  ...implementation,
                  operation: nextOperation?.id ?? "",
                  schema: "",
                  parameters: nextOperation
                    ? parametersForMooseOperation(nextOperation)
                    : {},
                });
              }}
            >
              <option value="">Select a Moose operation</option>
              {catalog?.operations.map((operation) => (
                <option key={operation.id} value={operation.id}>
                  {operation.label}
                </option>
              ))}
            </select>
            {selectedOperation?.description && (
              <p className="text-xs text-muted-foreground">
                {selectedOperation.description}
              </p>
            )}
          </div>

          {selectedOperation?.schema_capability && (
            <div className="space-y-2">
              <Label htmlFor="moose-schema">Schema</Label>
              <select
                id="moose-schema"
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
                value={implementation.schema}
                onChange={(event) =>
                  emitChange({ ...implementation, schema: event.target.value })
                }
              >
                <option value="">Select a compatible schema</option>
                {compatibleSchemas.map((schema) => (
                  <option key={schema.value} value={schema.value}>
                    {schema.label}
                  </option>
                ))}
              </select>
            </div>
          )}

          {selectedOperation && (
            <DynamicParameterForm
              parameters={selectedOperation.parameters}
              value={implementation.parameters}
              onChange={(parameters) =>
                emitChange({ ...implementation, parameters })
              }
            />
          )}

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="moose-provider">LLM provider</Label>
              <select
                id="moose-provider"
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
                value={implementation.llm.provider}
                onChange={(event) =>
                  emitChange({
                    ...implementation,
                    llm: {
                      ...implementation.llm,
                      provider: event.target.value,
                    },
                  })
                }
              >
                {catalog?.providers.map((provider) => (
                  <option key={provider.value} value={provider.value}>
                    {provider.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="moose-model">LLM model</Label>
              <Input
                id="moose-model"
                value={implementation.llm.model}
                onChange={(event) =>
                  emitChange({
                    ...implementation,
                    llm: { ...implementation.llm, model: event.target.value },
                  })
                }
                placeholder="provider/model"
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="moose-connection-ref">Connection profile</Label>
            <Input
              id="moose-connection-ref"
              value={implementation.connection_ref}
              onChange={(event) =>
                emitChange({
                  ...implementation,
                  connection_ref: event.target.value,
                })
              }
              placeholder="default-moose"
            />
            <p className="text-xs text-muted-foreground">
              Credentials and provider endpoints remain server-side.
            </p>
          </div>

          {catalog?.warnings.map((warning) => (
            <p key={warning} className="text-xs text-amber-400">
              {warning}
            </p>
          ))}

          {validation.errors.length > 0 && (
            <div className="space-y-1 rounded-md border border-red-500/30 bg-red-500/5 p-2">
              {validation.errors.map((validationError) => (
                <p key={validationError} className="text-xs text-red-400">
                  {validationError}
                </p>
              ))}
            </div>
          )}

          <p className="rounded-md border border-border bg-background/40 p-2 text-xs text-muted-foreground">
            Runtime generation is the next chronological Moose phase. This node
            can be configured and persisted now, but cannot generate an artifact yet.
          </p>
        </>
      )}
    </div>
  );
}
