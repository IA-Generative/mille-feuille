import type { Version } from "@/types/analyse";

/** Comment les pages d'un dossier sont découpées en passages : un modèle d'IA (par défaut) ou des fenêtres de taille fixe. */
export type ChunkStrategy = "ia" | "classique";

/** Ce que l'analyse enregistre. Un modèle laissé vide veut dire « celui de la plateforme ». */
export interface SearchSettings {
  strategy: ChunkStrategy;
  chunkModel: string | null;
  /** Découpage classique : taille d'un passage et chevauchement, en caractères. */
  size: number;
  overlap: number;
  /** Passages voisins renvoyés de chaque côté d'un passage trouvé. */
  window: number;
  embeddingModel: string | null;
}

export const DEFAULT_SEARCH_SETTINGS: SearchSettings = {
  strategy: "ia",
  chunkModel: null,
  size: 1000,
  overlap: 150,
  window: 1,
  embeddingModel: null,
};

export interface EmbeddingModel {
  id: string;
  dimension: number;
}

/** Où en sont les index de recherche des dossiers d'une analyse. */
export interface IndexOverview {
  dossiers: number;
  indexed: number;
  current: number;
  obsolete: number;
  errors: number;
  rebuilding: number;
  queued: number;
  toValidate: number;
}

export interface AnalyseSearch {
  settings: SearchSettings;
  /** Pourquoi les réglages ne se résolvent pas (par exemple : aucun modèle d'embeddings). */
  problem: string | null;
  overview: IndexOverview | null;
  versions: Version<SearchSettings>[];
}

/** Ce qu'un changement de réglages produirait, avant de l'enregistrer. */
export interface SearchImpact {
  problem: string | null;
  changesIndex: boolean;
  obsoleteDossiers: number;
  indexedDossiers: number;
  usesAiChunking: boolean;
}

export type RebuildStatus = "queued" | "building" | "swapped" | "finalized" | "rolled_back" | "failed";

export interface IndexRebuild {
  id: string;
  status: RebuildStatus;
  totalPages: number;
  donePages: number;
  error: string | null;
}

/** L'index de recherche d'un dossier : absent, à jour, ou construit avec d'autres réglages que ceux de l'analyse. */
export interface DossierIndex {
  freshness: "none" | "current" | "obsolete";
  status: "indexing" | "ready" | "error" | null;
  chunkCount: number;
  error: string | null;
  problem: string | null;
  rebuild: IndexRebuild | null;
}
