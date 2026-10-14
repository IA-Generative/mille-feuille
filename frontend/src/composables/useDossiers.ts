import { computed, reactive, ref } from "vue";

import { API_BASE_URL, apiFetch } from "@/utils/api";
import type { DocumentSource } from "@/types/documentSource";
import type {
  AnalyseSuggestion,
  Dossier,
  DossierDocument,
  ExecutionStep,
  Summary,
} from "@/types/dossier";

function mapSummary(api: any): Summary | undefined {
  if (!api) return undefined;
  return {
    id: api.id,
    content: api.content,
    model: api.model ?? undefined,
    createdAt: api.created_at,
  };
}

export function mapSource(api: any): DocumentSource {
  return {
    id: api.id,
    name: api.name,
    description: api.description ?? "",
    analyseId: api.analyse_id ?? undefined,
    dossierId: api.dossier_id ?? undefined,
  };
}

function mapDocument(api: any): DossierDocument {
  return {
    id: api.id,
    name: api.name,
    size: api.size,
    s3Key: api.s3_key,
    mimetype: api.mimetype,
    label: api.label ?? undefined,
    textExtractionStatus: api.text_extraction_status,
    textExtractionError: api.text_extraction_error ?? undefined,
    fileHash: api.file_hash ?? undefined,
    createdAt: api.created_at ?? undefined,
    source: api.source ? mapSource(api.source) : undefined,
    summaryStatus: api.summary_status,
    summaryError: api.summary_error ?? undefined,
    summary: mapSummary(api.summary),
  };
}

function mapStep(api: any): ExecutionStep {
  return {
    id: api.id,
    kind: api.kind,
    label: api.label,
    status: api.status,
    startedAt: api.started_at,
    endedAt: api.ended_at ?? undefined,
    output: api.output ?? undefined,
  };
}

function mapSuggestion(api: any): AnalyseSuggestion {
  return {
    analyseId: api.analyse_id,
    name: api.name,
    score: api.score,
    rationale: api.rationale,
  };
}

function mapDossier(api: any): Dossier {
  return {
    id: api.id,
    name: api.name,
    workflowStatus: api.workflow_status
      ? {
          id: api.workflow_status.id,
          name: api.workflow_status.name,
          color: api.workflow_status.color,
          position: api.workflow_status.position,
          isInitial: api.workflow_status.is_initial,
          isFinal: api.workflow_status.is_final,
        }
      : undefined,
    visibility: api.visibility,
    closedAt: api.closed_at ?? undefined,
    dueAt: api.due_at ?? undefined,
    due: api.due ? { level: api.due.level, daysLeft: api.due.days_left, color: api.due.color ?? undefined } : undefined,
    closedBeforeDue: api.closed_before_due ?? undefined,
    analyseId: api.analyse_id ?? undefined,
    analyseVersion: api.analyse_version,
    createdAt: api.created_at,
    status: api.status,
    startedAt: api.started_at ?? undefined,
    endedAt: api.ended_at ?? undefined,
    executionSteps: api.execution_steps.map(mapStep),
    documents: api.documents.map(mapDocument),
    summaryStatus: api.summary_status,
    summaryError: api.summary_error ?? undefined,
    summary: mapSummary(api.summary),
    suggestionStatus: api.suggestion_status,
    suggestedAnalyses: api.suggested_analyses?.map(mapSuggestion),
  };
}

// Store partagé par toute l'application : `dossiers` contient la page
// actuellement chargée (pagination côté serveur, voir fetchList) plus tout
// dossier ouvert individuellement (fetchDossier) qui ne s'y trouvait pas.
const dossiers = reactive<Dossier[]>([]);
const total = ref(0);
const pageCount = ref(1);
const currentPage = ref(1);
const pageSize = ref(10);

/**
 * Filtres et tri de la liste : par statut de dossier (#170), par échéance (#172 : dépassée, dans 7 ou 30 jours,
 * sans échéance ; seuls les dossiers non clos), tri par date de création (défaut), par statut ou par échéance.
 */
