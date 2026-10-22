import { computed, reactive, ref } from "vue";

import type { CustomField } from "@/types/tracking";
import { apiFetch } from "@/utils/api";
import type {
  Agent,
  Analyse,
  AnalyseSummary,
  EntityDefinition,
  LabelDefinition,
  Version,
  StatusDraft,
  DueSettings,
  WorkflowStatus,
} from "@/types/analyse";

function mapVersion<TApi, T>(v: { id: string; content: TApi; created_at: string }, mapContent: (c: TApi) => T): Version<T> {
  return { id: v.id, content: mapContent(v.content), createdAt: v.created_at };
}

const identity = <T,>(value: T) => value;

function mapLabel(api: { id: string; name: string; definition: string }): LabelDefinition {
  return { id: api.id, name: api.name, definition: api.definition };
}

function mapEntity(api: { id: string; name: string; definition: string; type: EntityDefinition["type"] }): EntityDefinition {
  return { id: api.id, name: api.name, definition: api.definition, type: api.type };
}

function mapStatus(api: any): WorkflowStatus {
  return {
    id: api.id,
    name: api.name,
    color: api.color,
    position: api.position,
    isInitial: api.is_initial,
    isFinal: api.is_final,
  };
}

function mapDueSettings(api: any): DueSettings {
  return {
    defaultDueDays: api.default_due_days ?? null,
    thresholds: {
      farColor: api.thresholds.far_color,
      steps: api.thresholds.steps.map((s: any) => ({ days: s.days, color: s.color })),
      overdueColor: api.thresholds.overdue_color,
    },
  };
}

function mapCustomField(api: any): CustomField {
  return {
    id: api.id,
    name: api.name,
    definition: api.definition ?? "",
    type: api.type,
    required: api.required,
    defaultValue: api.default_value ?? null,
    choices: api.choices ?? [],
    currency: api.currency ?? "EUR",
  };
}

function mapAgent(api: any): Agent {
  return {
    id: api.id,
    name: api.name,
    prompt: api.prompt,
    promptVersions: api.prompt_versions.map((v: any) => mapVersion(v, identity<string>)),
    tools: api.tools,
    toolsVersions: api.tools_versions.map((v: any) => mapVersion(v, identity<string[]>)),
    output: api.output,
    outputVersions: api.output_versions.map((v: any) => mapVersion(v, identity<boolean>)),
    model: api.model,
    modelVersions: api.model_versions.map((v: any) => mapVersion(v, identity<string | null>)),
  };
}

function mapAnalyse(api: any): Analyse {
  return {
    id: api.id,
    name: api.name,
    description: api.description,
    createdAt: api.created_at,
    version: api.version,
    classification: {
      prompt: api.classification.prompt,
      promptVersions: api.classification.prompt_versions.map((v: any) => mapVersion(v, identity<string>)),
      labels: api.classification.labels.map(mapLabel),
      labelsVersions: api.classification.labels_versions.map((v: any) =>
        mapVersion(v, (content: any[]) => content.map(mapLabel)),
      ),
    },
    extraction: {
      prompt: api.extraction.prompt,
      promptVersions: api.extraction.prompt_versions.map((v: any) => mapVersion(v, identity<string>)),
      entities: api.extraction.entities.map(mapEntity),
      entitiesVersions: api.extraction.entities_versions.map((v: any) =>
        mapVersion(v, (content: any[]) => content.map(mapEntity)),
      ),
    },
    statuses: (api.statuses ?? []).map(mapStatus),
    statusesVersions: (api.statuses_versions ?? []).map((v: any) =>
      mapVersion(v, (content: any[]) => content.map(mapStatus)),
    ),
    customFields: (api.custom_fields ?? []).map(mapCustomField),
    customFieldsVersions: (api.custom_fields_versions ?? []).map((v: any) =>
      mapVersion(v, (content: any[]) => content.map(mapCustomField)),
    ),
    dueSettings: mapDueSettings(api.due_settings),
    dueSettingsVersions: (api.due_settings_versions ?? []).map((v: any) => mapVersion(v, mapDueSettings)),
    agents: api.agents.map(mapAgent),
  };
}

