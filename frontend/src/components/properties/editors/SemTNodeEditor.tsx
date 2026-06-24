import { useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  RefreshCw,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { DynamicParameterForm } from "@/components/properties/fields/DynamicParameterForm";
import {
  catalogNameForDefinition,
  fetchSemTCatalog,
} from "@/features/semt/semtCatalogService";
import {
  normalizeSemTImplementation,
  parametersForCatalogItem,
  validateSemTImplementation,
} from "@/features/semt/semtValidation";
import type {
  SemTCatalog,
  SemTImplementation,
  SemTValidationResult,
} from "@/features/semt/types";

type SemTNodeEditorProps = {
  definitionId: string;
  implementation: Record<string, unknown> | undefined;
  onChange: (
    implementation: SemTImplementation,
    validation: SemTValidationResult,
  ) => void;
};

export function SemTNodeEditor({
  definitionId,
  implementation: implementationValue,
  onChange,
}: SemTNodeEditorProps) {
  const catalogName = catalogNameForDefinition(definitionId);
  const implementation = useMemo(
    () => normalizeSemTImplementation(definitionId, implementationValue),
    [definitionId, implementationValue],
  );
  const [catalog, setCatalog] = useState<SemTCatalog | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");

  const loadCatalog = async (force = false) => {
    if (!catalogName) return;
    setIsLoading(true);
    setError("");
    try {
      setCatalog(await fetchSemTCatalog(catalogName, force));
    } catch (loadError) {
      setError(
        loadError instanceof Error
          ? loadError.message
          : "Failed to load the SemT catalog.",
      );
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void loadCatalog();
    // The definition controls the catalog; force refresh is user initiated.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [catalogName]);

  const selectedItem = catalog?.items.find(
    (item) => item.id === implementation.service_id,
  );
  const validation = validateSemTImplementation(implementation, selectedItem);

  const emitChange = (nextImplementation: SemTImplementation) => {
    const nextItem = catalog?.items.find(
      (item) => item.id === nextImplementation.service_id,
    );
    onChange(
      nextImplementation,
      validateSemTImplementation(nextImplementation, nextItem),
    );
  };

  if (!catalogName) return null;

  return (
    <div className="space-y-4 rounded-lg border border-border bg-muted/20 p-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="text-sm font-medium">SemT configuration</h3>
          <p className="text-xs text-muted-foreground">
            Select one operation per canvas node.
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
        <p className="text-xs text-muted-foreground">Loading SemT services...</p>
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
            <Label htmlFor="semt-service">
              {definitionId === "semt.modification"
                ? "Modifier"
                : definitionId === "semt.setup"
                  ? "Connection"
                  : definitionId === "semt.export"
                    ? "Output Format"
                    : "Service"}
            </Label>
            <select
              id="semt-service"
              className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
              value={implementation.service_id}
              onChange={(event) => {
                const nextItem = catalog?.items.find(
                  (item) => item.id === event.target.value,
                );
                emitChange({
                  ...implementation,
                  service_id: event.target.value,
                  parameters: nextItem
                    ? parametersForCatalogItem(nextItem)
                    : {},
                });
              }}
            >
              <option value="">
                {definitionId === "semt.modification"
                  ? "Select a modifier"
                  : definitionId === "semt.setup"
                    ? "Select a connection"
                    : definitionId === "semt.export"
                      ? "Select output format"
                      : "Select a service"}
              </option>
              {catalog?.items
                .filter((item) => item.supported)
                .map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.label}
                  </option>
                ))}
            </select>
            {selectedItem?.description && (
              <p className="text-xs text-muted-foreground">
                {selectedItem.description}
              </p>
            )}
          </div>

          {selectedItem && (
            <DynamicParameterForm
              parameters={selectedItem.parameters}
              value={implementation.parameters}
              onChange={(parameters) =>
                emitChange({ ...implementation, parameters })
              }
            />
          )}

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

        </>
      )}
    </div>
  );
}
