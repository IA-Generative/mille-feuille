import { ref } from "vue";

import type { ChatWindowSource } from "@/components/ChatWindow.vue";
import type { DossierPresentation, SuggestedQuestion } from "@/types/dossierPresentation";
import { apiFetch } from "@/utils/api";

// La présentation d'un dossier, en tête de sa conversation : composée par le serveur de ce que l'analyse a produit, sans
// appel au modèle. Choisir une question suggérée fait entrer la question et sa réponse prête dans la conversation.

interface SourceOut {
  number: number | null;
  dossier_document_id: string | null;
  page_ids: string[];
  excerpt: string | null;
}

interface PresentationOut {
  status: DossierPresentation["status"];
  refreshing: boolean;
  error: string | null;
  dossier_name: string;
  summary: string | null;
  classification: { label: string; confidence: number | null } | null;
  entities: { name: string; value: string; page: number | null }[];
  agents: { name: string; output: string }[];
  documents: { id: string; name: string; label: string | null; page_count: number }[];
  suggestions: { id: string; question: string; answer: string; sources: SourceOut[] }[];
}

const toSource = (answerId: string, source: SourceOut, index: number): ChatWindowSource => ({
  id: `${answerId}-${index}`,
  number: source.number,
  excerpt: source.excerpt,
  dossierDocumentId: source.dossier_document_id,
  pages: [],
});

function toPresentation(out: PresentationOut): DossierPresentation {
  return {
    status: out.status,
    refreshing: out.refreshing,
    error: out.error ?? undefined,
    dossierName: out.dossier_name,
    summary: out.summary ?? undefined,
    classification: out.classification
      ? { label: out.classification.label, confidence: out.classification.confidence ?? undefined }
      : undefined,
    entities: out.entities.map((e) => ({ name: e.name, value: e.value, page: e.page ?? undefined })),
    agents: out.agents,
    documents: out.documents.map((d) => ({ id: d.id, name: d.name, label: d.label ?? undefined, pageCount: d.page_count })),
    suggestions: out.suggestions.map(
      (q): SuggestedQuestion => ({
        id: q.id,
        question: q.question,
        answer: q.answer,
        sources: q.sources.map((source, index) => toSource(q.id, source, index)),
      }),
    ),
  };
}

export function useDossierPresentation(dossierId: string) {
  const presentation = ref<DossierPresentation | null>(null);
  const error = ref("");

  async function load() {
    error.value = "";
    try {
      presentation.value = toPresentation(await apiFetch<PresentationOut>(`/api/dossiers/${dossierId}/presentation`));
    } catch (e) {
      error.value = e instanceof Error ? e.message : "Impossible de charger la présentation du dossier.";
    }
  }

  /** Pose une question suggérée : elle et sa réponse prête entrent dans la conversation (le serveur les y ajoute). */
  async function ask(conversationId: string, answerId: string): Promise<boolean> {
    error.value = "";
    try {
      await apiFetch(`/api/dossiers/${dossierId}/conversations/${conversationId}/question-answers/${answerId}/ask`, {
        method: "POST",
      });
      return true;
    } catch (e) {
      error.value = e instanceof Error ? e.message : "Impossible de poser cette question.";
      return false;
    }
  }

  return { presentation, error, load, ask };
}
