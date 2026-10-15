import { computed, ref, watch, type Ref } from "vue";

import type { EntityResult, ExtractedPage } from "@/types";

/** Sans accents ni majuscules : « Genève » se trouve en tapant « geneve ». */
const fold = (text: string) =>
  text
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase();

/**
 * État de la vue d'un document : page courante, recherche et filtre par entité. Les entités affichées (liste et
 * rectangles) sont celles qui passent la recherche et le filtre ; les pages qui en contiennent sont proposées pour
 * y aller directement.
 */
export function useExtractionExplorer(pages: Ref<ExtractedPage[]>) {
  const pageIndex = ref(0);
  const query = ref("");
  const selected = ref<string[]>([]);

  // Noms des entités trouvées dans le document, avec leur nombre de valeurs.
  const names = computed(() => {
    const counts = new Map<string, number>();
    for (const page of pages.value) for (const entity of page.entities) counts.set(entity.name, (counts.get(entity.name) ?? 0) + 1);
    return [...counts].map(([name, count]) => ({ name, count }));
  });

  const filtering = computed(() => !!query.value.trim() || selected.value.length > 0);

  const matches = (entity: EntityResult) => {
    if (selected.value.length && !selected.value.includes(entity.name)) return false;
    const needle = fold(query.value.trim());
    return !needle || fold(entity.name).includes(needle) || fold(entity.value).includes(needle);
  };

  const visibleEntities = (page: ExtractedPage) => page.entities.filter(matches);

  // Pages qui contiennent au moins une entité retenue, avec leur nombre : la liste proposée au-dessus de la page.
  const matchingPages = computed(() =>
    pages.value
      .map((page, index) => ({ index, pageNumber: page.page_number, count: visibleEntities(page).length }))
      .filter((page) => page.count > 0),
  );

  const current = computed(() => pages.value[pageIndex.value]);
  const currentEntities = computed(() => (current.value ? visibleEntities(current.value) : []));

  const goTo = (index: number) => {
    pageIndex.value = Math.max(0, Math.min(pages.value.length - 1, index));
  };

  const toggle = (name: string) => {
    selected.value = selected.value.includes(name) ? selected.value.filter((n) => n !== name) : [...selected.value, name];
  };

  const reset = () => {
    query.value = "";
    selected.value = [];
  };

  // Un nouveau filtre ramène sur la première page qui en contient : on ne reste pas sur une page vide.
  watch([query, selected], () => {
    if (filtering.value && matchingPages.value.length && !matchingPages.value.some((p) => p.index === pageIndex.value)) {
      goTo(matchingPages.value[0].index);
    }
  });

  return { pageIndex, query, selected, names, filtering, matchingPages, current, currentEntities, goTo, toggle, reset };
}
