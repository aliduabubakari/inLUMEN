import { useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  getParameterValue,
  setParameterValue,
} from "@/features/semt/semtValidation";
import type { SemTParameterDefinition } from "@/features/semt/types";

type DynamicParameterFormProps = {
  parameters: SemTParameterDefinition[];
  value: Record<string, unknown>;
  onChange: (value: Record<string, unknown>) => void;
};

const listFromText = (value: string) =>
  value
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean);

const mapFromText = (value: string) =>
  value.split("\n").reduce<Record<string, string>>((result, line) => {
    const separatorIndex = line.indexOf("=");
    if (separatorIndex < 1) return result;
    const key = line.slice(0, separatorIndex).trim();
    const mapValue = line.slice(separatorIndex + 1).trim();
    if (key) result[key] = mapValue;
    return result;
  }, {});

const textFromMap = (value: unknown) =>
  value && typeof value === "object" && !Array.isArray(value)
    ? Object.entries(value as Record<string, unknown>)
      .map(([key, mapValue]) => `${key}=${String(mapValue ?? "")}`)
      .join("\n")
    : "";

const listValue = (value: unknown) =>
  Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];

const isTextListParameter = (parameter: SemTParameterDefinition) =>
  parameter.type === "column-list" ||
  parameter.type === "property-list" ||
  parameter.type === "ordered-column-list" ||
  parameter.type === "multi-select";

export function DynamicParameterForm({
  parameters,
  value,
  onChange,
}: DynamicParameterFormProps) {
  const [listDrafts, setListDrafts] = useState<Record<string, string>>({});
  const [visibleSecrets, setVisibleSecrets] = useState<Record<string, boolean>>({});

  const updateParameter = (name: string, parameterValue: unknown) => {
    onChange(setParameterValue(value, name, parameterValue));
  };

  const toggleSecretVisibility = (name: string) => {
    setVisibleSecrets((prev) => ({ ...prev, [name]: !prev[name] }));
  };

  const commitListDraft = (name: string) => {
    if (!(name in listDrafts)) return;
    updateParameter(name, listFromText(listDrafts[name]));
    setListDrafts((drafts) => {
      const nextDrafts = { ...drafts };
      delete nextDrafts[name];
      return nextDrafts;
    });
  };

  return (
    <div className="space-y-4">
      {parameters.map((parameter) => {
        const parameterValue = getParameterValue(value, parameter.name);
        const fieldId = `parameter-${parameter.name.replaceAll(".", "-")}`;
        const isTextList = isTextListParameter(parameter);
        const listText = listDrafts[parameter.name] ?? listValue(parameterValue).join(", ");

        return (
          <div key={parameter.name} className="space-y-2">
            <div className="flex items-center justify-between gap-2">
              <Label htmlFor={fieldId} className="text-sm">
                {parameter.label}
              </Label>
              {parameter.required && (
                <span className="text-[10px] uppercase tracking-wide text-amber-400">
                  Required
                </span>
              )}
            </div>

            {parameter.type === "boolean" ? (
              <div className="flex items-center gap-2 rounded-md border border-border px-3 py-2">
                <Checkbox
                  id={fieldId}
                  checked={Boolean(parameterValue)}
                  onCheckedChange={(checked) =>
                    updateParameter(parameter.name, checked === true)
                  }
                />
                <Label htmlFor={fieldId} className="font-normal">
                  Enabled
                </Label>
              </div>
            ) : parameter.type === "select" ? (
              <select
                id={fieldId}
                className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
                value={typeof parameterValue === "string" ? parameterValue : ""}
                onChange={(event) =>
                  updateParameter(parameter.name, event.target.value)
                }
              >
                <option value="">Select a value</option>
                {parameter.options.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            ) : parameter.type === "secret-reference" ? (
              <div className="flex items-center gap-1">
                <Input
                  id={fieldId}
                  type={visibleSecrets[parameter.name] ? "text" : "password"}
                  value={
                    typeof parameterValue === "string" ? parameterValue : ""
                  }
                  onChange={(event) =>
                    updateParameter(parameter.name, event.target.value)
                  }
                  placeholder={parameter.placeholder || "Enter secret value"}
                  className="flex-1"
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="h-9 w-9 shrink-0"
                  onClick={() => toggleSecretVisibility(parameter.name)}
                  aria-label={visibleSecrets[parameter.name] ? "Hide" : "Show"}
                >
                  {visibleSecrets[parameter.name] ? (
                    <EyeOff className="h-4 w-4" />
                  ) : (
                    <Eye className="h-4 w-4" />
                  )}
                </Button>
              </div>
            ) : parameter.type === "multi-select" && parameter.options.length > 0 ? (
              <div className="space-y-2 rounded-md border border-border p-3">
                {parameter.options.map((option) => {
                  const selected = listValue(parameterValue);
                  const checked = selected.includes(option.value);
                  return (
                    <div key={option.value} className="flex items-center gap-2">
                      <Checkbox
                        id={`${fieldId}-${option.value}`}
                        checked={checked}
                        onCheckedChange={(nextChecked) => {
                          const next = nextChecked === true
                            ? [...selected, option.value]
                            : selected.filter((item) => item !== option.value);
                          updateParameter(parameter.name, next);
                        }}
                      />
                      <Label
                        htmlFor={`${fieldId}-${option.value}`}
                        className="font-normal"
                      >
                        {option.label}
                      </Label>
                    </div>
                  );
                })}
              </div>
            ) : parameter.type === "key-value-map" ? (
              <Textarea
                id={fieldId}
                value={textFromMap(parameterValue)}
                onChange={(event) =>
                  updateParameter(parameter.name, mapFromText(event.target.value))
                }
                placeholder={parameter.placeholder || "key=value"}
                className="min-h-24 font-mono text-xs"
              />
            ) : (
              <Input
                id={fieldId}
                type={parameter.type === "number" ? "number" : "text"}
                value={
                  isTextList
                    ? listText
                    : typeof parameterValue === "number"
                      ? parameterValue
                      : typeof parameterValue === "string"
                        ? parameterValue
                        : ""
                }
                onChange={(event) => {
                  if (parameter.type === "number") {
                    updateParameter(
                      parameter.name,
                      event.target.value === "" ? "" : Number(event.target.value),
                    );
                  } else if (isTextList) {
                    setListDrafts((drafts) => ({
                      ...drafts,
                      [parameter.name]: event.target.value,
                    }));
                  } else {
                    updateParameter(parameter.name, event.target.value);
                  }
                }}
                onBlur={() => commitListDraft(parameter.name)}
                placeholder={
                  parameter.placeholder ||
                  (isTextList
                    ? "Comma-separated values"
                    : undefined)
                }
              />
            )}

            {parameter.description && (
              <p className="text-xs text-muted-foreground">
                {parameter.description}
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
}
