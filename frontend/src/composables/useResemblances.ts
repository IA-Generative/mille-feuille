import { ref, shallowRef } from "vue";

import type { CatalogEntity, FoundDossier, Resemblance, ResemblanceRule, RuleCriterion, RuleDraft } from "@/types/crossSearch";
import { apiFetch, userMessage } from "@/utils/api";

const BASE = "/api/resemblances";
const PAGE_SIZE = 20;

const send = <T>(path: string, method: string, body?: unknown) =>
  apiFetch<T>(`${BASE}${path}`, { method, body: body === undefined ? undefined : JSON.stringify(body) });

function mapCriterion(api: any): RuleCriterion {
  return api.origin === "file"
    ? { id: api.id, origin: "file", name: api.name }
    : { id: api.id, origin: "analysis", name: api.name, entityIds: api.entity_ids, refusedIds: api.refused_ids ?? [] };
}

const criterionBody = (criterion: RuleCriterion) =>
  criterion.origin === "file"
    ? { id: criterion.id, origin: "file", name: criterion.name }
    : {
        id: criterion.id,
        origin: "analysis",
        name: criterion.name,
        entity_ids: criterion.entityIds,
        refused_ids: criterion.refusedIds ?? [],
      };

const mapDraft = (api: any): RuleDraft => ({
  name: api.name,
  description: api.description,
  criteria: api.criteria.map(mapCriterion),
  scope: api.scope,
  certainty: api.certainty,
  active: api.active,
});

const mapRule = (api: any): ResemblanceRule => ({
  ...mapDraft(api),
  id: api.id,
  computedAt: api.computed_at,
  groupCount: api.group_count,
  missingEntityIds: api.missing_entity_ids,
  versions: api.versions.map((v: any) => ({ id: v.id, createdAt: v.created_at, content: mapDraft(v.content) })),
});

const mapDossier = (api: any): FoundDossier => ({
  id: api.id,
  reference: api.reference,
  name: api.name,
  analyseName: api.analyse_name,
  themeName: api.theme_name,
  excerpts: [],
});

const mapGroup = (ruleId: string) => (api: any): Resemblance => ({
  id: api.key,
  ruleId,
  label: api.label,
  certainty: api.certainty,
  reason: api.reason,
  dismissed: api.dismissed,
  dossiers: api.dossiers.map(mapDossier),
  dossierIds: api.dossiers.map((d: any) => d.id),
  occurrences: api.occurrences.map((o: any) => ({
    dossierId: o.dossier_id,
    documentName: o.document_name ?? null,
    page: o.page ?? null,
    text: o.text,
    origin: o.origin ?? undefined,
  })),
});

/** Copie indépendante : les critères sont des objets, modifiés en place dans le formulaire. */
export const draftOf = ({ name, description, criteria, scope, certainty, active }: RuleDraft): RuleDraft => ({
  name,
  description,
  criteria: JSON.parse(JSON.stringify(criteria)) as RuleCriterion[],
  scope,
  certainty,
  active,
});

const bodyOf = (draft: RuleDraft) => ({ ...draftOf(draft), criteria: draft.criteria.map(criterionBody) });

/** Les thèmes de ressemblance et les groupes du thème affiché. */
export function useResemblances() {
  const rules = shallowRef<ResemblanceRule[]>([]);
  /** Faux quand le calcul est désactivé sur cet environnement. */
  const enabled = ref(true);
  const status = ref<"loading" | "ready" | "error">("loading");
  const error = ref("");
  const groups = shallowRef<Resemblance[]>([]);
  const total = ref(0);
  const groupsError = ref("");
  // Une réponse dépassée (autre thème choisi entre-temps) est ignorée.
  let latest = 0;
  let page = 1;

  async function load() {
    try {
      const data = await apiFetch<any>(`${BASE}/themes`);
      rules.value = data.items.map(mapRule);
      enabled.value = data.enabled;
      status.value = "ready";
    } catch (failure) {
      error.value = userMessage(failure, "Les thèmes n'ont pas pu être chargés.");
      status.value = "error";
    }
  }

  async function loadGroups(ruleId: string, dismissed: boolean, next = false) {
    const request = ++latest;
    page = next ? page + 1 : 1;
    if (!next) groups.value = [];
    groupsError.value = "";
    if (!ruleId) return;
    try {
      const data = await apiFetch<any>(
        `${BASE}/themes/${ruleId}/groups?page=${page}&page_size=${PAGE_SIZE}&dismissed=${dismissed}`,
      );
      if (request !== latest) return;
      const found = data.items.map(mapGroup(ruleId));
      groups.value = next ? [...groups.value, ...found] : found;
      total.value = data.total;
    } catch (failure) {
      if (request === latest) groupsError.value = userMessage(failure, "Les rapprochements n'ont pas pu être chargés.");
    }
  }

  /** Crée ou modifie un thème ; le serveur garde l'état précédent. Renvoie son identifiant. */
  async function saveRule(draft: RuleDraft, id?: string): Promise<string> {
    const saved = id
      ? await send<any>(`/themes/${id}`, "PUT", bodyOf(draft))
      : await send<any>("/themes", "POST", bodyOf(draft));
    await load();
    return saved.id;
  }

  async function restoreRule(id: string, versionId: string) {
    await send(`/themes/${id}/versions/${versionId}/restore`, "POST");
    await load();
  }

  async function removeRule(id: string) {
    await send(`/themes/${id}`, "DELETE");
    await load();
  }

  const setDismissed = (group: Resemblance, dismissed: boolean) =>
    send(`/themes/${group.ruleId}/groups/${group.id}/${dismissed ? "dismiss" : "restore"}`, "POST");

  return {
    rules,
    enabled,
    status,
    error,
    groups,
    total,
    groupsError,
    load,
    loadGroups,
    saveRule,
    restoreRule,
    removeRule,
    setDismissed,
  };
}

const mapEntity = (api: any): CatalogEntity => ({
  id: api.id,
  name: api.name,
  definition: api.definition,
  type: api.type,
  analyseName: api.analyse_name,
});

/** Les entités des analyses (réservées aux administrateurs). */
export async function fetchEntities(): Promise<CatalogEntity[]> {
  return (await apiFetch<any[]>(`${BASE}/entities`)).map(mapEntity);
}

/** Les entités proches de celles données, ou d'une description. `available` faux : à choisir à la main. */
export async function suggestEntities(query: { entityIds?: string[]; text?: string }) {
  const data = await send<any>("/entities/suggestions", "POST", {
    entity_ids: query.entityIds ?? [],
    text: query.text ?? "",
  });
  return { available: data.available as boolean, items: (data.items as any[]).map(mapEntity) };
}
