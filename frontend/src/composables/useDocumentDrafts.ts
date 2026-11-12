import { ref } from "vue";

import type {
  Completeness,
  DocumentDraft,
  DossierTemplate,
  DraftField,
  DraftSummary,
  FieldValue,
  FieldVersion,
  GeneratedDocument,
} from "@/types/documentDraft";
import { API_BASE_URL, ApiError, apiFetch, userMessage } from "@/utils/api";

function mapVersion(api: any): FieldVersion {
  return {
    id: api.id,
    fieldName: api.field_name,
    versionNumber: api.version_number,
    value: api.value,
    status: api.status,
    origin: api.origin,
    authorId: api.author_id,
    reason: api.reason,
    restoredFromVersionId: api.restored_from_version_id,
    promptVersion: api.prompt_version,
    model: api.model,
    createdAt: api.created_at,
  };
}

function mapField(api: any): DraftField {
  return {
    name: api.name,
    label: api.label,
    type: api.type,
    required: api.required,
    instruction: api.instruction ?? "",
    source: api.source,
    current: mapVersion(api.current),
    sourceDetails: (api.source_details ?? []).map((s: any) => ({ type: s.type, label: s.label, text: s.text, page: s.page })),
    stale: api.stale ?? false,
  };
}

function mapDraft(api: any): DocumentDraft {
  return {
    id: api.id,
    dossierId: api.dossier_id,
    analysisId: api.analysis_id,
    revisionId: api.revision_id,
    revisionNumber: api.revision_number,
    templateId: api.template_id,
    templateName: api.template_name,
    templateVersionNumber: api.template_version_number,
    status: api.status,
    createdBy: api.created_by,
    createdAt: api.created_at,
    fields: api.fields.map(mapField),
    completeness: api.completeness as Completeness,
    generationStatus: api.generation_status,
    generationError: api.generation_error,
    generationProposalCount: api.generation_proposal_count,
    generationMissing: api.generation_missing,
    generationTruncated: api.generation_truncated ?? false,
    generationPromptVersion: api.generation_prompt_version,
  };
}

function mapDocument(api: any): GeneratedDocument {
  return {
    id: api.id,
    draftId: api.draft_id,
    versionNumber: api.version_number,
    templateName: api.template_name,
    templateVersionNumber: api.template_version_number,
    revisionNumber: api.revision_number,
    fileName: api.file_name,
    hasPdf: api.has_pdf,
    odtSize: api.odt_size,
    pdfSize: api.pdf_size,
    incompleteFields: api.incomplete_fields ?? [],
    visibility: api.visibility,
    authorId: api.author_id,
    createdAt: api.created_at,
  };
}

/** Champs obligatoires non validés, quand le serveur refuse de générer un document incomplet (409). */
export function incompleteFieldsFrom(error: unknown): string[] | null {
  if (!(error instanceof ApiError) || error.status !== 409) return null;
  const detail = error.detail as any;
  return detail && typeof detail === "object" && Array.isArray(detail.incomplete_fields) ? detail.incomplete_fields : null;
}

/** Message lisible d'une erreur d'API (texte du serveur en français, sinon une phrase de `userMessage`). */
export function draftErrorMessage(error: unknown, fallback: string): string {
  return userMessage(error, fallback);
}

/**
 * Brouillons de document d'un dossier et documents générés. Un brouillon est interne : jamais montré à l'usager.
 * Rien n'est mis en cache : l'écran relit le brouillon après chaque écriture.
 */
