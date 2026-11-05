import { computed, reactive, ref } from "vue";

import { ApiError, apiFetch } from "@/utils/api";

// Catalogue des modèles LLM exposés par le hub configuré côté backend
// (GET /api/models) - partagé par tous les sélecteurs de modèle (agent,
// conversation, aide LLM) plutôt que refait par composant.
const models = reactive<string[]>([]);
let fetched = false;

// Préférence de modèle pour les boutons d'aide LLM (LlmAssistButton) :
// une seule sélection partagée par toute l'application ("" = « Auto »), modifiable depuis n'importe quel bouton non compact.
const assistModel = ref("");

async function fetchModels() {
  if (fetched) return;
  fetched = true;
  try {
    const data = await apiFetch<{ models: { id: string }[] }>("/api/models");
    models.splice(0, models.length, ...data.models.map((m) => m.id));
  } catch (error) {
    // Le hub LLM n'est pas forcément configuré (503) : le sélecteur reste
    // vide plutôt que de faire planter la page.
    if (!(error instanceof ApiError)) throw error;
  }
}

export function useModels() {
  return { models: computed(() => models), fetchModels, assistModel };
}
