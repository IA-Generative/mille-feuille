import { onBeforeUnmount, reactive } from "vue";

import { API_BASE_URL } from "@/utils/api";

/**
 * Captures des pages d'un document, chargées à la demande et gardées pour ne pas les redemander en revenant sur une
 * page. Le cookie de session impose un `fetch` avec identifiants, pas un simple `<img src>`.
 */
export function useExtractionScreenshots(dossierId: () => string, documentId: () => string) {
  const urls = reactive<Record<string, string>>({});
  const state = reactive<Record<string, "loading" | "failed">>({});

  async function load(pageId: string) {
    if (urls[pageId] || state[pageId] === "loading") return;
    state[pageId] = "loading";
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/dossiers/${dossierId()}/documents/${documentId()}/pages/${pageId}/screenshot`,
        { credentials: "include" },
      );
      if (!response.ok) throw new Error(String(response.status));
      urls[pageId] = URL.createObjectURL(await response.blob());
      delete state[pageId];
    } catch {
      state[pageId] = "failed";
    }
  }

  onBeforeUnmount(() => Object.values(urls).forEach((url) => URL.revokeObjectURL(url)));

  return { urls, state, load };
}