function mapSummary(api: any): AnalyseSummary {
  return {
    id: api.id,
    name: api.name,
    description: api.description,
    createdAt: api.created_at,
    agentCount: api.agent_count,
    statuses: (api.statuses ?? []).map(mapStatus),
  };
}

// Store partagé par toute l'application : `summaries` contient la page
// actuellement chargée (pagination côté serveur, voir fetchList), `cache`
// les analyses complètes une fois ouvertes (GET /analyses/:id ou réponse
// d'une mutation).
const summaries = reactive<AnalyseSummary[]>([]);
const cache = reactive<Record<string, Analyse>>({});
const total = ref(0);
const pageCount = ref(1);
const currentPage = ref(1);
const pageSize = ref(20);

async function fetchList(page = currentPage.value, size = pageSize.value) {
  const data = await apiFetch<{ items: any[]; total: number; page: number; page_size: number; pages: number }>(
    `/api/analyses?page=${page}&page_size=${size}`,
  );
  summaries.splice(0, summaries.length, ...data.items.map(mapSummary));
  total.value = data.total;
  pageCount.value = data.pages;
  currentPage.value = data.page;
  pageSize.value = data.page_size;
}

function replaceAgent(analyseId: string, agent: Agent) {
  const analyse = cache[analyseId];
  if (!analyse) return;
  const index = analyse.agents.findIndex((a) => a.id === agent.id);
  if (index === -1) analyse.agents.push(agent);
  else analyse.agents[index] = agent;
}

