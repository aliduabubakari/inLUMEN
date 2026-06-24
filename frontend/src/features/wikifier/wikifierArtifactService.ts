import { INLUMEN_API_URL } from "@/config/api";
import { apiFetch } from "@/utils/apiFetch";
import type { WikifierGenerationResponse } from "@/features/wikifier/types";

export const generateWikifierArtifacts = async (
  nodeId: string,
): Promise<WikifierGenerationResponse> => {
  const response = await apiFetch(
    `${INLUMEN_API_URL}/api/nodes/${encodeURIComponent(nodeId)}/generate`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ persist: true }),
    },
  );
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const message =
      payload && typeof payload.error === "string"
        ? payload.error
        : await response.text().catch(() => "");
    throw new Error(
      `Wikifier runtime generation failed (${response.status}): ${message}`,
    );
  }
  return await response.json() as WikifierGenerationResponse;
};
