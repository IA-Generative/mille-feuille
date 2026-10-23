import { computed, reactive, type Ref } from "vue";

import type { AnalyseSearch, EmbeddingModel, SearchImpact, SearchSettings } from "@/types/search";
import { ApiError, apiFetch } from "@/utils/api";
import {
  fromSettings,
  toAnalyseSearch,
  toImpact,
  toOverview,
  type AnalyseSearchOut,
  type ImpactOut,
  type OverviewOut,
} from "@/utils/searchMapping";

// Les réglages de recherche d'une analyse (découpage des pages, modèle d'embeddings) : versionnés comme tout ce qui
// se modifie dans une analyse, avec l'état des index de ses dossiers.

interface State {
  data: AnalyseSearch | null;
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

const embeddingModels = reactive<EmbeddingModel[]>([]);
let embeddingModelsFetched = false;

/** Les modèles d'embeddings du hub, avec la taille de leurs vecteurs (comme le catalogue des modèles de chat). */
export async function fetchEmbeddingModels() {
  if (embeddingModelsFetched) return;
  embeddingModelsFetched = true;
  try {
    const data = await apiFetch<{ models: EmbeddingModel[] }>("/api/models/embeddings");
    embeddingModels.splice(0, embeddingModels.length, ...data.models);
  } catch (e) {
    // Le hub n'est pas forcément configuré (503) : le sélecteur reste vide, le modèle de la plateforme s'applique.
    if (!(e instanceof ApiError)) throw e;
  }
}

export function useAnalyseSearch(analyseId: Ref<string>) {
  const state = computed(() => stateFor(analyseId.value));
  const data = computed(() => state.value.data);
  const loading = computed(() => state.value.loading);
  const error = computed({ get: () => state.value.error, set: (value: string) => (state.value.error = value) });

  const url = (suffix = "") => `/api/analyses/${analyseId.value}/search-settings${suffix}`;
  const message = (e: unknown, fallback: string) => (e instanceof Error ? e.message : fallback);

  async function load() {
    state.value.loading = true;
    error.value = "";
    try {
      state.value.data = toAnalyseSearch(await apiFetch<AnalyseSearchOut>(url()));
    } catch (e) {
      error.value = message(e, "Impossible de charger les réglages de recherche.");
    } finally {
      state.value.loading = false;
    }
  }

  /** Enregistre les réglages. Vrai si c'est fait ; sinon `error` dit pourquoi et rien n'a changé. */
  async function save(settings: SearchSettings): Promise<boolean> {
    error.value = "";
    try {
      state.value.data = toAnalyseSearch(
        await apiFetch<AnalyseSearchOut>(url(), { method: "PUT", body: JSON.stringify(fromSettings(settings)) }),
      );
      return true;
    } catch (e) {
      error.value = message(e, "Impossible d'enregistrer ces réglages.");
      return false;
    }
  }

  async function restore(versionId: string) {
    error.value = "";
    try {
      state.value.data = toAnalyseSearch(await apiFetch<AnalyseSearchOut>(url(`/restore/${versionId}`), { method: "POST" }));
    } catch (e) {
      error.value = message(e, "Impossible de restaurer cette version.");
    }
  }

  /** Ce que ces réglages feraient aux index déjà construits, sans rien enregistrer. */
  async function preview(settings: SearchSettings): Promise<SearchImpact | null> {
    try {
      return toImpact(await apiFetch<ImpactOut>(url("/preview"), { method: "POST", body: JSON.stringify(fromSettings(settings)) }));
    } catch {
      return null;
    }
  }

  /** Reconstruit les index obsolètes de l'analyse (un nombre limité à la fois, les autres attendent). */
  async function rebuildAll(): Promise<boolean> {
    error.value = "";
    try {
      const out = await apiFetch<{ overview: OverviewOut }>(`/api/analyses/${analyseId.value}/search-index/rebuild`, {
        method: "POST",
      });
      if (state.value.data) state.value.data.overview = toOverview(out.overview);
      return true;
    } catch (e) {
      error.value = message(e, "Impossible de lancer la reconstruction.");
      return false;
    }
  }

  async function refreshOverview() {
    try {
      const out = await apiFetch<OverviewOut>(`/api/analyses/${analyseId.value}/search-index`);
      if (state.value.data) state.value.data.overview = toOverview(out);
    } catch {
      // L'état des index est une information : une erreur passagère ne bloque rien.
    }
  }

  return { data, loading, error, embeddingModels: computed(() => embeddingModels), load, save, restore, preview, rebuildAll, refreshOverview };
}
