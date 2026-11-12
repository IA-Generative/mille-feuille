import { onBeforeUnmount, ref } from "vue";

import { apiFetch, userMessage } from "@/utils/api";
import type { DossierNote, NoteVersion } from "@/types/dossierNote";

function mapNote(api: any): DossierNote {
  return {
    id: api.id,
    dossierId: api.dossier_id,
    createdBy: api.created_by,
    archived: api.archived,
    content: api.content,
    versionNumber: api.version_number,
    lastAuthorId: api.last_author_id,
    createdAt: api.created_at,
    updatedAt: api.updated_at,
    analysisStatus: api.analysis_status,
    analysisVersionNumber: api.analysis_version_number,
    analysisProposalCount: api.analysis_proposal_count,
    analysisError: api.analysis_error,
  };
}

function mapVersion(api: any): NoteVersion {
  return {
    id: api.id,
    noteId: api.note_id,
    versionNumber: api.version_number,
    content: api.content,
    authorId: api.author_id,
    restoredFromVersionId: api.restored_from_version_id,
    createdAt: api.created_at,
  };
}

const POLL_INTERVAL_MS = 2500;

/**
 * Notes internes d'un dossier : liste, ajout, modification (ajoute une
 * version), historique et restauration, archivage, et analyse d'une note pour
 * proposer des mises à jour de l'analyse (sur demande, suivie par sondage tant
 * qu'elle est en cours). Instancié par dossier, comme useConversations.
 */
export function useDossierNotes(dossierId: string, onAnalysisFinished?: (note: DossierNote) => void) {
  const notes = ref<DossierNote[]>([]);
  const includeArchived = ref(false);
  const isLoading = ref(false);
  const error = ref<string | undefined>(undefined);

  const base = `/api/dossiers/${dossierId}/notes`;
  let timer: ReturnType<typeof setTimeout> | undefined;

  function stopPolling() {
    if (timer) clearTimeout(timer);
    timer = undefined;
  }

  /** Tant qu'une analyse de note est en cours, on relit la liste jusqu'à sa fin. */
  function schedulePolling() {
    stopPolling();
    if (!notes.value.some((n) => n.analysisStatus === "en_cours")) return;
    timer = setTimeout(async () => {
      const running = new Set(notes.value.filter((n) => n.analysisStatus === "en_cours").map((n) => n.id));
      await load({ silent: true });
      for (const note of notes.value) {
        if (running.has(note.id) && note.analysisStatus !== "en_cours") onAnalysisFinished?.(note);
      }
    }, POLL_INTERVAL_MS);
  }

  async function load(options: { silent?: boolean } = {}) {
    if (!options.silent) isLoading.value = true;
    try {
      const suffix = includeArchived.value ? "?include_archived=true" : "";
      notes.value = (await apiFetch<any[]>(`${base}${suffix}`)).map(mapNote);
      error.value = undefined;
    } catch (e) {
      error.value = userMessage(e, "Impossible de charger les notes.");
    } finally {
      isLoading.value = false;
    }
    schedulePolling();
  }

  async function setIncludeArchived(value: boolean) {
    includeArchived.value = value;
    await load();
  }

  async function create(content: string) {
    await apiFetch(base, { method: "POST", body: JSON.stringify({ content }) });
    await load({ silent: true });
  }

  async function update(noteId: string, content: string) {
    await apiFetch(`${base}/${noteId}`, { method: "PUT", body: JSON.stringify({ content }) });
    await load({ silent: true });
  }

  async function fetchVersions(noteId: string): Promise<NoteVersion[]> {
    return (await apiFetch<any[]>(`${base}/${noteId}/versions`)).map(mapVersion);
  }

  /** Restaure une version antérieure : ajoute une version, ne supprime rien. */
  async function restore(noteId: string, versionId: string) {
    await apiFetch(`${base}/${noteId}/restore`, { method: "POST", body: JSON.stringify({ version_id: versionId }) });
    await load({ silent: true });
  }

  async function setArchived(noteId: string, archived: boolean) {
    await apiFetch(`${base}/${noteId}/${archived ? "archive" : "unarchive"}`, { method: "POST" });
    await load({ silent: true });
  }

  /** Demande l'analyse de la note : des propositions en attente seront ajoutées, rien n'est appliqué. */
  async function requestProposals(noteId: string) {
    await apiFetch(`${base}/${noteId}/propose`, { method: "POST" });
    await load({ silent: true });
    // Analyse déjà terminée à la première lecture (rapide) : le sondage ne verrait
    // jamais la transition, on prévient tout de suite.
    const note = notes.value.find((n) => n.id === noteId);
    if (note && note.analysisStatus !== "en_cours") onAnalysisFinished?.(note);
  }

  onBeforeUnmount(stopPolling);

  return {
    notes,
    includeArchived,
    isLoading,
    error,
    load,
    setIncludeArchived,
    create,
    update,
    fetchVersions,
    restore,
    setArchived,
    requestProposals,
  };
}
