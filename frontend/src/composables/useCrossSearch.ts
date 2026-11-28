import { ref, shallowRef, watch, type Ref } from "vue";

import type { CrossSearchResult, Excerpt, FoundDossier, SharedItem } from "@/types/crossSearch";
import { ApiError, apiFetch, userMessage } from "@/utils/api";

export const MIN_QUERY_LENGTH = 2;
/** Au-delà, le graphe ne se lit plus. */
export const MAX_RESULTS = 20;
export const MAX_ANCHORS = 10;

export type SearchStatus = "idle" | "loading" | "ready" | "error";

function mapExcerpt(api: any): Excerpt {
  return {
    documentName: api.document_name ?? null,
    page: api.page ?? null,
    field: api.field ?? null,
    text: api.segments.map((s: { text: string }) => s.text).join(""),
    segments: api.segments,
  };
}

function mapDossier(api: any): FoundDossier {
  return {
    id: api.id,
    reference: api.reference,
    name: api.name,
    analyseName: api.analyse_name,
    themeName: api.theme_name,
    excerpts: api.excerpts.map(mapExcerpt),
  };
}

function mapItem(api: any): SharedItem {
  return {
    id: api.id,
    kind: api.kind,
    label: api.label,
    dossierIds: api.dossier_ids,
    occurrences: api.occurrences.map((o: any) => ({
      dossierId: o.dossier_id,
      documentName: o.document_name ?? null,
      page: o.page ?? null,
      text: o.text,
      origin: o.origin ?? undefined,
    })),
  };
}

function mapResult(api: any, query: string): CrossSearchResult {
  return {
    query,
    anchorIds: api.anchor_ids ?? [],
    dossiers: api.dossiers.map(mapDossier),
    items: (api.items ?? []).map(mapItem),
    // Des dossiers non accessibles : un nombre par thème, seulement si le serveur est configuré pour le dire.
    hidden: (api.hidden ?? []).map((h: any) => ({ themeName: h.theme_name, count: h.count, dossierIds: h.dossier_ids })),
  };
}

// POST : les mots cherchés ne vont ni dans l'URL ni dans les journaux d'accès.
const post = <T>(path: string, body: unknown) => apiFetch<T>(path, { method: "POST", body: JSON.stringify(body) });

/** Recherche par mots-clés, lancée à la validation. */
export function useCrossSearch() {
  const result = shallowRef<CrossSearchResult | null>(null);
  const total = ref(0);
  const status = ref<SearchStatus>("idle");
  const error = ref("");
  // Numéro de la dernière demande : une réponse plus ancienne, arrivée en retard, est ignorée.
  let latest = 0;
  let query = "";

  async function search(input: string) {
    const request = ++latest;
    query = input.trim();
    if (query.length < MIN_QUERY_LENGTH) {
      result.value = null;
      status.value = "idle";
      return;
    }
    status.value = "loading";
    try {
      const data = await post<any>("/api/search", { query, limit: MAX_RESULTS });
      if (request !== latest) return;
      result.value = mapResult(data, query);
      total.value = data.total;
      status.value = "ready";
    } catch (failure) {
      if (request !== latest) return;
      result.value = null;
      error.value = userMessage(failure, "La recherche a échoué.");
      status.value = "error";
    }
  }

  return { result, total, status, error, search, retry: () => search(query) };
}

/** Les dossiers proposés à l'ajout, sans extraits ni liens. */
export async function findDossiers(query: string): Promise<FoundDossier[]> {
  const data = await post<any>("/api/search", { query: query.trim(), limit: MAX_ANCHORS, details: false });
  return data.dossiers.map(mapDossier);
}

/** Ce qui relie les dossiers choisis, recalculé à chaque changement de la sélection. */
export function useDossierLinks(
  chosenIds: Ref<string[]>,
  includeRelated: Ref<boolean>,
  remove: (ids: string[]) => void,
) {
  const result = shallowRef<CrossSearchResult | null>(null);
  const status = ref<SearchStatus>("idle");
  const error = ref("");
  const notice = ref("");
  let latest = 0;

  async function load() {
    const request = ++latest;
    if (!chosenIds.value.length) {
      result.value = null;
      status.value = "idle";
      return;
    }
    status.value = "loading";
    try {
      const data = await post<any>("/api/search/links", {
        dossier_ids: chosenIds.value,
        include_related: includeRelated.value,
      });
      if (request !== latest) return;
      result.value = mapResult(data, "");
      status.value = "ready";
    } catch (failure) {
      if (request !== latest) return;
      const detail = failure instanceof ApiError ? (failure.detail as any) : null;
      if (detail?.code === "dossiers_not_found") {
        // Les autres dossiers restent : la sélection réduite relance le calcul.
        notice.value = `${detail.dossier_ids.length} dossier(s) retiré(s) de la sélection : vous n'y avez plus accès, ou ils ont été supprimés.`;
        remove(detail.dossier_ids);
        return;
      }
      result.value = null;
      error.value = userMessage(failure, "Les liens n'ont pas pu être calculés.");
      status.value = "error";
    }
  }

  watch([() => chosenIds.value.join(), includeRelated], load, { immediate: true });

  return { result, status, error, notice, retry: load };
}
