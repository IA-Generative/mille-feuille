import { reactive } from "vue";

import { loadScreenshot } from "@/utils/pageScreenshotCache";

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
    const url = await loadScreenshot(dossierId(), documentId(), pageId);
    if (url) {
      urls[pageId] = url;
      delete state[pageId];
    } else {
      state[pageId] = "failed";
    }
  }

  return { urls, state, load };
}
