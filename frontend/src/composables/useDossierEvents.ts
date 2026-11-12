import { computed, ref } from "vue";

import type { DossierEvent, DossierEventActor } from "@/types/dossierEvent";
import { apiFetch, userMessage } from "@/utils/api";

const mapEvent = (api: any): DossierEvent => ({
  id: api.id,
  type: api.type,
  actorId: api.actor_id ?? null,
  actorName: api.actor_name ?? null,
  createdAt: api.created_at,
  payload: api.payload ?? {},
});

export interface EventFilters {
  /** Types d'événements à garder ; vide ou absent = tous. */
  types?: string[];
  /** Identifiant d'un auteur. */
  actorId?: string;
}

/** Historique d'un dossier (issue #171) : lecture paginée du journal, du plus récent au plus ancien. */
export function useDossierEvents(dossierId: string) {
  const events = ref<DossierEvent[]>([]);
  const actors = ref<DossierEventActor[]>([]);
  const total = ref(0);
  const pageCount = ref(1);
  const loading = ref(false);
  const error = ref("");

  async function fetchEvents(page: number, pageSize: number, filters: EventFilters = {}) {
    loading.value = true;
    error.value = "";
    try {
      const query = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
      for (const type of filters.types ?? []) query.append("type", type);
      if (filters.actorId) query.set("actor_id", filters.actorId);
      const data = await apiFetch<{ items: any[]; total: number; pages: number }>(
        `/api/dossiers/${dossierId}/events?${query}`,
      );
      events.value = data.items.map(mapEvent);
      total.value = data.total;
      pageCount.value = data.pages;
    } catch (e) {
      error.value = userMessage(e, "Impossible de charger l'historique.");
      events.value = [];
    } finally {
      loading.value = false;
    }
  }

  async function fetchActors() {
    try {
      const data = await apiFetch<any[]>(`/api/dossiers/${dossierId}/events/actors`);
      actors.value = data.map((a) => ({ actorId: a.actor_id, actorName: a.actor_name ?? null }));
    } catch {
      actors.value = []; // le filtre « Auteur » est un confort : l'historique reste lisible sans lui
    }
  }

  return {
    events: computed(() => events.value),
    actors: computed(() => actors.value),
    total: computed(() => total.value),
    pageCount: computed(() => pageCount.value),
    loading: computed(() => loading.value),
    error: computed(() => error.value),
    fetchEvents,
    fetchActors,
  };
}
