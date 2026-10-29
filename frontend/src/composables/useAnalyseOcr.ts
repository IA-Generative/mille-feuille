import { computed, reactive, type Ref } from "vue";

import type { Version } from "@/types/analyse";
import { apiFetch } from "@/utils/api";

// Les réglages de lecture des documents scannés d'une analyse (modèle qui décrit les images et les tableaux) :
// versionnés comme tout ce qui se modifie dans une analyse. "" = le modèle de la plateforme.

export interface AnalyseOcr {
  captionModel: string;
  versions: Version<{ captionModel: string }>[];
}

interface OcrSettingsOut {
  caption_model: string | null;
}

interface AnalyseOcrOut {
  settings: OcrSettingsOut;
  versions: { id: string; created_at: string; content: OcrSettingsOut }[];
}

interface State {
  data: AnalyseOcr | null;
  loading: boolean;
  error: string;
}

const states = new Map<string, State>();

function stateFor(analyseId: string): State {
  let state = states.get(analyseId);
  if (!state) {
    state = reactive({ data: null, loading: false, error: "" });
    states.set(analyseId, state);
  }
  return state;
}

function toAnalyseOcr(out: AnalyseOcrOut): AnalyseOcr {
  return {
    captionModel: out.settings.caption_model ?? "",
    versions: out.versions.map((v) => ({
      id: v.id,
      createdAt: v.created_at,
      content: { captionModel: v.content.caption_model ?? "" },
    })),
  };
}

export function useAnalyseOcr(analyseId: Ref<string>) {
  const state = computed(() => stateFor(analyseId.value));
  const data = computed(() => state.value.data);
  const loading = computed(() => state.value.loading);
  const error = computed({ get: () => state.value.error, set: (value: string) => (state.value.error = value) });

  const url = (suffix = "") => `/api/analyses/${analyseId.value}/ocr-settings${suffix}`;
  const message = (e: unknown, fallback: string) => (e instanceof Error ? e.message : fallback);

  async function load() {
    state.value.loading = true;
    error.value = "";
    try {
      state.value.data = toAnalyseOcr(await apiFetch<AnalyseOcrOut>(url()));
    } catch (e) {
      error.value = message(e, "Impossible de charger les réglages de lecture des documents.");
    } finally {
      state.value.loading = false;
    }
  }

  /** Enregistre le modèle ("" : celui de la plateforme). Vrai si c'est fait ; sinon `error` dit pourquoi. */
  async function save(captionModel: string): Promise<boolean> {
    error.value = "";
    try {
      const body = JSON.stringify({ caption_model: captionModel || null });
      state.value.data = toAnalyseOcr(await apiFetch<AnalyseOcrOut>(url(), { method: "PUT", body }));
      return true;
    } catch (e) {
      error.value = message(e, "Impossible d'enregistrer ces réglages.");
      return false;
    }
  }

  async function restore(versionId: string): Promise<boolean> {
    error.value = "";
    try {
      state.value.data = toAnalyseOcr(await apiFetch<AnalyseOcrOut>(url(`/restore/${versionId}`), { method: "POST" }));
      return true;
    } catch (e) {
      error.value = message(e, "Impossible de restaurer cette version.");
      return false;
    }
  }

  return { data, loading, error, load, save, restore };
}
