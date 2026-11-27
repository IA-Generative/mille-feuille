import { ref } from "vue";

import { MOCK_DOSSIERS, MOCK_HIDDEN, MOCK_ITEMS } from "@/composables/mockCrossSearch";
import type { CrossSearchResult, FoundDossier } from "@/types/crossSearch";

const normalize = (text: string) => text.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();

/** Maquette : recherche dans les données fictives. L'API remplacera `search` sans changer la page. */
export function mockSearch(query: string): CrossSearchResult {
  const terms = normalize(query).split(/\s+/).filter(Boolean);

  const dossiers = MOCK_DOSSIERS.map((dossier) => {
    const text = normalize(
      [dossier.name, dossier.reference, ...dossier.excerpts.flatMap((e) => [e.documentName, e.text])].join(" "),
    );
    return { dossier, score: terms.filter((term) => text.includes(term)).length };
  })
    .filter(({ score }) => score > 0)
    .sort((a, b) => b.score - a.score)
    .map(({ dossier }) => dossier);

  const found = new Set(dossiers.map((d) => d.id));
  const among = (ids: string[]) => ids.filter((id) => found.has(id));

  return {
    query,
    anchorIds: [],
    dossiers,
    // Un point commun ne relie que s'il est partagé par au moins deux résultats.
    items: MOCK_ITEMS.map((item) => ({
      ...item,
      dossierIds: among(item.dossierIds),
      occurrences: item.occurrences.filter((o) => found.has(o.dossierId)),
    })).filter(
      (item) => item.dossierIds.length > 1,
    ),
    // Rien n'est signalé sans un résultat accessible auquel le rattacher.
    hidden: MOCK_HIDDEN.map((link) => ({ ...link, dossierIds: among(link.dossierIds) })).filter(
      (link) => link.dossierIds.length > 0,
    ),
  };
}

/** Dossiers proposés à l'ajout : par nom ou référence, sans ceux déjà choisis. */
export function mockFindDossiers(query: string, exclude: string[]): FoundDossier[] {
  const needle = normalize(query.trim());
  return MOCK_DOSSIERS.filter((d) => !exclude.includes(d.id) && normalize(`${d.name} ${d.reference}`).includes(needle));
}

export const mockDossiersByIds = (ids: string[]) =>
  ids.flatMap((id) => MOCK_DOSSIERS.filter((dossier) => dossier.id === id));

/**
 * Maquette : ce qui relie des dossiers choisis et, si demandé, les autres dossiers liés à au moins l'un d'eux. Un point
 * commun n'est montré que s'il touche la sélection.
 */
export function mockLinksFrom(anchorIds: string[], includeRelated: boolean): CrossSearchResult {
  const chosen = (id: string) => anchorIds.includes(id);
  const touching = MOCK_ITEMS.filter((item) => item.dossierIds.some(chosen));
  const shownIds = new Set([...anchorIds, ...(includeRelated ? touching.flatMap((item) => item.dossierIds) : [])]);

  return {
    query: "",
    anchorIds,
    // La sélection d'abord, dans l'ordre choisi.
    dossiers: mockDossiersByIds([...anchorIds, ...[...shownIds].filter((id) => !chosen(id)).sort()]),
    items: touching
      .map((item) => ({
        ...item,
        dossierIds: item.dossierIds.filter((id) => shownIds.has(id)),
        occurrences: item.occurrences.filter((o) => shownIds.has(o.dossierId)),
      }))
      .filter((item) => item.dossierIds.length > 1),
    hidden: MOCK_HIDDEN.map((link) => ({ ...link, dossierIds: link.dossierIds.filter(chosen) })).filter(
      (link) => link.dossierIds.length > 0,
    ),
  };
}

export function useCrossSearch() {
  const result = ref<CrossSearchResult | null>(null);

  function search(query: string) {
    const trimmed = query.trim();
    result.value = trimmed ? mockSearch(trimmed) : null;
  }

  return { result, search };
}
