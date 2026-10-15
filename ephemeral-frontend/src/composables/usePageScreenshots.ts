import { onBeforeUnmount, reactive } from "vue";

import { apiFetchBlob } from "@/api";

/** Images des pages d'un run, chargées à la demande et gardées pour ne pas les redemander en revenant sur une page. */
export function usePageScreenshots(runId: () => string) {
  const urls = reactive<Record<string, string>>({});
  const state = reactive<Record<string, "loading" | "failed">>({});

  const load = async (pageId: string) => {
    if (urls[pageId] || state[pageId] === "loading") return;
    state[pageId] = "loading";
    try {
      const blob = await apiFetchBlob(`/api/ephemeral/runs/${runId()}/pages/${pageId}/screenshot`);
      urls[pageId] = URL.createObjectURL(blob);
      delete state[pageId];
    } catch {
      state[pageId] = "failed";
    }
  };

  onBeforeUnmount(() => Object.values(urls).forEach((url) => URL.revokeObjectURL(url)));

  return { urls, state, load };
}
