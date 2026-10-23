import type {
  AnalyseSearch,
  DossierIndex,
  IndexOverview,
  IndexRebuild,
  SearchImpact,
  SearchSettings,
} from "@/types/search";

// Le serveur parle en snake_case, l'interface en camelCase : une seule traduction, ici.

export interface SearchSettingsOut {
  strategy: "ia" | "classique";
  chunk_model: string | null;
  size: number;
  overlap: number;
  window: number;
  embedding_model: string | null;
}

export interface OverviewOut {
  dossiers: number;
  indexed: number;
  current: number;
  obsolete: number;
  errors: number;
  rebuilding: number;
  queued: number;
  to_validate: number;
}

export interface AnalyseSearchOut {
  settings: SearchSettingsOut;
  problem: string | null;
  overview: OverviewOut | null;
  versions: { id: string; created_at: string; content: SearchSettingsOut }[];
}

export interface ImpactOut {
  problem: string | null;
  changes_index: boolean;
  obsolete_dossiers: number;
  indexed_dossiers: number;
  uses_ai_chunking: boolean;
}

export interface RebuildOut {
  id: string;
  status: IndexRebuild["status"];
  total_pages: number;
  done_pages: number;
  error: string | null;
}

export interface DossierIndexOut {
  freshness: DossierIndex["freshness"];
  status: DossierIndex["status"];
  chunk_count: number;
  error: string | null;
  problem: string | null;
  rebuild: RebuildOut | null;
}

export const toSettings = (s: SearchSettingsOut): SearchSettings => ({
  strategy: s.strategy,
  chunkModel: s.chunk_model,
  size: s.size,
  overlap: s.overlap,
  window: s.window,
  embeddingModel: s.embedding_model,
});

export const fromSettings = (s: SearchSettings): SearchSettingsOut => ({
  strategy: s.strategy,
  chunk_model: s.chunkModel || null,
  size: s.size,
  overlap: s.overlap,
  window: s.window,
  embedding_model: s.embeddingModel || null,
});

export const toOverview = (o: OverviewOut): IndexOverview => ({
  dossiers: o.dossiers,
  indexed: o.indexed,
  current: o.current,
  obsolete: o.obsolete,
  errors: o.errors,
  rebuilding: o.rebuilding,
  queued: o.queued,
  toValidate: o.to_validate,
});

export const toAnalyseSearch = (out: AnalyseSearchOut): AnalyseSearch => ({
  settings: toSettings(out.settings),
  problem: out.problem,
  overview: out.overview ? toOverview(out.overview) : null,
  versions: out.versions.map((v) => ({ id: v.id, createdAt: v.created_at, content: toSettings(v.content) })),
});

export const toImpact = (out: ImpactOut): SearchImpact => ({
  problem: out.problem,
  changesIndex: out.changes_index,
  obsoleteDossiers: out.obsolete_dossiers,
  indexedDossiers: out.indexed_dossiers,
  usesAiChunking: out.uses_ai_chunking,
});

export const toRebuild = (r: RebuildOut): IndexRebuild => ({
  id: r.id,
  status: r.status,
  totalPages: r.total_pages,
  donePages: r.done_pages,
  error: r.error,
});

export const toDossierIndex = (out: DossierIndexOut): DossierIndex => ({
  freshness: out.freshness,
  status: out.status,
  chunkCount: out.chunk_count,
  error: out.error,
  problem: out.problem,
  rebuild: out.rebuild ? toRebuild(out.rebuild) : null,
});
