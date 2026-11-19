import { computed, ref } from "vue";

import type { LabelExample } from "@/types/analyse";
import { API_BASE_URL, ApiError, apiFetch, userMessage } from "@/utils/api";

// Documents d'exemple d'un label (PDF ou image), conservés côté serveur : `GET|POST /api/analyses/{id}/classification/
// labels/{label}/examples`, `DELETE …/{example}` et `GET …/{example}/file`. Ils servent à reconnaître le label et à
// tracer les zones où chercher une entité (EntityLocation). Le serveur les renvoie avec l'analyse : `seedExamples`
// remplit ce magasin à chaque chargement, qui fait foi pour l'affichage.

export const MAX_EXAMPLES_PER_LABEL = 10;
export const MAX_EXAMPLE_SIZE = 10 * 1024 * 1024;
export const EXAMPLE_ACCEPT = "image/png,image/jpeg,image/webp,application/pdf";
const ACCEPTED = EXAMPLE_ACCEPT.split(",");

const examplesByLabel = ref<Record<string, LabelExample[]>>({});

export function formatSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} Ko`;
  return `${(bytes / (1024 * 1024)).toFixed(1).replace(".", ",")} Mo`;
}

const baseOf = (analyseId: string, labelId: string) => `/api/analyses/${analyseId}/classification/labels/${labelId}/examples`;

function mapExample(analyseId: string, labelId: string, api: any): LabelExample {
  return {
    id: api.id,
    name: api.name,
    kind: api.kind,
    size: api.size,
    previewUrl: null,
    fileUrl: `${baseOf(analyseId, labelId)}/${api.id}/file`,
  };
}

/** L'aperçu d'une image : le fichier est servi avec la session, on le charge donc nous-mêmes (URL d'objet). */
async function loadPreview(labelId: string, example: LabelExample) {
  if (example.kind !== "image" || example.previewUrl) return;
  try {
    const response = await fetch(`${API_BASE_URL}${example.fileUrl}`, { credentials: "include" });
    if (!response.ok) return;
    const url = URL.createObjectURL(await response.blob());
    const target = examplesByLabel.value[labelId]?.find((candidate) => candidate.id === example.id);
    if (target) target.previewUrl = url;
    else URL.revokeObjectURL(url);
  } catch {
    // Pas d'aperçu : l'exemple reste utilisable.
  }
}

/** Remplit le magasin avec les exemples que le serveur vient de renvoyer (à chaque chargement d'une analyse). */
export function seedExamples(analyseId: string, apiLabels: any[]) {
  const next: Record<string, LabelExample[]> = { ...examplesByLabel.value };
  for (const label of apiLabels) {
    const previous = examplesByLabel.value[label.id] ?? [];
    next[label.id] = (label.examples ?? []).map((api: any) => {
      const example = mapExample(analyseId, label.id, api);
      // Un aperçu déjà chargé est gardé : rien à retélécharger.
      return { ...example, previewUrl: previous.find((p) => p.id === example.id)?.previewUrl ?? null };
    });
  }
  examplesByLabel.value = next;
  for (const label of apiLabels) for (const example of examplesByLabel.value[label.id]) void loadPreview(label.id, example);
}

/** Cet exemple existe-t-il encore (dans l'un des labels chargés) ? */
export function examplesExist(exampleId: string): boolean {
  return Object.values(examplesByLabel.value).some((list) => list.some((example) => example.id === exampleId));
}

export function useLabelExamples() {
  const examplesOf = (labelId: string) => computed(() => examplesByLabel.value[labelId] ?? []);

  const listOf = (labelId: string) => examplesByLabel.value[labelId] ?? [];

  const countOf = (labelId: string) => (examplesByLabel.value[labelId] ?? []).length;

  /** Envoie les fichiers au serveur ; renvoie les messages d'erreur (un fichier refusé n'en laisse entrer aucun). */
  async function addFiles(analyseId: string, labelId: string, files: File[]): Promise<string[]> {
    const errors: string[] = [];
    const current = examplesByLabel.value[labelId] ?? [];
    for (const file of files) {
      if (!ACCEPTED.includes(file.type)) errors.push(`« ${file.name} » : format non pris en charge (PDF, PNG, JPEG ou WebP).`);
      else if (file.size > MAX_EXAMPLE_SIZE) errors.push(`« ${file.name} » : plus de ${formatSize(MAX_EXAMPLE_SIZE)}.`);
    }
    if (current.length + files.length > MAX_EXAMPLES_PER_LABEL) errors.push(`${MAX_EXAMPLES_PER_LABEL} exemples maximum par label.`);
    if (errors.length > 0) return errors;

    const body = new FormData();
    for (const file of files) body.append("files", file);
    try {
      const created = await apiFetch<any[]>(baseOf(analyseId, labelId), { method: "POST", body });
      const added = created.map((api) => mapExample(analyseId, labelId, api));
      examplesByLabel.value = { ...examplesByLabel.value, [labelId]: [...current, ...added] };
      for (const example of added) void loadPreview(labelId, example);
      return [];
    } catch (error) {
      return [userMessage(error, "Les exemples n'ont pas pu être envoyés.")];
    }
  }

  async function removeExample(analyseId: string, labelId: string, exampleId: string): Promise<string | null> {
    const list = examplesByLabel.value[labelId] ?? [];
    const target = list.find((example) => example.id === exampleId);
    try {
      await apiFetch<void>(`${baseOf(analyseId, labelId)}/${exampleId}`, { method: "DELETE" });
    } catch (error) {
      if (!(error instanceof ApiError && error.status === 404)) return userMessage(error, "L'exemple n'a pas pu être retiré.");
    }
    if (target?.previewUrl) URL.revokeObjectURL(target.previewUrl);
    examplesByLabel.value = { ...examplesByLabel.value, [labelId]: list.filter((example) => example.id !== exampleId) };
    return null;
  }

  return { examplesOf, listOf, countOf, addFiles, removeExample };
}