export interface DossierListOptions {
  workflowStatusId?: string;
  due?: "overdue" | "7" | "30" | "none";
  sort?: "created_at" | "status" | "due";
}

async function fetchList(page = currentPage.value, size = pageSize.value, options: DossierListOptions = {}) {
  const query = new URLSearchParams({ page: String(page), page_size: String(size) });
  if (options.workflowStatusId) query.set("workflow_status_id", options.workflowStatusId);
  if (options.due) query.set("due", options.due);
  if (options.sort && options.sort !== "created_at") query.set("sort", options.sort);
  const data = await apiFetch<{ items: any[]; total: number; page: number; page_size: number; pages: number }>(
    `/api/dossiers?${query}`,
  );
  dossiers.splice(0, dossiers.length, ...data.items.map(mapDossier));
  total.value = data.total;
  pageCount.value = data.pages;
  currentPage.value = data.page;
  pageSize.value = data.page_size;
}

function upsert(dossier: Dossier) {
  const index = dossiers.findIndex((d) => d.id === dossier.id);
  if (index === -1) dossiers.unshift(dossier);
  else dossiers[index] = dossier;
}

export function useDossiers() {
  const list = computed(() => dossiers);

  const getById = (id: string) => dossiers.find((d) => d.id === id);

  // Pour ouvrir un dossier qui n'est pas forcément dans la page actuellement
  // chargée (navigation directe vers /dossiers/:id).
  const fetchDossier = async (id: string) => {
    const data = await apiFetch<any>(`/api/dossiers/${id}`);
    const dossier = mapDossier(data);
    upsert(dossier);
    return dossier;
  };

  /**
   * Crée un dossier. `access` (#177) : « restreint » (par défaut côté serveur) avec au moins un des groupes de la
   * personne, ou « selon l'analyse » ; sans lui, le serveur restreint le dossier à tous les groupes de la personne.
   */
  const create = async (name: string, analyseId?: string, access?: { restricted: boolean; groups: string[] }) => {
    const body: Record<string, unknown> = { name };
    if (analyseId) body.analyse_id = analyseId;
    if (access) {
      body.visibility = access.restricted ? "restricted" : "analyse";
      if (access.restricted) body.group_paths = access.groups;
    }
    const data = await apiFetch<any>("/api/dossiers", {
      method: "POST",
      body: JSON.stringify(body),
    });
    const dossier = mapDossier(data);
    upsert(dossier);
    return dossier;
  };

  /** Change le statut de dossier ; le serveur pose ou efface la date de clôture. */
  const setWorkflowStatus = async (dossierId: string, statusId: string) => {
    const data = await apiFetch<any>(`/api/dossiers/${dossierId}/workflow-status`, {
      method: "PUT",
      body: JSON.stringify({ status_id: statusId }),
    });
    const dossier = mapDossier(data);
    upsert(dossier);
    return dossier;
  };

  /** Change l'échéance (AAAA-MM-JJ) ; `null` la supprime. Le serveur recalcule le niveau d'échéance. */
  const setDueAt = async (dossierId: string, dueAt: string | null) => {
    const data = await apiFetch<any>(`/api/dossiers/${dossierId}/due-at`, {
      method: "PUT",
      body: JSON.stringify({ due_at: dueAt }),
    });
    const dossier = mapDossier(data);
    upsert(dossier);
    return dossier;
  };

  // `sourceId` s'applique à tous les fichiers du dépôt.
  const addDocuments = async (dossierId: string, files: FileList | File[], sourceId?: string) => {
    const formData = new FormData();
    for (const file of Array.from(files)) formData.append("files", file);
    if (sourceId) formData.append("source_id", sourceId);
    const data = await apiFetch<any>(`/api/dossiers/${dossierId}/documents`, {
      method: "POST",
      body: formData,
    });
    upsert(mapDossier(data));
  };

  const setDocumentLabel = async (dossierId: string, documentId: string, label: string | null) => {
    await apiFetch<any>(`/api/dossiers/${dossierId}/documents/${documentId}/label`, {
      method: "PUT",
      body: JSON.stringify({ label }),
    });
    const data = await apiFetch<any>(`/api/dossiers/${dossierId}`);
    upsert(mapDossier(data));
  };

  const launch = async (dossierId: string) => {
    const data = await apiFetch<any>(`/api/dossiers/${dossierId}/launch`, { method: "POST" });
    upsert(mapDossier(data));
  };

  // Régénère le résumé d'un document (issue #52) : le backend dispatche
  // une tâche Celery sur la file agent_execution.
  const regenerateDocumentSummary = async (dossierId: string, documentId: string) => {
    await apiFetch<any>(`/api/dossiers/${dossierId}/documents/${documentId}/summary`, { method: "POST" });
    const data = await apiFetch<any>(`/api/dossiers/${dossierId}`);
    upsert(mapDossier(data));
  };

  // Régénère le résumé global du dossier (issue #52).
  const regenerateDossierSummary = async (dossierId: string) => {
    await apiFetch<any>(`/api/dossiers/${dossierId}/summary`, { method: "POST" });
    const data = await apiFetch<any>(`/api/dossiers/${dossierId}`);
    upsert(mapDossier(data));
  };

  // Déclenche la génération des suggestions d'analyse pour un dossier
  // « à ranger » (issue #54).
  const suggestAnalyse = async (dossierId: string) => {
    await apiFetch<any>(`/api/dossiers/${dossierId}/suggest-analysis`, { method: "POST" });
    const data = await apiFetch<any>(`/api/dossiers/${dossierId}`);
    upsert(mapDossier(data));
  };

  // Valide le rattachement d'un dossier « à ranger » à une analyse
  // (issue #54).
  const assignAnalyse = async (dossierId: string, analyseId: string) => {
    await apiFetch<any>(`/api/dossiers/${dossierId}/assign`, {
      method: "POST",
      body: JSON.stringify({ analyse_id: analyseId }),
    });
    const data = await apiFetch<any>(`/api/dossiers/${dossierId}`);
    upsert(mapDossier(data));
  };

  const stop = async (dossierId: string) => {
    const data = await apiFetch<any>(`/api/dossiers/${dossierId}/stop`, { method: "POST" });
    upsert(mapDossier(data));
  };

  // SSE : le navigateur s'abonne à /dossiers/{id}/stream, qui émet un
  // `execution-update` à chaque changement d'état (statut du dossier, statut
  // d'extraction de texte d'un document...) puis un `done` quand il n'y a
  // plus de travail actif. Le callback reçoit le dossier sérialisé (même
  // forme que GET /dossiers/{id}) et met à jour le store via upsert.
  const streamDossier = (dossierId: string, onUpdate: (dossier: Dossier) => void): (() => void) => {
    const url = `${API_BASE_URL}/api/dossiers/${dossierId}/stream`;
    const eventSource = new EventSource(url, { withCredentials: true });

    eventSource.addEventListener("execution-update", (event) => {
      const dossier = mapDossier(JSON.parse(event.data));
      upsert(dossier);
      onUpdate(dossier);
    });
    eventSource.addEventListener("done", () => {
      eventSource.close();
    });
    eventSource.addEventListener("error", () => {
      // Le navigateur reconnecte automatiquement en cas d'erreur réseau ;
      // on ferme pour éviter une boucle infinie (le serveur a déjà émis
      // `done` ou la session a expiré).
      eventSource.close();
    });

    return () => eventSource.close();
  };

  return {
    list,
    total,
    pageCount,
    currentPage,
    pageSize,
    getById,
    fetchDossier,
    fetchList,
    create,
    setWorkflowStatus,
    setDueAt,
    addDocuments,
    setDocumentLabel,
    launch,
    stop,
    regenerateDocumentSummary,
    regenerateDossierSummary,
    suggestAnalyse,
    assignAnalyse,
    streamDossier,
  };
}
