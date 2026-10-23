import { ref, type Ref } from "vue";

import type { DossierIndex } from "@/types/search";
import { apiFetch } from "@/utils/api";
import { toDossierIndex, type DossierIndexOut } from "@/utils/searchMapping";

// L'index de recherche d'un dossier : son état, et les actions sur sa reconstruction blue/green (reconstruire, valider
// la bascule, revenir à l'ancien index).
export function useDossierSearchIndex(dossierId: Ref<string>) {
  const index = ref<DossierIndex | null>(null);
  const error = ref("");

  const base = () => `/api/dossiers/${dossierId.value}/search-index`;

  async function load() {
    try {
      index.value = toDossierIndex(await apiFetch<DossierIndexOut>(base()));
      error.value = "";
    } catch (e) {
      error.value = e instanceof Error ? e.message : "Impossible de charger l'état de la recherche.";
    }
  }

  async function act(path: string, fallback: string) {
    error.value = "";
    try {
      await apiFetch(`${base()}${path}`, { method: "POST" });
    } catch (e) {
      error.value = e instanceof Error ? e.message : fallback;
    }
    await load();
  }

  const rebuild = () => act("/rebuild", "Impossible de lancer la reconstruction.");
  const validate = (rebuildId: string) => act(`/rebuilds/${rebuildId}/validate`, "Impossible de valider la bascule.");
  const rollback = (rebuildId: string) => act(`/rebuilds/${rebuildId}/rollback`, "Impossible de revenir à l'ancien index.");

  return { index, error, load, rebuild, validate, rollback };
}
