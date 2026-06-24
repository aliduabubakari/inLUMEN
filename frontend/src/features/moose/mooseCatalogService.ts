import { INLUMEN_API_URL } from "@/config/api";
import { apiFetch } from "@/utils/apiFetch";
import {
  mooseCatalogSchema,
  type MooseCatalog,
} from "@/features/moose/types";

let catalogPromise: Promise<MooseCatalog> | null = null;

export const fetchMooseCatalog = async (
  force = false,
): Promise<MooseCatalog> => {
  if (!force && catalogPromise) return catalogPromise;

  catalogPromise = (async () => {
    const query = force ? "?refresh=true" : "";
    const response = await apiFetch(
      `${INLUMEN_API_URL}/api/moose/catalog${query}`,
      { method: "GET" },
    );
    if (!response.ok) {
      const details = await response.text().catch(() => "");
      throw new Error(
        `Failed to load the Moose catalog (${response.status}): ${details}`,
      );
    }
    return mooseCatalogSchema.parse(await response.json());
  })();

  try {
    return await catalogPromise;
  } catch (error) {
    catalogPromise = null;
    throw error;
  }
};
