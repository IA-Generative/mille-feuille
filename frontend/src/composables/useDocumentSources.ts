import { ref } from "vue";

import { mapSource } from "@/composables/useDossiers";
import type { DocumentSource, SourceChoice } from "@/types/documentSource";
import { apiFetch } from "@/utils/api";

// Sources de fichiers : catalogue d'une analyse, sources tampon d'un dossier « à ranger ». Les sources ne sont pas
// versionnées (pas d'historique ni de restauration).

interface SourceInput {
  name: string;
  description: string;
}

/** Sources proposées pour un dossier : celles de son analyse, ou ses sources tampon s'il est « à ranger ». */
export async function fetchDossierSources(dossierId: string): Promise<DocumentSource[]> {
  return (await apiFetch<any[]>(`/api/dossiers/${dossierId}/sources`)).map(mapSource);
}

/** Catalogue d'une analyse : utile avant que le dossier existe (modale de création). */
export async function fetchAnalyseSources(analyseId: string): Promise<DocumentSource[]> {
  return (await apiFetch<any[]>(`/api/analyses/${analyseId}/sources`)).map(mapSource);
}

/** Crée une source pour un dossier : du catalogue de son analyse, ou tampon s'il n'a pas d'analyse. */
export async function createDossierSource(dossierId: string, input: SourceInput): Promise<DocumentSource> {
  const data = await apiFetch<any>(`/api/dossiers/${dossierId}/sources`, { method: "POST", body: JSON.stringify(input) });
  return mapSource(data);
}

export async function createAnalyseSource(analyseId: string, input: SourceInput): Promise<DocumentSource> {
  const data = await apiFetch<any>(`/api/analyses/${analyseId}/sources`, { method: "POST", body: JSON.stringify(input) });
  return mapSource(data);
}

export async function updateSource(sourceId: string, input: SourceInput): Promise<DocumentSource> {
  const data = await apiFetch<any>(`/api/sources/${sourceId}`, { method: "PUT", body: JSON.stringify(input) });
  return mapSource(data);
}

/** Supprimer une source utilisée est permis : ses documents restent, sans source. */
export async function deleteSource(sourceId: string): Promise<void> {
  await apiFetch<void>(`/api/sources/${sourceId}`, { method: "DELETE" });
}

/** Change (ou retire, avec `null`) la source d'un document déjà déposé. */
export async function setDocumentSource(dossierId: string, documentId: string, sourceId: string | null): Promise<void> {
  await apiFetch<void>(`/api/dossiers/${dossierId}/documents/${documentId}/source`, {
    method: "PUT",
    body: JSON.stringify({ source_id: sourceId }),
  });
}

/** Transforme le choix fait au dépôt en identifiant de source, en créant la nouvelle source si besoin. */
export async function resolveSourceChoice(dossierId: string, choice: SourceChoice): Promise<string | undefined> {
  if (choice.kind === "existing") return choice.id;
  if (choice.kind === "new" && choice.name.trim()) {
    return (await createDossierSource(dossierId, { name: choice.name.trim(), description: choice.description.trim() })).id;
  }
  return undefined;
}

/** Sources d'un dossier chargées pour un écran : liste réactive + rechargement. */
export function useDossierSources(dossierId: string) {
  const sources = ref<DocumentSource[]>([]);
  const load = async () => {
    try {
      sources.value = await fetchDossierSources(dossierId);
    } catch {
      sources.value = [];
    }
  };
  return { sources, load };
}
