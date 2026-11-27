import { computed, onScopeDispose, ref, watch } from "vue";

import { apiFetch } from "@/utils/api";
import type { ConversationSearchResult } from "@/types/conversation";

export const MIN_QUERY_LENGTH = 2;
export const SEARCH_DELAY_MS = 300;
const PAGE_SIZE = 20;

export type SearchStatus = "loading" | "ready" | "error";

function mapResult(api: any): ConversationSearchResult {
  return {
    conversationId: api.conversation_id,
    dossierId: api.dossier_id,
    dossierName: api.dossier_name,
    date: api.date,
    match: api.match ? { messageId: api.match.message_id, role: api.match.role, excerpt: api.match.excerpt } : null,
    matchCount: api.match_count,
  };
}

/** Recherche dans ses conversations, lancée pendant la frappe. */
export function useConversationSearch() {
  const query = ref("");
  const results = ref<ConversationSearchResult[]>([]);
  const total = ref(0);
  const status = ref<SearchStatus>("loading");
  const active = computed(() => query.value.trim().length >= MIN_QUERY_LENGTH);

  let timer: ReturnType<typeof setTimeout> | undefined;
  // Numéro de la dernière demande : une réponse plus ancienne, arrivée en retard, est ignorée.
  let latest = 0;
  let lastPage = 1;

  async function load(page: number) {
    const request = ++latest;
    lastPage = page;
    status.value = "loading";
    try {
      // POST : les mots cherchés ne vont ni dans l'URL ni dans les journaux d'accès.
      const data = await apiFetch<{ items: any[]; total: number }>("/api/conversations/search", {
        method: "POST",
        body: JSON.stringify({ query: query.value.trim(), page, page_size: PAGE_SIZE }),
      });
      if (request !== latest) return;
      const found = data.items.map(mapResult);
      results.value = page === 1 ? found : [...results.value, ...found];
      total.value = data.total;
      status.value = "ready";
    } catch {
      if (request === latest) status.value = "error";
    }
  }

  watch(
    () => query.value.trim(),
    () => {
      clearTimeout(timer);
      latest++;
      results.value = [];
      total.value = 0;
      status.value = "loading";
      if (active.value) timer = setTimeout(() => load(1), SEARCH_DELAY_MS);
    },
  );
  onScopeDispose(() => clearTimeout(timer));

  return {
    query,
    results,
    total,
    status,
    active,
    loadMore: () => load(lastPage + 1),
    retry: () => load(lastPage),
  };
}
