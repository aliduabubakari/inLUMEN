import { SemTNodeEditor } from "@/components/properties/editors/SemTNodeEditor";
import { MooseNodeEditor } from "@/components/properties/editors/MooseNodeEditor";
import { WikifierNodeEditor } from "@/components/properties/editors/WikifierNodeEditor";
import { getNodeDefinitionEditorKind } from "@/features/nodes/registry/nodeRegistry";
import type { GeneratedArtifact } from "@/features/nodes/nodeSchema";
import type {
  SemTImplementation,
  SemTValidationResult,
} from "@/features/semt/types";
import type { WikifierGeneratedArtifact } from "@/features/wikifier/types";

type NodeDefinitionEditorProps = {
  nodeId: string;
  definitionId?: string;
  implementation?: Record<string, unknown>;
  generatedArtifact?: GeneratedArtifact;
  onChange: (
    implementation: Record<string, unknown>,
    configurationStatus: "unconfigured" | "valid" | "invalid",
  ) => void;
  onArtifactGenerated: (artifact: GeneratedArtifact) => void;
};

export function NodeDefinitionEditor({
  nodeId,
  definitionId,
  implementation,
  generatedArtifact,
  onChange,
  onArtifactGenerated,
}: NodeDefinitionEditorProps) {
  const editorKind = getNodeDefinitionEditorKind(definitionId);

  if (editorKind === "moose") {
    return (
      <MooseNodeEditor
        implementation={implementation}
        onChange={(nextImplementation, validation) =>
          onChange(nextImplementation, validation.status)
        }
      />
    );
  }

  if (editorKind === "wikifier") {
    return (
      <WikifierNodeEditor
        nodeId={nodeId}
        implementation={implementation}
        generatedArtifact={
          generatedArtifact as WikifierGeneratedArtifact | undefined
        }
        onArtifactGenerated={onArtifactGenerated}
        onChange={(nextImplementation, validation) =>
          onChange(nextImplementation, validation.status)
        }
      />
    );
  }

  if (editorKind !== "semt" || !definitionId) return null;

  return (
    <SemTNodeEditor
      definitionId={definitionId}
      implementation={implementation}
      onChange={(
        nextImplementation: SemTImplementation,
        validation: SemTValidationResult,
      ) => onChange(nextImplementation, validation.status)}
    />
  );
}
