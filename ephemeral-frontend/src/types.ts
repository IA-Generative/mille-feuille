export type RunStatus = "en_attente" | "en_cours" | "terminé" | "arrêté" | "échec";
export type Mode = "classification" | "extraction";
export type EntityType = "texte" | "date" | "nombre" | "booléen" | "identifiant";

export interface LabelDef {
  name: string;
  definition: string;
}
export interface EntityDef extends LabelDef {
  type: EntityType;
}

export interface LabelResult {
  name: string;
  confidence: number | null;
  source: "textual" | "visual";
}
export interface EntityResult {
  name: string;
  value: string;
  confidence: number | null;
  source: "textual" | "gliner";
  pages: number[];
}
export interface ClassificationOut {
  run_id: string;
  status: RunStatus;
  error: string | null;
  expires_at: string | null;
  documents: { name: string; pages: { page_number: number; labels: LabelResult[] }[] }[];
}
export interface ExtractionOut {
  run_id: string;
  status: RunStatus;
  error: string | null;
  expires_at: string | null;
  documents: { name: string; pages: { page_number: number; entities: EntityResult[] }[] }[];
}
export type RunOut = ClassificationOut | ExtractionOut;

export const TERMINAL: RunStatus[] = ["terminé", "arrêté", "échec"];

export interface RunSummary {
  id: string;
  kind: Mode | "analyse";
  status: RunStatus;
  documents: string[];
  persist: boolean;
  created_at: string;
  ended_at: string | null;
  expires_at: string | null;
}
