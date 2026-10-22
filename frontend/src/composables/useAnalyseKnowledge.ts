import { computed, reactive, type Ref } from "vue";

import type { Version } from "@/types/analyse";
import type { AnalyseCollection, CollectionRef } from "@/types/knowledge";
import { ApiError, apiFetch } from "@/utils/api";
import { toAnalyseCollection, type AnalyseCollectionOut, type StoredCollectionOut } from "@/utils/knowledgeMapping";

// Les collections de la base de connaissances que l'analyse autorise : leur état **pour la personne qui regarde**, et
// l'historique des listes précédentes (tout ce qui se modifie est versionné).

interface KnowledgeCollectionsOut {
  collections: AnalyseCollectionOut[];
  versions: { id: string; created_at: string; content: StoredCollectionOut[] }[];
}

interface RefusedOut {
  source_id: string;
  collection_id: string;
  reason: string;
}

interface AnalyseKnowledgeState {
  collections: AnalyseCollection[];
  versions: Version<StoredCollectionOut[]>[];
  loading: boolean;
  error: string;
}

// L'état est partagé par analyse : le bloc « Base de connaissances » et le sélecteur d'outils d'un agent voient la même liste.
const states = new Map<string, AnalyseKnowledgeState>();

function stateFor(analyseId: string): AnalyseKnowledgeState {
  let state = states.get(analyseId);
  if (!state) {
    state = reactive({ collections: [], versions: [], loading: false, error: "" });
    states.set(analyseId, state);
  }
  return state;
}

export function useAnalyseKnowledge(analyseId: Ref<string>) {
  const state = computed(() => stateFor(analyseId.value));
  const collections = computed(() => state.value.collections);
  const versions = computed(() => state.value.versions);
  const loading = computed(() => state.value.loading);
  const error = computed({ get: () => state.value.error, set: (value: string) => (state.value.error = value) });

  const url = () => `/api/analyses/${analyseId.value}/knowledge-collections`;

  function apply(data: KnowledgeCollectionsOut) {
    state.value.collections = data.collections.map(toAnalyseCollection);
    state.value.versions = data.versions.map((v) => ({ id: v.id, createdAt: v.created_at, content: v.content }));
  }

  /** Dit pourquoi l'API a refusé : le message de l'API, avec la raison de chaque collection quand elle la donne. */
  function describeFailure(e: unknown, fallback: string): string {
    if (e instanceof ApiError && e.detail && typeof e.detail === "object" && "collections" in e.detail) {
      const refused = (e.detail as { collections: RefusedOut[] }).collections;
      return refused.map((r) => `${r.collection_id} : ${r.reason}`).join(" · ");
    }
    return e instanceof Error ? e.message : fallback;
  }

  async function load() {
    state.value.loading = true;
    error.value = "";
    try {
      apply(await apiFetch<KnowledgeCollectionsOut>(url()));
    } catch (e) {
      error.value = describeFailure(e, "Impossible de charger les collections de cette analyse.");
    } finally {
      state.value.loading = false;
    }
  }

  /** Remplace la liste. Retourne vrai si elle a été enregistrée ; sinon `error` dit pourquoi et rien n'a changé. */
  async function save(refs: CollectionRef[]): Promise<boolean> {
    error.value = "";
    try {
      apply(
        await apiFetch<KnowledgeCollectionsOut>(url(), {
          method: "PUT",
          body: JSON.stringify({ collections: refs.map((r) => ({ source_id: r.sourceId, collection_id: r.collectionId })) }),
        }),
      );
      return true;
    } catch (e) {
      error.value = describeFailure(e, "Impossible d'enregistrer ce choix.");
      return false;
    }
  }

  async function restore(versionId: string) {
    error.value = "";
    try {
      apply(await apiFetch<KnowledgeCollectionsOut>(`${url()}/restore/${versionId}`, { method: "POST" }));
    } catch (e) {
      error.value = describeFailure(e, "Impossible de restaurer cette version.");
    }
  }

  const refs = computed<CollectionRef[]>(() => collections.value.map(({ sourceId, collectionId }) => ({ sourceId, collectionId })));

  return { collections, versions, refs, loading, error, load, save, restore };
}
