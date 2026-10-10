import { ref } from "vue";

import { apiFetch } from "@/utils/api";

export type ResultKind = "label" | "entity";

export interface ResultRow {
  id: string;
  name: string;
  value: string;
  confidence?: number;
  documentId: string;
  documentName: string;
  pages: { id: string; pageNumber: number }[];
  boundingBoxes: { id: string; pageId: string; xMin: number; yMin: number; xMax: number; yMax: number }[];
}

export interface ResultsBreakdownRow {
  documentId: string;
  documentName: string;
  pageCount: number;
  classifiedPageCount: number;
  entityCount: number;
}

function mapRow(api: any): ResultRow {
  return {
    id: api.id,
    name: api.name,
    value: api.value,
    confidence: api.confidence ?? undefined,
    documentId: api.document_id,
    documentName: api.document_name,
    pages: api.pages.map((p: any) => ({ id: p.id, pageNumber: p.page_number })),
    boundingBoxes: api.bounding_boxes.map((b: any) => ({
      id: b.id,
      pageId: b.document_page_id,
      xMin: b.x_min,
      yMin: b.y_min,
      xMax: b.x_max,
      yMax: b.y_max,
    })),
  };
}

function mapBreakdownRow(api: any): ResultsBreakdownRow {
  return {
    documentId: api.document_id,
    documentName: api.document_name,
    pageCount: api.page_count,
    classifiedPageCount: api.classified_page_count,
    entityCount: api.entity_count,
  };
}

export const RESULTS_PAGE_SIZE = 10;

/**
 * Détail des résultats d'un dossier (modale des cartes Classification / Entités) :
 * répartition par fichier et liste paginée des classifications ou des entités.
 */
export function useDossierResults(dossierId: string) {
  const breakdown = ref<ResultsBreakdownRow[]>([]);
  const rows = ref<ResultRow[]>([]);
  const total = ref(0);
  const pageCount = ref(1);
  const isLoading = ref(false);
  const error = ref<string | undefined>(undefined);
  let requestSeq = 0;

  async function loadBreakdown() {
    try {
      const data = await apiFetch<any[]>(`/api/dossiers/${dossierId}/results/breakdown`);
      breakdown.value = data.map(mapBreakdownRow);
    } catch (e) {
      error.value = e instanceof Error ? e.message : "Erreur de chargement";
    }
  }

  /** `page` commence à 1, comme l'API. */
  async function loadRows(kind: ResultKind, page: number) {
    const seq = ++requestSeq;
    isLoading.value = true;
    error.value = undefined;
    try {
      const data = await apiFetch<any>(
        `/api/dossiers/${dossierId}/results?kind=${kind}&page=${page}&page_size=${RESULTS_PAGE_SIZE}`,
      );
      if (seq !== requestSeq) return; // une requête plus récente est partie
      rows.value = data.items.map(mapRow);
      total.value = data.total;
      pageCount.value = data.pages;
    } catch (e) {
      if (seq !== requestSeq) return;
      error.value = e instanceof Error ? e.message : "Erreur de chargement";
    } finally {
      if (seq === requestSeq) isLoading.value = false;
    }
  }

  return { breakdown, rows, total, pageCount, isLoading, error, loadBreakdown, loadRows };
}
