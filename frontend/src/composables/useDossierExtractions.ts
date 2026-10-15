import { ref } from "vue";

import type { ExtractedDocument } from "@/types/dossierExtraction";
import { apiFetch } from "@/utils/api";

function mapDocument(api: any): ExtractedDocument {
  return {
    id: api.id,
    name: api.name,
    pages: api.pages.map((page: any) => ({
      id: page.page_id,
      pageNumber: page.page_number,
      hasScreenshot: page.has_screenshot,
      entities: page.entities.map((entity: any) => ({
        id: entity.prediction_id,
        name: entity.name,
        value: entity.value,
        confidence: entity.confidence ?? undefined,
        source: entity.source,
        pages: entity.pages,
        boxes: entity.boxes.map((b: any) => ({ xMin: b.x_min, yMin: b.y_min, xMax: b.x_max, yMax: b.y_max })),
      })),
    })),
  };
}

/** Entités d'un dossier, document par document puis page par page, avec leurs zones. */
export function useDossierExtractions(dossierId: string) {
  const documents = ref<ExtractedDocument[]>([]);
  const isLoading = ref(false);
  const error = ref<string | undefined>(undefined);

  async function load() {
    isLoading.value = true;
    error.value = undefined;
    try {
      const data = await apiFetch<any[]>(`/api/dossiers/${dossierId}/extractions`);
      documents.value = data.map(mapDocument);
    } catch (e) {
      error.value = e instanceof Error ? e.message : "Erreur de chargement";
    } finally {
      isLoading.value = false;
    }
  }

  return { documents, isLoading, error, load };
}
