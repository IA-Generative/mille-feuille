import { ref } from "vue";

import type {
  AnalyseDefinitions,
  DocumentTemplate,
  DocumentTemplateVersion,
  ElementKind,
  FieldDefinition,
  FieldSource,
  GenerationPrompt,
  MetadataKey,
  PlaceholderReport,
  SourcesReport,
  TemplateInspection,
} from "@/types/documentTemplate";
import type { PromptVersion } from "@/types/analyse";
import { API_BASE_URL, ApiError, apiFetch, userMessage } from "@/utils/api";

const BASE = "/api/admin/document-templates";
const PROMPT_BASE = "/api/admin/generation-prompt";

function mapSource(api: any): FieldSource {
  if (api.kind === "analysis") {
    return { kind: "analysis", elementKind: api.element_kind as ElementKind, definitionName: api.definition_name };
  }
  if (api.kind === "dossier_metadata") return { kind: "dossier_metadata", key: api.key as MetadataKey };
  return { kind: "instruction" };
}

function mapField(api: any): FieldDefinition {
  return {
    name: api.name,
    label: api.label,
    type: api.type,
    required: api.required,
    instruction: api.instruction ?? "",
    source: mapSource(api.source),
  };
}

function mapTemplate(api: any): DocumentTemplate {
  return {
    id: api.id,
    analyseId: api.analyse_id,
    archived: api.archived,
    createdBy: api.created_by,
    createdAt: api.created_at,
    updatedAt: api.updated_at,
    versionNumber: api.version_number,
    name: api.name,
    description: api.description,
    generationInstructions: api.generation_instructions,
    fields: (api.fields ?? []).map(mapField),
    placeholders: api.placeholders ?? [],
    warnings: api.warnings ?? [],
    fileName: api.file_name,
    fileSize: api.file_size,
    lastAuthorId: api.last_author_id,
  };
}

function mapVersion(api: any): DocumentTemplateVersion {
  return {
    id: api.id,
    versionNumber: api.version_number,
    name: api.name,
    description: api.description,
    generationInstructions: api.generation_instructions,
    fields: (api.fields ?? []).map(mapField),
    placeholders: api.placeholders ?? [],
    fileName: api.file_name,
    fileSize: api.file_size,
    authorId: api.author_id,
    restoredFromVersionId: api.restored_from_version_id,
    createdAt: api.created_at,
  };
}

/** Champ au format du serveur (snake_case). */
function fieldToApi(field: FieldDefinition) {
  const source =
    field.source.kind === "analysis"
      ? { kind: "analysis", element_kind: field.source.elementKind, definition_name: field.source.definitionName.trim() }
      : field.source.kind === "dossier_metadata"
        ? { kind: "dossier_metadata", key: field.source.key }
        : { kind: "instruction" };
  return {
    name: field.name,
    label: field.label.trim(),
    type: field.type,
    required: field.required,
    instruction: field.instruction.trim(),
    source,
  };
}

export interface TemplateDraft {
  /** Analyse du modèle, à la création seulement : elle ne change plus ensuite. */
  analyseId?: string;
  name: string;
  description: string;
  generationInstructions: string;
  fields: FieldDefinition[];
  /** Nouveau fichier ODT ; absent, la version garde celui de la version courante. */
  file?: File | null;
}

function toFormData(draft: TemplateDraft): FormData {
  const form = new FormData();
  if (draft.analyseId) form.append("analyse_id", draft.analyseId);
  form.append("name", draft.name.trim());
  form.append("description", draft.description.trim());
  form.append("generation_instructions", draft.generationInstructions.trim());
  form.append("fields", JSON.stringify(draft.fields.map(fieldToApi)));
  if (draft.file) form.append("file", draft.file);
  return form;
}

/**
 * Rapport « placeholders / champs » du serveur (422), ou null si l'erreur est autre. Le serveur renvoie les
 * écarts dans les deux sens ; ils sont affichés tels quels, sans être ignorés.
 */
export function placeholderReportFrom(error: unknown): PlaceholderReport | null {
  if (!(error instanceof ApiError) || error.status !== 422) return null;
  const detail = error.detail as any;
  if (!detail || typeof detail !== "object" || !Array.isArray(detail.unknown_placeholders)) return null;
  return {
    message: detail.message,
    unknownPlaceholders: detail.unknown_placeholders,
    unusedFields: detail.unused_fields ?? [],
  };
}

/** Rapport « sources » du serveur (422) : des champs désignent des éléments que l'analyse ne définit pas. */
export function sourcesReportFrom(error: unknown): SourcesReport | null {
  if (!(error instanceof ApiError) || error.status !== 422) return null;
  const detail = error.detail as any;
  if (!detail || typeof detail !== "object" || !Array.isArray(detail.unknown_sources)) return null;
  return {
    message: detail.message,
    unknownSources: detail.unknown_sources.map((u: any) => ({
      field: u.field,
      elementKind: u.element_kind,
      definitionName: u.definition_name,
    })),
  };
}

