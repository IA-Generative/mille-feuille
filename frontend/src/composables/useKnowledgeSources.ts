import { ref } from "vue";

import type { KnowledgeSource, KnowledgeSourceDraft } from "@/types/knowledge";
import type { Page } from "@/types/pagination";
import { apiFetch } from "@/utils/api";
import { toKnowledgeSource, type KnowledgeSourceOut } from "@/utils/knowledgeMapping";

// Les sources de connaissances que la personne voit. L'état est partagé (module) : « Mes outils » et le choix des
// collections d'une analyse voient la même liste.

// Chargées d'un coup (le maximum de l'API) : la recherche et la pagination de « Mes outils » se font dans l'interface.
const SOURCES_PAGE_SIZE = 100;

const sources = ref<KnowledgeSource[]>([]);
const loading = ref(false);
const error = ref("");
const ready = ref(false);

async function load() {
  loading.value = true;
  error.value = "";
  try {
    const page = await apiFetch<Page<KnowledgeSourceOut>>(`/api/knowledge-sources?page_size=${SOURCES_PAGE_SIZE}`);
    sources.value = page.items.map(toKnowledgeSource);
    ready.value = true;
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Impossible de charger les sources de connaissances.";
  } finally {
    loading.value = false;
  }
}

export function useKnowledgeSources() {
  /** Charge les sources une fois ; `force` les recharge (après un ajout, une suppression…). */
  const fetchSources = async (force = false) => {
    if (force || !ready.value) await load();
  };

  /** Ajoute une source après avoir vérifié sa connexion. Lève `ApiError` (adresse refusée, fournisseur muet…). */
  async function addSource(draft: KnowledgeSourceDraft) {
    await apiFetch<KnowledgeSourceOut>("/api/knowledge-sources", {
      method: "POST",
      body: JSON.stringify({
        name: draft.name.trim(),
        url: draft.url.trim(),
        auth_mode: draft.authMode,
        audience: draft.audience.trim() || null,
        visibility: draft.visibility,
      }),
    });
    await fetchSources(true);
  }

  /** Revérifie la connexion avec l'identité de la personne. Lève `ApiError` si le fournisseur ne répond plus. */
  async function checkSource(id: string) {
    await apiFetch(`/api/knowledge-sources/${id}/check`, { method: "POST" });
  }

  async function removeSource(id: string) {
    await apiFetch(`/api/knowledge-sources/${id}`, { method: "DELETE" });
    await fetchSources(true);
  }

  return { sources, ready, loading, error, fetchSources, addSource, checkSource, removeSource };
}
