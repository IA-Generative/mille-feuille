import { computed, ref, watch, type Ref } from "vue";

/** Sans accents ni majuscules : « Genève » se trouve en tapant « geneve ». */
const fold = (text: string) =>
  text
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase();

/**
 * État de la vue d'un document page par page : page courante, recherche et filtre par nom (une entité, un label).
 * Les éléments affichés sont ceux qui passent la recherche et le filtre ; les pages qui en contiennent sont proposées
 * pour y aller directement. `itemsOf` donne les éléments d'une page (entités, labels), `valueOf` le texte de la
 * valeur sur lequel porte la recherche en plus du nom.
 */
export function usePageExplorer<P extends { page_number: number }, I extends { name: string }>(
  pages: Ref<P[]>,
  itemsOf: (page: P) => I[],
  valueOf: (item: I) => string,
) {
  const pageIndex = ref(0);
  const query = ref("");
  const selected = ref<string[]>([]);

  // Noms trouvés dans le document, avec leur nombre d'occurrences.
  const names = computed(() => {
    const counts = new Map<string, number>();
    for (const page of pages.value) for (const item of itemsOf(page)) counts.set(item.name, (counts.get(item.name) ?? 0) + 1);
    return [...counts].map(([name, count]) => ({ name, count }));
  });

  const filtering = computed(() => !!query.value.trim() || selected.value.length > 0);

  const matches = (item: I) => {
    if (selected.value.length && !selected.value.includes(item.name)) return false;
    const needle = fold(query.value.trim());
    return !needle || fold(item.name).includes(needle) || fold(valueOf(item)).includes(needle);
  };

  const visibleItems = (page: P) => itemsOf(page).filter(matches);

  // Pages qui contiennent au moins un élément retenu, avec leur nombre : la liste proposée au-dessus de la page.
  const matchingPages = computed(() =>
    pages.value
      .map((page, index) => ({ index, pageNumber: page.page_number, count: visibleItems(page).length }))
      .filter((page) => page.count > 0),
  );

  const current = computed(() => pages.value[pageIndex.value]);
  const currentItems = computed(() => (current.value ? visibleItems(current.value) : []));

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

  return { pageIndex, query, selected, names, filtering, matchingPages, current, currentItems, goTo, toggle, reset };
}