/** Message lisible d'une erreur d'API (texte, ou liste d'erreurs de validation des champs). */
export function errorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    const detail = error.detail as any;
    if (Array.isArray(detail)) {
      return detail
        .map((e) => (Array.isArray(e.loc) && e.loc.length ? `${e.loc.join(" › ")} : ${e.msg}` : e.msg))
        .join(" ; ");
    }
  }
  return userMessage(error, fallback);
}

/**
 * Modèles de document et prompt de l'agent de génération (administration, backend issues #138 et #141).
 * Rien n'est mis en cache : l'administration relit après chaque écriture.
 */
export function useDocumentTemplates() {
  const templates = ref<DocumentTemplate[]>([]);

  /** Modèles d'une analyse (un modèle appartient à une seule analyse). */
  async function fetchTemplates(analyseId: string, includeArchived = false): Promise<DocumentTemplate[]> {
    const data = await apiFetch<any[]>(`${BASE}?analyse_id=${analyseId}&include_archived=${includeArchived}`);
    templates.value = data.map(mapTemplate);
    return templates.value;
  }

  /** Entités, labels et agents que l'analyse définit : les choix possibles pour la source d'un champ. */
  async function fetchDefinitions(analyseId: string): Promise<AnalyseDefinitions> {
    return apiFetch<AnalyseDefinitions>(`${BASE}/analyses/${analyseId}/definitions`);
  }

  async function fetchTemplate(id: string): Promise<DocumentTemplate> {
    return mapTemplate(await apiFetch<any>(`${BASE}/${id}`));
  }

  async function fetchVersions(id: string): Promise<DocumentTemplateVersion[]> {
    return (await apiFetch<any[]>(`${BASE}/${id}/versions`)).map(mapVersion);
  }

  /** Lit un fichier sans rien enregistrer : ses placeholders, point de départ de la définition des champs. */
  async function inspectFile(file: File): Promise<TemplateInspection> {
    const form = new FormData();
    form.append("file", file);
    const data = await apiFetch<any>(`${BASE}/inspect`, { method: "POST", body: form });
    return {
      placeholders: data.placeholders,
      fileName: data.file_name,
      fileSize: data.file_size,
      fonts: (data.fonts ?? []).map((f: any) => ({ name: f.name, status: f.status, replacedBy: f.replaced_by })),
      warnings: data.warnings ?? [],
    };
  }

  async function createTemplate(draft: TemplateDraft): Promise<DocumentTemplate> {
    return mapTemplate(await apiFetch<any>(BASE, { method: "POST", body: toFormData(draft) }));
  }

  /** Ajoute une version (état complet souhaité) : l'ancienne reste dans l'historique. */
  async function addVersion(id: string, draft: TemplateDraft): Promise<DocumentTemplate> {
    return mapTemplate(await apiFetch<any>(`${BASE}/${id}/versions`, { method: "POST", body: toFormData(draft) }));
  }

  async function restoreVersion(id: string, versionId: string): Promise<DocumentTemplate> {
    return mapTemplate(
      await apiFetch<any>(`${BASE}/${id}/restore`, { method: "POST", body: JSON.stringify({ version_id: versionId }) }),
    );
  }

  async function setArchived(id: string, archived: boolean): Promise<DocumentTemplate> {
    return mapTemplate(await apiFetch<any>(`${BASE}/${id}/${archived ? "archive" : "unarchive"}`, { method: "POST" }));
  }

  function fileUrl(id: string, versionNumber: number): string {
    return `${API_BASE_URL}${BASE}/${id}/versions/${versionNumber}/file`;
  }

  // --- Prompt de l'agent de génération ---

  async function fetchPrompt(): Promise<GenerationPrompt> {
    const data = await apiFetch<any>(PROMPT_BASE);
    return { versionNumber: data.version_number, label: data.label, content: data.content, isDefault: data.is_default };
  }

  /** Versions du prompt, de la plus récente à la plus ancienne. */
  async function fetchPromptVersions(): Promise<PromptVersion[]> {
    const data = await apiFetch<any[]>(`${PROMPT_BASE}/versions`);
    return data.map((v) => ({ id: v.id, content: v.content, createdAt: v.created_at })).reverse();
  }

  async function savePrompt(content: string): Promise<void> {
    await apiFetch(`${PROMPT_BASE}/versions`, { method: "POST", body: JSON.stringify({ content }) });
  }

  async function restorePrompt(versionId: string): Promise<void> {
    await apiFetch(`${PROMPT_BASE}/restore`, { method: "POST", body: JSON.stringify({ version_id: versionId }) });
  }

  return {
    templates,
    fetchTemplates,
    fetchDefinitions,
    fetchTemplate,
    fetchVersions,
    inspectFile,
    createTemplate,
    addVersion,
    restoreVersion,
    setArchived,
    fileUrl,
    fetchPrompt,
    fetchPromptVersions,
    savePrompt,
    restorePrompt,
  };
}
