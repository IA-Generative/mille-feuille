import { ref, watch } from "vue";

export const PAGE_SIZE_OPTIONS = [5, 10, 20] as const;
const DEFAULT_PAGE_SIZE = 10;
const STORAGE_KEY = "mille-feuille.page-size";

function readStoredSize(): number {
  try {
    const stored = Number(localStorage.getItem(STORAGE_KEY));
    return (PAGE_SIZE_OPTIONS as readonly number[]).includes(stored) ? stored : DEFAULT_PAGE_SIZE;
  } catch {
    return DEFAULT_PAGE_SIZE;
  }
}

// Une seule valeur pour toute l'application : choisir « 20 » dans une liste vaut pour les autres, et se retrouve au
// prochain chargement. Le stockage du navigateur peut être indisponible : la valeur reste alors celle de la session.
const pageSize = ref(readStoredSize());
watch(pageSize, (size) => {
  try {
    localStorage.setItem(STORAGE_KEY, String(size));
  } catch {
    // stockage indisponible (navigation privée...) : sans conséquence
  }
});

/** Nombre d'éléments par page des listes paginées côté interface (5, 10 ou 20), partagé et mémorisé. */
export function usePageSize() {
  return pageSize;
}
