import { ref, type Ref } from "vue";

import type { KnowledgeCollection } from "@/types/knowledge";
import type { Page } from "@/types/pagination";
import { apiFetch } from "@/utils/api";
import { toKnowledgeCollection, type KnowledgeCollectionOut } from "@/utils/knowledgeMapping";

/**
 * Les collections qu'une source offre à la personne (ses droits chez le fournisseur). La recherche et la pagination se
 * font **chez le fournisseur** : la plateforme n'a jamais la liste complète.
 */
export function useSourceCollections(sourceId: Ref<string | undefined>) {
  const collections = ref<KnowledgeCollection[]>([]);
  const total = ref(0);
  const loading = ref(false);
  const error = ref("");

  /** `page` est un numéro à partir de 1. Une réponse tardive d'une requête périmée est ignorée. */
  let latest = 0;
  async function load(query: string, page: number, pageSize: number) {
    if (!sourceId.value) return;
    const request = ++latest;
    loading.value = true;
    error.value = "";
    const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (query.trim()) params.set("q", query.trim());
    try {
      const result = await apiFetch<Page<KnowledgeCollectionOut>>(
        `/api/knowledge-sources/${sourceId.value}/collections?${params.toString()}`,
      );
      if (request !== latest) return;
      collections.value = result.items.map(toKnowledgeCollection);
      total.value = result.total;
    } catch (e) {
      if (request !== latest) return;
      collections.value = [];
      total.value = 0;
      error.value = e instanceof Error ? e.message : "Impossible de lister les collections de cette source.";
    } finally {
      if (request === latest) loading.value = false;
    }
  }

  return { collections, total, loading, error, load };
}