export function useDocumentDrafts(dossierId: string) {
  const base = `/api/dossiers/${dossierId}`;
  const draftBase = (draftId: string) => `${base}/document-drafts/${draftId}`;
  const busy = ref(false);

  /** Modèles que ce dossier peut utiliser : ceux, non archivés, de son analyse. */
  async function fetchTemplates(): Promise<DossierTemplate[]> {
    const data = await apiFetch<any[]>(`${base}/document-templates`);
    return data.map((t) => ({
      id: t.id,
      name: t.name,
      description: t.description,
      versionNumber: t.version_number,
      fieldCount: t.fields.length,
    }));
  }

  async function fetchDrafts(): Promise<DraftSummary[]> {
    const data = await apiFetch<any[]>(`${base}/document-drafts`);
    return data.map((d) => ({
      id: d.id,
      templateName: d.template_name,
      templateVersionNumber: d.template_version_number,
      status: d.status,
      createdBy: d.created_by,
      createdAt: d.created_at,
    }));
  }

  async function createDraft(templateId: string): Promise<DocumentDraft> {
    return mapDraft(await apiFetch<any>(`${base}/document-drafts`, { method: "POST", body: JSON.stringify({ template_id: templateId }) }));
  }

  async function fetchDraft(draftId: string): Promise<DocumentDraft> {
    return mapDraft(await apiFetch<any>(draftBase(draftId)));
  }

  const post = (path: string, body: unknown = {}) => apiFetch<any>(path, { method: "POST", body: JSON.stringify(body) });

  /** Saisie à la main : la valeur est validée d'office. */
  const setValue = (draftId: string, name: string, value: FieldValue, reason?: string) =>
    apiFetch<any>(`${draftBase(draftId)}/fields/${name}`, { method: "PUT", body: JSON.stringify({ value, reason: reason || null }) });
  const validate = (draftId: string, name: string) => post(`${draftBase(draftId)}/fields/${name}/validate`);
  const reject = (draftId: string, name: string, reason?: string) =>
    post(`${draftBase(draftId)}/fields/${name}/reject`, { reason: reason || null });
  /** Accepte d'un coup les valeurs proposées (celles données, ou toutes). */
  const validateAll = (draftId: string, names?: string[]) => post(`${draftBase(draftId)}/validate`, { names: names ?? null });

  async function fetchFieldVersions(draftId: string, name: string): Promise<FieldVersion[]> {
    return (await apiFetch<any[]>(`${draftBase(draftId)}/fields/${name}/versions`)).map(mapVersion);
  }
  const restoreFieldVersion = (draftId: string, name: string, versionId: string) =>
    post(`${draftBase(draftId)}/fields/${name}/restore`, { version_id: versionId });

  /** Demande à l'agent de proposer des valeurs (tous les champs non validés, ou ceux donnés) : asynchrone. */
  const generateValues = (draftId: string, names?: string[]) => post(`${draftBase(draftId)}/generate`, { names: names ?? null });
  /** Régénère un seul champ, avec une consigne facultative : asynchrone. */
  const regenerateField = (draftId: string, name: string, instruction?: string) =>
    post(`${draftBase(draftId)}/fields/${name}/regenerate`, { instruction: instruction || null });

  /** Assemble le document (ODT et PDF) depuis les valeurs validées. 409 si des champs obligatoires ne le sont pas. */
  async function generateDocument(draftId: string, confirmIncomplete = false): Promise<GeneratedDocument> {
    return mapDocument(await post(`${draftBase(draftId)}/documents`, { confirm_incomplete: confirmIncomplete }));
  }

  async function fetchDocuments(draftId?: string): Promise<GeneratedDocument[]> {
    const query = draftId ? `?draft_id=${draftId}` : "";
    return (await apiFetch<any[]>(`${base}/generated-documents${query}`)).map(mapDocument);
  }

  function documentUrl(documentId: string, format: "odt" | "pdf", inline = false): string {
    return `${API_BASE_URL}${base}/generated-documents/${documentId}/file?format=${format}${inline ? "&inline=true" : ""}`;
  }

  /** Aperçu PDF du modèle rempli avec les valeurs courantes (validées et proposées). */
  async function fetchPreview(draftId: string): Promise<Blob> {
    const response = await fetch(`${API_BASE_URL}${draftBase(draftId)}/preview`, { credentials: "include" });
    if (!response.ok) {
      const body = await response.json().catch(() => null);
      throw new ApiError(response.status, typeof body?.detail === "string" ? body.detail : response.statusText, body?.detail);
    }
    return response.blob();
  }

  async function archiveDraft(draftId: string): Promise<DocumentDraft> {
    return mapDraft(await post(`${draftBase(draftId)}/archive`));
  }

  return {
    busy,
    fetchTemplates,
    fetchDrafts,
    createDraft,
    fetchDraft,
    setValue,
    validate,
    reject,
    validateAll,
    fetchFieldVersions,
    restoreFieldVersion,
    generateValues,
    regenerateField,
    generateDocument,
    fetchDocuments,
    documentUrl,
    fetchPreview,
    archiveDraft,
  };
}
