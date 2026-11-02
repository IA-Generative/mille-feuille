import { computed, ref, watch, type Ref } from "vue";

import { usePageSize } from "@/composables/usePageSize";

/** Au-delà de ce nombre d'éléments, un champ de recherche s'affiche au-dessus de la liste. */
export const SEARCH_THRESHOLD = 10;

/**
 * Filtre (recherche texte) et pagination côté interface d'une liste éditable. `searchText` donne les champs
 * interrogés pour un élément. `reveal` amène un élément à l'écran (efface le filtre, va à sa page) : à appeler
 * après un ajout, sinon un nouvel élément resterait caché par la recherche ou la pagination.
 */
export function useListView<T extends { id: string }>(items: Ref<T[]>, searchText: (item: T) => string) {
  const query = ref("");
  const pageIndex = ref(0);
  const pageSize = usePageSize();

  const hasSearch = computed(() => items.value.length > SEARCH_THRESHOLD);
  const filtered = computed(() => {
    const needle = query.value.trim().toLowerCase();
    if (!hasSearch.value || !needle) return items.value;
    return items.value.filter((item) => searchText(item).toLowerCase().includes(needle));
  });
  const pageCount = computed(() => Math.max(1, Math.ceil(filtered.value.length / pageSize.value)));
  const paged = computed(() => filtered.value.slice(pageIndex.value * pageSize.value, (pageIndex.value + 1) * pageSize.value));

  // Une recherche repart de la première page ; une suppression ne doit pas laisser sur une page devenue vide.
  watch(query, () => (pageIndex.value = 0));
  watch(pageCount, (count) => (pageIndex.value = Math.min(pageIndex.value, count - 1)));

  function reveal(id: string) {
    query.value = "";
    const position = items.value.findIndex((item) => item.id === id);
    if (position >= 0) pageIndex.value = Math.floor(position / pageSize.value);
  }

  return { query, pageIndex, pageSize, hasSearch, filtered, paged, reveal };
}
