import type { ToolAuthMode, ToolVisibility } from "@/types/tool";

/** Un fournisseur de collections branché sur la plateforme (contrat docs/backend/base-de-connaissances-api.yaml). */
export interface KnowledgeSource {
  id: string;
  name: string;
  url: string;
  authMode: ToolAuthMode;
  audience: string | null;
  visibility: ToolVisibility;
  ownerName: string;
  ownedByMe: boolean;
  createdAt: string;
}

export interface KnowledgeSourceDraft {
  name: string;
  url: string;
  authMode: ToolAuthMode;
  audience: string;
  visibility: ToolVisibility;
}

/** Une collection d'un fournisseur, telle que la personne la voit chez lui. */
export interface KnowledgeCollection {
  id: string;
  name: string;
  description: string;
  documentCount: number;
  /** Accueil de la collection chez le fournisseur, s'il en a une. */
  url: string | null;
  /** Vignette de la collection, si le fournisseur en a une. */
  previewUrl: string | null;
}

/** Une collection choisie pour une analyse, désignée par sa source et son identifiant chez elle. */
export interface CollectionRef {
  sourceId: string;
  collectionId: string;
}

/**
 * `available` : la personne la voit. `not_found` : elle n'existe plus chez le fournisseur. `forbidden` : la personne n'y
 * a plus droit. `source_unavailable` : la source n'est plus visible, ou ne répond pas.
 */
export type CollectionStatus = "available" | "not_found" | "forbidden" | "source_unavailable";

export const COLLECTION_STATUS_LABELS: Record<Exclude<CollectionStatus, "available">, string> = {
  not_found: "Introuvable chez le fournisseur",
  forbidden: "Accès refusé",
  source_unavailable: "Source inaccessible",
};

export interface AnalyseCollection extends CollectionRef {
  name: string;
  sourceName: string;
  status: CollectionStatus;
}

/** Une zone à surligner sur une page, en coordonnées normalisées 0..1 (origine en haut à gauche). */
export interface ExternalBox {
  page: number;
  xMin: number;
  yMin: number;
  xMax: number;
  yMax: number;
}

/** Une source d'une base de connaissances citée par un message de l'assistant : un document ou une page web. */
export interface ExternalSource {
  sourceId: string;
  kind: "document" | "web";
  title: string;
  url: string;
  previewUrl: string | null;
  page: number | null;
  boxes: ExternalBox[];
  passage: string;
  score: number;
  collectionName: string;
  sourceName: string;
}
