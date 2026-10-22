import type {
  AnalyseCollection,
  CollectionStatus,
  ExternalSource,
  KnowledgeCollection,
  KnowledgeSource,
} from "@/types/knowledge";
import type { ToolAuthMode, ToolVisibility } from "@/types/tool";

// Les formes renvoyées par l'API (snake_case), et leur passage au camelCase du frontend.

export interface KnowledgeSourceOut {
  id: string;
  name: string;
  url: string;
  auth_mode: ToolAuthMode;
  audience: string | null;
  visibility: ToolVisibility;
  owner_name: string;
  owned_by_me: boolean;
  created_at: string;
}

export interface KnowledgeCollectionOut {
  id: string;
  name: string;
  description: string;
  document_count: number;
  url: string | null;
  preview_url: string | null;
}

export interface AnalyseCollectionOut {
  source_id: string;
  collection_id: string;
  name: string;
  source_name: string;
  status: CollectionStatus;
}

export interface StoredCollectionOut {
  source_id: string;
  collection_id: string;
  name: string;
}

export interface ExternalSourceOut {
  source_id: string;
  kind: "document" | "web";
  title: string;
  url: string;
  preview_url: string | null;
  page: number | null;
  boxes: { page: number; x_min: number; y_min: number; x_max: number; y_max: number }[];
  passage: string;
  score: number;
  collection_name: string;
  source_name: string;
}

export const toKnowledgeSource = (raw: KnowledgeSourceOut): KnowledgeSource => ({
  id: raw.id,
  name: raw.name,
  url: raw.url,
  authMode: raw.auth_mode,
  audience: raw.audience,
  visibility: raw.visibility,
  ownerName: raw.owner_name,
  ownedByMe: raw.owned_by_me,
  createdAt: raw.created_at,
});

export const toKnowledgeCollection = (raw: KnowledgeCollectionOut): KnowledgeCollection => ({
  id: raw.id,
  name: raw.name,
  description: raw.description ?? "",
  documentCount: raw.document_count,
  url: raw.url,
  previewUrl: raw.preview_url,
});

export const toAnalyseCollection = (raw: AnalyseCollectionOut): AnalyseCollection => ({
  sourceId: raw.source_id,
  collectionId: raw.collection_id,
  name: raw.name,
  sourceName: raw.source_name,
  status: raw.status,
});

export const toExternalSource = (raw: ExternalSourceOut): ExternalSource => ({
  sourceId: raw.source_id,
  kind: raw.kind,
  title: raw.title,
  url: raw.url,
  previewUrl: raw.preview_url,
  page: raw.page,
  boxes: raw.boxes.map((box) => ({ page: box.page, xMin: box.x_min, yMin: box.y_min, xMax: box.x_max, yMax: box.y_max })),
  passage: raw.passage,
  score: raw.score,
  collectionName: raw.collection_name,
  sourceName: raw.source_name,
});
