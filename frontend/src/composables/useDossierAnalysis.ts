import { computed, ref } from "vue";

import { apiFetch, userMessage } from "@/utils/api";
import type {
  AnalysisElement,
  AnalysisElementKind,
  DossierAnalysis,
  DossierAnalysisSummary,
  ElementValue,
  ElementVersion,
  Proposal,
} from "@/types/dossierAnalysis";

function mapVersion(api: any): ElementVersion {
  return {
    id: api.id,
    elementId: api.element_id,
    versionNumber: api.version_number,
    value: api.value,
    confidence: api.confidence,
    origin: api.origin,
    predictionId: api.prediction_id,
    authorId: api.author_id,
    reason: api.reason,
    sourceType: api.source_type,
    sourceId: api.source_id,
    restoredFromVersionId: api.restored_from_version_id,
    createdAt: api.created_at,
  };
}

function mapElement(api: any): AnalysisElement {
  return {
    id: api.id,
    analysisId: api.analysis_id,
    unitId: api.unit_id,
    kind: api.kind,
    definitionName: api.definition_name,
    documentId: api.document_id,
    firstPageNumber: api.first_page_number,
    originElementId: api.origin_element_id,
    needsReview: api.needs_review,
    reviewReason: api.review_reason,
    retainedVersion: api.retained_version ? mapVersion(api.retained_version) : null,
    latestModelVersion: api.latest_model_version ? mapVersion(api.latest_model_version) : null,
    createdAt: api.created_at,
  };
}

function mapSummary(api: any): DossierAnalysisSummary {
  return {
    id: api.id,
    dossierId: api.dossier_id,
    sequence: api.sequence,
    status: api.status,
    analyseVersion: api.analyse_version,
    model: api.model,
    startedAt: api.started_at,
    endedAt: api.ended_at,
    createdAt: api.created_at,
  };
}

function mapAnalysis(api: any): DossierAnalysis {
  return { ...mapSummary(api), elements: (api.elements ?? []).map(mapElement) };
}

export function mapProposal(api: any): Proposal {
  return {
    id: api.id,
    analysisId: api.analysis_id,
    elementId: api.element_id,
    kind: api.kind,
    definitionName: api.definition_name,
    proposedValue: api.proposed_value,
    reason: api.reason,
    sourceType: api.source_type,
    proposedBy: api.proposed_by,
    status: api.status,
    decidedBy: api.decided_by,
    decidedAt: api.decided_at,
    createdAt: api.created_at,
  };
}

/**
 * Analyse de dossier d'un dossier : les analyses (une par exécution), les
 * éléments de celle qu'on consulte, ses propositions en attente et les
 * actions de l'instructeur (modifier, restaurer, accepter, rejeter).
 * Instancié par dossier, comme useConversations.
 */
export function useDossierAnalysis(dossierId: string) {
  const analyses = ref<DossierAnalysisSummary[]>([]);
  const analysis = ref<DossierAnalysis | undefined>(undefined);
  const proposals = ref<Proposal[]>([]);
  const isLoading = ref(false);
  const error = ref<string | undefined>(undefined);

  const base = `/api/dossiers/${dossierId}`;
  const analysisBase = (analysisId: string) => `${base}/analyses-dossier/${analysisId}`;

  /** L'analyse la plus récente est la seule modifiable depuis l'interface. */
  const isCurrent = computed(() => !!analysis.value && analyses.value[0]?.id === analysis.value.id);
  const isFrozen = computed(() => analysis.value?.status === "figée");
  const canEdit = computed(() => isCurrent.value && !isFrozen.value);

  async function loadProposals() {
    if (!analysis.value) {
      proposals.value = [];
      return;
    }
    const api = await apiFetch<any[]>(`${analysisBase(analysis.value.id)}/proposals?status=pending`);
    proposals.value = api.map(mapProposal);
  }

  async function select(analysisId: string) {
    analysis.value = mapAnalysis(await apiFetch<any>(analysisBase(analysisId)));
    await loadProposals();
  }

  /** Charge la liste des analyses et sélectionne la plus récente (ou celle demandée). */
  async function load(analysisId?: string) {
    isLoading.value = true;
    error.value = undefined;
    try {
      analyses.value = (await apiFetch<any[]>(`${base}/analyses-dossier`)).map(mapSummary);
      const target = analysisId ?? analyses.value[0]?.id;
      if (target) await select(target);
      else {
        analysis.value = undefined;
        proposals.value = [];
      }
    } catch (e) {
      error.value = userMessage(e, "Impossible de charger l'analyse du dossier.");
    } finally {
      isLoading.value = false;
    }
  }

  /** Recharge l'analyse affichée après une modification. */
  async function refresh() {
    if (analysis.value) await select(analysis.value.id);
  }

  async function fetchVersions(elementId: string): Promise<ElementVersion[]> {
    if (!analysis.value) return [];
    const api = await apiFetch<any[]>(`${analysisBase(analysis.value.id)}/elements/${elementId}/versions`);
    return api.map(mapVersion);
  }

  /** Apporte une nouvelle valeur à un élément (le motif est obligatoire). */
  async function addVersion(elementId: string, value: ElementValue, reason: string, baseVersionId?: string | null) {
    if (!analysis.value) return;
    await apiFetch(`${analysisBase(analysis.value.id)}/elements/${elementId}/versions`, {
      method: "POST",
      // base_version_id : la version que l'instructeur avait sous les yeux ; si
      // l'élément a changé depuis, le serveur refuse au lieu d'écraser (409).
      body: JSON.stringify({ value, reason, base_version_id: baseVersionId ?? null }),
    });
    await refresh();
  }

  /** Restaure une version antérieure : ajoute une version, ne supprime rien. */
  async function restoreVersion(elementId: string, versionId: string, reason?: string) {
    if (!analysis.value) return;
    await apiFetch(`${analysisBase(analysis.value.id)}/elements/${elementId}/restore`, {
      method: "POST",
      body: JSON.stringify({ version_id: versionId, reason: reason || null }),
    });
    await refresh();
  }

  async function createElement(kind: AnalysisElementKind, value: ElementValue, definitionName: string, reason: string) {
    if (!analysis.value) return;
    await apiFetch(`${analysisBase(analysis.value.id)}/elements`, {
      method: "POST",
      body: JSON.stringify({ kind, value, definition_name: definitionName || null, reason: reason || null }),
    });
    await refresh();
  }

  async function decide(proposalId: string, action: "accept" | "modify" | "reject", body: object = {}) {
    if (!analysis.value) return;
    await apiFetch(`${analysisBase(analysis.value.id)}/proposals/${proposalId}/${action}`, {
      method: "POST",
      body: JSON.stringify(body),
    });
    await refresh();
  }

  const acceptProposal = (proposalId: string) => decide(proposalId, "accept");
  const modifyProposal = (proposalId: string, value: ElementValue, reason?: string) =>
    decide(proposalId, "modify", { value, reason: reason || null });
  const rejectProposal = (proposalId: string, reason?: string) =>
    decide(proposalId, "reject", { reason: reason || null });

  return {
    analyses,
    analysis,
    proposals,
    isLoading,
    error,
    isCurrent,
    isFrozen,
    canEdit,
    load,
    select,
    refresh,
    fetchVersions,
    addVersion,
    restoreVersion,
    createElement,
    acceptProposal,
    modifyProposal,
    rejectProposal,
  };
}
