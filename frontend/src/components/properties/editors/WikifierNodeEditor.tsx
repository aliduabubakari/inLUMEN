import { useMemo, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Download,
  Loader2,
  PackageCheck,
  Tags,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { generateWikifierArtifacts } from "@/features/wikifier/wikifierArtifactService";
import {
  normalizeWikifierImplementation,
  validateWikifierImplementation,
} from "@/features/wikifier/wikifierValidation";
import type {
  WikifierGeneratedArtifact,
  WikifierGeneratedFile,
  WikifierImplementation,
  WikifierValidationResult,
} from "@/features/wikifier/types";

type WikifierNodeEditorProps = {
  nodeId: string;
  implementation: Record<string, unknown> | undefined;
  generatedArtifact?: WikifierGeneratedArtifact;
  onChange: (
    implementation: WikifierImplementation,
    validation: WikifierValidationResult,
  ) => void;
  onArtifactGenerated: (artifact: WikifierGeneratedArtifact) => void;
};

export function WikifierNodeEditor({
  nodeId,
  implementation: implementationValue,
  generatedArtifact,
  onChange,
  onArtifactGenerated,
}: WikifierNodeEditorProps) {
  const implementation = useMemo(
    () => normalizeWikifierImplementation(implementationValue),
    [implementationValue],
  );
  const [isGenerating, setIsGenerating] = useState(false);
  const [generationError, setGenerationError] = useState("");
  const [generatedFiles, setGeneratedFiles] = useState<WikifierGeneratedFile[]>([]);
  const validation = validateWikifierImplementation(implementation);

  const emitChange = (nextImplementation: WikifierImplementation) => {
    onChange(nextImplementation, validateWikifierImplementation(nextImplementation));
  };

  const generateArtifacts = async () => {
    setIsGenerating(true);
    setGenerationError("");
    try {
      const response = await generateWikifierArtifacts(nodeId);
      setGeneratedFiles(response.files);
      onArtifactGenerated(response.generated_artifact);
    } catch (generationFailure) {
      setGenerationError(
        generationFailure instanceof Error
          ? generationFailure.message
          : "Failed to generate the Wikifier runtime.",
      );
    } finally {
      setIsGenerating(false);
    }
  };

  const downloadGeneratedFile = (generatedFile: WikifierGeneratedFile) => {
    const blob = new Blob([generatedFile.content], {
      type: generatedFile.content_type || "text/plain;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = generatedFile.filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-4 rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="flex items-center gap-2 text-sm font-medium">
            <Tags className="h-4 w-4 text-emerald-400" />
            Wikifier configuration
          </h3>
          <p className="text-xs text-muted-foreground">
            Annotate one text column with Wikipedia concepts.
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

      <div className="space-y-2">
        <Label htmlFor="wikifier-source-column">Source column</Label>
        <Input
          id="wikifier-source-column"
          value={implementation.parameters.source_column}
          onChange={(event) =>
            emitChange({
              ...implementation,
              parameters: {
                ...implementation.parameters,
                source_column: event.target.value,
              },
            })
          }
          placeholder="text"
        />
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="wikifier-language">Language</Label>
          <Input
            id="wikifier-language"
            value={implementation.parameters.language}
            onChange={(event) =>
              emitChange({
                ...implementation,
                parameters: {
                  ...implementation.parameters,
                  language: event.target.value,
                },
              })
            }
            placeholder="en or auto"
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="wikifier-threshold">Threshold</Label>
          <Input
            id="wikifier-threshold"
            type="number"
            min={0}
            max={1}
            step={0.05}
            value={implementation.parameters.threshold}
            onChange={(event) =>
              emitChange({
                ...implementation,
                parameters: {
                  ...implementation.parameters,
                  threshold:
                    event.target.value === "" ? 0 : Number(event.target.value),
                },
              })
            }
          />
        </div>
      </div>

      <div className="space-y-2">
        <Label htmlFor="wikifier-output-mode">Output mode</Label>
        <select
          id="wikifier-output-mode"
          className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
          value={implementation.parameters.output_mode}
          onChange={(event) =>
            emitChange({
              ...implementation,
              parameters: {
                ...implementation.parameters,
                output_mode: event.target.value as WikifierImplementation["parameters"]["output_mode"],
              },
            })
          }
        >
          <option value="compact_and_raw">Compact columns + raw JSON</option>
          <option value="raw_only">Raw JSON only</option>
        </select>
      </div>

      <div className="space-y-2">
        <Label htmlFor="wikifier-connection-ref">Connection profile</Label>
        <Input
          id="wikifier-connection-ref"
          value={implementation.connection_ref}
          onChange={(event) =>
            emitChange({
              ...implementation,
              connection_ref: event.target.value,
            })
          }
          placeholder="default-wikifier"
        />
        <p className="text-xs text-muted-foreground">
          Runtime resolves the API key from WIKIFIER_USER_KEY.
        </p>
      </div>

      {validation.errors.length > 0 && (
        <div className="rounded-md border border-border bg-background/70 p-2 text-xs text-muted-foreground">
          {validation.errors.join(" ")}
        </div>
      )}

      <div className="space-y-2 rounded-md border border-border bg-background/40 p-3">
        <div className="flex items-center justify-between gap-2">
          <div>
            <p className="text-sm font-medium">Python runtime artifacts</p>
            <p className="text-xs text-muted-foreground">
              Generates main.py, requirements.txt, Dockerfile, and manifest.
            </p>
          </div>
          {generatedArtifact?.status && (
            <Badge
              variant="outline"
              className={
                generatedArtifact.status === "current"
                  ? "border-emerald-500/40 text-emerald-400"
                  : "border-amber-500/40 text-amber-400"
              }
            >
              <PackageCheck className="mr-1 h-3 w-3" />
              {generatedArtifact.status}
            </Badge>
          )}
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={validation.status !== "valid" || isGenerating}
          onClick={() => { void generateArtifacts(); }}
        >
          {isGenerating ? (
            <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />
          ) : (
            <PackageCheck className="mr-2 h-3.5 w-3.5" />
          )}
          {generatedArtifact ? "Regenerate runtime" : "Generate runtime"}
        </Button>
        {generationError && (
          <p className="text-xs text-red-400">{generationError}</p>
        )}
        {generatedArtifact?.files && generatedFiles.length === 0 && (
          <p className="text-xs text-muted-foreground">
            Stored files:{" "}
            {generatedArtifact.files
              .map((file) => file.filename)
              .filter(Boolean)
              .join(", ")}
          </p>
        )}
        {generatedFiles.length > 0 && (
          <div className="space-y-1">
            {generatedFiles.map((generatedFile) => (
              <Button
                key={generatedFile.filename}
                type="button"
                variant="ghost"
                size="sm"
                className="h-7 w-full justify-start px-2 text-xs"
                onClick={() => downloadGeneratedFile(generatedFile)}
              >
                <Download className="mr-2 h-3.5 w-3.5" />
                {generatedFile.filename}
              </Button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
