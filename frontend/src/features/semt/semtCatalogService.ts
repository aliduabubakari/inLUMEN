import { INLUMEN_API_URL } from "@/config/api";
import { apiFetch } from "@/utils/apiFetch";
import {
  semtCatalogSchema,
  type SemTCatalog,
} from "@/features/semt/types";

export type SemTCatalogName = "setup" | "modifications" | "reconciliators" | "extenders" | "export";

const catalogPromises = new Map<SemTCatalogName, Promise<SemTCatalog>>();

export const fetchSemTCatalog = async (
  catalogName: SemTCatalogName,
  force = false,
): Promise<SemTCatalog> => {
  if (!force) {
    const cached = catalogPromises.get(catalogName);
    if (cached) return cached;
  }

  const promise = (async () => {
    const query = force ? "?refresh=true" : "";
    const response = await apiFetch(
      `${INLUMEN_API_URL}/api/semt/catalog/${catalogName}${query}`,
      { method: "GET" },
    );
    if (!response.ok) {
      const details = await response.text().catch(() => "");
      throw new Error(
        `Failed to load the SemT ${catalogName} catalog (${response.status}): ${details}`,
      );
    }
    return semtCatalogSchema.parse(await response.json());
  })();

  catalogPromises.set(catalogName, promise);
  try {
    return await promise;
  } catch (error) {
    catalogPromises.delete(catalogName);
    throw error;
  }
};

export const catalogNameForDefinition = (
  definitionId: string,
): SemTCatalogName | null => {
  if (definitionId === "semt.setup") return "setup";
  if (definitionId === "semt.modification") return "modifications";
  if (definitionId === "semt.reconciliation") return "reconciliators";
  if (definitionId === "semt.extension") return "extenders";
  if (definitionId === "semt.export") return "export";
  return null;
};