export function useAnalyses() {
  const list = computed(() => summaries);

  const getById = (id: string) => cache[id];

  const fetchAnalyse = async (id: string) => {
    const data = await apiFetch<any>(`/api/analyses/${id}`);
    cache[id] = mapAnalyse(data);
    return cache[id];
  };

  const create = async (name: string, description: string) => {
    const data = await apiFetch<any>("/api/analyses", {
      method: "POST",
      body: JSON.stringify({ name, description }),
    });
    const analyse = mapAnalyse(data);
    cache[analyse.id] = analyse;
    await fetchList(1, pageSize.value);
    return analyse;
  };

  // --- Classification ---

  const updateClassificationPrompt = async (analyseId: string, prompt: string) => {
    const data = await apiFetch<any>(`/api/analyses/${analyseId}/classification/prompt`, {
      method: "PUT",
      body: JSON.stringify({ prompt }),
    });
    cache[analyseId] = mapAnalyse(data);
  };

  const restoreClassificationPromptVersion = async (analyseId: string, versionId: string) => {
    const data = await apiFetch<any>(`/api/analyses/${analyseId}/classification/prompt/restore/${versionId}`, {
      method: "POST",
    });
    cache[analyseId] = mapAnalyse(data);
  };

  const updateClassificationLabels = async (analyseId: string, labels: LabelDefinition[]) => {
    const data = await apiFetch<any>(`/api/analyses/${analyseId}/classification/labels`, {
      method: "PUT",
      body: JSON.stringify({ labels: labels.map(({ name, definition }) => ({ name, definition })) }),
    });
    cache[analyseId] = mapAnalyse(data);
  };

  const restoreClassificationLabelsVersion = async (analyseId: string, versionId: string) => {
    const data = await apiFetch<any>(`/api/analyses/${analyseId}/classification/labels/restore/${versionId}`, {
      method: "POST",
    });
    cache[analyseId] = mapAnalyse(data);
  };

  // --- Extraction ---

  const updateExtractionPrompt = async (analyseId: string, prompt: string) => {
    const data = await apiFetch<any>(`/api/analyses/${analyseId}/extraction/prompt`, {
      method: "PUT",
      body: JSON.stringify({ prompt }),
    });
    cache[analyseId] = mapAnalyse(data);
  };

  const restoreExtractionPromptVersion = async (analyseId: string, versionId: string) => {
    const data = await apiFetch<any>(`/api/analyses/${analyseId}/extraction/prompt/restore/${versionId}`, {
      method: "POST",
    });
    cache[analyseId] = mapAnalyse(data);
  };

  const updateExtractionEntities = async (analyseId: string, entities: EntityDefinition[]) => {
    const data = await apiFetch<any>(`/api/analyses/${analyseId}/extraction/entities`, {
      method: "PUT",
      body: JSON.stringify({ entities: entities.map(({ name, definition, type }) => ({ name, definition, type })) }),
    });
    cache[analyseId] = mapAnalyse(data);
  };

  const restoreExtractionEntitiesVersion = async (analyseId: string, versionId: string) => {
    const data = await apiFetch<any>(`/api/analyses/${analyseId}/extraction/entities/restore/${versionId}`, {
      method: "POST",
    });
    cache[analyseId] = mapAnalyse(data);
  };

  // --- Statuts de dossier (issue #168) ---

  /**
   * Remplace la liste des statuts. Un statut qui a un `id` est conservé (les dossiers y font référence) ;
   * sans `id`, il est créé. `replacements` : pour chaque statut supprimé encore utilisé, le statut qui reprend
   * ses dossiers. Sans remplaçant, le serveur répond 409 (ApiError, `detail.statuses` liste les statuts
   * concernés et leur nombre de dossiers).
   */
  const updateStatuses = async (
    analyseId: string,
    statuses: StatusDraft[],
    replacements: Record<string, string> = {},
  ) => {
    const data = await apiFetch<any>(`/api/analyses/${analyseId}/statuses`, {
      method: "PUT",
      body: JSON.stringify({
        statuses: statuses.map(({ id, name, color, isInitial, isFinal }) => ({
          id: id ?? undefined,
          name,
          color,
          is_initial: isInitial,
          is_final: isFinal,
        })),
        replacements,
      }),
    });
    cache[analyseId] = mapAnalyse(data);
  };

  const restoreStatusesVersion = async (
    analyseId: string,
    versionId: string,
    replacements: Record<string, string> = {},
  ) => {
    const data = await apiFetch<any>(`/api/analyses/${analyseId}/statuses/restore/${versionId}`, {
      method: "POST",
      body: JSON.stringify({ replacements }),
    });
    cache[analyseId] = mapAnalyse(data);
  };

  /** Enregistre la durée par défaut et les seuils de couleur de l'échéance ; l'ancien état entre dans l'historique. */
  const updateDueSettings = async (analyseId: string, settings: DueSettings) => {
    const data = await apiFetch<any>(`/api/analyses/${analyseId}/due-settings`, {
      method: "PUT",
      body: JSON.stringify({
        default_due_days: settings.defaultDueDays,
        thresholds: {
          far_color: settings.thresholds.farColor,
          steps: settings.thresholds.steps,
          overdue_color: settings.thresholds.overdueColor,
        },
      }),
    });
    cache[analyseId] = mapAnalyse(data);
  };

  /**
   * Remplace les colonnes personnalisées du suivi (administrateurs). Un champ sans `id` est nouveau ; un champ supprimé
   * garde ses valeurs sauf `purgeRemoved` ; un champ dont le type change perd ses valeurs.
   */
  const updateCustomFields = async (analyseId: string, fields: CustomField[], purgeRemoved: boolean, newIds: Set<string>) => {
    const data = await apiFetch<any>(`/api/analyses/${analyseId}/custom-fields`, {
      method: "PUT",
      body: JSON.stringify({
        fields: fields.map((f) => ({
          id: newIds.has(f.id) ? null : f.id,
          name: f.name,
          definition: f.definition,
          type: f.type,
          required: f.required,
          default_value: f.defaultValue,
          choices: f.choices,
          currency: f.currency,
        })),
        purge_removed: purgeRemoved,
      }),
    });
    cache[analyseId] = mapAnalyse(data);
  };

  const restoreCustomFieldsVersion = async (analyseId: string, versionId: string) => {
    const data = await apiFetch<any>(`/api/analyses/${analyseId}/custom-fields/restore/${versionId}`, { method: "POST" });
    cache[analyseId] = mapAnalyse(data);
  };

  const restoreDueSettingsVersion = async (analyseId: string, versionId: string) => {
    const data = await apiFetch<any>(`/api/analyses/${analyseId}/due-settings/restore/${versionId}`, { method: "POST" });
    cache[analyseId] = mapAnalyse(data);
  };

  // --- Agents (créés librement par l'utilisateur pour un but métier) ---

  const addAgent = async (
    analyseId: string,
    name: string,
    prompt: string,
    tools: string[] = [],
    output = true,
    model: string | null = null,
  ) => {
    const data = await apiFetch<any>(`/api/analyses/${analyseId}/agents`, {
      method: "POST",
      body: JSON.stringify({ name, prompt, tools, output, model }),
    });
    const agent = mapAgent(data);
    replaceAgent(analyseId, agent);
    const summary = summaries.find((s) => s.id === analyseId);
    if (summary) summary.agentCount += 1;
    return agent;
  };

  const updateAgentPrompt = async (analyseId: string, agentId: string, newPrompt: string) => {
    const data = await apiFetch<any>(`/api/analyses/${analyseId}/agents/${agentId}/prompt`, {
      method: "PUT",
      body: JSON.stringify({ prompt: newPrompt }),
    });
    replaceAgent(analyseId, mapAgent(data));
  };

  const restoreAgentPromptVersion = async (analyseId: string, agentId: string, versionId: string) => {
    const data = await apiFetch<any>(`/api/analyses/${analyseId}/agents/${agentId}/prompt/restore/${versionId}`, {
      method: "POST",
    });
    replaceAgent(analyseId, mapAgent(data));
  };

  const updateAgentTools = async (analyseId: string, agentId: string, tools: string[]) => {
    const data = await apiFetch<any>(`/api/analyses/${analyseId}/agents/${agentId}/tools`, {
      method: "PUT",
      body: JSON.stringify({ tools }),
    });
    replaceAgent(analyseId, mapAgent(data));
  };

  const restoreAgentToolsVersion = async (analyseId: string, agentId: string, versionId: string) => {
    const data = await apiFetch<any>(`/api/analyses/${analyseId}/agents/${agentId}/tools/restore/${versionId}`, {
      method: "POST",
    });
    replaceAgent(analyseId, mapAgent(data));
  };

  const updateAgentOutput = async (analyseId: string, agentId: string, output: boolean) => {
    const data = await apiFetch<any>(`/api/analyses/${analyseId}/agents/${agentId}/output`, {
      method: "PUT",
      body: JSON.stringify({ output }),
    });
    replaceAgent(analyseId, mapAgent(data));
  };

  const restoreAgentOutputVersion = async (analyseId: string, agentId: string, versionId: string) => {
    const data = await apiFetch<any>(`/api/analyses/${analyseId}/agents/${agentId}/output/restore/${versionId}`, {
      method: "POST",
    });
    replaceAgent(analyseId, mapAgent(data));
  };

  const updateAgentModel = async (analyseId: string, agentId: string, model: string | null) => {
    const data = await apiFetch<any>(`/api/analyses/${analyseId}/agents/${agentId}/model`, {
      method: "PUT",
      body: JSON.stringify({ model }),
    });
    replaceAgent(analyseId, mapAgent(data));
  };

  const restoreAgentModelVersion = async (analyseId: string, agentId: string, versionId: string) => {
    const data = await apiFetch<any>(`/api/analyses/${analyseId}/agents/${agentId}/model/restore/${versionId}`, {
      method: "POST",
    });
    replaceAgent(analyseId, mapAgent(data));
  };

  return {
    list,
    total,
    pageCount,
    currentPage,
    pageSize,
    getById,
    fetchAnalyse,
    fetchList,
    create,
    updateClassificationPrompt,
    restoreClassificationPromptVersion,
    updateClassificationLabels,
    restoreClassificationLabelsVersion,
    updateExtractionPrompt,
    restoreExtractionPromptVersion,
    updateExtractionEntities,
    restoreExtractionEntitiesVersion,
    updateStatuses,
    restoreStatusesVersion,
    updateDueSettings,
    updateCustomFields,
    restoreCustomFieldsVersion,
    restoreDueSettingsVersion,
    addAgent,
    updateAgentPrompt,
    restoreAgentPromptVersion,
    updateAgentTools,
    restoreAgentToolsVersion,
    updateAgentOutput,
    restoreAgentOutputVersion,
    updateAgentModel,
    restoreAgentModelVersion,
  };
}
