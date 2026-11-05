import { computed, ref } from "vue";

import type { HubModel, LlmCapability, LlmModel, LlmType, RoutingMode } from "@/types/llmModel";
import { apiFetch } from "@/utils/api";

// Administration des modèles LLM (backend : /api/admin/llm-capabilities, llm-models, llm-hub-models, llm-routing).
// L'état est partagé par toute l'application : l'onglet le recharge à son ouverture.

interface ApiModel {
  id: string;
  name: string;
  position: number;
  enabled: boolean;
  capability_ids: string[];
  types: LlmType[] | null;
}

const mapModel = (api: ApiModel): LlmModel => ({
  id: api.id,
  name: api.name,
  position: api.position,
  enabled: api.enabled,
  capabilityIds: api.capability_ids,
  types: api.types,
});

const capabilities = ref<LlmCapability[]>([]);
const models = ref<LlmModel[]>([]);
const hubModels = ref<HubModel[]>([]);
const hubReadAt = ref<Date | null>(null);
const hubError = ref("");
const mode = ref<RoutingMode>("first");
const loading = ref(false);
const error = ref("");

const sorted = computed(() => [...models.value].sort((a, b) => a.position - b.position));
/** Le modèle qui fait tout hors mode auto : le premier modèle actif. */
const defaultModelId = computed(() => sorted.value.find((m) => m.enabled)?.id ?? null);

const message = (e: unknown, fallback: string) => (e instanceof Error && e.message ? e.message : fallback);

async function loadCore() {
  const [caps, list, routing] = await Promise.all([
    apiFetch<LlmCapability[]>("/api/admin/llm-capabilities"),
    apiFetch<ApiModel[]>("/api/admin/llm-models"),
    apiFetch<{ auto_mode: boolean }>("/api/admin/llm-routing"),
  ]);
  capabilities.value = caps;
  models.value = list.map(mapModel);
  mode.value = routing.auto_mode ? "auto" : "first";
}

/** Le hub : ses modèles et leurs types. Une erreur (hub non configuré, injoignable) n'empêche pas de gérer la liste. */
async function loadHub(refresh: boolean) {
  try {
    const data = await apiFetch<{ models: HubModel[]; read_at: string }>(
      `/api/admin/llm-hub-models${refresh ? "?refresh=true" : ""}`,
    );
    hubModels.value = data.models;
    hubReadAt.value = new Date(data.read_at);
    hubError.value = "";
  } catch (e) {
    hubError.value = message(e, "Impossible de lire les modèles du hub.");
  }
}

/** Fait une modification puis relit la liste ; l'échec est montré, la liste reste celle du serveur. */
async function change(action: () => Promise<unknown>, failure: string) {
  error.value = "";
  try {
    await action();
  } catch (e) {
    error.value = message(e, failure);
  }
  try {
    await loadCore();
  } catch {
    /* la liste affichée reste la dernière connue */
  }
}

export function useLlmModels() {
  const load = async () => {
    loading.value = true;
    error.value = "";
    try {
      await loadCore();
    } catch (e) {
      error.value = message(e, "Impossible de charger les modèles.");
    } finally {
      loading.value = false;
    }
    await loadHub(false);
  };

  const updateModel = (id: string, changes: { capabilityIds?: string[]; enabled?: boolean }) =>
    change(
      () =>
        apiFetch(`/api/admin/llm-models/${id}`, {
          method: "PATCH",
          body: JSON.stringify({ capability_ids: changes.capabilityIds, enabled: changes.enabled }),
        }),
      "La modification a échoué.",
    );

  const move = (id: string, direction: -1 | 1) => {
    const ids = sorted.value.map((m) => m.id);
    const index = ids.indexOf(id);
    const target = index + direction;
    if (index === -1 || target < 0 || target >= ids.length) return Promise.resolve();
    [ids[index], ids[target]] = [ids[target], ids[index]];
    return change(
      () => apiFetch("/api/admin/llm-models/order", { method: "PUT", body: JSON.stringify({ model_ids: ids }) }),
      "Le changement d'ordre a échoué.",
    );
  };

  const removeModel = (id: string) =>
    change(() => apiFetch(`/api/admin/llm-models/${id}`, { method: "DELETE" }), "La suppression a échoué.");

  /** Ajoute un modèle du hub, sans capacité : c'est à l'administrateur de les lui donner. Renvoie son identifiant. */
  const addModel = async (hub: HubModel): Promise<string | null> => {
    let id: string | null = null;
    await change(async () => {
      const created = await apiFetch<ApiModel>("/api/admin/llm-models", {
        method: "POST",
        body: JSON.stringify({ name: hub.name, capability_ids: [] }),
      });
      id = created.id;
    }, "L'ajout a échoué.");
    hubModels.value = hubModels.value.filter((h) => h.name !== hub.name);
    return id;
  };

  const saveCapability = (input: { id?: string; name: string; description: string }) =>
    change(
      () =>
        input.id
          ? apiFetch(`/api/admin/llm-capabilities/${input.id}`, {
              method: "PATCH",
              body: JSON.stringify({ name: input.name, description: input.description }),
            })
          : apiFetch("/api/admin/llm-capabilities", {
              method: "POST",
              body: JSON.stringify({ name: input.name, description: input.description }),
            }),
      "L'enregistrement de la capacité a échoué.",
    );

  const removeCapability = (id: string) =>
    change(
      () => apiFetch(`/api/admin/llm-capabilities/${id}`, { method: "DELETE" }),
      "La suppression de la capacité a échoué.",
    );

  /** Relit le hub (chaque modèle est sondé pour connaître ses types) ; les modèles déjà enregistrés n'y sont pas proposés. */
  const refreshHub = async () => {
    await loadHub(true);
    await loadCore(); // les modèles enregistrés ont pris les types de cette lecture
  };

  const setMode = (value: RoutingMode) =>
    change(
      () =>
        apiFetch("/api/admin/llm-routing", {
          method: "PUT",
          body: JSON.stringify({ auto_mode: value === "auto" }),
        }),
      "Le changement de mode a échoué.",
    );

  return {
    capabilities,
    models: sorted,
    hubModels,
    hubReadAt,
    hubError,
    mode,
    loading,
    error,
    defaultModelId,
    load,
    updateModel,
    move,
    removeModel,
    addModel,
    saveCapability,
    removeCapability,
    refreshHub,
    setMode,
  };
}
