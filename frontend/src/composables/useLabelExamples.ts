import { computed, ref } from "vue";

import type { LabelExample } from "@/types/analyse";

// MAQUETTE : les exemples ne sont pas envoyés au backend. Ils vivent en mémoire, par label, le temps de la page.
// À remplacer par l'API (stockage S3 + vecteurs visuels dans la collection Qdrant de l'analyse).

export const MAX_EXAMPLES_PER_LABEL = 10;
export const MAX_EXAMPLE_SIZE = 10 * 1024 * 1024;
export const EXAMPLE_ACCEPT = "image/png,image/jpeg,image/webp,application/pdf";

const examplesByLabel = ref<Record<string, LabelExample[]>>({});

function kindOf(file: File): LabelExample["kind"] | null {
  if (file.type === "application/pdf") return "pdf";
  if (["image/png", "image/jpeg", "image/webp"].includes(file.type)) return "image";
  return null;
}

export function formatSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} Ko`;
  return `${(bytes / (1024 * 1024)).toFixed(1).replace(".", ",")} Mo`;
}

export function useLabelExamples() {
  const examplesOf = (labelId: string) => computed(() => examplesByLabel.value[labelId] ?? []);

  const listOf = (labelId: string) => examplesByLabel.value[labelId] ?? [];

  const countOf = (labelId: string) => (examplesByLabel.value[labelId] ?? []).length;

  /** Ajoute des fichiers ; renvoie les messages d'erreur des fichiers refusés. */
  function addFiles(labelId: string, files: File[]): string[] {
    const errors: string[] = [];
    const current = [...(examplesByLabel.value[labelId] ?? [])];
    for (const file of files) {
      const kind = kindOf(file);
      if (!kind) errors.push(`« ${file.name} » : format non pris en charge (PDF, PNG, JPEG ou WebP).`);
      else if (file.size > MAX_EXAMPLE_SIZE) errors.push(`« ${file.name} » : plus de ${formatSize(MAX_EXAMPLE_SIZE)}.`);
      else if (current.length >= MAX_EXAMPLES_PER_LABEL) errors.push(`« ${file.name} » : ${MAX_EXAMPLES_PER_LABEL} exemples maximum par label.`);
      else {
        current.push({
          id: `example-${Date.now()}-${current.length}`,
          name: file.name,
          kind,
          size: file.size,
          previewUrl: kind === "image" ? URL.createObjectURL(file) : null,
        });
      }
    }
    examplesByLabel.value = { ...examplesByLabel.value, [labelId]: current };
    return errors;
  }

  function removeExample(labelId: string, exampleId: string) {
    const list = examplesByLabel.value[labelId] ?? [];
    const target = list.find((example) => example.id === exampleId);
    if (target?.previewUrl) URL.revokeObjectURL(target.previewUrl);
    examplesByLabel.value = { ...examplesByLabel.value, [labelId]: list.filter((example) => example.id !== exampleId) };
  }

  return { examplesOf, listOf, countOf, addFiles, removeExample };
}
